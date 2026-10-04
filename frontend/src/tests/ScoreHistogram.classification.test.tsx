import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { sizedResponsiveContainer } from "../test-utils/recharts";
import { buildBuckets } from "../components/ScoreHistogram";

/**
 * WHY THIS FILE EXISTS — the histogram contradicted the table.
 *
 * The bars were coloured by POSITION: buckets 0-20 and 20-40 were green,
 * 40-60 and 60-80 amber, 80-100 red, with a legend reading
 * "Legítimo (0-40) / Revisión (41-80) / Fraude (81-100)".
 *
 * That mapping is not how this product classifies anything. The backend's
 * threshold is TIERED BY AMOUNT (`src/core/config.py:207-227`: 70 / 50 / 45 / 40
 * by amount band) and `ensemble.classify` calls `score > threshold` fraud
 * (src/services/ensemble.py:158). So on a low-amount transaction 76.46 is FRAUDE
 * — and it was drawn inside the amber "Revisión" bar. The same dashboard showed
 * that row as "Fraude" in the table directly below the chart.
 *
 * The second half is the legend, which asserted a range-to-verdict mapping that
 * does not exist. Even after the bars are fixed, a legend that says
 * "Fraude (81-100)" is a claim about the data, and the data does not support it:
 * the same score classifies differently at a different amount.
 *
 * Every colour below is a LITERAL, for the reason `surface-consistency.test.tsx`
 * gives: importing the token under test moves both sides of the assertion, so
 * the test stays green while the mapping drifts. `chart-theme.test.ts` is the
 * layer that holds those literals against `index.css`.
 */
const CRITICAL = "#ef4444";
const WARN = "#f59e0b";
const CLEAN = "#22c55e";
/** slate-700 — the neutral the app paints an undetermined state with. */
const NEUTRAL = "#334155";

/**
 * recharts' `ResponsiveContainer` measures its own box, and jsdom reports 0x0,
 * so it renders an EMPTY div — no SVG at all. `sizedResponsiveContainer` is the
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

const { default: ScoreHistogramComponent } = await import(
  "../components/ScoreHistogram"
);

/** A transaction row as the dashboard holds it. */
function row(risk_score: number | null, classification: string | null) {
  return { risk_score, classification };
}

/** The single segment of a bucket, addressed by verdict. */
function segmentOf(
  buckets: ReturnType<typeof buildBuckets>,
  range: string,
  classification: string,
) {
  const bucket = buckets.find((b) => b.range === range);
  if (!bucket) throw new Error(`no bucket labelled ${range}`);
  return bucket.segments.find((s) => s.classification === classification);
}

