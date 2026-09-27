import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { RiskMeter } from "../components/RiskMeter";

/**
 * V-02 regression: `classificationToTone` returned `clean` for anything it did
 * not recognise, so a pending or unknown classification drew a confident GREEN
 * bar — a "safe" colour wrapped around a state nobody had determined.
 *
 * Score-derived tone is unchanged: `riskTone` bands purely on the number, and a
 * low score legitimately is clean.
 */
describe("RiskMeter classification tone", () => {
  const fillClass = (props: { value: number; classification?: string }) => {
    // Scoped to this render's container: the loop test below mounts several
    // meters, and an unscoped getByTestId would find all of them.
    const { container } = render(<RiskMeter {...props} />);
    return container.querySelector('[data-testid="risk-meter-fill"]')!.className;
  };

  it("renders a green fill for a low score with no classification", () => {
    expect(fillClass({ value: 10 })).toContain("bg-risk-clean");
  });

  it("renders amber for review", () => {
    expect(fillClass({ value: 10, classification: "review" })).toContain(
      "bg-risk-warn",
    );
  });

  it("renders red for fraud", () => {
    expect(fillClass({ value: 10, classification: "fraud" })).toContain(
      "bg-risk-critical",
    );
  });

  it("does NOT render green for a pending classification", () => {
    const cls = fillClass({ value: 10, classification: "pending" });
    expect(cls).not.toContain("bg-risk-clean");
  });

  it("does NOT render green for an unknown classification", () => {
    for (const unknown of ["mystery", "FRAUD", "approved"]) {
      const cls = fillClass({ value: 10, classification: unknown });
      expect(cls, `classification=${JSON.stringify(unknown)}`).not.toContain(
        "bg-risk-clean",
      );
    }
  });

  it("treats an empty classification as 'not provided' and bands on score", () => {
    // `classification` is an optional override: only a non-empty value replaces
    // the score band. Pinned here so the behaviour is intentional rather than
    // an accident of truthiness — an empty string means "no classification
    // supplied", not "a classification I do not recognise".
    expect(fillClass({ value: 10, classification: "" })).toContain(
      "bg-risk-clean",
    );
  });

  it("uses the neutral slate fill for unknown classifications", () => {
    expect(fillClass({ value: 10, classification: "pending" })).toContain(
      "bg-slate-600",
    );
  });

  it("still bands on the score when the classification is legitimate", () => {
    // A known classification takes precedence over the score band.
    expect(
      fillClass({ value: 99, classification: "legitimate" }),
    ).toContain("bg-risk-clean");
  });

  it("keeps aria-valuenow consistent with the clamped value", () => {
    const { getByTestId } = render(
      <RiskMeter value={150} classification="pending" />,
    );
    expect(getByTestId("risk-meter").getAttribute("aria-valuenow")).toBe("100");
  });
});
