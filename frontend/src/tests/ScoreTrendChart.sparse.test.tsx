import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactElement } from "react";
import {
  MIN_CONSECUTIVE_DAYS_FOR_LINE,
  longestMeasuredRun,
  needsVisibleDots,
} from "../lib/trend";
import { buildDailyAverages } from "../components/ScoreTrendChart";
import type { DailyAverage } from "../lib/trend";
import { sizedResponsiveContainer } from "../test-utils/recharts";

/**
 * WHY THIS FILE EXISTS — the chart drew nothing and said nothing.
 *
 * `dot={false}` plus `connectNulls={false}` is a combination that renders an
 * EMPTY chart whenever no two measured days are adjacent. A lone measured day
 * produced the path `M186.67,77 L186.67,165 Z` — a zero-width vertical sliver,
 * i.e. no pixels — and no dots to fall back on. The chart took its full 200px,
 * drew its axes, showed no "no data" message (because `hasData` was true), and
 * left the analyst looking at an empty panel that claimed nothing.
 *
 * Measured on the pre-fix component, not reasoned about:
 *   1 of 7 days  -> curves ["M186.67,77L186.67,165Z"]  dots 0  no-data false
 *   2 of 7 days  -> curves ["M186.67,77L186.67,165Z M430,53L430,165Z"]  dots 0
 *   7 of 7 days  -> a real curve                       dots 0  no-data false
 *
 * The null handling itself is CORRECT and is deliberately not touched: a day
 * with no transactions is a gap, and `connectNulls={false}` is what keeps it
 * one. Interpolating through it would draw a fabricated score for a day nobody
 * transacted on. These tests hold that line while the sparse case is fixed.
 */

