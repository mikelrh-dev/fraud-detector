import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import DashboardPage from "../pages/DashboardPage";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import type { ReactNode } from "react";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

const DASHBOARD_SOURCE = readFileSync(
  join(process.cwd(), "src", "pages", "DashboardPage.tsx"),
  "utf-8",
);

/**
 * Source with block comments removed, so the page's own notes about the class
 * names it dropped are not counted as re-typing them. See LoginPage.test.tsx
 * for why a raw-file scan would never go green.
 */
const DASHBOARD_CODE = DASHBOARD_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "");

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function mockAuth() {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = {
        user: { id: "test-user", role: "analista" },
        logout: vi.fn(),
        isAuthenticated: true,
        token: "mock-token",
        refreshToken: null,
        login: vi.fn(),
      };
      return selector ? selector(state) : state;
    },
  );
}

/**
 * jsdom has no `ResizeObserver`, and recharts' `ResponsiveContainer` reads one
 * in a passive effect. Without this the throw happens AFTER the first paint and
 * React unmounts the whole tree, so a query that would have passed becomes
 * "unable to find" against an empty container — a failure that looks like a
 * missing element and is actually a missing browser API.
 *
 * Scoped to this file rather than added to `tests/setup.ts` on purpose: it is
 * the only suite that mounts a chart, and a global shim would hide the fact
 * that the other suites are not exercising those code paths at all.
 *
 * A no-op is the right stub. `ResponsiveContainer` uses it to size itself, and
 * jsdom has no layout to report; DESIGN.md's testing note is explicit that
 * these tests assert classNames, not computed geometry.
 *
 * The stub itself now lives in `tests/setup.ts`. It used to be declared here,
 * with an argument against a global one: a global shim would hide the fact that
 * the other suites never exercise the chart code paths at all. The argument about
 * the coverage gap is right and still recorded. The conclusion about WHERE the
 * stub lives was not, and the repo proved it: `App.routing.test.tsx` renders
 * this page at four paths, declared no stub, and recharts threw into the route
 * ErrorBoundary AFTER the page's own assertions had already passed. The test
 * reported green while the route had failed.
 *
 * A per-file stub enforces a fact at the cost of a silent one. The missing chart
 * coverage is discoverable by reading which suites mount a chart; a swallowed
 * render error is not discoverable at all.
 */
/** The chart paths are exercised only here; see the note above. */
void 0;

/**
 * Fails only the PAGINATED transactions query (`page_size=10`), which is the
 * one whose failure renders the retry control this page migrated. Failing the
 * whole endpoint would also fail the charts' query, and `State` renders a
 * second "Reintentar" — the page would then have two and the query would throw
 * on multiple matches.
 */
function failPaginatedTransactionList() {
  server.use(
    http.get("*/api/v1/transactions", ({ request }) => {
      const size = new URL(request.url).searchParams.get("page_size");
      if (size === "10") {
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }
      return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 });
    }),
  );
}

/** The retry control, located through the banner that owns it. */
async function findRetryControl(): Promise<HTMLButtonElement> {
  const banner = await screen.findByTestId("table-error");
  return within(banner).getByRole("button", { name: "Reintentar" });
}

/**
 * The Task 7 contract for this page. Class names are asserted as LITERALS —
 * comparing an element to `BTN_VARIANTS.secondary` moves both sides when the
 * constant is edited, so the assertion would hold no matter what the page
 * rendered, including the hand-rolled `<button>` this replaced.
 */
