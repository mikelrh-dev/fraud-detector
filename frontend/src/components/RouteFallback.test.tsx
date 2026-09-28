import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RouteFallback } from "./RouteFallback";
import { expectCarries } from "../test-utils/className";

/**
 * Plain DOM assertions, not jest-dom matchers.
 *
 * `tsconfig.json` excludes `src/tests`, so the jest-dom matcher types are
 * invisible to any file under `src/components` (see Button.test.tsx for the
 * same reason). Asserting on the DOM directly keeps the build honest instead
 * of widening `tsconfig` to fit a test.
 *
 * Every assertion below is falsifiable against the implementation: delete the
 * attribute, the class or the wrapper and the matching test goes red. None of
 * them re-derives the answer from an imported constant, which would only prove
 * the constant equals itself.
 */
function allClasses(root: HTMLElement): string[] {
  return Array.from(root.querySelectorAll<HTMLElement>("*")).flatMap((el) =>
    Array.from(el.classList),
  );
}

describe("RouteFallback", () => {
  it("is a polite live region, so a route transition is not a silent wait", () => {
    render(<RouteFallback />);

    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-live")).toBe("polite");
  });

  it("carries an accessible name — an unlabelled spinner announces nothing", () => {
    render(<RouteFallback />);

    // `role="status"` takes its name from the author, never from its contents,
    // so this only passes because `aria-label` is really on the element. Strip
    // it and the query fails.
    const status = screen.getByRole("status", { name: "Cargando página" });
    expect(status).not.toBeNull();
  });

  it("leaves the visible copy IN the accessibility tree, because the region announces by content", () => {
    render(<RouteFallback />);

    // This inverted. The previous version asserted the copy was `aria-hidden`,
    // on the reasoning that the region's `aria-label` is the name source so the
    // text would otherwise be "said twice". That is wrong: a live region is
    // announced by its CONTENT, and `aria-label` names it for a name-and-role
    // query without becoming the announcement text. With every text node hidden,
    // a screen reader announcing by content had nothing to say -- the region was
    // well named and mute.
    //
    // One string, no duplication, and the announcement has content: the text is
    // both the visible copy and the announced copy.
    const visible = screen.getByText("Cargando página…");
    expect(visible.closest("[aria-hidden='true']")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Cargando página");
  });

  it("reserves the same surface the page it replaces occupies", () => {
    // No layout jump: every page root in the app is `min-h-screen` over
    // `slate-950` (`bg-page-bg` is the same colour under its token name, and
    // the auth layout is `min-h-dvh`, which is >= this). Remove `min-h-screen`
    // and the fallback collapses to the spinner, so the page body changes
    // height on arrival.
    render(<RouteFallback />);

    expectCarries(screen.getByRole("status"), "min-h-screen bg-slate-950");
    expect(allClasses(document.body)).toEqual(
      expect.arrayContaining(["flex", "items-center", "justify-center"]),
    );
  });

  it("keeps the busy animation, and relies on the global reduced-motion guard", () => {
    render(<RouteFallback />);

    const spinner = document.querySelector(".animate-spin");
    expect(spinner).not.toBeNull();

    // The opt-out is NOT at the call site. The global `prefers-reduced-motion`
    // guard in index.css covers `animate-spin` for every spinner in the product,
    // so a per-call-site class would be dead weight -- and this test previously
    // PINNED that dead weight on a comment asserting the global guard was
    // incomplete, which is exactly the kind of self-justifying test that keeps
    // redundancy alive after its reason has expired.
    //
    // What replaces it is the assertion that the spinner is decoration: it is
    // aria-hidden, so assistive tech is not told about a spinning ring, while
    // the label text beside it stays readable. A live region is announced by its
    // content, so hiding that content would leave the region well named and
    // mute.
    expect(spinner!.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("status").textContent).toContain("Cargando");
  });

  it("uses no risk or accent colour — a loading indicator is not a fraud state", () => {
    const { container } = render(<RouteFallback />);

    // DESIGN.md: `risk-*` is reserved for fraud semantics and `accent` is
    // reserved for brand actions, "never use accent to color data or badges".
    // Repaint the sweep with `border-t-risk-critical` and this goes red.
    const reserved = allClasses(container).filter(
      (cls) =>
        cls.includes("risk-") ||
        cls.includes("accent") ||
        cls.includes("action-hover") ||
        cls.includes("fraud-"),
    );
    expect(reserved).toEqual([]);
  });
});
