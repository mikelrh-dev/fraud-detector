import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import AlertsPage from "../pages/AlertsPage";
import DashboardPage from "../pages/DashboardPage";
import TransactionsPage from "../pages/TransactionsPage";
import { ErrorBoundary, RouteErrorFallback } from "../components/ErrorBoundary";
import TransactionTable from "../components/TransactionTable";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

/**
 * PROOF THAT MERGING THE TWO STATE COMPONENTS CHANGED NO PIXELS AND NO WORDS.
 *
 * The point of this file is that it runs against BOTH revisions. Every selector
 * here is STRUCTURAL — a text node's parent, or the `data-testid="error-state"`
 * the failure state already published — and never a test id the merge
 * introduced, so the same file compiles and passes on either side.
 *
 * VERIFIED, not asserted. `git worktree add --detach <tmp> b4c7f34~1` gives a
 * tree with `EmptyState.tsx` and `ErrorState.tsx` and no `State.tsx`; this
 * file was copied in unchanged and run there. 8/8 on both sides.
 *
 * Coverage is all ten call sites, audited: ErrorBoundary x2, AlertsPage x4
 * (mobile card + desktop cell, error and empty), DashboardPage x2, TransactionTable
 * x1, TransactionsPage x1. The three added last (DashboardPage's two failure
 * blocks and TransactionsPage's empty list) are the ones the file originally
 * missed — its describe labels read `3+4+7+8` for four AlertsPage sites and
 * `10` for a TransactionTable that is the ninth, so the indices were not a
 * reliable count of what was covered.
 *
 * The class literals are the exact `class` attributes captured from the
 * pre-merge DOM. They are compared with `toBe`, not `toContain`, so a class
 * ADDED during the merge turns this red as well as one removed.
 *
 * WHAT THIS DOES NOT COVER: jsdom has no layout engine, so "no pixels" here
 * means the emitted class list and the rendered text, not computed geometry. It
 * also cannot see a token that Tailwind never emitted for both revisions; the
 * stylesheet size gate covers that half.
 */

vi.mock("../store/authStore", () => ({ useAuthStore: vi.fn() }));
const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

const FULL_FRAME = "flex flex-col items-center justify-center px-6 text-center py-12";
const COMPACT_FRAME = "flex flex-col items-center justify-center px-6 text-center py-6";

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

/** The state block is the parent of the title paragraph. Works on both revisions. */
const rootOf = (title: string) => screen.getByText(title).parentElement as HTMLElement;

beforeEach(() => {
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
});

describe("call site 1+2 — ErrorBoundary", () => {
  function Boom(): ReactNode {
    throw new Error("boom");
  }

  it("the default fallback keeps the full-height failure frame", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>
      </MemoryRouter>,
    );

    const root = screen.getByTestId("error-state");
    expect(root.className).toBe(FULL_FRAME);
    expect(root.getAttribute("role")).toBe("alert");
    // Default copy, the case most at risk from a merge that drops fallbacks.
    expect(root).toHaveTextContent("No se pudieron cargar los datos");
    expect(
      root.querySelector("[aria-hidden='true']")!.className,
    ).toBe("mb-4 text-risk-critical");
  });

  it("the route fallback keeps the same frame with caller copy", () => {
    // `RouteErrorFallback` is the boundary's own router-aware recovery UI, so
    // this renders it directly rather than provoking a throw a second time.
    render(
      <MemoryRouter>
        <RouteErrorFallback reset={() => {}} />
      </MemoryRouter>,
    );

    const root = screen.getByTestId("error-state");
    expect(root.className).toBe(FULL_FRAME);
    expect(root).toHaveTextContent("Esta página no se pudo mostrar");
  });
});

describe("call site 3+4+5+6 — AlertsPage", () => {
  it("the failure branch keeps the compact failure frame, in both the card and the table", async () => {
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    render(<AlertsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId("error-state").length).toBeGreaterThan(0);
    });

    // Mobile card + desktop table cell both render one.
    const roots = screen.getAllByTestId("error-state");
    expect(roots.length).toBe(2);
    for (const root of roots) {
      expect(root.className).toBe(COMPACT_FRAME);
      expect(root.getAttribute("role")).toBe("alert");
      expect(
        root.querySelector("[aria-hidden='true']")!.className,
      ).toBe("mb-4 text-risk-critical");
    }
    expect(screen.getAllByRole("button", { name: /reintentar/i }).length).toBe(2);
  });

  it("the empty branch keeps its frame: full height with a CTA on mobile, compact in the table", async () => {
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 }),
      ),
    );
    render(<AlertsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByText("No hay alertas").length).toBeGreaterThan(0);
    });

    // Sorted so the assertion does not depend on which branch React mounted
    // first — both are in the DOM, one hidden by a media query.
    const roots = screen
      .getAllByText("No hay alertas")
      .map((el) => el.parentElement as HTMLElement);
    expect(roots.length).toBe(2);
    expect(roots.map((r) => r.className).sort()).toEqual(
      [FULL_FRAME, COMPACT_FRAME].sort(),
    );

    // The empty state announces nothing, in either branch.
    for (const root of roots) {
      expect(root.getAttribute("role")).toBeNull();
      expect(root.querySelector("[aria-hidden='true']")!.className).toBe(
        "mb-4 text-slate-600",
      );
    }
    // Only the mobile one carries the caller's CTA.
    expect(screen.getAllByRole("button", { name: "Ver transacciones" }).length).toBe(1);
  });
});

