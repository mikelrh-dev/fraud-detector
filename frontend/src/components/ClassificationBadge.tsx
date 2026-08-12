import { classificationColor, classificationLabel } from "../lib/score";
import type { ScoreClassification } from "../lib/score";

const colorMap: Record<string, string> = {
  approved: "text-status-approved border-status-approved/30 bg-status-approved/10",
  flagged: "text-status-flagged border-status-flagged/30 bg-status-flagged/10",
  blocked: "text-status-blocked border-status-blocked/30 bg-status-blocked/10",
};

export function ClassificationBadge({ classification }: { classification: string }) {
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
