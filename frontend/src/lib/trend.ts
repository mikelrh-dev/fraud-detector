/**
 * One day in the trend window.
 *
 * `null` means "no transactions that day" and is NEVER 0. That distinction is
 * the backbone of this file's honesty rules: a 0 would render as a measured
 * "risk 0", and a gap rendered as 0 is how a failed query once became a flat
 * line at the bottom of the chart.
 */
export interface DailyAverage {
  date: string;
  /** null means "no transactions that day" — never 0, which reads as a real score. */
  avgScore: number | null;
}

/**
 * How many consecutive measured days a line needs before the line itself says
 * anything.
 *
 * Two. Not one, because a SEGMENT is defined by two points: a lone measured day
 * produced the path `M186.67,77 L186.67,165 Z` — a zero-width vertical sliver,
 * i.e. no pixels at all — and with `dot={false}` there was nothing to fall back
 * on, so the panel rendered blank while claiming nothing. Not three, because two
 * adjacent days already draw a real segment and a third dot adds nothing an axis
 * label does not.
 *
 * This is a statement about GEOMETRY, not about how much data would be
 * statistically useful. The question it answers is narrow and answerable: "can
 * this chart draw a stroke, or is it about to render blank?"
 */
export const MIN_CONSECUTIVE_DAYS_FOR_LINE = 2;

/**
 * Length of the longest run of consecutive days that carry a measurement.
 *
 * The RUN, not the count of non-null days, and the difference is not academic:
 * three measured days at positions 1, 3 and 5 draw three unconnected points and
 * no line, so a plain "how many days did we measure" rule would call that a
 * drawable trend and switch the dots off. Measuring three days is not the same
 * claim as being able to connect any two of them.
 */
export function longestMeasuredRun(data: DailyAverage[]): number {
  let longest = 0;
  let current = 0;
  for (const day of data) {
    // `!== null`, never a truthiness test: an average of exactly 0 is a real
    // measurement, and treating it as a gap is the bug this file's sibling
    // `buildDailyAverages` already fixed once.
    if (day.avgScore === null) {
      current = 0;
      continue;
    }
    current += 1;
    if (current > longest) longest = current;
  }
  return longest;
}

/**
 * Whether this window needs visible dots to not render blank.
 *
 * Two conditions, and the first is the whole point:
 *   - there IS a measurement. An empty window reaches the "Sin datos suficientes"
 *     message and never draws a chart, so "mark the measurements" has nothing to
 *     mark. This is a real guard rather than a formality: without it this returns
 *     `true` for zero measured days, which is only harmless today because the
 *     caller returns early — and a predicate that answers wrongly for the one
 *     input with no drawing attached to it is a predicate that will be wrong
 *     later.
 *   - and no two of them are adjacent, so no stroke can be drawn.
 */
export function needsVisibleDots(data: DailyAverage[]): boolean {
  const hasMeasurement = data.some((d) => d.avgScore !== null);
  return (
    hasMeasurement && longestMeasuredRun(data) < MIN_CONSECUTIVE_DAYS_FOR_LINE
  );
}

/**
 * recharts' `ResponsiveContainer` measures its own box before drawing, and jsdom
 * has no layout to report — it renders an EMPTY div with no SVG at all. Verified
 * rather than assumed: an unmocked render of a chart component in this suite
 * yields `svg` count 0, which turns every geometry assertion into a failure that
 * looks like a missing element and is actually a missing browser API.
 *
 * The stand-in lives in `src/test-utils/` for the same reason `setup.ts` holds
 * the shared `ResizeObserver` stub: it is test infrastructure, and shipping it
 * in `src/lib/` would put a fake measurement in the production bundle.
 */

