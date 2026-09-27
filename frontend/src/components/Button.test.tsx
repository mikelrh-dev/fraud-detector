import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { FormEvent } from "react";
import { Button } from "./Button";
import { BTN_SIZES, BTN_VARIANTS } from "../lib/ui";

/** Token-wise comparison. A substring check on the whole class string would
 *  pass on a partial match and fail on a class that `className` legitimately
 *  interleaves; the contract is that every class in a fragment is present. */
function expectCarries(el: Element, fragment: string) {
  for (const cls of fragment.split(" ").filter(Boolean)) {
    expect(el.classList.contains(cls), `missing class ${cls}`).toBe(true);
  }
}

const variantNames = Object.keys(BTN_VARIANTS) as (keyof typeof BTN_VARIANTS)[];
const sizeNames = Object.keys(BTN_SIZES) as (keyof typeof BTN_SIZES)[];

/**
 * Plain DOM assertions, not jest-dom matchers.
 *
 * `tsconfig.json` excludes `src/tests`, so the jest-dom matcher types are
 * invisible to any file under `src/components`. Rather than widen the build to
 * fit a test, assert on the DOM directly — `getAttribute` returns the raw value
 * and `hasAttribute` distinguishes absent from empty, which is exactly the
 * distinction the aria-busy test needs anyway.
 */
function button(): HTMLButtonElement {
  return screen.getByRole("button") as HTMLButtonElement;
}

