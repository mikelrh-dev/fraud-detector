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
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function renderPage() {
  return render(<TransactionsPage />, { wrapper: createWrapper() });
}

describe("TransactionsPage", () => {
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

  it("renders page title and transaction rows", async () => {
    renderPage();

    // Wait for data to load — Merchant 0 appears in both mobile card and desktop table
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });

    // Heading is an h1
    const heading = screen.getAllByText("Transacciones");
    expect(heading.length).toBeGreaterThanOrEqual(1);
  });

  it("renders filter status pills", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Todas")).toBeInTheDocument();
      expect(screen.getByText("Legítimo")).toBeInTheDocument();
      expect(screen.getByText("Revisión")).toBeInTheDocument();
      expect(screen.getByText("Fraude")).toBeInTheDocument();
    });
  });

  it("has a 'Nueva transacción' button that links to /transactions/new", async () => {
    renderPage();
    await waitFor(() => {
      const button = screen.getByRole("link", { name: /nueva transacción/i });
      expect(button).toBeInTheDocument();
      expect(button).toHaveAttribute("href", "/transactions/new");
    });
  });

  it("renders pagination controls", async () => {
    renderPage();
    await waitFor(() => {
      // Pagination should show page info (50 total / 10 per page = 5 pages)
      expect(screen.getByText(/50 transacciones/)).toBeInTheDocument();
    });
  });

  it("shows a classification column with live scores from deterministic fixtures", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Clasificación")).toBeInTheDocument();
    });

    // Merchant 0 is a review row (risk_score 62) — score rendered live
    const merchant0Elements = screen.getAllByText("Merchant 0");
    expect(merchant0Elements.length).toBeGreaterThanOrEqual(1);
    // The table row has the score
    const row0 = merchant0Elements[merchant0Elements.length - 1].closest("tr");
    expect(row0).toHaveTextContent("62.0");
    // Merchant 1 is legitimate (risk_score 15)
    const merchant1Elements = screen.getAllByText("Merchant 1");
    const row1 = merchant1Elements[merchant1Elements.length - 1].closest("tr");
    expect(row1).toHaveTextContent("15.0");
  });
});
