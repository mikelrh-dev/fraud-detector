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
    // Unknown status routes through the Badge primitive's neutral fallback.
    return <Badge tone="neutral" size="sm">{status}</Badge>;
  }
  return (
    <Badge tone={tone} size="sm">
      {ALERT_STATUS_LABELS[status] ?? status}
    </Badge>
  );
}
