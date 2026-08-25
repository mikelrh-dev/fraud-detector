import type { RiskTone } from "../lib/risk";
import { RISK_THRESHOLDS, riskTone } from "../lib/risk";

/**
 * Tone → token fill classes. Zero inline hex: colors come from the
 * --color-risk-* @theme tokens (see DESIGN.md).
 */
const FILL_CLASSES: Record<RiskTone, string> = {
  clean: "bg-risk-clean",
  warn: "bg-risk-warn",
  critical: "bg-risk-critical",
};

export interface RiskMeterProps {
  /** Risk score 0–100. Values outside the range are clamped.
   *  null/undefined renders nothing — never draw a fake 0-width bar next
   *  to an em-dash placeholder (honest-data rule). */
  value?: number | null;
  /** Tailwind width utility for the track. Defaults to w-16. */
  widthClass?: string;
}

/**
 * Shared horizontal risk meter with threshold ticks at the RISK_THRESHOLDS
 * boundaries (45% / 60%). Single source for every score bar in the app —
 * replaces per-page inline-styled divs.
 */
export function RiskMeter({ value, widthClass = "w-16" }: RiskMeterProps) {
  if (value === null || value === undefined) return null;
  const clamped = Math.min(Math.max(value, 0), 100);
  const tone = riskTone(clamped);
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
      data-testid="risk-meter"
      className={`relative h-1.5 rounded-full bg-slate-800 ${widthClass}`}
    >
      <div
        data-testid="risk-meter-fill"
        className={`h-full rounded-full transition-all ${FILL_CLASSES[tone]}`}
        style={{ width: `${clamped}%` }}
      />
      {[
        RISK_THRESHOLDS.warnAt,
        RISK_THRESHOLDS.criticalAt,
      ].map((threshold) => (
        <span
          key={threshold}
          aria-hidden="true"
          data-testid="risk-meter-tick"
          className="absolute inset-y-0 w-0 border-l border-slate-600/50"
          style={{ left: `${threshold}%` }}
        />
      ))}
    </div>
  );
}
