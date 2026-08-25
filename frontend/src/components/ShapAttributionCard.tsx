import { useEffect, useState } from "react";
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
 * SEMANTICS — preserved verbatim from the previous stacked-bars layout:
 * a POSITIVE SHAP contribution pushes the ML score toward FRAUD and renders
 * RED, extending RIGHT of the central zero axis; a NEGATIVE contribution
 * pushes toward LEGITIMATE and renders GREEN, extending LEFT. The
 * sign → direction mapping lives in `lib/shap.ts::contributionDirection`
 * ("fraud" for >= 0, "legitimate" otherwise) and is pinned by tests.
 *
 * Phase 2 only changed the LAYOUT (diverging bars around a central zero
 * axis) — never the meaning. Colors moved from raw palette utilities
 * (red-500/green-500) to the equivalent semantic tokens (risk-critical /
 * risk-clean) per the DESIGN.md single-source rule; same hues.
 */

/** Direction → token classes for bar fill and direction text. */
const DIRECTION_CLASSES = {
  fraud: {
    bar: "bg-risk-critical left-1/2",
    text: "text-risk-critical",
  },
  legitimate: {
    bar: "bg-risk-clean right-1/2",
    text: "text-risk-clean",
  },
} as const;

/**
 * Mount animation: width starts at 0% and transitions to its target on the
 * next frame so the CSS transition actually runs. Reduced-motion users get
 * the final width immediately (transition also disabled via utility).
 */
function DivergingBar({
  widthPercent,
  direction,
}: {
  widthPercent: number;
  direction: "fraud" | "legitimate";
}) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setArmed(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const tone =
    direction === "fraud"
      ? DIRECTION_CLASSES.fraud
      : DIRECTION_CLASSES.legitimate;

  return (
    <div className="relative h-4 w-full flex-1 sm:w-auto">
      {/* Central zero axis */}
      <span
        aria-hidden="true"
        data-testid="shap-zero-axis"
        className="absolute inset-y-0 left-1/2 -translate-x-1/2 border-l border-slate-700"
      />
      <div
        data-testid="shap-bar"
        style={{ width: armed ? `${widthPercent}%` : "0%" }}
        className={`absolute inset-y-0.5 rounded-full transition-[width] duration-[600ms] ease-[cubic-bezier(0.16,1,0.3,1)] motion-reduce:transition-none ${tone.bar}`}
      />
    </div>
  );
}

/**
 * "Atribución SHAP" section (FRD-SHP-002): up to 5 diverging bars, one per
 * feature, with Spanish labels and direction — positive contributions push
 * toward fraud (red, right of the zero axis), negative toward legitimate
 * (green, left). Renders nothing when contributions is null/empty (worker
 * has not run yet).
 */
export function ShapAttributionCard({
  contributions,
}: ShapAttributionCardProps) {
  if (!contributions || contributions.length === 0) {
    return null;
  }

  // Normalize bar widths against the largest |contribution| in the set;
  // each side of the zero axis spans half the track, so full scale = 50%.
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
        Qué características empujaron el score del modelo ML. Barras a la
        derecha del eje empujan hacia fraude; hacia la izquierda, hacia
        operación legítima.
      </p>
      <ul className="space-y-3">
        {contributions.map((c) => {
          const direction = contributionDirection(c.contribution);
          const isFraud = direction === "fraud";
          // Half-track scaling keeps the largest bar reaching its edge.
          const width =
            maxAbs > 0 ? (Math.abs(c.contribution) / maxAbs) * 50 : 0;
          const tone = isFraud
            ? DIRECTION_CLASSES.fraud
            : DIRECTION_CLASSES.legitimate;
          return (
            <li key={c.feature} className="flex flex-col sm:flex-row items-start sm:items-center gap-1 sm:gap-3">
              <span
                className="w-auto sm:w-44 max-w-full shrink-0 truncate text-sm text-slate-300"
                title={featureLabel(c.feature)}
              >
                {featureLabel(c.feature)}
              </span>
              <DivergingBar widthPercent={width} direction={direction} />
              <span className="w-auto sm:w-14 shrink-0 sm:text-right text-sm font-mono text-slate-300">
                {formatContribution(c.contribution)}
              </span>
              <span
                className={`w-auto sm:w-24 shrink-0 sm:text-right text-xs ${tone.text}`}
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
