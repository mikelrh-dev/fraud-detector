import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import App from "../App";
import { MAIN_LANDMARK_ID } from "../lib/focusable";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

/**
 * The skip link. Three claims, and each one has a failure mode that a weaker
 * test would wave through:
 *
 *  1. IT IS THE FIRST TABBLE. Not "it exists", and not "it is near the top of
 *     the file". A skip link that is rendered but is second in the tab order is
 *     not a skip link: the user has already tabbed through the navigation to
 *     reach it, which is the cost it exists to avoid. `user.tab()` walks the
 *     real tab order, so this is not a proxy for it.
 *
 *  2. IT IS VISIBLE WHEN FOCUSED. Clipping is a CSS question and vitest runs
 *     with `css: false`, so jsdom has no stylesheet and no layout:
 *     `toBeVisible()` would happily pass on a link that is 1px wide and
 *     invisible, and so would an assertion on the class name alone — the class
 *     is on the element whether or not the rule that uses it exists. So the
 *     reveal is asserted where it is authored, in `index.css`.
 *
 *  3. ACTIVATING IT MOVES FOCUS. `href="#main"` alone is not enough to write
 *     this test — jsdom implements fragment navigation (it updates the hash) but
 *     does not move focus, which is exactly why `SkipLink` also calls `focus()`
 *     on the target explicitly. Asserting `document.activeElement` is the whole
 *     point: the landmark is a skip target, so focus has to be there afterwards,
 *     not merely the URL.
 *
 * The assertions use CLASS LITERALS, never a class imported from `lib/ui.ts`.
 * Comparing a className against the constant that produced it is a tautology:
 * mutate the constant and both sides of the assertion move together while the
 * design changes underneath.
 *
 * ROUTES CHOSEN: `/transactions` (sidebar shell, the case where a link placed
 * inside a page would NOT be first), `/login` (the auth split shell, which has
 * no sidebar and proves the link is above the routes rather than inside either
 * shell) and `/dashboard` (the chart shell). The dashboard used to be skipped
 * here because recharts' `ResponsiveContainer` needs a `ResizeObserver` stub
 * that this file did not install, and the chart then threw into the route
 * boundary. That stub moved to `src/tests/setup.ts` in 252d942 — infrastructure
 * belongs in the setup, not in whichever test first needed it — so the reason
 * for the exclusion expired and the route was added rather than the excuse
 * quietly refreshed. Verified before adding it: the first Tab at `/dashboard`
 * lands on the link and the route boundary does not fire.
 *
 * NOTE ON TAILWIND AND THIS FILE: naming a Tailwind class in a source comment
 * is enough for the build to EMIT a rule for it — the scanner reads raw text,
 * comments included, which has already backfired in this repo once. Every class
 * named below is one the component really uses, so nothing here manufactures a
 * dead rule.
 */

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function authState() {
  return {
    user: { id: "test-user-id", role: "analista" },
    logout: vi.fn(),
    isAuthenticated: true,
    token: "mock-token",
    refreshToken: null,
    login: vi.fn(),
    setTokens: vi.fn(),
  };
}

function renderAppAt(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeAll(async () => {
  await Promise.all([
    import("../pages/TransactionsPage"),
    import("../pages/LoginPage"),
    import("../pages/DashboardPage"),
  ]);
}, 120_000);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = authState();
      return selector ? selector(state) : state;
    },
  );
});

function skipLink() {
  return screen.getByRole("link", { name: "Saltar al contenido" });
}

