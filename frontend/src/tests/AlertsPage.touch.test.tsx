import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import AlertsPage from "../pages/AlertsPage";
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

describe("AlertsPage — mobile touch targets and dual-mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = makeAuthState();
        return selector ? selector(state) : state;
      },
    );
  });

  it("mobile card div has md:hidden class", async () => {
    render(<AlertsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      // Wait for alerts to load — find any alert card
      const cards = document.querySelectorAll("[data-testid^='alert-card-']");
      expect(cards.length).toBeGreaterThan(0);
    });
    const card = document.querySelector("[data-testid^='alert-card-']");
    expect(card).toBeTruthy();
    // Walk up to find md:hidden parent
    let el: HTMLElement | null = card!.parentElement;
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

  it("action buttons have max-md:min-h-[40px]", async () => {
    render(<AlertsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      const cards = document.querySelectorAll("[data-testid^='alert-card-']");
      expect(cards.length).toBeGreaterThan(0);
    });
    // Find action buttons inside alert cards
    const buttons = document.querySelectorAll("[data-testid^='alert-card-'] button");
    // Filter to action buttons (not the tx link button)
    const actionButtons = Array.from(buttons).filter(
      (b) => b.textContent === "Revisar" || b.textContent === "Falso Pos." || b.textContent === "Revertir",
    );
    expect(actionButtons.length).toBeGreaterThan(0);
    for (const btn of actionButtons) {
      expect(btn.className).toContain("max-md:min-h-[40px]");
    }
  });

  it("table wrapper has hidden md:block", async () => {
    render(<AlertsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      const cards = document.querySelectorAll("[data-testid^='alert-card-']");
      expect(cards.length).toBeGreaterThan(0);
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
});
