import type { ScoreResponse } from "../api/transactions";
import { classificationColor, classificationLabel, formatScore, isMLTrained } from "../lib/score";
import type { ScoreClassification } from "../lib/score";

interface ScoreResultCardProps {
  result: ScoreResponse | null;
  isLoading?: boolean;
}

const colorMap: Record<string, string> = {
  approved: "text-status-approved border-status-approved/30 bg-status-approved/10",
  flagged: "text-status-flagged border-status-flagged/30 bg-status-flagged/10",
  blocked: "text-status-blocked border-status-blocked/30 bg-status-blocked/10",
};

const gaugeColorMap: Record<string, string> = {
  approved: "bg-status-approved",
  flagged: "bg-status-flagged",
  blocked: "bg-status-blocked",
};

function ScoreGauge({ score, threshold }: { score: number; threshold: number }) {
  const clamped = Math.min(Math.max(score, 0), 100);
  return (
    <div className="mb-6">
      <div className="flex justify-between text-xs text-slate-400 mb-1">
        <span>Score de Riesgo</span>
        <span>{formatScore(score)}</span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-status-approved via-status-flagged to-status-blocked"
          style={{ width: `${clamped}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-500 mt-0.5">
        <span>0</span>
        <span>Umbral: {threshold}</span>
        <span>100</span>
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
  icon: string;
  score: number | null;
  isMlUntrained?: boolean;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="material-symbols-outlined text-slate-400 text-base">{icon}</span>
        <span className="text-xs text-slate-400 font-medium">{title}</span>
      </div>
      {isMlUntrained ? (
        <div className="flex items-center gap-2 mt-1">
          <span className="material-symbols-outlined text-slate-500 text-lg">psychology</span>
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

function ClassificationBadge({ classification }: { classification: string }) {
  const cls = classification as ScoreClassification;
  const token = classificationColor(cls);
  const label = classificationLabel(cls);
  const colors = colorMap[token] || colorMap.flagged;

  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium border ${colors}`}
    >
      <span className="material-symbols-outlined text-base mr-1">
        {token === "approved" ? "check_circle" : token === "blocked" ? "gavel" : "info"}
      </span>
      {label}
    </span>
  );
}

function FiredRulesChips({ rules }: { rules: string[] }) {
  if (rules.length === 0) return null;
  return (
    <div className="mt-4">
      <h4 className="text-xs text-slate-400 font-medium mb-2">Reglas Activadas</h4>
      <div className="flex flex-wrap gap-2">
        {rules.map((rule) => (
          <span
            key={rule}
            className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-red-900/30 text-red-400 border border-red-800/30"
          >
            {rule}
          </span>
        ))}
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-4 bg-slate-700 rounded w-1/3 mb-4" />
      <div className="h-2 bg-slate-800 rounded-full mb-6" />
      <div className="grid grid-cols-3 gap-4">
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

  const classification = result.classification;
  const cls = classification as ScoreClassification;
  const token = classificationColor(cls);
  const gaugeToken = gaugeColorMap[token] || gaugeColorMap.flagged;
  const mlTrained = isMLTrained(result.ml_score);

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-xl p-6 mt-6">
      {/* Header with classification badge */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-200">Resultado de Scoring</h3>
        <ClassificationBadge classification={classification} />
      </div>

      {/* Ensemble Score Gauge */}
      <ScoreGauge score={result.ensemble_score} threshold={result.threshold} />

      {/* Breakdown Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <BreakdownCard title="Reglas" icon="gavel" score={result.rule_score} />
        <BreakdownCard
          title="ML"
          icon="psychology"
          score={result.ml_score}
          isMlUntrained={!mlTrained}
        />
        <BreakdownCard title="Ensemble" icon="neurology" score={result.ensemble_score} />
      </div>

      {/* Fired Rules */}
      <FiredRulesChips rules={result.fired_rules} />
    </div>
  );
}
