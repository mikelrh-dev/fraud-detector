import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render } from "@testing-library/react";
import { Badge, type BadgeTone } from "../components/Badge";

const TONES: BadgeTone[] = ["clean", "warn", "critical", "info"];

const EXPECTED_COLOR_TOKEN: Record<BadgeTone, string> = {
  clean: "risk-clean",
  warn: "risk-warn",
  critical: "risk-critical",
  info: "status-info",
};

describe("Badge primitive", () => {
  it.each(TONES)("tone=%s renders the semantic color token classes", (tone) => {
    const token = EXPECTED_COLOR_TOKEN[tone];
    const { container } = render(<Badge tone={tone}>X</Badge>);
    const pill = container.firstElementChild as HTMLElement;
    // /10 bg + border pattern per DESIGN.md badges contract
    expect(pill.className).toContain(`bg-${token}/10`);
    expect(pill.className).toContain(`border-${token}/30`);
    expect(pill.className).toContain(`text-${token}`);
  });

  it.each(TONES)("tone=%s contains zero hardcoded hex", (tone) => {
    const { container } = render(<Badge tone={tone}>X</Badge>);
    expect(container.innerHTML).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });

  it("renders children text", () => {
    const { getByText } = render(<Badge tone="clean">Legítimo</Badge>);
    expect(getByText("Legítimo")).toBeTruthy();
  });

  it("passes an icon glyph through the icon slot", () => {
    const { container } = render(
      <Badge tone="clean" icon="check_circle">
        Ok
      </Badge>,
    );
    const icon = container.querySelector(".material-symbols-outlined");
    expect(icon).toBeTruthy();
    expect(icon!.textContent).toBe("check_circle");
  });

  it("renders no icon slot when no icon is given", () => {
    const { container } = render(<Badge tone="warn">Sin icono</Badge>);
    expect(container.querySelector(".material-symbols-outlined")).toBeNull();
  });

  it("is a rounded-full pill", () => {
    const { container } = render(<Badge tone="info">Info</Badge>);
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("rounded-full");
    expect(pill.className).toContain("border");
  });

  it("tone=neutral renders slate fallback styling (unknown-state route)", () => {
    const { container } = render(<Badge tone="neutral">?</Badge>);
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("bg-slate-800");
    expect(pill.className).toContain("border-slate-700");
    expect(pill.className).toContain("text-slate-400");
  });

  it("source file has no hardcoded hex colors", () => {
    const src = readFileSync(
      join(process.cwd(), "src", "components", "Badge.tsx"),
      "utf-8",
    );
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
