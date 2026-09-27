import { describe, it, expect } from "vitest";
import {
  FOCUS_RING,
  BTN_BASE,
  BTN_VARIANTS,
  BTN_SIZES,
  INPUT_BASE,
  FIELD_LABEL,
  FIELD_ERROR,
  FIELD_HINT,
} from "./ui";

describe("ui class constants", () => {
  it("focus ring uses focus-visible, never focus:", () => {
    expect(FOCUS_RING).toContain("focus-visible:ring-2");
    // A bare `focus:` shows the ring on mouse click, which is the defect the
    // audit found repeated 15 times.
    expect(FOCUS_RING).not.toMatch(/(^|\s)focus:(?!-)/);
  });

  it("focus ring targets the focus-ring token, not a raw colour", () => {
    expect(FOCUS_RING).toContain("ring-focus-ring");
    expect(FOCUS_RING).not.toMatch(/ring-(red|blue|slate)-\d/);
  });

  it("every button variant and size has a class", () => {
    for (const [name, classes] of Object.entries(BTN_VARIANTS)) {
      expect(classes, `variant ${name}`).toBeTruthy();
    }
    for (const [name, classes] of Object.entries(BTN_SIZES)) {
      expect(classes, `size ${name}`).toBeTruthy();
    }
  });

  it("button base carries touch-action and the motion class", () => {
    expect(BTN_BASE).toContain("btn-motion");
    expect(BTN_BASE).toContain("touch-manipulation");
    expect(BTN_BASE).toContain(FOCUS_RING);
  });

  it("only the primary variant uses the action tokens", () => {
    // A secondary or ghost button that hovered to the accent colour would read
    // as the primary action, which is the V-07 class of defect.
    expect(BTN_VARIANTS.primary).toContain("bg-accent");
    expect(BTN_VARIANTS.secondary).not.toContain("bg-accent");
    expect(BTN_VARIANTS.ghost).not.toContain("bg-accent");
  });

  it("danger hover is a real, distinct token — not the tone it sits on", () => {
    // `--color-risk-critical` is #ef4444, which IS red-500. A
    // `hover:bg-red-500` here rendered and changed nothing: a destructive
    // control with an invisible hover. The hover must be its own token.
    expect(BTN_VARIANTS.danger).toContain("hover:bg-risk-critical-hover");
    expect(BTN_VARIANTS.danger).not.toMatch(/hover:bg-(red|rose)-\d/);
    // And it must not borrow the accent family's hover, which is a different
    // semantic family (DESIGN.md keeps risk and accent independent).
    expect(BTN_VARIANTS.danger).not.toContain("action-hover");
  });

  it("no variant reaches for a raw risk or accent palette value", () => {
    // Only the *semantic* families are token-first. Neutral surface chrome is
    // still allowed to use the slate palette, because the rest of the codebase
    // (TABLE_HEADER_BASE, the table cells, the existing components) does, and
    // minting slate tokens is a separate change with a much wider blast radius.
    // What must never appear is a raw red/green/amber, because those collide
    // with the risk tones and are how V-07 happened.
    for (const [name, classes] of Object.entries(BTN_VARIANTS)) {
      const raw = classes.match(/(bg|text)-(red|rose|green|amber|emerald)-\d/);
      expect(raw?.[0] ?? null, `variant ${name} uses raw ${raw?.[0]}`).toBeNull();
    }
  });

  it("input base carries the focus ring", () => {
    expect(INPUT_BASE).toContain(FOCUS_RING);
    expect(INPUT_BASE).toContain("placeholder-slate-500");
  });

  it("field error uses the risk-critical token, not a raw red", () => {
    expect(FIELD_ERROR).toContain("text-risk-critical");
    expect(FIELD_ERROR).not.toMatch(/text-red-/);
  });

  it("label constant exists", () => {
    expect(FIELD_LABEL).toContain("text-slate-300");
  });

  it("hint constant exists and is muted, not an error colour", () => {
    expect(FIELD_HINT).toContain("text-slate-500");
    expect(FIELD_HINT).not.toContain("risk-critical");
  });

  it("hint and error are told apart by colour, not by size", () => {
    // Both sit at text-xs under a field; colour is the only channel carrying
    // "this is wrong" vs "this is optional". Same size keeps that legible.
    expect(FIELD_ERROR).toContain("text-xs");
    expect(FIELD_HINT).toContain("text-xs");
  });
});
