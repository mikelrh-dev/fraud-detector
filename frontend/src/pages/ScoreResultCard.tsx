import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Brain, Circuitry, Scales } from "@phosphor-icons/react";
import type { ScoreResponse } from "../api/transactions";
import { ClassificationBadge } from "../components/ClassificationBadge";
import { MotionList } from "../components/MotionList";
import { formatScore, isMLTrained } from "../lib/score";
import type { RiskTone } from "../lib/risk";
import { RISK_THRESHOLDS, riskTone } from "../lib/risk";
import { classificationToTone } from "../components/RiskMeter";
import {
  GAUGE_START_ANGLE_DEG,
  polarToPoint,
  scoreToDashOffset,
  thresholdToPosition,
  totalArcLength,
} from "../lib/gauge";

interface ScoreResultCardProps {
  result: ScoreResponse | null;
  isLoading?: boolean;
}

/* Gauge dial geometry in the 200×200 SVG viewBox. */
const GAUGE_CX = 100;
const GAUGE_CY = 100;
const GAUGE_RADIUS = 80;
const GAUGE_STROKE_WIDTH = 14;
/** Tick segments cross the arc band so they read as notches ON the dial. */
const TICK_INNER_RADIUS = GAUGE_RADIUS - 10;
const TICK_OUTER_RADIUS = GAUGE_RADIUS + 10;

/** Risk tone → token stroke class (zero inline hex; see DESIGN.md). */
const TONE_STROKE_CLASSES: Record<RiskTone, string> = {
  clean: "stroke-risk-clean",
  warn: "stroke-risk-warn",
  critical: "stroke-risk-critical",
};

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Signature 270° score gauge (gap at the bottom). Track is slate-800, the
 * progress arc takes the score's risk tone, and ticks sit at the shared
 * RISK_THRESHOLDS display convention (45 / 60) — same source as RiskMeter.
 * The arc animates its stroke-dashoffset once on mount; reduced-motion
 * users get the final state immediately with no transition.
 */
