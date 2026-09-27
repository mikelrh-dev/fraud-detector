import { describe, it, expect } from "vitest";
import { buildBuckets } from "../components/ScoreHistogram";
import {
  buildDailyAverages,
  type DailyAverage,
} from "../components/ScoreTrendChart";

/**
 * Regression tests for the two data-honesty defects:
 *
 * 1. buildBuckets dropped every score that fell in a float gap between
 *    inclusive buckets (0-20, 21-40, ...), so 20.5 / 40.5 / 60.5 / 80.5 were
 *    discarded and the bars did not sum to the transaction count.
 * 2. buildDailyAverages fabricated avgScore: 0 for days with no data, so a
 *    failed query rendered as a flat "risk is zero" line, and a falsy check
 *    dropped transactions whose score was legitimately 0.
 */

const totalCount = (buckets: { count: number }[]) =>
  buckets.reduce((sum, b) => sum + b.count, 0);

describe("buildBuckets", () => {
  it("counts every in-range score, including the old gap values", () => {
    const scores = [20.5, 40.5, 60.5, 80.5];
    const buckets = buildBuckets(scores);

    expect(totalCount(buckets)).toBe(4);
  });

  it("buckets sum to the input length for a wide sample", () => {
    const scores = Array.from({ length: 501 }, (_, i) => i * 0.2); // 0 .. 100
    expect(totalCount(buildBuckets(scores))).toBe(scores.length);
  });

  it("places boundaries in exactly one bucket each", () => {
    for (const edge of [0, 20, 40, 60, 80, 100]) {
      const buckets = buildBuckets([edge]);
      expect(totalCount(buckets)).toBe(1);
    }
  });

  it("keeps 100 in the top bucket", () => {
    const buckets = buildBuckets([100]);
    expect(buckets[buckets.length - 1].count).toBe(1);
  });

  it("clamps out-of-contract values instead of dropping them", () => {
    expect(totalCount(buildBuckets([150]))).toBe(1);
    expect(totalCount(buildBuckets([-5]))).toBe(1);
  });

  it("ignores non-finite scores", () => {
    expect(totalCount(buildBuckets([NaN, Infinity, 50]))).toBe(1);
  });

  it("returns five contiguous buckets", () => {
    const buckets = buildBuckets([]);
    expect(buckets).toHaveLength(5);
  });
});

describe("buildDailyAverages", () => {
  const today = new Date();
  const iso = (d: Date) => d.toISOString();

  it("uses null, never 0, for a day with no transactions", () => {
    const result = buildDailyAverages([], 7);

    expect(result).toHaveLength(7);
    for (const day of result) {
      expect(day.avgScore).toBeNull();
    }
  });

  it("includes transactions whose score is exactly 0", () => {
    const result = buildDailyAverages(
      [{ risk_score: 0, created_at: iso(today) }],
      7,
    );

    const withData = result.filter((d) => d.avgScore !== null);
    expect(withData).toHaveLength(1);
    expect(withData[0].avgScore).toBe(0);
  });

  it("keeps a real 0 distinguishable from a gap", () => {
    const result = buildDailyAverages(
      [{ risk_score: 0, created_at: iso(today) }],
      7,
    );

    const nulls = result.filter((d) => d.avgScore === null);
    const zeros = result.filter((d) => d.avgScore === 0);

    expect(nulls.length).toBe(6);
    expect(zeros.length).toBe(1);
  });

  it("averages real scores", () => {
    const result = buildDailyAverages(
      [
        { risk_score: 20, created_at: iso(today) },
        { risk_score: 40, created_at: iso(today) },
      ],
      7,
    );

    const scored = result.filter((d): d is DailyAverage & { avgScore: number } =>
      d.avgScore !== null,
    );
    expect(scored).toHaveLength(1);
    expect(scored[0].avgScore).toBe(30);
  });

  it("ignores null scores without treating them as zero", () => {
    const result = buildDailyAverages(
      [{ risk_score: null, created_at: iso(today) }],
      7,
    );
    expect(result.every((d) => d.avgScore === null)).toBe(true);
  });
});
