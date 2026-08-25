import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render } from "@testing-library/react";
import { RiskMeter } from "../components/RiskMeter";

describe("RiskMeter", () => {
  it("renders nothing when value is null", () => {
    const { container } = render(<RiskMeter value={null} />);
    expect(container.querySelector('[data-testid="risk-meter"]')).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("renders nothing when value is undefined", () => {
    const { container } = render(<RiskMeter value={undefined} />);
    expect(container.querySelector('[data-testid="risk-meter"]')).toBeNull();
    expect(container.textContent).toBe("");
  });

  it("clamps values above 100 to a full-width fill", () => {
    const { getByTestId } = render(<RiskMeter value={150} />);
    const fill = getByTestId("risk-meter-fill");
    expect(fill.style.width).toBe("100%");
  });

  it("clamps negative values to a zero-width fill", () => {
    const { getByTestId } = render(<RiskMeter value={-20} />);
    const fill = getByTestId("risk-meter-fill");
    expect(fill.style.width).toBe("0%");
  });

  it.each([
    [44.9, "bg-risk-clean"],
    [45, "bg-risk-warn"],
    [59.9, "bg-risk-warn"],
    [60, "bg-risk-critical"],
  ] as const)("tone boundary score=%s renders fill class %s", (score, expected) => {
    const { getByTestId } = render(<RiskMeter value={score} />);
    expect(getByTestId("risk-meter-fill").className).toContain(expected);
  });

  it("renders two threshold ticks at 45% and 60%", () => {
    const { getAllByTestId } = render(<RiskMeter value={50} />);
    const ticks = getAllByTestId("risk-meter-tick");
    expect(ticks).toHaveLength(2);
    expect(ticks[0].style.left).toBe("45%");
    expect(ticks[1].style.left).toBe("60%");
  });

  it("ticks use the shared slate-600/50 border color", () => {
    const { getAllByTestId } = render(<RiskMeter value={50} />);
    for (const tick of getAllByTestId("risk-meter-tick")) {
      expect(tick.className).toContain("border-slate-600/50");
    }
  });

  it("track uses the shared dark chrome (h-1.5 rounded-full bg-slate-800)", () => {
    const { getByTestId } = render(<RiskMeter value={10} />);
    const cls = getByTestId("risk-meter").className;
    expect(cls).toContain("h-1.5");
    expect(cls).toContain("rounded-full");
    expect(cls).toContain("bg-slate-800");
  });

  it("exposes meter semantics with the clamped value", () => {
    const { getByRole } = render(<RiskMeter value={72} />);
    const meter = getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("72");
    expect(meter.getAttribute("aria-valuemin")).toBe("0");
    expect(meter.getAttribute("aria-valuemax")).toBe("100");
  });

  it("component source has no hardcoded hex colors", () => {
    const src = readFileSync(
      join(process.cwd(), "src", "components", "RiskMeter.tsx"),
      "utf-8",
    );
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
