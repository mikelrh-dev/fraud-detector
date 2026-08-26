import type { ReactNode } from "react";
import { CheckCircle, Info, Scales } from "@phosphor-icons/react";
import { classificationColor, classificationLabel } from "../lib/score";
import type { ScoreClassification } from "../lib/score";
import { Badge, type BadgeTone } from "./Badge";

const TONE_MAP: Record<string, BadgeTone> = {
  approved: "clean",
  flagged: "warn",
  blocked: "critical",
};

/* Single icon system (Phosphor). approved renders weight="fill" per the
   iconography contract; blocked uses the gavel-equivalent Scales. */
const ICON_MAP: Record<string, ReactNode> = {
  approved: <CheckCircle weight="fill" size={14} />,
  blocked: <Scales size={14} />,
};

export function ClassificationBadge({ classification }: { classification: string }) {
  const cls = classification as ScoreClassification;
  const token = classificationColor(cls);
  const label = classificationLabel(cls);
  const tone = TONE_MAP[token] ?? "warn";
  const icon = ICON_MAP[token] ?? <Info size={14} />;

  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}
