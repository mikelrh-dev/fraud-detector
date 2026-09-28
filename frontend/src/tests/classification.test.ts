import { describe, it, expect } from "vitest";
import {
  classificationTone,
  classificationText,
  classificationTextClass,
  isKnownClassification,
} from "../lib/classification";
import { formatMoney } from "../lib/money";

/**
 * The classification → colour relationship used to be expressed five times
 * (RiskMeter, ScoreResultCard, TransactionTable, TransactionDetail,
 * AlertsPage) and had already drifted: TransactionDetail's copy was
 * byte-identical to TransactionTable's, AlertsPage's was missing `pending`, and
 * the dashboard rendered two different green pills for the same "legitimate"
 * state in the same table.
 *
 * The worst part was the fallback. `classificationToTone` returned `clean` for
 * everything it did not recognise, so an unknown or pending classification drew
 * a confident GREEN gauge — a "safe" colour wrapped around a value nobody had
 * determined.
 */
describe("classificationTone", () => {
  it("maps the three backend classifications", () => {
    expect(classificationTone("legitimate")).toBe("clean");
    expect(classificationTone("review")).toBe("warn");
    expect(classificationTone("fraud")).toBe("critical");
  });

  it("returns neutral — never clean — for an unknown classification", () => {
    // The V-02 regression: these all used to return "clean".
    expect(classificationTone("pending")).toBe("neutral");
    expect(classificationTone("unknown")).toBe("neutral");
    expect(classificationTone("")).toBe("neutral");
  });

  it("returns neutral for null and undefined", () => {
    expect(classificationTone(null)).toBe("neutral");
    expect(classificationTone(undefined)).toBe("neutral");
  });

  it("is case sensitive like the backend", () => {
    // Backend emits lowercase; "Fraud" is not a value it produces, so it must
    // not be guessed at.
    expect(classificationTone("Fraud")).toBe("neutral");
  });
});

describe("isKnownClassification", () => {
  it("recognises only the three backend values", () => {
    expect(isKnownClassification("legitimate")).toBe(true);
    expect(isKnownClassification("review")).toBe(true);
    expect(isKnownClassification("fraud")).toBe(true);
    expect(isKnownClassification("pending")).toBe(false);
    expect(isKnownClassification(null)).toBe(false);
  });
});

describe("classificationText", () => {
  it("labels the three known classifications", () => {
    expect(classificationText("legitimate")).toBe("Legítimo");
    expect(classificationText("review")).toBe("Revisión");
    expect(classificationText("fraud")).toBe("Fraude");
  });

  it("never labels an unknown value as Legítimo", () => {
    // A null classification means "no score recorded", not "safe".
    expect(classificationText(null)).toBe("Pendiente");
    expect(classificationText(undefined)).toBe("Pendiente");
    expect(classificationText("")).toBe("Pendiente");
    expect(classificationText("mystery")).toBe("Pendiente");
  });
});

describe("classificationTextClass", () => {
  it("returns slate for unknown rather than a risk colour", () => {
    expect(classificationTextClass("pending")).toBe("text-slate-400");
    expect(classificationTextClass(null)).toBe("text-slate-400");
  });

  it("returns a coloured class for known values", () => {
    expect(classificationTextClass("fraud")).toBe("text-fraud-fraud");
    expect(classificationTextClass("review")).toBe("text-fraud-review");
    expect(classificationTextClass("legitimate")).toBe("text-fraud-legitimate");
  });
});

/**
 * The same amount was rendered three ways, and one of them dropped the cents:
 * a $1,234.56 charge displayed as "$1.235" on the detail page and in the table,
 * while the mobile card showed "$1234.56" for the same record. On a
 * fraud-investigation surface, hiding cents from the amount under review is a
 * data-fidelity defect.
 */
describe("formatMoney", () => {
  it("preserves cents", () => {
    const formatted = formatMoney(1234.56, "USD");
    expect(formatted).toContain("56");
    expect(formatted).not.toBe("$1.235");
  });

  it("keeps cents for values that would round to whole units", () => {
    expect(formatMoney(1100.0, "USD")).toContain("00");
  });

  it("uses the es-AR convention: dot for thousands, comma for decimals", () => {
    const formatted = formatMoney(1234.56, "USD");
    // 1.234,56 — the previous `$${amount.toLocaleString("es-AR")}` produced
    // "$1.235": a dot as the decimal separator and the cents discarded, so the
    // figure was ambiguous (it read as 1235) and unfaithful to the record.
    expect(formatted).toContain("1.234");
    expect(formatted).toContain(",56");
  });

  it("does not emit the old ambiguous dot-decimal form", () => {
    // "$1.235" is the bug: dot + 3 digits + nothing else, i.e. cents dropped.
    expect(formatMoney(1234.56, "USD")).not.toBe("$1.235");
  });

  it("is identical for the same amount and currency", () => {
    // The mobile card and the desktop table must not disagree.
    expect(formatMoney(1100, "USD")).toBe(formatMoney(1100, "USD"));
  });

  it("honours the currency instead of hardcoding a symbol", () => {
    expect(formatMoney(100, "USD")).toMatch(/\$/);
    expect(formatMoney(100, "EUR")).toMatch(/€/);
  });

  it("keeps the familiar $ for USD rather than switching to US$", () => {
    // The default es-AR currency display is "US$ 1.100,00", which would change
    // how every amount in the product looks. narrowSymbol keeps "$1.100,00".
    expect(formatMoney(100, "USD")).toMatch(/^\$/);
    expect(formatMoney(100, "USD")).not.toContain("US$");
  });

  it("does not throw on an unknown currency code", () => {
    expect(() => formatMoney(100, "NOT_A_CODE")).not.toThrow();
  });

  it("renders a dash for non-finite amounts", () => {
    expect(formatMoney(NaN, "USD")).toBe("—");
    expect(formatMoney(Infinity, "USD")).toBe("—");
  });

  it("defaults to USD", () => {
    expect(formatMoney(50)).toBe(formatMoney(50, "USD"));
  });
});