describe("Button primitive", () => {
  it("defaults to type=button, so it does not submit a form it sits in", () => {
    // The behavioural fix. A bare <button> in a form submits it, and a submit
    // button that was never meant to be live was live on CreateTransactionPage.
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button>Enviar</Button>
      </form>,
    );

    const target = button();
    expect(target.getAttribute("type")).toBe("button");

    fireEvent.click(target);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("honours type=submit passed through props — the spread must beat the default", () => {
    // The paired half of the test above. The default may be overridden, but
    // only from props: this fails if `{...rest}` ever lands before `type`.
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button type="submit">Enviar</Button>
      </form>,
    );

    const target = button();
    expect(target.getAttribute("type")).toBe("submit");

    fireEvent.click(target);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("forwards the rest of the button props, including event handlers", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick} name="accion" value="1" />);
    const target = button();
    expect(target.getAttribute("name")).toBe("accion");
    fireEvent.click(target);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("disabled prop disables the control", () => {
    render(<Button disabled>Guardar</Button>);
    expect(button().disabled).toBe(true);
  });

  it("loading disables the control and marks it busy", () => {
    render(<Button loading>Guardar</Button>);
    const target = button();
    expect(target.disabled).toBe(true);
    expect(target.getAttribute("aria-busy")).toBe("true");
  });

  it("loading also absorbs a click — a busy control is not a live one", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Guardar
      </Button>,
    );
    fireEvent.click(button());
    expect(onClick).not.toHaveBeenCalled();
  });

  it("not loading leaves aria-busy OFF the DOM, not set to false", () => {
    // Omitted rather than `aria-busy="false"`. Worth being precise about WHY,
    // because the obvious reason is wrong: absent and "false" are equivalent
    // to every screen reader -- `false` is the attribute's default, per the
    // ARIA spec. The real reason is DOM tidiness: this component is not
    // tracking a state it has no reason to advertise, so it writes nothing.
    render(<Button>Guardar</Button>);
    expect(button().hasAttribute("aria-busy")).toBe(false);
  });

  it("not loading carries no wait treatment", () => {
    render(<Button>Guardar</Button>);
    const target = button();
    expect(target.querySelector("[data-loading-spinner]")).toBeNull();
  });

  it("loading shows a spinner, which no cascade rule can kill", () => {
    // The previous treatment was `opacity-70 cursor-wait` on the button itself.
    // That is DEAD CSS: `loading` implies `disabled`, so `disabled:opacity-50`
    // (specificity 0-2-0) beats `opacity-70` (0-1-0), and
    // `disabled:cursor-not-allowed` beats `cursor-wait`. Verified with
    // getComputedStyle in a real engine: a loading button rendered
    // opacity=0.5 cursor=not-allowed — pixel-identical to a disabled one. The
    // user never saw the wait.
    //
    // A spinner is a separate element, so no `disabled:` rule competes for it.
    render(<Button loading>Guardar</Button>);
    const spinner = button().querySelector("[data-loading-spinner]");
    expect(spinner).not.toBeNull();
    expect(spinner!.getAttribute("aria-hidden")).toBe("true");
  });

  it("the wait state is never expressed as an opacity the disabled rule shadows", () => {
    // Guards the bug CLASS, not just this instance. jsdom does no cascade, so
    // a class-presence assertion cannot see that a style is shadowed; asserting
    // that no competing `opacity-*` is applied to the button is the closest
    // check available without a browser engine, and it fails loudly if someone
    // reintroduces the dead treatment.
    render(<Button loading>Guardar</Button>);
    const target = button();
    expect(target.className).not.toMatch(/(^|\s)opacity-\d/);
  });

  it("keeps its label while loading, so the button does not change width", () => {
    // DESIGN.md: "a non-changing label while loading, so the button width does
    // not shift." A label swap ("Guardar" -> "Procesando...") is a real layout
    // jump on a destructive-adjacent action. The spinner carries the state
    // instead; `aria-busy` carries it to assistive tech.
    render(<Button loading>Guardar</Button>);
    expect(button().textContent).toBe("Guardar");
  });

  it("defaults to the primary variant at the md size", () => {
    render(<Button>Guardar</Button>);
    expectCarries(button(), BTN_VARIANTS.primary);
    expectCarries(button(), BTN_SIZES.md);
  });

  it.each(variantNames)("variant %s reaches the DOM class list", (variant) => {
    // Iterated over the object, not a hand-written list: a variant added to
    // `ui.ts` is covered by the next run instead of being silently untested.
    render(<Button variant={variant}>Accion</Button>);
    expectCarries(button(), BTN_VARIANTS[variant]);
  });

  it.each(sizeNames)("size %s reaches the DOM class list", (size) => {
    render(<Button size={size}>Accion</Button>);
    expectCarries(button(), BTN_SIZES[size]);
  });

  it("applies exactly one variant and one size", () => {
    // Guards against the map-passing hazard `cn` refuses at compile time:
    // passing the whole variant map would put every variant's bg/text on the
    // element at once and let stylesheet order decide the render.
    render(
      <Button variant="secondary" size="sm">
        Accion
      </Button>,
    );
    const backgrounds = Array.from(button().classList).filter((c) =>
      c.startsWith("bg-"),
    );
    expect(backgrounds).toEqual(["bg-transparent"]);
  });

  it("merges a caller className instead of replacing the constants", () => {
    render(<Button className="w-full">Guardar</Button>);
    expectCarries(button(), "w-full");
    expectCarries(button(), BTN_VARIANTS.primary);
    expectCarries(button(), BTN_SIZES.md);
  });

  it("puts the caller's className after the constants, by convention", () => {
    // Not a CSS override — Tailwind resolves competing utilities by
    // STYLESHEET order, not attribute order. This pins the documented
    // "lands last" convention so a future refactor cannot quietly reverse it
    // and make the attribute unreadable.
    render(<Button className="w-full">Guardar</Button>);
    const { className } = button();
    expect(className.lastIndexOf("w-full")).toBeGreaterThan(
      className.lastIndexOf("rounded-lg"),
    );
  });

  it("renders children", () => {
    render(<Button>Guardar transaccion</Button>);
    expect(screen.getByRole("button", { name: "Guardar transaccion" })).toBeTruthy();
  });

  it("source file has no hardcoded hex colors", () => {
    const src = readFileSync(
      join(process.cwd(), "src", "components", "Button.tsx"),
      "utf-8",
    );
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });

  it("the variant class is present even when className conflicts with it", () => {
    // Documents the real behaviour rather than the hoped-for one: both
    // classes reach the DOM, and which one paints is decided by Tailwind's
    // stylesheet order. The primitive's job is to make that rare and visible,
    // not to pretend it is impossible.
    render(
      <Button variant="primary" className="bg-slate-800">
        Choque
      </Button>,
    );
    const cls = screen.getByRole("button").getAttribute("class") ?? "";
    expect(cls).toContain("bg-accent");
    expect(cls).toContain("bg-slate-800");
  });
});
