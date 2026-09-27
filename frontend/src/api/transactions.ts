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
  ml_score: number | null;
  ensemble_score: number;
  threshold: number;
  classification: string;
  fired_rules: string[];
  created_at: string;
}

export interface TransactionFilters {
  page?: number;
  page_size?: number;
  status?: string;
  user_id?: string;
  date_from?: string;
  date_to?: string;
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
