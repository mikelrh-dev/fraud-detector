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

  it("hides the visible copy from assistive tech, so the label is said once", () => {
    render(<RouteFallback />);

    // The string lives in the DOM for sighted users; the region's name is the
    // single source, so the visual cluster is aria-hidden rather than a second
    // announcement of the same sentence.
    const visible = screen.getByText("Cargando página…");
    expect(visible.closest("[aria-hidden='true']")).not.toBeNull();
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

  it("keeps the busy animation but opts out under prefers-reduced-motion", () => {
    render(<RouteFallback />);

    const spinner = document.querySelector(".animate-spin");
    expect(spinner).not.toBeNull();
    // DESIGN.md (Reduced-motion guarantee) says reduced-motion users get the
    // final state immediately. The global guard in index.css does not cover
    // `animate-spin`, so the opt-out has to be at the call site.
    expect(spinner!.classList.contains("motion-reduce:animate-none")).toBe(true);
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