describe("buildBuckets — the verdict a row carries decides its colour", () => {
  it("puts a 76.46 fraud in the 60-80 bucket painted CRITICAL, not amber", () => {
    // The reported contradiction, as a fixture: threshold 70 (low amount),
    // 76.46 > 70, so the backend classified this fraud.
    const buckets = buildBuckets([row(76.46, "fraud")]);

    const fraud = segmentOf(buckets, "60-80", "fraud");
    expect(fraud).toBeDefined();
    expect(fraud!.count).toBe(1);
    expect(fraud!.color).toBe(CRITICAL);
    // And explicitly not the colour the old position-based palette gave this
    // bucket. This is the assertion the defect turns on.
    expect(fraud!.color).not.toBe(WARN);
  });

  it("gives two rows in the SAME bucket different colours", () => {
    // 55 crosses the 40-tier (amount >= 50000.01) but not the 70-tier, so the
    // identical score is a fraud at one amount and a review at another. Same
    // bucket, same position, opposite colours — which position-based colouring
    // cannot express at all.
    const buckets = buildBuckets([
      row(55, "review"),
      row(55, "fraud"),
    ]);

    expect(segmentOf(buckets, "40-60", "review")!.color).toBe(WARN);
    expect(segmentOf(buckets, "40-60", "fraud")!.color).toBe(CRITICAL);
  });

  it("never colours by bucket index: identical positions, different fills", () => {
    // A representative sample across all five buckets, and the rule is stated
    // once: the fill follows the row's classification, full stop.
    const buckets = buildBuckets([
      row(10, "legitimate"),
      row(30, "legitimate"),
      row(45, "review"),
      row(65, "review"),
      row(85, "fraud"),
    ]);
    const fills = buckets
      .flatMap((b) => b.segments)
      .filter((s) => s.count > 0)
      .map((s) => `${s.classification}:${s.color}`);

    expect(fills).toEqual([
      `legitimate:${CLEAN}`,
      `legitimate:${CLEAN}`,
      `review:${WARN}`,
      `review:${WARN}`,
      `fraud:${CRITICAL}`,
    ]);
  });

  it("treats a missing or unknown classification as undetermined, never safe", () => {
    // The V-02 rule from lib/classification.ts, applied here too: an absent
    // verdict is not a green one. A chart that painted unscored rows green
    // would be the same defect the gauge had.
    const buckets = buildBuckets([row(50, null), row(60, "escalated")]);

    for (const range of ["40-60", "60-80"]) {
      const undetermined = bucket(buckets, range);
      expect(undetermined.tone).toBe("neutral");
      expect(undetermined.color).toBe(NEUTRAL);
      expect(undetermined.color).not.toBe(CLEAN);
    }
  });

  function bucket(buckets: ReturnType<typeof buildBuckets>, range: string) {
    const b = buckets.find((x) => x.range === range);
    if (!b) throw new Error(`no bucket ${range}`);
    return b.segments.find((s) => s.count > 0)!;
  }

  it("counts every float-edge score exactly once, in one bucket", () => {
    // The prior bug class for this function: inclusive buckets with a one-unit
    // step (0-20, 21-40, ...) dropped 20.5 / 40.5 / 60.5 / 80.5 on the floor, so
    // the bars did not sum to the transaction count. Half-open intervals fix it,
    // and the verdict must not have been traded away for the fix.
    const buckets = buildBuckets([
      row(20.5, "legitimate"),
      row(40.5, "review"),
      row(60.5, "review"),
      row(80.5, "fraud"),
    ]);

    // Four rows, four DIFFERENT buckets, one row each — so exactly one bucket is
    // empty. Asserting "every bucket has 1" here would be a test bug, not a
    // stricter check, so the occupancy is asserted as a shape.
    expect(buckets.map((b) => b.count)).toEqual([0, 1, 1, 1, 1]);
    expect(buckets.reduce((sum, b) => sum + b.count, 0)).toBe(4);

    // And each landed in the bucket its label names, which is the part the old
    // gap-dropping definition got wrong.
    expect(segmentOf(buckets, "20-40", "legitimate")!.count).toBe(1);
    expect(segmentOf(buckets, "40-60", "review")!.count).toBe(1);
    expect(segmentOf(buckets, "60-80", "review")!.count).toBe(1);
    expect(segmentOf(buckets, "80-100", "fraud")!.count).toBe(1);
  });

  it("keeps the boundary in exactly one bucket and the total equal to the input", () => {
    for (const edge of [0, 20, 40, 60, 80, 100]) {
      const buckets = buildBuckets([row(edge, "review")]);
      expect(buckets.reduce((sum, b) => sum + b.count, 0)).toBe(1);
    }
  });

  it("emits the same verdict slots in every bucket so a stack cannot misalign", () => {
    // If bucket A carried [legitimate, fraud] and bucket B only [legitimate],
    // a positional stack would draw B's legitimate segment where A's fraud
    // segment sits. Uniform slots make that unrepresentable.
    const buckets = buildBuckets([
      row(10, "legitimate"),
      row(85, "fraud"),
    ]);
    const shapes = buckets.map((b) => b.segments.map((s) => s.classification));
    for (const shape of shapes) {
      expect(shape).toEqual(shapes[0]);
    }
  });

  it("still accepts bare scores, which carry no verdict", () => {
    // The numeric form is how this function was already called, and a score
    // with no classification is a real state — it is simply undetermined.
    const buckets = buildBuckets([10, 85]);
    expect(buckets.reduce((sum, b) => sum + b.count, 0)).toBe(2);
    expect(segmentOf(buckets, "0-20", "undetermined")!.tone).toBe("neutral");
  });

  it("ignores non-finite and null scores rather than bucketing them", () => {
    const buckets = buildBuckets([
      row(NaN, "fraud"),
      row(Infinity, "fraud"),
      row(null, "fraud"),
      row(50, "review"),
    ]);
    expect(buckets.reduce((sum, b) => sum + b.count, 0)).toBe(1);
  });
});


