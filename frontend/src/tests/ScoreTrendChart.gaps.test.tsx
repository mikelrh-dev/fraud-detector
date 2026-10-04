import { describe, it, expect, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import {
  countUnmeasuredDays,
  findGapRuns,
  gapRunSpan,
} from "../lib/trend";
import type { DailyAverage } from "../lib/trend";
import { sizedResponsiveContainer } from "../test-utils/recharts";

/**
 * WHY THIS FILE EXISTS — a sparse window read as a broken chart.
 *
 * `ScoreTrendChart` broke its line across days with no transactions, and that
 * break is CORRECT and stays: `connectNulls={false}` is the honesty rule (see
 * `honest-data.test.ts`), and interpolating through a day nobody transacted on
 * would draw a fabricated score. The dots landed in the previous fix so the
 * measurements are visible.
 *
 * What was still missing is the EXPLANATION. Three isolated points on a 7-day
 * axis, with nothing on the other four days, is indistinguishable from a chart
 * that failed to load. The reader has no way to tell "we measured three days"
 * from "this panel is broken", so the honest gaps were indistinguishable from
 * an honest bug. These tests hold the fix for that: the unmeasured days are
 * visibly marked AS unmeasured, and the caption states the count.
 *
 * WHY THE BANDS ARE NOT `ReferenceArea` — measured, not assumed.
 * recharts' `ReferenceArea` looks like the obvious tool and silently does not
 * work on this axis. The categorical XAxis here resolves to a POINT scale
 * (`bandwidth() === 0`, range `[65, 795]`, 7 categories, step 121.67), and
 * `ReferenceArea` maps its bounds through `ScaleHelper.apply`:
 *
 *   - `x1` with `position: 'start'` -> `scale(x1)`, the day CENTRE
 *   - `x2` with `position: 'end'`   -> `scale(x2) + bandwidth()` -> `scale(x2)`
 *
 * so a run of days shades the space BETWEEN their centres, never the day cells,
 * and a run of ONE day resolves to a zero-width rect that recharts discards.
 * Probed against recharts 2.15.4:
 *   - `x1="d1" x2="d1"` (one day)  -> `<g class="recharts-reference-area"></g>`, EMPTY
 *   - `x1="d4" x2="d5"` (two days) -> rect x=430 width=121.67 == ONE step, not two
 *
 * Half-step numeric bounds (`-0.5`/`0.5`) were the other candidate and render
 * NOTHING: d3's point scale does not extrapolate numeric values against a
 * string domain, so `getRect` returns null and the reference is dropped.
 *
 * The bands are therefore drawn as real rects from the chart's own scale via
 * `Customized`, which is what the width assertions below exist to protect.
 *
 * WHY THESE TESTS MEASURE AGAINST AXIS TICKS, NOT DOTS — measured, not assumed.
 * recharts only renders an `Area`'s dots once its entrance animation finishes
 * (`Area.renderDots` returns null while `isAnimationActive && !isAnimationFinished`),
 * and jsdom has no SVG animation timeline to fire the end event on. The way out
 * is `hasSinglePoint`, which skips the animated area entirely — so under jsdom a
 * window with ONE measured day shows its fallback dots, and a window with TWO OR
 * MORE isolated measured days shows none, forever. Verified: for this file's
 * window `needsVisibleDots` is `true` while `circle.recharts-dot` count is 0 and
 * no `.recharts-area-dots` layer exists at all.
 *
 * That is pre-existing and correct behaviour in a browser — it is only the test
 * environment that cannot see it — so the dot fallback is left alone. It also
 * means these tests cannot calibrate off dots, and do not: the x-axis tick
 * positions are the axis' own day coordinates, which makes them the honest
 * reference to check the bands against.
 */

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) =>
      sizedResponsiveContainer(children),
  };
});

const { default: ScoreTrendChart } = await import(
  "../components/ScoreTrendChart"
);

/** A 7-day window; `null` is a day with no transactions. */
function week(...avgScores: (number | null)[]): DailyAverage[] {
  return avgScores.map((avgScore, i) => ({
    date: `2026-10-0${i + 1}`,
    avgScore,
  }));
}

/**
 * The shape the real window had: gaps at BOTH ENDS and in the MIDDLE, so three
 * disjoint runs and a single-day run at index 0 (the case `ReferenceArea`
 * dropped on the floor).
 */
const THREE_RUNS = week(null, 55, null, null, 62, null, null);
const MEASURED_DATES = ["2026-10-02", "2026-10-05"];

// ---------------------------------------------------------------------------
// Pure logic
// ---------------------------------------------------------------------------

