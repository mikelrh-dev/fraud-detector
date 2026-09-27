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
  cn,
  type ButtonVariant,
  type ButtonSize,
} from "./ui";

/**
 * The expected key sets, pinned as literals.
 *
 * Typed against the derived unions, so this array is checked in BOTH
 * directions by `tsc`: a key deleted from the object leaves a literal that no
 * longer type-checks, and a key ADDED leaves the runtime `toEqual` below
 * failing. Adding a variant is therefore a deliberate act: the compiler and
 * the test both stop you until this list is updated on purpose.
 */
const EXPECTED_VARIANTS: readonly ButtonVariant[] = [
  "primary",
  "secondary",
  "ghost",
  "danger",
];
const EXPECTED_SIZES: readonly ButtonSize[] = ["sm", "md"];

const RAW_CHROME_PALETTE = /\b(red|rose|green|amber|emerald)-\d/;

describe("ui class constants", () => {
  it("focus ring uses focus-visible, never focus:", () => {
    expect(FOCUS_RING).toContain("focus-visible:ring-2");
    // A bare `focus:` shows the ring on mouse click, which is the defect the
    // audit found at 9 sites.
    expect(FOCUS_RING).not.toMatch(/(^|\s)focus:(?!-)/);
  });

  it("focus ring targets the focus-ring token, not a raw colour", () => {
    expect(FOCUS_RING).toContain("ring-focus-ring");
    expect(FOCUS_RING).not.toMatch(/ring-(red|blue|slate)-\d/);
  });

  it("button variant and size key sets are exactly the pinned list", () => {
    expect([...Object.keys(BTN_VARIANTS)].sort()).toEqual(
      [...EXPECTED_VARIANTS].sort(),
    );
    expect([...Object.keys(BTN_SIZES)].sort()).toEqual([...EXPECTED_SIZES].sort());
  });

  it("button base carries touch-action and the motion class", () => {
    expect(BTN_BASE).toContain("btn-motion");
    expect(BTN_BASE).toContain("touch-manipulation");
    expect(BTN_BASE).toContain(FOCUS_RING);
  });

  it("only the variants DESIGN.md calls action-bearing carry the accent", () => {
    // A secondary or ghost button that hovered to the accent colour would read
    // as the primary action, which is the V-07 class of defect. Iterated over
    // the object rather than naming variants, so a fifth variant added later
    // cannot slip past this check.
    //
    // `danger` IS action-bearing: DESIGN.md says "Danger: same as primary
    // (this product's primary action IS risky)", so it is deliberately in the
    // set rather than exempted from it.
    const ACCENT_BEARING = new Set(["primary", "danger"]);
    for (const [name, classes] of Object.entries(BTN_VARIANTS)) {
      if (ACCENT_BEARING.has(name)) {
        expect(classes, `variant ${name} must use the accent background`).toContain(
          "bg-accent",
        );
        expect(classes, `variant ${name} must use the action hover`).toContain(
          "enabled:hover:bg-action-hover",
        );
      } else {
        expect(classes, `variant ${name} must not use bg-accent`).not.toContain(
          "bg-accent",
        );
        expect(classes, `variant ${name} must not borrow the action hover`).not.toContain(
          "action-hover",
        );
      }
    }
  });

  it("no variant's hover fires while the button is disabled", () => {
    // `BTN_BASE` sets `disabled:opacity-50`, so a disabled control is visibly
    // inert — but a bare `hover:` still swapped its background under the
    // cursor, which reads as "pressable". `enabled:hover:` gates it to the
    // enabled state only.
    for (const [name, classes] of Object.entries(BTN_VARIANTS)) {
      expect(classes, `variant ${name} must not carry a bare hover:`).not.toMatch(
        /(^|\s)hover:/,
      );
      expect(classes, `variant ${name} must react to hover`).toMatch(
        /(^|\s)enabled:hover:/,
      );
    }
  });

  it("secondary is transparent with a border, not a filled surface", () => {
    // DESIGN.md (Buttons) and the live button at LoginPage.tsx:165 agree:
    // transparent background, slate-700 border, hover fills slate-800. A
    // filled slate-800 surface with a hover DARKER than its own rest state
    // inverted both.
    expect(BTN_VARIANTS.secondary).toContain("bg-transparent");
    expect(BTN_VARIANTS.secondary).toContain("border-slate-700");
    expect(BTN_VARIANTS.secondary).toContain("text-slate-300");
    expect(BTN_VARIANTS.secondary).toContain("enabled:hover:bg-slate-800");
    expect(BTN_VARIANTS.secondary).not.toContain("bg-slate-800 ");
  });

  it("ghost is text-only and changes the TEXT on hover, not the background", () => {
    // DESIGN.md: "text only, slate-400, hover text slate-100". Giving ghost a
    // background made it an unregistered secondary.
    expect(BTN_VARIANTS.ghost).toContain("text-slate-400");
    expect(BTN_VARIANTS.ghost).toContain("enabled:hover:text-slate-100");
    expect(BTN_VARIANTS.ghost).not.toMatch(/bg-/);
    expect(BTN_VARIANTS.ghost).not.toContain("border");
  });

  it("danger is the primary treatment, per DESIGN.md — not a lighter red", () => {
    // DESIGN.md: "Danger: same as primary (this product's primary action IS
    // risky)". So danger and primary are intentionally the same tokens.
    //
    // This replaced a previous attempt that gave danger its own risk-family
    // hover token. That token resolved to #dc2626 — byte-identical to
    // --color-accent — so HOVERING a destructive button landed on the exact
    // rest colour of a primary one, which is a sharper V-07 than the one it was
    // meant to fix. Minting a second red ramp to express "risky" was the
    // mistake; the design system already decided the answer.
    expect(BTN_VARIANTS.danger).toBe(BTN_VARIANTS.primary);

    // A destructive control must never read as weaker than the action beside
    // it, and `bg-risk-critical` (#ef4444) is LIGHTER than `bg-accent`
    // (#dc2626). Guard the value, not just the class name, so swapping the
    // token back cannot pass unnoticed.
    expect(BTN_VARIANTS.danger).not.toContain("risk-critical");
  });

  it("no variant reaches for a raw risk or accent palette value", () => {
    // The match is on the COLOUR, not the `(bg|text)-` prefix, so a raw value
    // smuggled in through `border-`, `ring-`, `divide-`, `fill-` or
    // `placeholder-` is caught too — the old prefix alternation only policed
    // two of those five.
    // Only the *semantic* families are token-first. `slate` is deliberately
    // NOT in this list: neutral surface chrome legitimately uses the slate
    // palette across this codebase (TABLE_HEADER_BASE, the table cells, the
    // existing components), and minting slate tokens is a separate change with
    // a much wider blast radius. What must never appear is a raw red/green/
    // amber, because those collide with the risk tones and are how V-07
    // happened.
    for (const [name, classes] of Object.entries(BTN_VARIANTS)) {
      const raw = classes.match(RAW_CHROME_PALETTE);
      expect(raw?.[0] ?? null, `variant ${name} uses raw ${raw?.[0]}`).toBeNull();
    }
  });

  it("no size reaches for a raw risk or accent palette value", () => {
    for (const [name, classes] of Object.entries(BTN_SIZES)) {
      expect(classes.match(RAW_CHROME_PALETTE), `size ${name}`).toBeNull();
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

  it("label stacks above its input and never wears an error colour", () => {
    // The invariant that matters is structural, not cosmetic: a label is a
    // block above an input. Drop `block` and the label and its input share a
    // line. The colour guard is what stops a copy-paste from turning every
    // label in the product into an error message.
    expect(FIELD_LABEL.split(" ")).toContain("block");
    expect(FIELD_LABEL).not.toMatch(/risk-critical/);
    expect(FIELD_LABEL).not.toMatch(RAW_CHROME_PALETTE);
  });

  it("hint is muted, not an error colour", () => {
    expect(FIELD_HINT).toContain("text-slate-500");
    expect(FIELD_HINT).not.toContain("risk-critical");
  });

  it("hint and error are told apart by colour alone, same size for both", () => {
    // Both sit at text-xs under a field; colour is the ONLY channel carrying
    // "this is wrong" vs "this is optional", so the colour is the invariant
    // that must hold. Asserting that both contain `text-xs` proved the shared
    // half and would have passed even if the two constants were byte-identical
    // — the exact copy-paste failure the rule exists to catch. So: the classes
    // must differ, and the ONLY differences must be the two text colours.
    const error = FIELD_ERROR.split(" ").filter(Boolean);
    const hint = FIELD_HINT.split(" ").filter(Boolean);

    expect(error).not.toEqual(hint);

    const errorOnly = error.filter((c) => !hint.includes(c));
    const hintOnly = hint.filter((c) => !error.includes(c));
    const shared = error.filter((c) => hint.includes(c));

    expect(errorOnly, "error differs from hint by exactly one class").toHaveLength(1);
    expect(hintOnly, "hint differs from error by exactly one class").toHaveLength(1);
    expect(errorOnly[0]).toBe("text-risk-critical");
    expect(hintOnly[0]).toBe("text-slate-500");

    // Same size is deliberate: the pair reads as one system, and a size change
    // would make a hint look like a different kind of message.
    expect(shared).toContain("text-xs");
  });
});

describe("cn", () => {
  it("joins fragments with a single space", () => {
    expect(cn("a", "b")).toBe("a b");
    expect(cn("a", "b", "c")).toBe("a b c");
  });

  it("drops falsy entries so conditional classes need no template strings", () => {
    expect(cn("a", false, "b")).toBe("a b");
    expect(cn("a", null, "b")).toBe("a b");
    expect(cn("a", undefined, "b")).toBe("a b");
    expect(cn("a", false && "b", null, undefined, "")).toBe("a");
  });

  it("returns an empty string for no input", () => {
    expect(cn()).toBe("");
    expect(cn(false, null, undefined, "")).toBe("");
  });

  it("does not leave a leading, trailing or doubled separator", () => {
    // The whole point of routing the join through one helper: hand-rolled
    // `[a, cond && b].filter(Boolean).join(" ")` copies are where an unguarded
    // separator leaks in as a stray double space.
    expect(cn("a", false, false, "b")).toBe("a b");
    expect(cn("", "a")).toBe("a");
    expect(cn("a", "")).toBe("a");
  });

  it("flattens nested fragments", () => {
    // Variant maps are objects of strings, so a caller holding a map needs to
    // be able to spread it in. A signature that only took `string` made
    // `cn(BTN_VARIANTS[variant])` a type error and pushed every call site
    // toward a hand-rolled `[...].filter().join()`.
    expect(cn("a", { b: "x", c: "y" })).toBe("a x y");
    expect(cn(["a", "b"], "c")).toBe("a b c");
    expect(cn("a", { b: false, c: "y" })).toBe("a y");
  });
});
