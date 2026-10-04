import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import ConflictQueuePage from "../pages/ConflictQueuePage";
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

const FAILING = () =>
  http.get("*/api/v1/transactions", () =>
    HttpResponse.json({ detail: "boom" }, { status: 500 }),
  );

/**
 * The conflict queue's failure modes, and why each is a hard false negative.
 *
 * A conflict queue answers one question: "which transactions did the two
 * scoring layers disagree about?". An empty answer is a routine, believable
 * outcome — the layers mostly agree, and a quiet day is a good day. So the UI
 * must never be able to render "0 conflicts" for a request that failed. It did
 * on `AlertsPage` once, and the fix there was to make the three states
 * (loading / failed / loaded) distinct and separately named. This page has the
 * same exposure with a worse consequence: a silent zero here reads as "the
 * model and the rules never disagreed today", which is exactly the kind of
 * false assurance a fraud surface must not manufacture.
 */
describe("ConflictQueuePage - failure honesty", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = makeAuthState();
        return selector ? selector(state) : state;
      },
    );
  });

  it("does not claim zero conflicts when the request fails", async () => {
    server.use(FAILING());

    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId("conflicts-total-error")).toBeInTheDocument();
    });

    // The literal claim "0 conflictos" must not appear anywhere.
    expect(screen.queryByTestId("conflicts-total")).not.toBeInTheDocument();
    expect(screen.queryByText(/0 conflictos/)).not.toBeInTheDocument();
  });

  it("surfaces a retryable error state", async () => {
    server.use(FAILING());

    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("button", { name: /reintentar/i }).length,
    ).toBeGreaterThan(0);
  });

  it("does not render the empty state on failure", async () => {
    server.use(FAILING());

    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId("conflicts-total-error")).toBeInTheDocument();
    });

    // "No hay conflictos" is a true statement only when the query succeeded.
    expect(screen.queryByText("No hay conflictos")).not.toBeInTheDocument();
  });

  it("still reports a real zero when the query succeeds and is empty", async () => {
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 }),
      ),
    );

    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    // Wait for the empty state itself: the total span resolves earlier, and
    // asserting on it alone would pass even with no data loaded at all.
    await waitFor(() => {
      expect(screen.getAllByText("No hay conflictos").length).toBeGreaterThan(0);
    });

    expect(screen.getByTestId("conflicts-total")).toHaveTextContent("0 conflictos");
    expect(screen.queryByTestId("conflicts-total-error")).not.toBeInTheDocument();
  });

  it("shows no total while the request is in flight", async () => {
    server.use(
      http.get("*/api/v1/transactions", async () => {
        await new Promise((r) => setTimeout(r, 50));
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 });
      }),
    );

    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    // `data?.total ?? 0` would print a confident "0 conflictos" during loading.
    expect(screen.getByTestId("conflicts-total-pending")).toBeInTheDocument();
    expect(screen.queryByTestId("conflicts-total")).not.toBeInTheDocument();
  });

  it("does not nest two live regions in the failure block", async () => {
    // `State`'s error tone owns the assertive region. A wrapper carrying a
    // second `role="alert"` around it announces the same failure twice — which
    // is what AlertsPage did before it was fixed, in both responsive modes.
    server.use(FAILING());

    const { container } = render(<ConflictQueuePage />, { wrapper: createWrapper() });

    await screen.findAllByRole("alert");
    const nested = Array.from(container.querySelectorAll('[role="alert"]')).filter(
      (node) => node.querySelector('[role="alert"]') !== null,
    );
    expect(nested).toHaveLength(0);
  });
});