/**
 * recharts' `ResponsiveContainer` measures its own box and jsdom reports 0x0, so
 * it renders an empty div with no SVG at all. `sizedResponsiveContainer` is the
 * shared stand-in; see `src/test-utils/recharts.ts` for why it exists and what
 * it deliberately does not change.
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

describe("longestMeasuredRun — what can actually draw a line", () => {
  it("counts consecutive measured days", () => {
    expect(longestMeasuredRun(week(10, 20, 30, null, null, null, null))).toBe(3);
    expect(longestMeasuredRun(week(null, null, null, null, null, null, 42))).toBe(1);
  });

  it("returns the LONGEST run, not the total, so isolated days do not count as a line", () => {
    // Three measured days that share no adjacency. A count of "3 non-null days"
    // would call this a drawable trend; it is three unconnected points.
    expect(longestMeasuredRun(week(10, null, 20, null, 30, null, null))).toBe(1);
  });

  it("is 0 for a window with nothing measured", () => {
    expect(longestMeasuredRun(week(null, null, null, null, null, null, null))).toBe(0);
    expect(longestMeasuredRun([])).toBe(0);
  });

  it("treats a genuine 0 as measured — a gap and a zero are different claims", () => {
    expect(longestMeasuredRun(week(null, null, 0, 0, null, null, null))).toBe(2);
  });
});

describe("needsVisibleDots", () => {
  it("asks for dots when a single day was measured", () => {
    expect(needsVisibleDots(week(null, null, 55, null, null, null, null))).toBe(true);
  });

  it("asks for dots when measured days are all isolated, however many there are", () => {
    // The case a plain "fewer than N non-null days" rule gets wrong: three
    // measured days, zero segments drawable.
    expect(needsVisibleDots(week(10, null, 20, null, 30, null, null))).toBe(true);
  });

  it("does not ask for dots once two adjacent days can draw a segment", () => {
    expect(needsVisibleDots(week(null, 55, 60, null, null, null, null))).toBe(false);
    expect(needsVisibleDots(week(10, 20, 30, 40, 50, 60, 70))).toBe(false);
  });

  it("does not ask for dots on an empty window, which gets the no-data message", () => {
    expect(needsVisibleDots(week(null, null, null, null, null, null, null))).toBe(
      false,
    );
  });

  it("names the threshold it reasons about", () => {
    // The constant is the decision. If someone tunes it, this is the line that
    // makes the tuning deliberate instead of accidental.
    expect(MIN_CONSECUTIVE_DAYS_FOR_LINE).toBe(2);
  });
});

describe("ScoreTrendChart — a sparse window is still drawn", () => {
  it("draws a visible point for a single measured day", async () => {
    const { container } = render(
      <ScoreTrendChart data={week(null, null, 55, null, null, null, null)} />,
    );

    // The assertion the defect turns on. Pre-fix this was 0 and the curve was a
    // zero-width sliver, so the panel was blank.
    const dots = await waitForDots(1);
    expect(dots).toBe(1);

    // The dot sits at the measured day's own coordinates, so it is a reading of
    // the data and not a decorative dot dropped in the middle of the panel.
    const dot = document.querySelector("circle.recharts-dot")!;
    const xs = [...document.querySelectorAll(".recharts-cartesian-axis-tick-value")].map(
      (t) => t.textContent,
    );
    expect(xs).toContain("2026-10-03");
    expect(Number(dot.getAttribute("cx"))).toBeGreaterThan(0);

    // And no message claiming there is nothing to see — there IS a measurement.
    expect(container.textContent).not.toContain("Sin datos suficientes");
  });

  it("keeps the no-data message for a window with nothing measured", () => {
    const { container } = render(
      <ScoreTrendChart data={week(null, null, null, null, null, null, null)} />,
    );

    expect(screen.getByText("Sin datos suficientes")).toBeInTheDocument();
    // No chart at all, so there is nothing half-drawn to misread.
    expect(container.querySelectorAll("svg")).toHaveLength(0);
  });

  it("keeps a gap a gap: two runs stay two strokes, and the gap day gets no point", async () => {
    // Days 1-2 and 4-5 measured, day 3 empty. `connectNulls={false}` must keep
    // those as two separate strokes — a single continuous line would draw a
    // score for a day with no transactions.
    const { container } = render(
      <ScoreTrendChart data={week(10, 20, null, 40, 50, null, null)} />,
    );

    const d = await waitForCurve();
    // Two subpaths: the path starts a new one with "M" instead of continuing.
    expect(d.match(/M/g)?.length).toBe(2);
    expect(d).not.toContain("NaN");

    // Four measured days, four points — the gap day contributes none, and the
    // sparse-dot fallback stays OFF because a segment was drawable.
    expect(countDots(container)).toBe(0);
  });
  it("never interpolates through a gap, in the source", () => {
    // The behavioural test above covers the rendered result; this pins the
    // prop, because the day `connectNulls` is flipped is the day a gap becomes
    // a fabricated measurement, and no assertion about two subpaths survives
    // someone deleting the gap entirely to make a screenshot look tidy.
    const source = readFileSync(
      join(process.cwd(), "src", "components", "ScoreTrendChart.tsx"),
      "utf-8",
    );
    expect(source).toContain("connectNulls={false}");
    expect(source).not.toContain("connectNulls={true}");
  });

  it("still never fabricates a score for a day with no transactions", () => {
    // The honesty invariant behind `connectNulls={false}`, re-checked here
    // because the fix touches this file: a 0 would read as a real measurement.
    const result = buildDailyAverages(
      [{ risk_score: 55, created_at: new Date().toISOString() }],
      7,
    );
    expect(result.filter((d) => d.avgScore === 0)).toHaveLength(0);
    expect(result.filter((d) => d.avgScore === null)).toHaveLength(6);
  });
});

/**
 * recharts draws each measured day as `circle.recharts-dot`, inside a
 * `g.recharts-area-dots` layer — and only for days that carry a value, so a gap
 * day never gets one. Verified against recharts 2.15.4 rather than assumed:
 * an isolated measured day surrounded by nulls yields exactly one dot at that
 * day's own coordinates.
 */
function countDots(container: HTMLElement): number {
  return container.querySelectorAll("circle.recharts-dot").length;
}

async function waitForDots(expected: number): Promise<number> {
  let count = 0;
  await waitFor(
    () => {
      count = countDots(document.body);
      expect(count).toBe(expected);
    },
    { timeout: 5000 },
  );
  return count;
}

/**
 * The area's stroke path. Bars and areas both grow in from zero, so this waits
 * for real geometry rather than reading the pre-animation state.
 */
async function waitForCurve(): Promise<string> {
  let d = "";
  await waitFor(
    () => {
      d =
        document.querySelector("path.recharts-curve")?.getAttribute("d") ?? "";
      expect(d.length).toBeGreaterThan(0);
    },
    { timeout: 5000 },
  );
  return d;
}
