import { classificationLabel, type ScoreClassification } from "./score";

/**
 * The single source of truth for "what colour is this classification".
 *
 * WHY THIS FILE EXISTS
 * The classification → colour relationship used to be expressed five times:
 * RiskMeter.FILL_CLASSES, ScoreResultCard.TONE_STROKE_CLASSES, and three
 * per-page CLASSIFICATION_COLORS maps (TransactionTable, TransactionDetail and
 * AlertsPage). TransactionDetail's copy was byte-identical to TransactionTable's
 * and AlertsPage's was missing `pending` entirely, so an unrecognised value fell
 * through to a fourth, undocumented colour path.
 *
 * They had already drifted in a visible way: the dashboard rendered two
 * different green pills for the same "legitimate" state in the same table
 * (`bg-fraud-legitimate-bg`, an opaque forest green, in the classification
 * column vs `bg-status-approved/10`, a translucent emerald, in the status
 * column). A user who learned "dark green = legitimate" on one page saw a
 * different-looking pill on the next.
 *
 * Everything that needs a classification colour now reads it from here.
 */

/** Semantic tone vocabulary. `neutral` is the unknown/pending state. */
export type ClassificationTone = "clean" | "warn" | "critical" | "neutral";

/** The three classifications the backend actually emits. */
const KNOWN = new Set<string>(["legitimate", "review", "fraud"]);

const TONE_BY_CLASSIFICATION: Record<ScoreClassification, ClassificationTone> = {
  legitimate: "clean",
  review: "warn",
  fraud: "critical",
};

/**
 * Map a classification to its semantic tone.
 *
 * Unknown and missing values return `neutral`, never `clean`. The previous
 * fallback returned `clean`, which painted a confident green gauge around an
 * unknown state — a "safe" colour wrapping a value nobody had determined.
 */
export function classificationTone(
  classification: string | null | undefined,
): ClassificationTone {
  if (classification && KNOWN.has(classification)) {
    return TONE_BY_CLASSIFICATION[classification as ScoreClassification];
  }
  return "neutral";
}

/** True when the value is one the backend is expected to emit. */
export function isKnownClassification(
  classification: string | null | undefined,
): boolean {
  return !!classification && KNOWN.has(classification);
}

/**
 * Human label for a classification, with an honest fallback.
 *
 * A null/empty classification means "no score recorded yet" and must not be
 * rendered as "Legítimo".
 */
export function classificationText(
  classification: string | null | undefined,
): string {
  if (classification && KNOWN.has(classification)) {
    return classificationLabel(classification as ScoreClassification);
  }
  return "Pendiente";
}

/**
 * Rectangular pill classes for table cells.
 *
 * Kept separate from <Badge>'s rounded treatment because the data tables have
 * their own compact look; the important part is that the *token choice* comes
 * from one table, so the two renderings can no longer disagree about hue.
 */
const PILL_BY_TONE: Record<ClassificationTone, string> = {
  clean: "text-fraud-legitimate bg-fraud-legitimate-bg border-fraud-legitimate/30",
  warn: "text-fraud-review bg-fraud-review-bg border-fraud-review/30",
  critical: "text-fraud-fraud bg-fraud-fraud-bg border-fraud-fraud/30",
  neutral: "text-slate-400 bg-slate-800 border-slate-600/30",
};

/** Text-only variant for compact cells. */
export function classificationTextClass(
  classification: string | null | undefined,
): string {
  const tone = classificationTone(classification);
  if (tone === "neutral") return "text-slate-400";
  return PILL_BY_TONE[tone].split(" ").slice(0, 1).join(" ");
}