describe("findGapRuns — which stretches were not measured", () => {
  it("returns one run per maximal stretch of unmeasured days", () => {
    expect(findGapRuns(THREE_RUNS)).toEqual([
      { startIndex: 0, endIndex: 0 },
      { startIndex: 2, endIndex: 3 },
      { startIndex: 5, endIndex: 6 },
    ]);
  });

  it("finds nothing when every day was measured", () => {
    expect(findGapRuns(week(10, 20, 30, 40, 50, 60, 70))).toEqual([]);
  });

  it("finds one run covering the whole window when nothing was measured", () => {
    expect(findGapRuns(week(null, null, null, null, null, null, null))).toEqual([
      { startIndex: 0, endIndex: 6 },
    ]);
  });

  it("finds nothing for an empty window", () => {
    expect(findGapRuns([])).toEqual([]);
  });

  it("treats a genuine 0 as measured, so it never opens a gap", () => {
    // A gap and a score of 0 are different claims; `longestMeasuredRun` already
    // learned this and a falsy test here would reopen the defect it closed.
    expect(findGapRuns(week(0, null, 0))).toEqual([
      { startIndex: 1, endIndex: 1 },
    ]);
  });

  it("joins adjacent unmeasured days into one run rather than one per day", () => {
    // Two rects with a hairline seam between them read as two regions, not one
    // four-day hole, so a run has to be a single span.
    expect(findGapRuns(week(10, null, null, null, 20))).toHaveLength(1);
  });
});

describe("countUnmeasuredDays", () => {
  it("counts every unmeasured day, not the number of runs", () => {
    // 3 runs covering 5 days: 1 + 2 + 2. Reporting "3" here would be a
    // different — and wrong — fact.
    expect(countUnmeasuredDays(THREE_RUNS)).toBe(5);
  });

  it("is 0 for a fully measured window", () => {
    expect(countUnmeasuredDays(week(10, 20, 30, 40, 50, 60, 70))).toBe(0);
  });

  it("is the whole window when nothing was measured", () => {
    expect(countUnmeasuredDays(week(null, null, null, null, null, null, null))).toBe(
      7,
    );
    expect(countUnmeasuredDays([])).toBe(0);
  });
});

describe("gapRunSpan — turning a run into pixels on a point scale", () => {
  // The measured geometry of the mocked chart: plot 65..795 (width 730),
  // 7 categories, step 730/6 = 121.6667, every day cell 121.6667 wide.
  const PLOT = { left: 65, width: 730 };
  const STEP = 730 / 6;
  const dayXs = [0, 1, 2, 3, 4, 5, 6].map(
    (i) => 65 + i * STEP,
  );

  it("covers exactly the run's days, one step each, when the run is inside the plot", () => {
    // Indices 2-3 and a lone 2: none of these touch either edge, so the span is
    // a whole number of day cells with nothing clipped.
    const pair = gapRunSpan({ startIndex: 2, endIndex: 3 }, dayXs, PLOT)!;
    expect(pair.width).toBeCloseTo(STEP * 2, 5);

    const single = gapRunSpan({ startIndex: 2, endIndex: 2 }, dayXs, PLOT)!;
    expect(single.width).toBeCloseTo(STEP, 5);
  });

  it("cuts an edge run back to the part of it that is inside the plot", () => {
    // The consequence of a POINT scale worth recording: day 0 sits exactly ON
    // the left edge and day 6 exactly ON the right, so half of each edge cell
    // is off-plot. The band marks what the plot can show — the visible half of
    // the first day — rather than spilling into the axis margin. Giving the edge
    // days a full cell would mean changing the axis scale, which would move the
    // line and the dots this file is not allowed to move.
    const atStart = gapRunSpan({ startIndex: 0, endIndex: 0 }, dayXs, PLOT)!;
    expect(atStart.x).toBe(PLOT.left);
    expect(atStart.width).toBeCloseTo(STEP / 2, 5);

    // Same at the other end, where the run keeps its own days and loses the
    // trailing half-cell to the frame.
    const atEnd = gapRunSpan({ startIndex: 6, endIndex: 6 }, dayXs, PLOT)!;
    expect(atEnd.x + atEnd.width).toBeCloseTo(PLOT.left + PLOT.width, 5);
    expect(atEnd.width).toBeCloseTo(STEP / 2, 5);
  });

  it("centres the run on its own days, not on the gap between them", () => {
    // The defect being guarded: shading between centres is what ReferenceArea
    // did, so both edges were off by half a cell in opposite directions.
    const span = gapRunSpan({ startIndex: 2, endIndex: 3 }, dayXs, PLOT)!;
    expect(span.x + span.width / 2).toBeCloseTo(
      (dayXs[2] + dayXs[3]) / 2,
      5,
    );
  });

  it("clamps a run at the window edge to the plot instead of spilling into the margin", () => {
    const atStart = gapRunSpan({ startIndex: 0, endIndex: 0 }, dayXs, PLOT)!;
    expect(atStart.x).toBe(PLOT.left);

    const atEnd = gapRunSpan({ startIndex: 6, endIndex: 6 }, dayXs, PLOT)!;
    expect(atEnd.x + atEnd.width).toBeCloseTo(PLOT.left + PLOT.width, 5);
  });

  it("returns null rather than a zero-width rect", () => {
    // recharts discards a zero-width rect, which is how a one-day gap would
    // silently vanish if this ever returned {x, width: 0}.
    expect(gapRunSpan({ startIndex: 9, endIndex: 9 }, dayXs, PLOT)).toBeNull();
    expect(gapRunSpan({ startIndex: 2, endIndex: 1 }, dayXs, PLOT)).toBeNull();
  });

  it("gives a single-day window its whole cell", () => {
    const span = gapRunSpan({ startIndex: 0, endIndex: 0 }, [430], PLOT)!;
    expect(span.width).toBeCloseTo(PLOT.width, 5);
  });
});

