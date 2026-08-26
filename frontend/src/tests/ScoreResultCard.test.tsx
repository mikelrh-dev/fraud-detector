import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScoreResultCard } from "../pages/ScoreResultCard";
import type { ScoreResponse } from "../api/transactions";

const baseFixture = {
  transaction_id: "test-uuid",
  threshold: 40,
  created_at: new Date().toISOString(),
};

describe("ScoreResultCard", () => {
  it("renders loading skeleton when isLoading is true", () => {
    const { container } = render(<ScoreResultCard result={null} isLoading={true} />);
    // Should have pulse animation class
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("renders legitimate state with green badge and no fired rules", () => {
    const result: ScoreResponse = {
      ...baseFixture,
      classification: "legitimate",
      rule_score: 10,
      ml_score: 12.3,
      ensemble_score: 15.0,
      fired_rules: [],
    };
    render(<ScoreResultCard result={result} />);
    expect(screen.getByText("Legítimo")).toBeInTheDocument();
    // No fired rules section
    expect(screen.queryByText("Reglas Activadas")).not.toBeInTheDocument();
    // Score values visible (15.0 appears in both gauge and breakdown card)
    expect(screen.getByText("10.0")).toBeInTheDocument();
    expect(screen.getByText("12.3")).toBeInTheDocument();
    expect(screen.getAllByText("15.0").length).toBeGreaterThan(0);
  });

  it("renders review state with yellow badge and fired rules chips", () => {
    const result: ScoreResponse = {
      ...baseFixture,
      classification: "review",
      rule_score: 50,
      ml_score: 55.0,
      ensemble_score: 62.0,
      fired_rules: ["high_amount"],
    };
    render(<ScoreResultCard result={result} />);
    expect(screen.getByText("Revisión")).toBeInTheDocument();
    expect(screen.getByText("Reglas Activadas")).toBeInTheDocument();
    expect(screen.getByText("high_amount")).toBeInTheDocument();
    // Score values visible
    expect(screen.getByText("50.0")).toBeInTheDocument();
  });

  it("renders fraud state with red badge and multiple fired rules", () => {
    const result: ScoreResponse = {
      ...baseFixture,
      classification: "fraud",
      rule_score: 90,
      ml_score: 88.0,
      ensemble_score: 91.0,
      fired_rules: ["high_amount", "high_velocity", "new_merchant"],
    };
    render(<ScoreResultCard result={result} />);
    expect(screen.getByText("Fraude")).toBeInTheDocument();
    expect(screen.getByText("Reglas Activadas")).toBeInTheDocument();
    expect(screen.getByText("high_amount")).toBeInTheDocument();
    expect(screen.getByText("high_velocity")).toBeInTheDocument();
    expect(screen.getByText("new_merchant")).toBeInTheDocument();
  });

  it("renders ML-not-trained state when ml_score is null", () => {
    const result: ScoreResponse = {
      ...baseFixture,
      classification: "legitimate",
      rule_score: 10,
      ml_score: null,
      ensemble_score: 15.0,
      fired_rules: [],
    };
    render(<ScoreResultCard result={result} />);
    // ML-not-trained indicator
    expect(screen.getByText("ML: no entrenado")).toBeInTheDocument();
    // Rule and ensemble scores still render (15.0 appears in gauge + card)
    expect(screen.getByText("10.0")).toBeInTheDocument();
    expect(screen.getAllByText("15.0").length).toBeGreaterThan(0);
    // Phosphor Brain icon present (single icon system)
    expect(
      document.querySelector('[data-testid="ml-untrained-icon"] svg'),
    ).not.toBeNull();
  });
});
