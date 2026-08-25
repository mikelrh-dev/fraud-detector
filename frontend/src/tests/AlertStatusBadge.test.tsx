import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { AlertStatusBadge } from "../components/AlertStatusBadge";

describe("AlertStatusBadge", () => {
  it("open maps to the warn tone (risk-warn)", () => {
    const { container, getByText } = render(<AlertStatusBadge status="open" />);
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("bg-risk-warn/10");
    expect(pill.className).toContain("border-risk-warn/30");
    expect(pill.className).toContain("text-risk-warn");
    expect(getByText("Abierta")).toBeTruthy();
  });

  it("reviewed maps to the info tone (status-info)", () => {
    const { container, getByText } = render(
      <AlertStatusBadge status="reviewed" />,
    );
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("bg-status-info/10");
    expect(pill.className).toContain("border-status-info/30");
    expect(pill.className).toContain("text-status-info");
    expect(getByText("Revisada")).toBeTruthy();
  });

  it("resolved maps to the clean tone (risk-clean)", () => {
    const { container, getByText } = render(
      <AlertStatusBadge status="resolved" />,
    );
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("bg-risk-clean/10");
    expect(pill.className).toContain("border-risk-clean/30");
    expect(pill.className).toContain("text-risk-clean");
    expect(getByText("Resuelta")).toBeTruthy();
  });

  it("unknown status falls back to neutral slate styling with raw label", () => {
    const { container, getByText } = render(
      <AlertStatusBadge status="mystery" />,
    );
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("bg-slate-800");
    expect(pill.className).toContain("text-slate-400");
    expect(getByText("mystery")).toBeTruthy();
  });
});
