import apiClient from "./client";

export interface ShapContribution {
  feature: string;
  contribution: number;
}

export interface Transaction {
  id: string;
  amount: number;
  currency: string;
  merchant_name: string;
  merchant_category: string | null;
  card_last4: string;
  status: string;
  risk_score: number | null;
  classification: string | null;
  /**
   * The two layer scores, present on the LIST response and always null on the
   * detail response.
   *
   * They exist because the conflict queue is unreadable without them: a
   * disagreement is a claim about two numbers, and the list carried only their
   * weighted blend, so the one screen whose subject is the gap between the
   * layers could not show the gap.
   *
   * `null` means "this transaction has no score row" and is NOT the same as a
   * layer having run and produced 0.0. The backend does not invent a zero,
   * because the product already records that distinction deliberately (A15: an
   * absent ML layer is reported through `layers_used`, never by nulling the
   * score), and a fabricated 0 here would be read as a measurement.
   *
   * Required rather than optional: the backend sends both on every
   * `TransactionResponse`, null included, so there is no wire state in which
   * they are absent — only states in which they are null.
   */
  rule_score: number | null;
  ml_score: number | null;
  scoring?: {
    rule_score: number;
    ml_score: number; // backend guarantees non-nullable float
    ensemble_score: number;
    threshold: number;
    classification: string | null; // defensive; backend non-null
    // FRD-SHP-001/2: detail-only, null when the worker has not computed it
    shap_contributions?: ShapContribution[] | null;
  } | null;
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface TransactionListResponse {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateTransactionRequest {
  amount: number;
  currency: string;
  merchant_name: string;
  merchant_category?: string | null;
  card_last4: string;
  /**
   * A30: removed from the form and from this contract. The server ignores it
   * and always uses the authenticated identity (F2), and the schema marks it
   * deprecated. As a required field it was a permanent dead end: an empty value
   * failed validation forever and disabled the submit button with no error
   * shown, because the hidden input was the one field with no error node.
   */
}

export interface ScoreResponse {
  transaction_id: string;
  rule_score: number;
  // Non-nullable, and that is a real guarantee rather than an optimistic
  // guess. ScoreResponse.ml_score is `float` in Pydantic (schemas/scoring.py),
  // and scoring_service.py:154-158 is an explicit decision (A15): when the ML
  // layer is absent the ensemble redistributes its weight and the *stored*
  // value stays 0.0, because FraudScore.ml_score is a non-nullable column. The
  // absence is recorded in `layers_used`, never by nulling the score. The wire
  // therefore cannot carry a null here, and the old `number | null` let the
  // client defend against a state the server cannot produce.
  ml_score: number;
  ensemble_score: number;
  threshold: number;
  classification: string;
  fired_rules: string[];
  /**
   * Which ensemble layers contributed to this score — a subset of
   * `"rule" | "ml" | "context"`, in evaluation order.
   *
   * This is where a missing ML layer is recorded. A15: the ensemble
   * redistributes an absent layer's weight instead of spending it on nothing,
   * and the *stored* `ml_score` stays `0.0` because `FraudScore.ml_score` is a
   * non-nullable column. So a degraded score is a normal-looking number, and
   * `"ml" in layers_used` is what tells the two apart — true when the model
   * ran and genuinely scored zero, false when it never ran.
   *
   * OPTIONAL, and required to be. POST /transactions always sends it;
   * GET /transactions/{id} cannot, because `ScoreBreakdown` is read from a
   * stored `FraudScore` row and persisting this needs a column and therefore a
   * migration — blocked on a live database (see
   * `docs/plans/2026-09-28-fix-loop.md`, D7-1). `buildScoreResponse` in
   * pages/TransactionDetail.tsx synthesises this shape from that GET response,
   * so it cannot supply the field. Making it required here would mean
   * fabricating it, which is the failure mode the optionality is avoiding.
   */
  layers_used?: string[];
  created_at: string;
  // Required on the server (str) and required here. `action` is nullable on
  // both sides: it is one of request_3d_secure | request_sms |
  // request_biometric | block_transaction, or null when the transaction is
  // allowed through with no friction. Both were missing from this interface
  // while the sibling `Transaction.scoring` above carried a comment about
  // backend guarantees -- two interfaces in one file disagreeing about the
  // same backend.
  friction_level: string;
  action: string | null;
}

export interface TransactionFilters {
  page?: number;
  page_size?: number;
  status?: string;
  user_id?: string;
  date_from?: string;
  date_to?: string;
  /**
   * Restrict to the conflict queue — transactions whose rule and ML layers
   * disagreed. Read-only on the server: it changes no score and no verdict.
   *
   * A boolean rather than a string, and omitted when falsy, so the plain
   * transaction list and the queue share one endpoint and one serialiser
   * instead of two that can drift.
   */
  conflict?: boolean;
}

/**
 * List transactions with optional filters.
 */
export async function listTransactions(
  filters: TransactionFilters = {},
): Promise<TransactionListResponse> {
  const params = new URLSearchParams();
  if (filters.page) params.set("page", String(filters.page));
  if (filters.page_size) params.set("page_size", String(filters.page_size));
  if (filters.status) params.set("status", filters.status);
  if (filters.user_id) params.set("user_id", filters.user_id);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  if (filters.conflict) params.set("conflict", "true");

  const response = await apiClient.get<TransactionListResponse>(
    `/transactions?${params.toString()}`,
  );
  return response.data;
}

/**
 * Get a single transaction by ID.
 */
export async function getTransaction(
  id: string,
): Promise<Transaction> {
  const response = await apiClient.get<Transaction>(`/transactions/${id}`);
  return response.data;
}

/**
 * Create a transaction and run the scoring pipeline.
 */
export async function createTransaction(
  data: CreateTransactionRequest,
): Promise<ScoreResponse> {
  const response = await apiClient.post<ScoreResponse>("/transactions", data);
  return response.data;
}

/**
 * Helper: map status to classification label.
 */
export function statusToClassification(status: string): string {
  switch (status) {
    case "approved":
      return "legitimate";
    case "flagged":
      return "review";
    case "blocked":
      return "fraud";
    default:
      return "pending";
  }
}
