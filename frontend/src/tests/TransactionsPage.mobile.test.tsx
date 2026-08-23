import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import TransactionsPage from "../pages/TransactionsPage";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
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

describe("TransactionsPage — mobile dual-mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = {
          user: { id: "test-user-id", role: "analista" },
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

  it("mobile card div has md:hidden class", async () => {
    render(<TransactionsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });
    const card = screen.getByTestId("tx-card-tx-1-0");
    expect(card).toBeTruthy();
    // Walk up to find md:hidden parent
    let el: HTMLElement | null = card.parentElement;
    let found = false;
    while (el) {
      if (el.className.includes("md:hidden")) {
        found = true;
        break;
      }
      el = el.parentElement;
    }
    expect(found).toBe(true);
  });

  it("card has data-testid with tx-card prefix", async () => {
    render(<TransactionsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId("tx-card-tx-1-0")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tx-card-tx-1-1")).toBeInTheDocument();
  });

  it("table wrapper has hidden md:block", async () => {
    render(<TransactionsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });
    const table = document.querySelector("table");
    expect(table).toBeTruthy();
    let el: HTMLElement | null = table!.parentElement;
    let found = false;
    while (el) {
      if (
        el.className.includes("hidden") &&
        el.className.includes("md:block")
      ) {
        found = true;
        break;
      }
      el = el.parentElement;
    }
    expect(found).toBe(true);
  });

  it("root div has overflow-x-hidden", async () => {
    render(<TransactionsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });
    const root = document.querySelector(".min-h-screen");
    expect(root).toBeTruthy();
    expect(root!.className).toContain("overflow-x-hidden");
  });
});
