import { Badge, type BadgeTone } from "./Badge";

/**
 * Alert workflow status → semantic tone.
 * open=warn (amber), reviewed=info (blue), resolved=clean (green).
 */
const ALERT_STATUS_TONES: Record<string, BadgeTone> = {
  open: "warn",
  reviewed: "info",
  resolved: "clean",
};

const ALERT_STATUS_LABELS: Record<string, string> = {
  open: "Abierta",
  reviewed: "Revisada",
  resolved: "Resuelta",
};

export function AlertStatusBadge({ status }: { status: string }) {
  const tone = ALERT_STATUS_TONES[status];
  if (!tone) {
    // Unknown status: neutral fallback (no hex — slate utilities only)
    return (
      <span className="inline-flex items-center px-2 py-0.5 text-[11px] rounded-full font-medium border bg-slate-800 border-slate-700 text-slate-400">
        {status}
      </span>
    );
  }
  return (
    <Badge tone={tone} size="sm">
      {ALERT_STATUS_LABELS[status] ?? status}
    </Badge>
  );
}