// ---------------------------------------------------------------------------
// Rendered DOM
// ---------------------------------------------------------------------------

describe("ScoreTrendChart — the unmeasured region is marked as unmeasured", () => {
  it("shades every gap run, and only the days that were not measured", async () => {
    render(<ScoreTrendChart data={THREE_RUNS} />);

    // Three disjoint runs — one of them a SINGLE day at index 0, the exact
    // input `ReferenceArea` rendered as nothing at all.
    const bands = await waitForBands(3);
    const covered = bands.flatMap((b) => bandDates(b));
    expect(covered.sort()).toEqual(
      ["2026-10-01", "2026-10-03", "2026-10-04", "2026-10-06", "2026-10-07"].sort(),
    );

    // The stronger half of the claim: no band may cover a measured day. The
    // union above is already exhaustive, so this pins it per band.
    for (const band of bands) {
      for (const date of bandDates(band)) {
        expect(MEASURED_DATES).not.toContain(date);
      }
    }
  });

  it("covers exactly the axis ticks of the days it claims — and no measured day", async () => {
    // The strongest form of the claim, and the one that needs no hardcoded
    // geometry: every band's pixel range is read back and the tick positions
    // inside it are compared to the days the band declares. A band that is
    // offset by half a cell, or one that swallowed a measured day, fails here
    // however plausible it looks.
    render(<ScoreTrendChart data={THREE_RUNS} />);
    const bands = await waitForBands(3);
    const ticks = tickPositions();
    expect(ticks).toHaveLength(7);

    for (const band of bands) {
      const from = Number(band.getAttribute("x"));
      const width = Number(band.getAttribute("width"));
      const to = from + width;
      // recharts drops a zero-width rect, so a band can be "present" in the
      // model and invisible on screen. This is the check that noticed.
      expect(width).toBeGreaterThan(0);

      const covered = ticks
        .filter((t) => t.x >= from && t.x <= to)
        .map((t) => t.date);

      // Exactly the declared days — not one more, not one fewer.
      expect(covered).toEqual(bandDates(band));
      for (const date of MEASURED_DATES) expect(covered).not.toContain(date);
    }

    // Read together, the two measured days are proven to sit in unshaded
    // territory, so the wash never dims a data point it is not describing.
    for (const measured of MEASURED_DATES) {
      const tick = ticks.find((t) => t.date === measured)!;
      for (const band of bands) {
        const from = Number(band.getAttribute("x"));
        const to = from + Number(band.getAttribute("width"));
        expect(tick.x >= from && tick.x <= to).toBe(false);
      }
    }
  });

  it("gives an interior run one cell per day, measured off the axis", async () => {
    render(<ScoreTrendChart data={THREE_RUNS} />);
    const bands = await waitForBands(3);

    // The step, read off the axis ticks rather than hardcoded: 7 ticks spanning
    // the plot, so last-minus-first over 6 steps.
    const ticks = tickPositions();
    const step = (ticks[6].x - ticks[0].x) / 6;
    const widths = bands.map((b) => Number(b.getAttribute("width")));

    // THE discriminating assertion. The middle run is 2 days and touches
    // neither edge, so its span is exactly two cells. recharts' ReferenceArea
    // drew ONE category step for the very same run — shading the gap between
    // the two day centres and covering neither day.
    expect(widths[1]).toBeCloseTo(step * 2, 3);

    // The run at index 0 is a SINGLE day, the input ReferenceArea rendered as
    // nothing at all. Half a cell is still a solid 60px band; the point is that
    // it is a real width and not the 0 a zero-width rect takes.
    expect(widths[0]).toBeGreaterThan(step / 4);
    expect(widths[2]).toBeGreaterThan(step);

    for (const w of widths) {
      expect(w).toBeGreaterThan(0);
      expect(w).toBeLessThanOrEqual(step * 3);
    }
  });

  it("keeps the bands inside the plot, not over the axis", async () => {
    render(<ScoreTrendChart data={THREE_RUNS} />);
    const bands = await waitForBands(3);

    for (const band of bands) {
      expect(Number(band.getAttribute("x"))).toBeGreaterThanOrEqual(0);
      expect(
        Number(band.getAttribute("x")) + Number(band.getAttribute("width")),
      ).toBeLessThanOrEqual(800);
    }
  });

  it("states the count as chart metadata, derived from the data", async () => {
    render(<ScoreTrendChart data={THREE_RUNS} />);
    await waitForBands(3);

    // 5 unmeasured days of a 7-day window — not "3", which is the run count.
    expect(caption()).toBe("5 de 7 días sin transacciones");
  });

  it("counts a single unmeasured day correctly", async () => {
    render(<ScoreTrendChart data={week(10, 20, 30, 40, 50, 60, null)} />);
    await waitForBands(1);

    expect(caption()).toBe("1 de 7 días sin transacciones");
  });

  it("says nothing when every day was measured", async () => {
    render(<ScoreTrendChart data={week(10, 20, 30, 40, 50, 60, 70)} />);

    // No gaps, so no bands AND no caption: "0 de 7 días sin transacciones" is
    // a true sentence that adds nothing to a complete chart.
    await waitFor(() => {
      expect(document.querySelector("path.recharts-curve")?.getAttribute("d"))
        .toBeTruthy();
    });
    expect(containerBands()).toHaveLength(0);
    expect(caption()).toBeNull();
  });

  it("adds no caption to the fully-unmeasured window, which already says so", () => {
    // The early return keeps this branch free of the caption: the chart does
    // not exist, so "7 de 7 días sin transacciones" under "Sin datos
    // suficientes" would be a second, weaker statement of the same fact.
    render(
      <ScoreTrendChart data={week(null, null, null, null, null, null, null)} />,
    );

    expect(caption()).toBeNull();
    expect(containerBands()).toHaveLength(0);
  });

  it("still does not bridge a gap with the line", async () => {
    // The honesty rule this whole file must not erode. Two measured runs with
    // a gap between them have to stay two strokes.
    //
    // This window has TWO gap runs — day 3 on its own, then days 6-7 — so
    // `waitForBands(2)`. Asking for one would have timed out on a correct
    // render, which is how a test ends up "passing" by asserting less.
    const { container } = render(
      <ScoreTrendChart data={week(10, 20, null, 40, 50, null, null)} />,
    );
    await waitForBands(2);

    const d = await waitForCurve(container);
    expect(d.match(/M/g)?.length).toBe(2);
    expect(d).not.toContain("NaN");
  });

  it("still renders a full-span line when every day was measured", async () => {
    const { container } = render(
      <ScoreTrendChart data={week(10, 20, 30, 40, 50, 60, 70)} />,
    );

    const d = await waitForCurve(container);
    // One continuous subpath across all seven days, and no dot fallback —
    // a fully measured window has nothing to explain.
    expect(d.match(/M/g)?.length).toBe(1);
    expect(countDots(container)).toBe(0);
    expect(containerBands()).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function containerBands(): Element[] {
  return Array.from(
    document.querySelectorAll('[data-testid="trend-gap-band"]'),
  );
}

function bandDates(band: Element): string[] {
  return (band.getAttribute("data-gap-dates") ?? "").split(",").filter(Boolean);
}

function caption(): string | null {
  return document.querySelector('[data-testid="trend-gap-caption"]')
    ?.textContent?.trim() ?? null;
}

function countDots(container: HTMLElement): number {
  return container.querySelectorAll("circle.recharts-dot").length;
}

/**
 * Each day's tick on the x axis, with the pixel it sits at.
 *
 * recharts puts the position on the tick's `<text x=…>` rather than a transform
 * on the tick group, which reads as `transform=null` if you go looking there.
 * These are the axis' own day positions, so they are the reference the bands are
 * checked against — measuring the bands against themselves would prove nothing.
 */
function tickPositions(): { date: string; x: number }[] {
  return Array.from(
    document.querySelectorAll(".recharts-xAxis .recharts-cartesian-axis-tick"),
  ).map((tick) => {
    const value = tick.querySelector(".recharts-cartesian-axis-tick-value")!;
    return {
      date: value.textContent ?? "",
      x: Number(value.getAttribute("x")),
    };
  });
}

async function waitForBands(expected: number): Promise<Element[]> {
  await waitFor(
    () => {
      expect(containerBands()).toHaveLength(expected);
    },
    { timeout: 5000 },
  );
  return containerBands();
}

async function waitForCurve(container: HTMLElement): Promise<string> {
  let d = "";
  await waitFor(
    () => {
      d = container.querySelector("path.recharts-curve")?.getAttribute("d") ?? "";
      expect(d.length).toBeGreaterThan(0);
    },
    { timeout: 5000 },
  );
  return d;
}