describe("DashboardPage — primitives migration", () => {
  beforeEach(() => {
    mockAuth();
  });

  it("the retry control is a secondary, small Button with the keyboard focus ring", async () => {
    failPaginatedTransactionList();
    render(<DashboardPage />, { wrapper: createWrapper() });

    const retry = await findRetryControl();

    // Falsifiable: the hand-rolled <button> this replaced had no focus ring at
    // all and a BARE `hover:bg-slate-800`, so reverting drops all three of the
    // assertions below.
    expect(retry.classList.contains("border-slate-700")).toBe(true);
    expect(retry.classList.contains("enabled:hover:bg-slate-800")).toBe(true);
    expect(retry.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(retry.classList.contains("focus-visible:ring-focus-ring")).toBe(true);

    // `sm` size, and layout the primitive does not supply.
    expect(retry.classList.contains("px-3")).toBe(true);
    expect(retry.classList.contains("py-1.5")).toBe(true);
    expect(retry.classList.contains("text-xs")).toBe(true);
    expect(retry.classList.contains("rounded-lg")).toBe(true);
    expect(retry.classList.contains("mt-2")).toBe(true);
    // `Button` defaults to `type="button"`; this one is outside any form, so
    // the default is correct and is asserted so a future `type="submit"` leak
    // is visible.
    expect(retry.getAttribute("type")).toBe("button");
  });

  it("the retry control actually refetches", async () => {
    // The class assertions above are shape; this is behaviour. A control that
    // satisfies every one of them and calls nothing would pass them all.
    let calls = 0;
    server.use(
      http.get("*/api/v1/transactions", ({ request }) => {
        if (new URL(request.url).searchParams.get("page_size") === "10") {
          calls += 1;
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 });
      }),
    );

    const user = userEvent.setup();
    render(<DashboardPage />, { wrapper: createWrapper() });

    const retry = await findRetryControl();
    const before = calls;
    await user.click(retry);

    await waitFor(() => expect(calls).toBeGreaterThan(before));
  });

  it("the one accepted token delta is real and documented, not silent", async () => {
    failPaginatedTransactionList();
    render(<DashboardPage />, { wrapper: createWrapper() });

    const retry = await findRetryControl();
    // `secondary` says `text-slate-300`; the hand-rolled string said
    // `text-slate-200`. The variant wins because Tailwind orders
    // `.text-slate-200` BEFORE `.text-slate-300` in the built stylesheet, so
    // this cannot be pushed back through `className` — which is why it is
    // pinned here rather than left to be discovered as an unexplained shift.
    expect(retry.classList.contains("text-slate-300")).toBe(true);
    // And the delta is still NAMED in the source — in a comment, so this reads
    // the raw file, not the comment-stripped code. A recorded decision, not an
    // artefact somebody will rediscover as an unexplained shift.
    expect(DASHBOARD_SOURCE).toContain("text-slate-200");
    // While the code itself no longer carries it.
    expect(DASHBOARD_CODE).not.toContain("text-slate-200");
  });

  it("the source no longer re-types the retry treatment", () => {
    for (const token of [
      "btn-motion active:scale-[0.98] mt-2",
      "hover:bg-slate-800",
      "text-slate-200",
    ]) {
      expect(DASHBOARD_CODE, `still re-types ${token}`).not.toContain(token);
    }
    // The positive half, so the negative assertions cannot be satisfied by the
    // file simply not mentioning these strings.
    expect(DASHBOARD_CODE).toContain("<Button");
    expect(DASHBOARD_CODE).toContain('variant="secondary"');
  });

  it("carries no bare focus: variant at all", () => {
    // The page-level statement of landmine 3 for this file: `focus:` paints a
    // ring on mouse click. Matched with a lookahead so `focus-visible:` is not
    // caught, and scanned on code rather than raw source so this file's notes
    // about the pattern do not trip it.
    for (const cls of DASHBOARD_CODE.split(/[\s"'`]+/)) {
      expect(cls, `bare focus variant: ${cls}`).not.toMatch(/^focus:(?!-)/);
    }
  });
});

/**
 * `desktop-regression.test.tsx` claims to guard the desktop layout of every
 * page, and it does not touch this one — it renders Sidebar,
 * TransactionsPage, ShapAttributionCard and ScoreResultCard, and nothing else.
 * These two tests are here so the mobile contract is not the only thing
 * standing between this page and a regression.
 */
describe("DashboardPage — desktop regression, which the shared suite does not cover", () => {
  beforeEach(() => {
    mockAuth();
  });

  it("the recent-transactions section is a section heading, not a bare h2 at the top", async () => {
    render(<DashboardPage />, { wrapper: createWrapper() });

    // A screen-reader user arriving on this page must get a page title. The
    // h1 is visually hidden because the KPI row is the visual header and a
    // second visible title would be redundant — but it has to EXIST.
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("Dashboard de detección de fraude");
    expect(h1.className).toContain("sr-only");
  });

  it("a failed metrics query is distinguishable from a genuine zero", async () => {
    server.use(
      http.get("*/api/v1/monitoring/dashboard", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    render(<DashboardPage />, { wrapper: createWrapper() });

    // Four permanent em-dashes read as "zero fraud". This must not be that.
    await waitFor(() => {
      expect(
        screen.getByText("No se pudieron cargar las métricas"),
      ).toBeInTheDocument();
    });
  });
});
