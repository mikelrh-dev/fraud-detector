import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ShapAttributionCard } from "../components/ShapAttributionCard";
import type { ShapContribution } from "../api/transactions";

describe("ShapAttributionCard", () => {
  it("renders rows with Spanish labels, signed contributions and direction", () => {
    const contributions: ShapContribution[] = [
      { feature: "amount", contribution: 35 },
      { feature: "merchant_risk_level", contribution: -5 },
    ];
    render(<ShapAttributionCard contributions={contributions} />);

    expect(screen.getByText("Atribución SHAP")).toBeInTheDocument();
    expect(screen.getByText("Monto")).toBeInTheDocument();
    expect(screen.getByText("Riesgo del comercio")).toBeInTheDocument();
    expect(screen.getByText("+35.0")).toBeInTheDocument();
    expect(screen.getByText("-5.0")).toBeInTheDocument();
    // Direction semantics: positive → fraud, negative → legitimate
    expect(screen.getByText("Hacia fraude")).toBeInTheDocument();
    expect(screen.getByText("Hacia legítimo")).toBeInTheDocument();
  });

  it("renders nothing when contributions is null", () => {
    const { container } = render(<ShapAttributionCard contributions={null} />);
    expect(container.firstChild).toBeNull();
    expect(
      screen.queryByText("Atribución SHAP"),
    ).not.toBeInTheDocument();
  });

  it("renders nothing when contributions is an empty array", () => {
    const { container } = render(<ShapAttributionCard contributions={[]} />);
    expect(container.firstChild).toBeNull();
    expect(
      screen.queryByText("Atribución SHAP"),
    ).not.toBeInTheDocument();
  });

  it("rows have responsive stacking classes (flex-col sm:flex-row)", () => {
    const contributions: ShapContribution[] = [
      { feature: "amount", contribution: 35 },
    ];
    render(<ShapAttributionCard contributions={contributions} />);
    const li = document.querySelector("ul li");
    expect(li).toBeTruthy();
    expect(li!.className).toContain("flex-col");
    expect(li!.className).toContain("sm:flex-row");
  });

  it("label has truncate class and title attribute", () => {
    const contributions: ShapContribution[] = [
      { feature: "amount", contribution: 35 },
    ];
    render(<ShapAttributionCard contributions={contributions} />);
    const label = screen.getByText("Monto");
    expect(label).toHaveClass("truncate");
    expect(label).toHaveAttribute("title", "Monto");
  });
});
