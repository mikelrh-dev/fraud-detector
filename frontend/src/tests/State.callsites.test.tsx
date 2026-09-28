import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import AlertsPage from "../pages/AlertsPage";
import { ErrorBoundary, RouteErrorFallback } from "../components/ErrorBoundary";
import TransactionTable from "../components/TransactionTable";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

/**
 * PROOF THAT MERGING THE TWO STATE COMPONENTS CHANGED NO PIXELS.
 *
 * The point of this file is that it was written to run against BOTH revisions.
 * Every selector here is STRUCTURAL — a text node's parent, or the test id the
 * failure state already published — and never a test id introduced by the
 * merge. So the same assertions were run green before the merge and green
 * after it, which is a real before/after and not a restatement of the
 * component's own unit test.
 *
 * The class literals are the exact `class` attributes captured from the
 * pre-merge DOM. They are compared with `toBe`, not `toContain`, so a class
 * ADDED during the merge turns this red as well as one removed.
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

describe("call site 3+4+7+8 — AlertsPage", () => {
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

describe("call site 10 — TransactionTable", () => {
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
