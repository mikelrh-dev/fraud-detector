import { describe, it, expect } from "vitest";
import { classificationColor, classificationLabel, formatScore, isMLTrained } from "./score";

type ScoreClassification = "legitimate" | "review" | "fraud";

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

  it("returns false when score is null", () => {
    expect(isMLTrained(null)).toBe(false);
  });
});