describe("skip link", () => {
  it("is the first element focus reaches, past the sidebar", async () => {
    // The authenticated shell puts a seven-item nav in the document BEFORE the
    // page content, so this is the case where a skip link living inside a page
    // would fail. `user.tab()` walks the real tab order rather than a proxy for
    // it, and there is no positive tabindex anywhere in the tree, so DOM order
    // IS the tab order here.
    const user = userEvent.setup();
    renderAppAt("/transactions");
    await screen.findByRole("heading", { name: "Transacciones" });

    await user.tab();

    expect(document.activeElement).toBe(skipLink());
  });

  it("is the first element focus reaches on the auth shell too", async () => {
    // Different shell, no sidebar — which is the point. If the link were
    // rendered by a page or by one shell, it would not be first here.
    const user = userEvent.setup();
    renderAppAt("/login");
    await screen.findByRole("heading", { name: "Iniciar sesión" });

    await user.tab();

    expect(document.activeElement).toBe(skipLink());
  });

  it("is the first element focus reaches on the chart shell too", async () => {
    // The third shell, added once the ResizeObserver stub moved into the
    // setup. `/transactions` and `/login` already cover the two orderings
    // that matter — nav before content, and no nav at all — so this is
    // coverage rather than a new claim: it is a third shell, and a skip link
    // that regressed on exactly one of them would be a shell-specific bug.
    const user = userEvent.setup();
    renderAppAt("/dashboard");
    await screen.findByRole("heading", { name: "Dashboard de detección de fraude" });

    await user.tab();

    expect(document.activeElement).toBe(skipLink());
  });

  it("carries the class the reveal rule is written against", () => {
    renderAppAt("/transactions");
    expect(skipLink().className).toContain("skip-link");
  });

  it("declares a reveal in the stylesheet, because jsdom loads none", () => {
    // WHY READ THE CSS: vitest runs with `css: false`, so no stylesheet reaches
    // jsdom and `toBeVisible()` passes on a link that is 1px wide and clipped.
    // A class-presence assertion has exactly the same blind spot — the class is
    // on the element whether or not the rule that uses it exists. Deleting the
    // `:focus` block below would leave every other assertion in this file green.
    // `index.css` is the one place the reveal is authored, so it is the one
    // place that can be asked about it.
    //
    // Read as TEXT, not parsed: the point is that the declarations exist and
    // that they are the revealing ones, and a regex over the source is enough.
    // `process.cwd()` rather than `import.meta.url`: under vitest's jsdom
    // environment `import.meta.url` is an http URL, so `new URL(..., base)`
    // throws ERR_INVALID_URL_SCHEME. cwd is the vite root, which is where
    // index.css lives.
    const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

    const rest = css.match(/\.skip-link\s*\{([^}]*)\}/)?.[1] ?? "";
    const focus = css.match(/\.skip-link:focus\s*\{([^}]*)\}/)?.[1] ?? "";

    // Clipped at rest — otherwise it is a stray control at the top of every
    // page, and a link that is only ever visible is not a skip link.
    expect(rest).toContain("clip-path: inset(50%)");
    expect(rest).toMatch(/width: 1px/);
    // Revealed on focus, on the BARE `:focus` state and not `:focus-visible`:
    // a link reached by an assistive technology or by a programmatic
    // `element.focus()` misses the focus-visible heuristic, and a 1px invisible
    // link the user is sitting on is the worst outcome this component has.
    expect(focus).toContain("clip-path: none");
    expect(focus).toMatch(/width: auto/);
    expect(css).not.toContain(".skip-link:focus-visible");
    // ONE state declares the position and the other declares none, so there is
    // no second declaration of `position` to compete with the first — which is
    // the whole reason the geometry is hand-written instead of three utilities
    // that each set it. The assertion is deliberately asymmetric: `rest` must
    // declare `position: fixed`, and `focus` must declare NO `position` at
    // all. An earlier version of this comment claimed "both states declare the
    // same positioning", which the line below it disproves.
    expect(rest).toMatch(/position: fixed/);
    expect(focus).not.toMatch(/position:/);
  });

  it("wears the same focus ring as every other control", () => {
    renderAppAt("/transactions");
    const link = skipLink();
    // Tailwind-spelled literals, not a comparison against FOCUS_RING: the point
    // is what ships. A test that rebuilt the expected class from the constant
    // would move both sides when the constant changed.
    expect(link.className).toContain("focus:ring-focus-ring");
    expect(link.className).toContain("focus:ring-2");
  });

  it("moves focus onto the main landmark when activated", async () => {
    const user = userEvent.setup();
    renderAppAt("/transactions");
    await screen.findByRole("heading", { name: "Transacciones" });

    const main = document.getElementById(MAIN_LANDMARK_ID);
    expect(main).not.toBeNull();

    await user.tab();
    expect(document.activeElement).toBe(skipLink());

    await user.click(skipLink());

    // The claim, not a proxy for it: after activating, focus is ON the
    // landmark. It is also focusable without being a tab stop, otherwise
    // skipping to it would just move the problem one step down.
    expect(document.activeElement).toBe(main);
    expect(main).toHaveAttribute("tabindex", "-1");
  });

  it("leaves the landmark out of the tab order, so skipping is one stop not two", async () => {
    const user = userEvent.setup();
    renderAppAt("/transactions");
    await screen.findByRole("heading", { name: "Transacciones" });

    await user.tab();
    await user.click(skipLink());
    await user.tab();

    // Tab again from the landmark and the next stop must be a real control
    // inside the content, not the landmark we are already sitting on.
    expect(document.activeElement).not.toBe(
      document.getElementById(MAIN_LANDMARK_ID),
    );
    expect(document.activeElement).not.toBe(document.body);
  });

  it("keeps a real href, for middle-click and for a browser without JS", async () => {
    const user = userEvent.setup();
    renderAppAt("/login");
    await screen.findByRole("heading", { name: "Iniciar sesión" });

    // The handler is what moves focus in jsdom; the href is what makes the link
    // a LINK. Without it there is no fragment to copy, no status-bar URL, and
    // nothing works if the bundle fails to load.
    expect(skipLink()).toHaveAttribute("href", `#${MAIN_LANDMARK_ID}`);

    await user.click(skipLink());
    expect(document.activeElement).toBe(
      document.getElementById(MAIN_LANDMARK_ID),
    );
  });
});
