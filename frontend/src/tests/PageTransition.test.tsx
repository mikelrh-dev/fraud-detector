import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { PageTransition } from "../components/PageTransition";

/**
 * Harness that mounts at /first and, whenever `target` differs, hard-navigates
 * there through <Navigate>. This drives real location changes through the
 * router so the keyed remount behavior of PageTransition is exercised.
 */
function Harness({ target }: { target: string }) {
  const page = (testId: string) => (
    <PageTransition>
      <span data-testid={testId}>content</span>
    </PageTransition>
  );

  return (
    <MemoryRouter initialEntries={["/first"]}>
      <Routes>
        <Route
          path="/first"
          element={
            target === "/first" ? (
              page("page-first")
            ) : (
              <Navigate to={target} replace />
            )
          }
        />
        <Route
          path="/second"
          element={target === "/second" ? page("page-second") : null}
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("PageTransition", () => {
  it("wraps page content in an animated transition wrapper", () => {
    render(<Harness target="/first" />);
    const wrapper = screen.getByTestId("page-transition");
    expect(wrapper.className).toContain("animate-fade-slide-up");
    expect(screen.getByTestId("page-first")).toBeInTheDocument();
  });

  it("remounts the wrapper when the pathname changes (animation replays)", () => {
    const { rerender } = render(<Harness target="/first" />);
    const firstWrapper = screen.getByTestId("page-transition");

    rerender(<Harness target="/second" />);

    const secondWrapper = screen.getByTestId("page-transition");
    expect(secondWrapper).not.toBe(firstWrapper);
    expect(secondWrapper.className).toContain("animate-fade-slide-up");
    expect(screen.getByTestId("page-second")).toBeInTheDocument();
  });

  it("keeps the same wrapper instance when the pathname is unchanged", () => {
    const ui = (
      <section>
        <Harness target="/first" />
      </section>
    );
    const { rerender } = render(ui);
    const wrapperBefore = screen.getByTestId("page-transition");

    // Identical tree shape + identical pathname: the key must stay put and
    // React must reconcile (not remount) the transition wrapper.
    rerender(ui);

    expect(screen.getByTestId("page-transition")).toBe(wrapperBefore);
  });
});
