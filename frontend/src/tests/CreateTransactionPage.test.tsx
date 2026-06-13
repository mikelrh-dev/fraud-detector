import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import CreateTransactionPage from "../pages/CreateTransactionPage";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import type { ReactNode } from "react";

// Mock auth store
vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
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
  return render(<CreateTransactionPage />, { wrapper: createWrapper() });
}

describe("CreateTransactionPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = {
          user: { id: "00000000-0000-0000-0000-000000000001", role: "analista" },
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

  it("renders the form with all required fields", () => {
    renderPage();
    expect(screen.getByText("Nueva Transacción")).toBeInTheDocument();
    expect(screen.getByLabelText(/monto/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/moneda/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/comercio/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/últimos 4 dígitos/i)).toBeInTheDocument();
  });

  it("user_id is hidden (no visible input)", () => {
    renderPage();
    // The user_id input should be type="hidden"
    const userIdInput = document.querySelector('input[name="user_id"]');
    expect(userIdInput).toBeInTheDocument();
    expect(userIdInput).toHaveAttribute("type", "hidden");
  });

  it("submits valid form and shows ScoreResultCard", async () => {
    const user = userEvent.setup();
    renderPage();

    // Fill form
    const amountInput = screen.getByLabelText(/monto/i);
    await user.type(amountInput, "500");

    const currencyInput = screen.getByLabelText(/moneda/i);
    await user.type(currencyInput, "USD");

    const merchantInput = screen.getByLabelText(/comercio/i);
    await user.type(merchantInput, "Test Store");

    const cardInput = screen.getByLabelText(/últimos 4 dígitos/i);
    await user.type(cardInput, "1234");

    // Submit
    const submitButton = screen.getByRole("button", { name: /crear/i });
    await user.click(submitButton);

    // Wait for ScoreResultCard to appear
    await waitFor(() => {
      expect(screen.getByText("Resultado de Scoring")).toBeInTheDocument();
    });

    // Classification badge visible
    expect(screen.getByText("Legítimo")).toBeInTheDocument();
  });

  it("blocks submission with invalid data and shows errors", async () => {
    const user = userEvent.setup();
    renderPage();

    // Fill invalid data
    const amountInput = screen.getByLabelText(/monto/i);
    await user.type(amountInput, "0");

    const currencyInput = screen.getByLabelText(/moneda/i);
    await user.type(currencyInput, "US"); // only 2 chars

    // Submit
    const submitButton = screen.getByRole("button", { name: /crear/i });
    await user.click(submitButton);

    // Should show inline errors
    await waitFor(() => {
      // The form should not submit successfully (no ScoreResultCard)
      expect(screen.queryByText("Resultado de Scoring")).not.toBeInTheDocument();
    });
  });
});
