import { describe, it, expect } from "vitest";
import {
  FOCUS_RING,
  BTN_BASE,
  BTN_VARIANTS,
  BTN_SIZES,
  INPUT_BASE,
  FIELD_LABEL,
  FIELD_ERROR,
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
});
