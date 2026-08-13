import { describe, it, expect } from "vitest";
import {
  featureLabel,
  formatContribution,
  contributionDirection,
} from "./shap";

describe("featureLabel", () => {
  it("maps backend feature names to Spanish labels (FRD-SHP-002)", () => {
    expect(featureLabel("amount")).toBe("Monto");
    expect(featureLabel("amount_vs_user_avg")).toBe("Monto promedio");
    expect(featureLabel("amount_vs_user_std")).toBe("Desviación del monto");
    expect(featureLabel("tx_count_last_5min")).toBe("Transacciones últimas 5 min");
    expect(featureLabel("tx_count_last_1h")).toBe("Transacciones última hora");
    expect(featureLabel("hour_of_day")).toBe("Hora del día");
    expect(featureLabel("is_weekend")).toBe("Fin de semana");
    expect(featureLabel("merchant_risk_level")).toBe("Riesgo del comercio");
    expect(featureLabel("is_crypto")).toBe("Criptomoneda");
    expect(featureLabel("amount_round_number")).toBe("Monto redondo");
  });

  it("falls back to the raw feature name when the map has no entry", () => {
    expect(featureLabel("unknown_feature")).toBe("unknown_feature");
  });
});

describe("formatContribution", () => {
  it("prepends a plus sign for positive contributions", () => {
    expect(formatContribution(35)).toBe("+35.0");
  });

  it("keeps the minus sign for negative contributions", () => {
    expect(formatContribution(-5)).toBe("-5.0");
  });

  it("treats zero as a signed positive value", () => {
    expect(formatContribution(0)).toBe("+0.0");
  });
});

describe("contributionDirection", () => {
  it("returns fraud for positive contributions (pushes toward fraud)", () => {
    expect(contributionDirection(35)).toBe("fraud");
  });

  it("returns legitimate for negative contributions", () => {
    expect(contributionDirection(-5)).toBe("legitimate");
  });
});
