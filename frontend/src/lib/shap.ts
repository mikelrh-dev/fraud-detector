/**
 * SHAP attribution display helpers (FRD-SHP-002).
 *
 * Spanish label map for feature names produced by the backend
 * (src/services/feature_engine.py FEATURE_NAMES). Alias keys from the
 * design are included defensively so any historical payload still resolves.
 */
const FEATURE_LABELS: Record<string, string> = {
  amount: "Monto",
  amount_vs_user_avg: "Monto promedio",
  avg_amount: "Monto promedio",
  amount_vs_user_std: "Desviación del monto",
  std_amount: "Desviación del monto",
  tx_count_last_5min: "Transacciones últimas 5 min",
  tx_count_last_1h: "Transacciones última hora",
  hour_of_day: "Hora del día",
  hour: "Hora del día",
  is_weekend: "Fin de semana",
  weekend: "Fin de semana",
  merchant_risk_level: "Riesgo del comercio",
  merchant_risk: "Riesgo del comercio",
  is_crypto: "Criptomoneda",
  amount_round_number: "Monto redondo",
  round_amount: "Monto redondo",
};

/**
 * Spanish label for a feature name; falls back to the raw name.
 */
export function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature;
}

/**
 * Signed, one-decimal formatting of a contribution: "+35.0" / "-5.0".
 */
export function formatContribution(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}`;
}

/**
 * Direction semantics: positive contribution pushes toward fraud,
 * negative pushes toward legitimate.
 */
export function contributionDirection(
  value: number,
): "fraud" | "legitimate" {
  return value >= 0 ? "fraud" : "legitimate";
}