describe("ScoreHistogram — the drawn chart and its legend", () => {
  it("paints a 76.46 fraud in red, not amber", async () => {
    render(
      <ScoreHistogramComponent
        transactions={[row(76.46, "fraud"), row(10, "legitimate")]}
      />,
    );

    const fills = await drawnFills(2);
    expect(fills).toContain(CRITICAL);
    expect(fills).toContain(CLEAN);
    // The falsifiable half: this fixture used to draw amber and NO red at all,
    // because the 60-80 bucket was amber by position.
    expect(fills).not.toContain(WARN);
  });

  it("stacks a mixed bucket into ONE bar, both verdicts on one column", async () => {
    // The essential claim, stated so a positional palette cannot satisfy it: two
    // verdicts in the same bucket share an x and are stacked, rather than being
    // drawn as two bars side by side at one category.
    render(
      <ScoreHistogramComponent
        transactions={[row(55, "review"), row(58, "fraud"), row(10, "legitimate")]}
      />,
    );

    const columns = await drawnColumns(3);
    const mixed = columns.find(
      (c) => c.fills.includes(WARN) && c.fills.includes(CRITICAL),
    );

    expect(mixed, "no column carries both amber and red").toBeDefined();
    expect(mixed!.fills).toHaveLength(2);
    // Stacked, not overlapping: the red segment sits strictly ABOVE the amber
    // one. SVG y grows downward, so above means smaller.
    const [amber, red] = mixed!.segments;
    expect(red.x).toBe(amber.x);
    expect(Number(red.y)).toBeLessThan(Number(amber.y));

    // And the legitimate row is a DIFFERENT column, so the pairing above is a
    // property of that one bucket and not of the chart as a whole.
    const green = columns.find((c) => c.fills.includes(CLEAN));
    expect(green).toBeDefined();
    expect(green!.x).not.toBe(mixed!.x);
  });

  it("stacks least severe at the bottom, so a colour always sits in one place", async () => {
    // The stack order is part of the reading: "red on top" is something a reader
    // learns once. If the order came from which verdict happened to appear first
    // in the data, the same rows would stack differently for two analysts — and
    // the input order here is deliberately fraud-first.
    //
    // All six rows sit in the 40-60 bucket on purpose. That is not a contrivance:
    // 45 is legitimate below the 70-tier (its review floor is 52.5) and 55 is a
    // fraud above the 40-tier. One score range, three verdicts — which is the
    // whole reason this chart cannot colour by position.
    render(
      <ScoreHistogramComponent
        transactions={[
          row(55, "fraud"),
          row(55, "review"),
          row(45, "legitimate"),
          row(56, "fraud"),
          row(56, "review"),
          row(46, "legitimate"),
        ]}
      />,
    );

    // Six rows, all in the 40-60 bucket, so exactly THREE drawn segments: one
    // per verdict. Four buckets' worth of tracks are drawn too, but a track is
    // not a segment.
    const columns = await drawnColumns(3);
    const full = columns.find(
      (c) =>
        c.fills.includes(CLEAN) && c.fills.includes(WARN) && c.fills.includes(CRITICAL),
    );
    expect(full, "no column carries all three verdicts").toBeDefined();

    const yOf = (fill: string) =>
      Number(full!.segments.find((s) => s.fill === fill)!.y);
    expect(yOf(CLEAN)).toBeGreaterThan(yOf(WARN));
    expect(yOf(WARN)).toBeGreaterThan(yOf(CRITICAL));
  });

  it("names each verdict with the count actually drawn, and no score range", () => {
    render(
      <ScoreHistogramComponent
        transactions={[
          row(10, "legitimate"),
          row(12, "legitimate"),
          row(76.46, "fraud"),
        ]}
      />,
    );

    const legend = screen.getByTestId("histogram-legend");

    // What is drawn: two legitimate, one fraud.
    expect(within(legend).getByText(/Leg.timo\s*\(2\)/)).toBeInTheDocument();
    expect(within(legend).getByText(/Fraude\s*\(1\)/)).toBeInTheDocument();
    // A verdict with nothing in it is not advertised: the chart cannot support
    // a claim about a colour that is not on screen.
    expect(within(legend).queryByText(/Revisi/)).not.toBeInTheDocument();

    // The falsifiable half: the fixed range-to-verdict mapping is gone. That is
    // the claim which made a 76.46 fraud read as an amber "Revisión (41-80)".
    for (const lie of [
      "0-40",
      "41-80",
      "81-100",
      "(0-40)",
      "(41-80)",
      "(81-100)",
    ]) {
      expect(legend.textContent).not.toContain(lie);
    }
    // No score RANGE anywhere in the legend, in any spelling.
    expect(legend.textContent).not.toMatch(/\d+\s*-\s*\d+/);
  });
});

interface Segment {
  fill: string;
  x: string;
  y: string;
}

/** Drawn bar segments grouped by the x column they occupy. */
interface Column {
  x: string;
  fills: string[];
  segments: Segment[];
}

/**
 * recharts grows each bar in from zero height, and `Rectangle` renders NOTHING
 * at all while the height is 0 — so immediately after render the chart holds
 * five tracks and no bars. Measured rather than assumed: an un-waited render of
 * this component yields 0 bar rectangles and 3 once the animation settles.
 *
 * Hence the wait, and hence waiting for an EXACT count rather than "> 0": a
 * partially-finished animation satisfies the weaker condition, and a test that
 * passed on a half-drawn bar would be asserting nothing.
 */
async function drawnColumns(expectedSegments: number): Promise<Column[]> {
  let segments: Segment[] = [];
  await waitFor(
    () => {
      segments = [...document.querySelectorAll("path.recharts-rectangle")]
        .filter((p) => !p.getAttribute("class")?.includes("background"))
        .map((p) => ({
          fill: p.getAttribute("fill") ?? "",
          x: p.getAttribute("x") ?? "",
          y: p.getAttribute("y") ?? "",
        }));
      expect(segments).toHaveLength(expectedSegments);
    },
    { timeout: 5000 },
  );

  const byX = new Map<string, Segment[]>();
  for (const segment of segments) {
    byX.set(segment.x, [...(byX.get(segment.x) ?? []), segment]);
  }
  return [...byX.entries()].map(([x, group]) => ({
    x,
    fills: group.map((s) => s.fill),
    segments: group,
  }));
}

/** Just the fills, for the assertions that do not care about geometry. */
async function drawnFills(expectedSegments: number): Promise<string[]> {
  return (await drawnColumns(expectedSegments)).flatMap((c) => c.fills);
}