function ScoreGauge({
  score,
  classification,
}: {
  score: number;
  classification: string;
}) {
  const clamped = Math.min(Math.max(score, 0), 100);
  const tone = classificationToTone(classification);
  const circumference = 2 * Math.PI * GAUGE_RADIUS;
  const arcLength = totalArcLength(GAUGE_RADIUS);

  // Two-phase mount: start empty, then arm to the target offset on the next
  // frame so the CSS transition actually runs on first paint.
  const [armed, setArmed] = useState(() => prefersReducedMotion());
  useEffect(() => {
    if (armed) return undefined;
    const frame = requestAnimationFrame(() => setArmed(true));
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dashOffset = armed ? scoreToDashOffset(score, arcLength) : arcLength;
  const dashPattern = `${arcLength} ${circumference}`;

  return (
    <div className="relative mx-auto mb-6 w-fit">
      <svg
        viewBox="0 0 200 200"
        className="h-52 w-52"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={clamped}
        aria-label={`Score de riesgo: ${formatScore(score)} de 100`}
      >
        {/* Static 270° track */}
        <circle
          cx={GAUGE_CX}
          cy={GAUGE_CY}
          r={GAUGE_RADIUS}
          fill="none"
          strokeWidth={GAUGE_STROKE_WIDTH}
          strokeLinecap="round"
          transform={`rotate(${GAUGE_START_ANGLE_DEG} ${GAUGE_CX} ${GAUGE_CY})`}
          strokeDasharray={dashPattern}
          className="stroke-slate-800"
        />
        {/* Progress arc — tone-colored, animated via stroke-dashoffset */}
        <circle
          cx={GAUGE_CX}
          cy={GAUGE_CY}
          r={GAUGE_RADIUS}
          fill="none"
          strokeWidth={GAUGE_STROKE_WIDTH}
          strokeLinecap="round"
          transform={`rotate(${GAUGE_START_ANGLE_DEG} ${GAUGE_CX} ${GAUGE_CY})`}
          strokeDasharray={dashPattern}
          style={{ strokeDashoffset: dashOffset }}
          data-testid="score-gauge-progress"
          className={`fill-none transition-[stroke-dashoffset] duration-[600ms] ease-[cubic-bezier(0.16,1,0.3,1)] motion-reduce:transition-none ${TONE_STROKE_CLASSES[tone]}`}
        />
        {/* Threshold ticks at the RISK_THRESHOLDS boundaries (45 / 60) */}
        {[RISK_THRESHOLDS.warnAt, RISK_THRESHOLDS.criticalAt].map((t) => {
          const inner = polarToPoint(
            GAUGE_CX,
            GAUGE_CY,
            TICK_INNER_RADIUS,
            thresholdToPosition(t),
          );
          const outer = polarToPoint(
            GAUGE_CX,
            GAUGE_CY,
            TICK_OUTER_RADIUS,
            thresholdToPosition(t),
          );
          return (
            <line
              key={t}
              x1={inner.x}
              y1={inner.y}
              x2={outer.x}
              y2={outer.y}
              strokeWidth={2}
              strokeLinecap="round"
              data-testid="score-gauge-tick"
              className="stroke-slate-600/70"
            />
          );
        })}
      </svg>
      {/* Center readout: score + scale + classification */}
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <p className="flex items-baseline gap-0.5 font-mono tabular-nums leading-none">
          <span className="text-3xl font-bold text-slate-100" data-testid="gauge-score-value">
            {formatScore(score)}
          </span>
          <span className="text-sm font-medium text-slate-500">/100</span>
        </p>
        <div className="mt-2">
          <ClassificationBadge classification={classification} />
        </div>
      </div>
    </div>
  );
}

function BreakdownCard({
  title,
  icon,
  score,
  isMlUntrained,
}: {
  title: string;
  icon: ReactNode;
  score: number | null;
  isMlUntrained?: boolean;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center text-slate-400">{icon}</span>
        <span className="text-xs text-slate-400 font-medium">{title}</span>
      </div>
      {isMlUntrained ? (
        <div className="flex items-center gap-2 mt-1">
          <span
            className="inline-flex items-center text-slate-500"
            data-testid="ml-untrained-icon"
          >
            <Brain size={18} aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm text-slate-300">ML: no entrenado</p>
            <a
              href="#"
              className="text-[10px] text-status-info hover:underline"
              onClick={(e) => e.preventDefault()}
            >
              Ver documentación
            </a>
          </div>
        </div>
      ) : (
        <p className="text-xl font-bold text-slate-100">{formatScore(score)}</p>
      )}
    </div>
  );
}

function FiredRulesChips({ rules }: { rules: string[] }) {
  if (rules.length === 0) return null;
  return (
    <div className="mt-4">
      <h4 className="text-xs text-slate-400 font-medium mb-2">Reglas Activadas</h4>
      <MotionList className="flex flex-wrap gap-2">
        {rules.map((rule) => (
          <span
            key={rule}
            className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-red-900/30 text-red-400 border border-red-800/30"
          >
            {rule}
          </span>
        ))}
      </MotionList>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-4 bg-slate-700 rounded w-1/3 mb-4" />
      <div className="h-2 bg-slate-800 rounded-full mb-6" />
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-slate-900 border border-slate-800 rounded-lg p-4">
            <div className="h-3 bg-slate-700 rounded w-1/2 mb-3" />
            <div className="h-6 bg-slate-800 rounded w-2/3" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ScoreResultCard({ result, isLoading }: ScoreResultCardProps) {
  if (isLoading || !result) {
    return <LoadingSkeleton />;
  }

  const mlTrained = isMLTrained(result.ml_score);

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-xl p-6 mt-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-200">Resultado de Scoring</h3>
      </div>

      {/* Ensemble Score Gauge — classification badge lives in the dial center */}
      <ScoreGauge
        score={result.ensemble_score}
        classification={result.classification}
      />

      {/* Breakdown Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <BreakdownCard title="Reglas" icon={<Scales size={16} aria-hidden="true" />} score={result.rule_score} />
        <BreakdownCard
          title="ML"
          icon={<Brain size={16} aria-hidden="true" />}
          score={result.ml_score}
          isMlUntrained={!mlTrained}
        />
        <BreakdownCard title="Ensemble" icon={<Circuitry size={16} aria-hidden="true" />} score={result.ensemble_score} />
      </div>

      {/* Fired Rules */}
      <FiredRulesChips rules={result.fired_rules} />
    </div>
  );
}
