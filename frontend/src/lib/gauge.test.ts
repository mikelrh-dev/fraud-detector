import { describe, expect, it } from "vitest";
import {
  GAUGE_START_ANGLE_DEG,
  GAUGE_SWEEP_DEG,
  polarToPoint,
  scoreToDashOffset,
  thresholdToPosition,
  totalArcLength,
} from "./gauge";

describe("totalArcLength", () => {
  it("is three quarters of the full circumference (270° sweep)", () => {
    const r = 80;
    expect(totalArcLength(r)).toBeCloseTo(2 * Math.PI * r * 0.75, 10);
  });

  it("scales linearly with the radius", () => {
    expect(totalArcLength(40)).toBeCloseTo(totalArcLength(80) / 2, 10);
  });
});

describe("scoreToDashOffset", () => {
  const L = totalArcLength(80);

  it("full score hides nothing (zero offset)", () => {
    expect(scoreToDashOffset(100, L)).toBeCloseTo(0, 10);
  });

  it("half score offsets half the arc", () => {
    expect(scoreToDashOffset(50, L)).toBeCloseTo(L / 2, 10);
  });

  it("zero score offsets the whole arc (nothing drawn)", () => {
    expect(scoreToDashOffset(0, L)).toBeCloseTo(L, 10);
  });

  it("clamps negative scores to the empty-gauge offset", () => {
    expect(scoreToDashOffset(-25, L)).toBeCloseTo(L, 10);
  });

  it("clamps scores above 100 to the full-gauge offset", () => {
    expect(scoreToDashOffset(150, L)).toBeCloseTo(0, 10);
  });

  it("decreases monotonically as the score grows", () => {
    let prev = scoreToDashOffset(0, L);
    for (let s = 10; s <= 100; s += 10) {
      const current = scoreToDashOffset(s, L);
      expect(current).toBeLessThan(prev);
      prev = current;
    }
  });
});

describe("thresholdToPosition", () => {
  it("maps thresholds to their fraction of the 0-100 scale", () => {
    expect(thresholdToPosition(0)).toBe(0);
    expect(thresholdToPosition(45)).toBeCloseTo(0.45, 12);
    expect(thresholdToPosition(60)).toBeCloseTo(0.6, 12);
    expect(thresholdToPosition(100)).toBe(1);
  });

  it("keeps warn below critical ordering", () => {
    expect(thresholdToPosition(45)).toBeLessThan(thresholdToPosition(60));
    expect(thresholdToPosition(60) - thresholdToPosition(45)).toBeCloseTo(
      0.15,
      12,
    );
  });

  it("clamps out-of-range thresholds into [0, 1]", () => {
    expect(thresholdToPosition(-10)).toBe(0);
    expect(thresholdToPosition(120)).toBe(1);
  });
});

describe("polarToPoint / 270° gap geometry", () => {
  const CX = 100;
  const CY = 100;
  const R = 80;

  it("starts the arc at the bottom-left (135°)", () => {
    const { x, y } = polarToPoint(CX, CY, R, 0);
    expect(x).toBeCloseTo(CX - R * Math.SQRT1_2, 10);
    expect(y).toBeCloseTo(CY + R * Math.SQRT1_2, 10);
  });

  it("ends the arc at the bottom-right (45° after full sweep)", () => {
    const { x, y } = polarToPoint(CX, CY, R, 1);
    expect(x).toBeCloseTo(CX + R * Math.SQRT1_2, 10);
    expect(y).toBeCloseTo(CY + R * Math.SQRT1_2, 10);
  });

  it("reaches straight up at mid-progress", () => {
    const { x, y } = polarToPoint(CX, CY, R, 0.5);
    expect(x).toBeCloseTo(CX, 10);
    expect(y).toBeCloseTo(CY - R, 10);
  });

  it("never maps a progress fraction into the bottom gap (45°–135°)", () => {
    for (let i = 0; i <= 100; i++) {
      const fraction = i / 100;
      const angle =
        (GAUGE_START_ANGLE_DEG + fraction * GAUGE_SWEEP_DEG) % 360;
      const inGap = angle > 45 && angle < 135;
      expect(inGap).toBe(false);
    }
  });

  it("respects the configured sweep and start constants", () => {
    expect(GAUGE_SWEEP_DEG).toBe(270);
    expect(GAUGE_START_ANGLE_DEG).toBe(135);
  });
});
