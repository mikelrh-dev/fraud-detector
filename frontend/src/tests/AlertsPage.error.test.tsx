import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import AlertsPage from "../pages/AlertsPage";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import { makeAuthState } from "../test-utils/authState";
import type { ReactNode } from "react";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

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

/**
 * A failed alerts query used to be indistinguishable from an empty one:
 * `data?.total || 0` rendered "0 alertas", and `data?.items.length === 0`
 * evaluated to `undefined === 0` (false), so control reached the `.map()` and
 * rendered an empty list. On a fraud alerting surface that is a hard false
 * negative — the UI asserted there was nothing to review when in fact it could
 * not ask.
 */
describe("AlertsPage - failure honesty", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = makeAuthState();
        return selector ? selector(state) : state;
      },
    );
  });

  it("does not claim zero alerts when the request fails", async () => {
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    render(<AlertsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId("alerts-total-error")).toBeInTheDocument();
    });

    // The literal claim "0 alertas" must not appear.
    expect(screen.queryByTestId("alerts-total")).not.toBeInTheDocument();
    expect(screen.queryByText(/0 alertas/)).not.toBeInTheDocument();
  });

  it("surfaces a retryable error state", async () => {
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    render(<AlertsPage />, { wrapper: createWrapper() });

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("button", { name: /reintentar/i }).length,
    ).toBeGreaterThan(0);
  });

  it("does not render the empty state on failure", async () => {
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    render(<AlertsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId("alerts-total-error")).toBeInTheDocument();
    });

    // "No hay alertas" is a true statement only when the query succeeded.
    expect(screen.queryByText("No hay alertas")).not.toBeInTheDocument();
  });

  it("still reports a real zero when the query succeeds and is empty", async () => {
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 }),
      ),
    );

    render(<AlertsPage />, { wrapper: createWrapper() });

    // Wait for the empty state itself: the total span resolves earlier, and
    // asserting on it alone would pass even with no data loaded at all.
    await waitFor(() => {
      expect(screen.getAllByText("No hay alertas").length).toBeGreaterThan(0);
    });

    expect(screen.getByTestId("alerts-total")).toHaveTextContent("0 alertas");
    expect(screen.queryByTestId("alerts-total-error")).not.toBeInTheDocument();
  });

  it("shows no total while the request is in flight", async () => {
    server.use(
      http.get("*/api/v1/alerts", async () => {
        await new Promise((r) => setTimeout(r, 50));
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 });
      }),
    );

    render(<AlertsPage />, { wrapper: createWrapper() });

    // `data?.total ?? 0` used to print a confident "0 alertas" during loading.
    expect(screen.getByTestId("alerts-total-pending")).toBeInTheDocument();
    expect(screen.queryByTestId("alerts-total")).not.toBeInTheDocument();
  });
});
