import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Input } from "./Input";
import { INPUT_BASE } from "../lib/ui";
import { expectCarries } from "../test-utils/className";


/** Plain DOM assertions, not jest-dom matchers — `tsconfig.json` excludes
 *  `src/tests`, so the matcher types are invisible under `src/components`.
 *  `getAttribute`/`hasAttribute` is also the only way to tell an absent
 *  attribute from an empty one, which is the point of half these tests. */
function input(): HTMLInputElement {
  return screen.getByRole("textbox") as HTMLInputElement;
}

const INVALID_BORDER = "aria-invalid:border-risk-critical";
const INVALID_RING = "aria-invalid:focus-visible:ring-risk-critical";

describe("Input primitive", () => {
  it("carries the shared INPUT_BASE chrome", () => {
    render(<Input placeholder="0.00" />);
    expectCarries(input(), INPUT_BASE);
  });

  it("not invalid leaves aria-invalid OFF the DOM, not set to false", () => {
    // Same reasoning as Button's `aria-busy`: `false` is the ARIA default, so
    // absent and "false" mean the same thing to a screen reader. The honest
    // reason is DOM tidiness — there is no invalid state to advertise.
    render(<Input />);
    expect(input().hasAttribute("aria-invalid")).toBe(false);
  });

  it("invalid marks the control and applies the risk border", () => {
    render(<Input invalid />);
    expect(input().getAttribute("aria-invalid")).toBe("true");
    expectCarries(input(), INVALID_BORDER);
  });

  it("the invalid treatment hangs off the ARIA attribute, not the prop", () => {
    // The single-signal claim. If this ever goes red, `Input` has grown a
    // second way to say "invalid" and the two can diverge — `Field` injects
    // only `aria-invalid`, so a prop-driven border would leave a control that
    // announces the error while looking perfectly valid.
    render(<Input aria-invalid="true" />);
    expectCarries(input(), INVALID_BORDER);
  });

  it("the invalid classes are always in the class list — the attribute gates them", () => {
    // Worth stating, because a class-list assertion is the only thing a unit
    // test in jsdom can see: both classes are present either way, and only
    // `[aria-invalid="true"]` lets them match. Their presence proves nothing
    // about the rendered state; the attribute does.
    render(<Input />);
    expectCarries(input(), `${INVALID_BORDER} ${INVALID_RING}`);
  });

  it("the risk treatment is always variant-gated, never painted unconditionally", () => {
    // jsdom runs no cascade, so a class assertion cannot see a rule that paints
    // unconditionally. This is the closest available check, and it is worth
    // having: a bare `border-risk-critical` would turn every valid field red,
    // and a bare `focus-visible:ring-risk-critical` would be the shadowed-rule
    // bug Button had. Any class naming the risk colour must sit behind
    // `aria-invalid:`.
    render(<Input />);
    const ungated = Array.from(input().classList).filter(
      (c) => c.includes("risk") && !c.startsWith("aria-invalid:"),
    );
    expect(ungated).toEqual([]);
  });

  it("a caller-supplied aria-invalid beats the invalid prop", () => {
    // Fails if `{...rest}` ever lands before `aria-invalid`. This is the
    // mechanism `Field` uses, so it is load-bearing, not incidental.
    render(<Input invalid aria-invalid="false" />);
    expect(input().getAttribute("aria-invalid")).toBe("false");
  });

  it("forwards the rest of the input props, including the describedby wiring", () => {
    const onChange = vi.fn();
    render(
      <Input
        id="amount"
        name="amount"
        type="number"
        required
        aria-describedby="amount-error"
        onChange={onChange}
      />,
    );
    // `type="number"` maps to spinbutton, not textbox — queried by its real
    // role so the test would still find the element if the type were dropped.
    const target = screen.getByRole("spinbutton") as HTMLInputElement;
    expect(target.getAttribute("id")).toBe("amount");
    expect(target.getAttribute("name")).toBe("amount");
    expect(target.getAttribute("type")).toBe("number");
    expect(target.hasAttribute("required")).toBe(true);
    expect(target.getAttribute("aria-describedby")).toBe("amount-error");

    fireEvent.change(target, { target: { value: "12" } });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("merges a caller className instead of replacing INPUT_BASE", () => {
    render(<Input className="uppercase" />);
    expectCarries(input(), INPUT_BASE);
    expectCarries(input(), "uppercase");
  });

  it("puts the caller's className after the constants, by convention", () => {
    // Not a CSS override — Tailwind resolves competing utilities by
    // STYLESHEET order. Same convention as Button, pinned so it cannot be
    // quietly reversed.
    render(<Input className="uppercase" />);
    const { className } = input();
    expect(className.lastIndexOf("uppercase")).toBeGreaterThan(
      className.lastIndexOf("rounded-lg"),
    );
  });

  it("source file has no hardcoded hex colors", () => {
    const src = readFileSync(
      join(process.cwd(), "src", "components", "Input.tsx"),
      "utf-8",
    );
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
