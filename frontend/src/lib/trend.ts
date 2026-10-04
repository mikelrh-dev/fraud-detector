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
 * A maximal stretch of consecutive days that carry no measurement.
 *
 * A RUN, not a day: the reader needs to see "nothing happened across these four
 * days" as one region. Shading each unmeasured day separately draws hairlines
 * between them that read as four separate holes rather than one four-day one.
 */
export interface GapRun {
  /** Index of the first unmeasured day in the stretch. */
  startIndex: number;
  /** Index of the last unmeasured day in the stretch (inclusive). */
  endIndex: number;
}

/**
 * Every maximal run of consecutive unmeasured days, in window order.
 *
 * This is the map that makes an honest gap legible. `connectNulls={false}`
 * correctly refuses to draw a line across a day with no transactions, but a
 * reader cannot tell that refusal from a broken panel — so the same fact has to
 * be stated in pixels and in words instead.
 *
 * `!== null`, never a truthiness test, for the reason `longestMeasuredRun`
 * already carries: a measured average of exactly 0 is a real reading, and
 * treating it as unmeasured would put a band on top of a data point.
 */
export function findGapRuns(data: DailyAverage[]): GapRun[] {
  const runs: GapRun[] = [];
  let start = -1;
  // One step past the end so a run that reaches the last day is still closed;
  // `i < data.length` keeps that final step from reading past the array.
  for (let i = 0; i <= data.length; i++) {
    const unmeasured = i < data.length && data[i].avgScore === null;
    if (unmeasured && start === -1) start = i;
    if (!unmeasured && start !== -1) {
      runs.push({ startIndex: start, endIndex: i - 1 });
      start = -1;
    }
  }
  return runs;
}

/**
 * How many days in the window carry no measurement.
 *
 * Days, NOT runs — "3" here would describe the shape of the holes rather than
 * how much of the window is missing, which is the number an analyst asking
 * "how much of this week do I actually have?" wants.
 */
export function countUnmeasuredDays(data: DailyAverage[]): number {
  return data.reduce(
    (total, day) => (day.avgScore === null ? total + 1 : total),
    0,
  );
}

/** The plot rectangle recharts measured, in SVG pixels. */
export interface PlotBounds {
  left: number;
  width: number;
}

/** One run's pixel span along the x axis. */
export interface DaySpan {
  x: number;
  width: number;
}

/**
 * Pixel span covering exactly the days of one gap run.
 *
 * WHY THIS IS COMPUTED BY HAND — recharts' `ReferenceArea` looks like the tool
 * for this and silently is not, on this axis. A categorical XAxis resolves to a
 * POINT scale (`bandwidth() === 0`), and `ReferenceArea` maps its bounds
 * through `ScaleHelper.apply`:
 *
 *   - `x1` with `position: 'start'` → `scale(x1)` — the day CENTRE
 *   - `x2` with `position: 'end'`   → `scale(x2) + bandwidth()` → `scale(x2)`
 *
 * so a run shades the space BETWEEN its days' centres and never covers the day
 * cells, and a run of exactly ONE day collapses to a zero-width rect that
 * recharts then discards entirely. Measured on recharts 2.15.4: `x1="d1"
 * x2="d1"` rendered `<g class="recharts-reference-area"></g>` — empty — and a
 * two-day run rendered width 121.67, which is one category step rather than
 * two. Half-step numeric bounds do not rescue it either: d3's point scale will
 * not extrapolate a number against a string domain, so those render nothing.
 *
 * A day cell is therefore `step` wide, centred on `dayXs[i]`, where `step` is
 * the distance between adjacent day centres. `dayXs` comes from the chart's own
 * scale (passed in by the caller) rather than being re-derived here, so the
 * band cannot drift from the axis it is drawn over.
 *
 * Returns `null` — never a zero-width span — because a zero-width rect is
 * discarded by the renderer, which is precisely how a one-day gap disappears
 * while still looking like it was drawn.
 */
export function gapRunSpan(
  run: GapRun,
  dayXs: readonly number[],
  plot: PlotBounds,
): DaySpan | null {
  const last = dayXs.length - 1;
  const { startIndex, endIndex } = run;
  if (startIndex < 0 || endIndex > last || startIndex > endIndex) return null;

  const startX = dayXs[startIndex];
  const endX = dayXs[endIndex];
  if (!Number.isFinite(startX) || !Number.isFinite(endX)) return null;

  // A one-day window has no step to read, so its cell is the whole plot.
  const step =
    dayXs.length > 1 ? (dayXs[last] - dayXs[0]) / (dayXs.length - 1) : plot.width;
  const half = step / 2;

  // Clamped to the plot, so a run on the first or last day is cut off at the
  // axis instead of spilling a half-cell into the margin, where it would read
  // as a rendering fault rather than as the edge of the window.
  const min = plot.left;
  const max = plot.left + plot.width;
  const clamp = (value: number) => Math.min(Math.max(value, min), max);

  const x = clamp(startX - half);
  const width = clamp(endX + half) - x;
  if (!(width > 0)) return null;
  return { x, width };
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

