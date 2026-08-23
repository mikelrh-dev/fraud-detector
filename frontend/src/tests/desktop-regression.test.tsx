import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../components/Sidebar";
import { useAuthStore } from "../store/authStore";
import { ShapAttributionCard } from "../components/ShapAttributionCard";
import { ScoreResultCard } from "../pages/ScoreResultCard";
import TransactionsPage from "../pages/TransactionsPage";
import type { AuthState } from "../store/authStore";
import type { ShapContribution } from "../api/transactions";
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

describe("Desktop regression — md+ classes survive mobile retrofit", () => {
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

  it("Sidebar aside retains hidden md:flex for desktop visibility", () => {
    render(
      <MemoryRouter>
        <Sidebar activeItem="dashboard" />
      </MemoryRouter>,
    );
    const aside = document.querySelector("aside");
    expect(aside).toBeTruthy();
    expect(aside!.className).toContain("hidden");
    expect(aside!.className).toContain("md:flex");
  });

  it("TransactionsPage table wrapper has hidden md:block", async () => {
    render(<TransactionsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });
    // The table wrapper should have hidden md:block
    const table = document.querySelector("table");
    expect(table).toBeTruthy();
    // Navigate up to find the wrapper div with hidden md:block
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

  it("ShapAttributionCard rows have sm:flex-row for horizontal layout at sm+", () => {
    const contributions: ShapContribution[] = [
      { feature: "amount", contribution: 35 },
    ];
    render(<ShapAttributionCard contributions={contributions} />);
    const li = document.querySelector("ul li");
    expect(li).toBeTruthy();
    expect(li!.className).toContain("sm:flex-row");
  });

  it("ScoreResultCard loading skeleton has sm:grid-cols-3", () => {
    const { container } = render(
      <ScoreResultCard result={null} isLoading={true} />,
    );
    const grid = container.querySelector(".grid");
    expect(grid).toBeTruthy();
    expect(grid!.className).toContain("sm:grid-cols-3");
  });
});
