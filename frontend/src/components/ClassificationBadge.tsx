import { classificationColor, classificationLabel } from "../lib/score";
import type { ScoreClassification } from "../lib/score";
import { Badge, type BadgeTone } from "./Badge";

const TONE_MAP: Record<string, BadgeTone> = {
  approved: "clean",
  flagged: "warn",
  blocked: "critical",
};

const ICON_MAP: Record<string, string> = {
  approved: "check_circle",
  blocked: "gavel",
};

export function ClassificationBadge({ classification }: { classification: string }) {
  const cls = classification as ScoreClassification;
  const token = classificationColor(cls);
  const label = classificationLabel(cls);
  const tone = TONE_MAP[token] ?? "warn";
  const icon = ICON_MAP[token] ?? "info";

  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}
