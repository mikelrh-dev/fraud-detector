import type { ShapContribution } from "../api/transactions";
import {
  featureLabel,
  formatContribution,
  contributionDirection,
} from "../lib/shap";

interface ShapAttributionCardProps {
  contributions: ShapContribution[] | null | undefined;
}

/**
 * "Atribución SHAP" section (FRD-SHP-002): up to 5 bars, one per feature,
 * with Spanish labels and direction — positive contribution pushes toward
 * fraud (red), negative toward legitimate (green). Renders nothing when
 * contributions is null/empty (worker has not run yet).
 */
export function ShapAttributionCard({
  contributions,
}: ShapAttributionCardProps) {
  if (!contributions || contributions.length === 0) {
    return null;
  }

  // Normalize bar widths against the largest |contribution| in the set.
  const maxAbs = Math.max(
    ...contributions.map((c) => Math.abs(c.contribution)),
  );

  return (
    <section
      data-testid="shap-attribution"
      className="bg-slate-900 rounded-lg border border-slate-800 p-5"
    >
      <h2 className="text-sm font-semibold text-slate-300 mb-4">
        Atribución SHAP
      </h2>
      <p className="text-xs text-slate-500 mb-4">
        Qué características empujaron el score del modelo ML. Las positivas
        favorecen fraude; las negativas favorecen operación legítima.
      </p>
      <ul className="space-y-3">
        {contributions.map((c) => {
          const direction = contributionDirection(c.contribution);
          const isFraud = direction === "fraud";
          const width =
            maxAbs > 0 ? (Math.abs(c.contribution) / maxAbs) * 100 : 0;
          return (
            <li key={c.feature} className="flex flex-col sm:flex-row items-start sm:items-center gap-1 sm:gap-3">
              <span
                className="w-auto sm:w-44 max-w-full shrink-0 truncate text-sm text-slate-300"
                title={featureLabel(c.feature)}
              >
                {featureLabel(c.feature)}
              </span>
              <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden w-full sm:w-auto">
                <div
                  className={`h-full rounded-full ${
                    isFraud ? "bg-red-500" : "bg-green-500"
                  }`}
                  style={{ width: `${width}%` }}
                />
              </div>
              <span className="w-auto sm:w-14 shrink-0 sm:text-right text-sm font-mono text-slate-300">
                {formatContribution(c.contribution)}
              </span>
              <span
                className={`w-auto sm:w-24 shrink-0 sm:text-right text-xs ${
                  isFraud ? "text-red-400" : "text-green-400"
                }`}
              >
                {isFraud ? "Hacia fraude" : "Hacia legítimo"}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
