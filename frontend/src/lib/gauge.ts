/**
 * Score gauge arc geometry — pure math for the 270° risk gauge.
 *
 * Coordinate convention: SVG user space (x right, y DOWN). Angles in degrees
 * measured from the positive x-axis; increasing angle sweeps clockwise on
 * screen. The 270° arc leaves a gap centered at the bottom of the dial:
 *
 *   start = 135°  (bottom-left)  →  end = 405° ≡ 45°  (bottom-right)
 *
 * The visible arc therefore covers [135°, 360°] ∪ [0°, 45°]; the bottom gap
 * spans the open interval (45°, 135°).
 */

/** Degrees swept by the arc (360 minus the bottom gap). */
export const GAUGE_SWEEP_DEG = 270;

/** Start angle of the arc, bottom-left of the dial. */
export const GAUGE_START_ANGLE_DEG = 135;

/**
 * Length of the stroked arc for radius `r` along the 270° sweep:
 * three quarters of the full circumference.
 */
export function totalArcLength(r: number): number {
  return 2 * Math.PI * r * (GAUGE_SWEEP_DEG / 360);
}

/**
 * Map a 0–100 score to the stroke-dashoffset that reveals exactly that
 * fraction of the arc (dash pattern = [arcLength]). Scores are clamped to
 * [0, 100]: offset 0 = full arc, offset arcLength = empty arc. Monotonically
 * decreasing in `score`.
 */
export function scoreToDashOffset(score: number, arcLength: number): number {
  const clamped = Math.min(Math.max(score, 0), 100);
  return arcLength * (1 - clamped / 100);
}

/**
 * Map a threshold (0–100 scale) to its progress fraction along the arc,
 * clamped to [0, 1]. Multiply by totalArcLength or feed to polarToPoint.
 */
export function thresholdToPosition(threshold: number): number {
  return Math.min(Math.max(threshold, 0), 100) / 100;
}

/**
 * Progress fraction along the arc → polar point in SVG user space.
 * fraction 0 sits at GAUGE_START_ANGLE_DEG (bottom-left), fraction 1 at the
 * arc's end (bottom-right); the path never enters the bottom gap.
 */
export function polarToPoint(
  cx: number,
  cy: number,
  r: number,
  fraction: number,
): { x: number; y: number } {
  const angleDeg =
    GAUGE_START_ANGLE_DEG + Math.min(Math.max(fraction, 0), 1) * GAUGE_SWEEP_DEG;
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}
