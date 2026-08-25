/**
 * Risk score → UI tone banding.
 *
 * SOURCE-OF-TRUTH NOTE: backend classification is DYNAMIC — thresholds vary
 * per transaction amount (`src/core/config.py` threshold_tiers) with a grey
 * zone in `services/ensemble.py::classify`. A score-only UI component cannot
 * reproduce that mapping, so these bands are the agreed display convention
 * for risk meters: clean < 45, warn 45–59, critical >= 60. The tick marks
 * rendered by <RiskMeter> sit exactly at these boundaries.
 */
export type RiskTone = "clean" | "warn" | "critical";

export const RISK_THRESHOLDS = {
  /** score >= warnAt renders the warn tone; first tick position. */
  warnAt: 45,
  /** score >= criticalAt renders the critical tone; second tick position. */
  criticalAt: 60,
} as const;

/** Map a 0–100 risk score to its semantic tone band. */
export function riskTone(score: number): RiskTone {
  if (score >= RISK_THRESHOLDS.criticalAt) return "critical";
  if (score >= RISK_THRESHOLDS.warnAt) return "warn";
  return "clean";
}
