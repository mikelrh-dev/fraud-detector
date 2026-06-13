export type ScoreClassification = "legitimate" | "review" | "fraud";

/**
 * Map a classification to a UI status token for styling.
 */
export function classificationColor(cls: ScoreClassification): "approved" | "flagged" | "blocked" {
  switch (cls) {
    case "legitimate":
      return "approved";
    case "review":
      return "flagged";
    case "fraud":
      return "blocked";
  }
}

/**
 * Return a human-readable label for a classification.
 */
export function classificationLabel(cls: ScoreClassification): string {
  switch (cls) {
    case "legitimate":
      return "Legítimo";
    case "review":
      return "Revisión";
    case "fraud":
      return "Fraude";
  }
}

/**
 * Format a score number to one decimal, or show "—" when null.
 */
export function formatScore(n: number | null): string {
  if (n === null) return "—";
  return n.toFixed(1);
}

/**
 * Return true if the ML model has been trained (score is not null).
 */
export function isMLTrained(score: number | null): boolean {
  return score !== null;
}