describe("call site 7+8 — DashboardPage", () => {
  /** The metrics banner. `monitoring/dashboard` is its own endpoint, so this
   *  leaves both chart queries green. */
  function failMetrics() {
    server.use(
      http.get("*/api/v1/monitoring/dashboard", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
  }

  /**
   * Only the CHART query (`page_size=100`). The recent-transactions table asks
   * for `page_size=10` and has its own error banner, so failing both would put
   * two failure blocks on the page and the selector below would stop being
   * able to say which is which.
   */
  function failCharts() {
    server.use(
      http.get("*/api/v1/transactions", ({ request }) => {
        const size = new URL(request.url).searchParams.get("page_size");
        if (size === "100") {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 10 });
      }),
    );
  }

  it("the metrics failure keeps the compact frame beside the KPI row", async () => {
    failMetrics();
    render(<DashboardPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(rootOf("No se pudieron cargar las métricas")).toBeInTheDocument();
    });

    const root = rootOf("No se pudieron cargar las métricas");
    expect(root.className).toBe(COMPACT_FRAME);
    expect(root.getAttribute("role")).toBe("alert");
    expect(
      root.querySelector("[aria-hidden='true']")!.className,
    ).toBe("mb-4 text-risk-critical");
    // Both error states in this file are compact, so `py-6` here is the
    // assertion that `compact` reached this call site and not just the first.
    expect(root.className).not.toBe(FULL_FRAME);
  });

  it("the chart failure keeps the compact frame and its own copy", async () => {
    failCharts();
    render(<DashboardPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(rootOf("No se pudieron cargar los gráficos")).toBeInTheDocument();
    });

    const root = rootOf("No se pudieron cargar los gráficos");
    expect(root.className).toBe(COMPACT_FRAME);
    expect(root.getAttribute("role")).toBe("alert");
    // Caller copy, so this site never touches the default strings — asserted
    // so a merge that wrongly routed it through the fallback would go red.
    expect(root).toHaveTextContent(
      "Sin estos datos no se puede evaluar la tendencia de riesgo.",
    );
    expect(root).not.toHaveTextContent("Revisá tu conexión");
  });
});

describe("call site 9 — TransactionTable", () => {
  it("the empty table cell keeps the compact empty frame and no action row", () => {
    render(
      <MemoryRouter>
        <TransactionTable
          transactions={[]}
          total={0}
          page={1}
          pageSize={20}
          onSort={() => {}}
          onPageChange={() => {}}
          onFilterChange={() => {}}
          onTransactionClick={() => {}}
        />
      </MemoryRouter>,
    );

    const root = rootOf("No se encontraron transacciones");
    expect(root.className).toBe(COMPACT_FRAME);
    expect(root.getAttribute("role")).toBeNull();
    expect(root.querySelector("div.mt-4")).toBeNull();
    expect(
      root.querySelector("[aria-hidden='true']")!.className,
    ).toBe("mb-4 text-slate-600");
  });
});

describe("call site 10 — TransactionsPage", () => {
  it("the empty list keeps the full-height frame and its own CTA", async () => {
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 }),
      ),
    );
    render(<TransactionsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(rootOf("No hay transacciones")).toBeInTheDocument();
    });

    // The only FULL-height empty state that is NOT inside a table cell, and the
    // only one whose action is a router link rather than a button — so it is
    // the only place `action` passing a node through untouched is observable.
    const root = rootOf("No hay transacciones");
    expect(root.className).toBe(FULL_FRAME);
    expect(root.getAttribute("role")).toBeNull();
    expect(root.querySelector("[aria-hidden='true']")!.className).toBe(
      "mb-4 text-slate-600",
    );

    const cta = root.querySelector("div.mt-4")!;
    expect(cta.className).toBe("mt-4");
    expect(cta.firstElementChild!.tagName).toBe("A");
    expect(cta.firstElementChild!.textContent).toBe("Crear primera transacción");
    // The caller's own link classes, not ones the state could have imposed.
    expect(cta.firstElementChild!.className).toBe(
      "max-md:inline-flex max-md:min-h-[40px] max-md:items-center max-md:px-3 text-sm text-status-info hover:underline",
    );
  });
});
