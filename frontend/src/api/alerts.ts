import apiClient from "./client";

export interface Alert {
  id: string;
  transaction_id: string;
  status: string;
  score: number;
  threshold: number;
  classification: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AlertListResponse {
  items: Alert[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlertActionRequest {
  action: string;
  reason?: string;
}

export interface AlertFilters {
  status?: string;
  page?: number;
  page_size?: number;
  date_from?: string;
  date_to?: string;
}

/**
 * List alerts with optional filters.
 */
export async function listAlerts(
  filters: AlertFilters = {},
): Promise<AlertListResponse> {
  const params = new URLSearchParams();
  if (filters.page) params.set("page", String(filters.page));
  if (filters.page_size) params.set("page_size", String(filters.page_size));
  if (filters.status) params.set("status", filters.status);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);

  const response = await apiClient.get<AlertListResponse>(
    `/alerts?${params.toString()}`,
  );
  return response.data;
}

/**
 * Mark an alert as reviewed.
 */
export async function reviewAlert(
  alertId: string,
  reason?: string,
): Promise<Alert> {
  const response = await apiClient.post<Alert>(`/alerts/${alertId}/review`, {
    action: "review",
    reason,
  });
  return response.data;
}

/**
 * Mark an alert as false positive.
 */
export async function markFalsePositive(
  alertId: string,
  reason?: string,
): Promise<Alert> {
  const response = await apiClient.post<Alert>(
    `/alerts/${alertId}/false-positive`,
    { action: "false_positive", reason },
  );
  return response.data;
}

/**
 * Mark an alert as confirmed fraud.
 *
 * The mirror of `markFalsePositive`. It exists because the queue offered only
 * "look at it" and "it's wrong": an analyst who correctly confirmed a fraud
 * had no control to press, so a correct confirmation and an alert nobody
 * examined left the row indistinguishable.
 *
 * `action` must be exactly `confirm_fraud` — the backend validates it against
 * `^(review|false_positive|confirm_fraud|revert)$`, so any other spelling is a
 * 422 raised by the body parser and reads as a broken route rather than a
 * wrong enum member.
 */
export async function confirmFraud(
  alertId: string,
  reason?: string,
): Promise<Alert> {
  const response = await apiClient.post<Alert>(
    `/alerts/${alertId}/confirm-fraud`,
    { action: "confirm_fraud", reason },
  );
  return response.data;
}

/**
 * Revert an alert action (reopen).
 */
export async function revertBlock(
  alertId: string,
  reason?: string,
): Promise<Alert> {
  const response = await apiClient.post<Alert>(`/alerts/${alertId}/revert`, {
    action: "revert",
    reason,
  });
  return response.data;
}
