import { describe, it, expect } from "vitest";
import { classificationColor, classificationLabel, formatScore, isMLTrained } from "./score";

describe("classificationColor", () => {
  it('returns "approved" for legitimate', () => {
    expect(classificationColor("legitimate")).toBe("approved");
  });

  it('returns "flagged" for review', () => {
    expect(classificationColor("review")).toBe("flagged");
  });

  it('returns "blocked" for fraud', () => {
    expect(classificationColor("fraud")).toBe("blocked");
  });
});

describe("classificationLabel", () => {
  it('returns "Legítimo" for legitimate', () => {
    expect(classificationLabel("legitimate")).toBe("Legítimo");
  });

  it('returns "Revisión" for review', () => {
    expect(classificationLabel("review")).toBe("Revisión");
  });

  it('returns "Fraude" for fraud', () => {
    expect(classificationLabel("fraud")).toBe("Fraude");
  });
});

describe("formatScore", () => {
  it("formats a valid number with one decimal", () => {
    expect(formatScore(67.5)).toBe("67.5");
  });

  it("formats a whole number", () => {
    expect(formatScore(80)).toBe("80.0");
  });

  it('returns "—" for null', () => {
    expect(formatScore(null)).toBe("—");
  });
});

describe("isMLTrained", () => {
  it("returns true when score is a number", () => {
    expect(isMLTrained(42.0)).toBe(true);
  });

  // D7-2 (b). The case this file used to hold here was
  //
  //     it("returns false when score is null", () => {
  //       expect(isMLTrained(null)).toBe(false);
  //     });
  //
  // which was green, and proved nothing. `ScoreResponse.ml_score` is
  // `number`, not `number | null` (frontend/src/api/transactions.ts:65), and
  // the comment above that field records why: Pydantic types it `float`,
  // FraudScore.ml_score is a non-nullable column, and A15 keeps the stored
  // value at 0.0 when the ML layer is absent. The wire cannot carry a null.
  // The test therefore asserted a state no producer can create, and it kept
  // the "modelo no entrenado" affordance looking tested while nothing tested it.
  //
  // The affordance itself is NOT removed here. Whether an untrained model
  // should be able to render at all is a product decision (fix-loop plan
  // section 3, D7-2 (a)), and deleting the branch would quietly answer it.
  // The TEST is the defect, so the test goes and the branch stays.
  //
  // 0.0 is the state that IS reachable, and it is the one worth pinning.
  // An untrained model reports 0.0, not null, so a truthiness-based
  // `isMLTrained` would report "not trained" for every transaction the
  // pipeline scored without the ML layer -- the most common case, silently
  // inverted. Nullability is the distinction this function actually has to
  // make, and `score !== null` is the only check that makes it.
  it("returns true for 0.0 — an untrained model reports 0.0, not null", () => {
    expect(isMLTrained(0.0)).toBe(true);
  });

  it("returns true across the whole producible range", () => {
    for (const score of [0, 0.0, 1, 42.5, 100]) {
      expect(isMLTrained(score)).toBe(true);
    }
  });
});
