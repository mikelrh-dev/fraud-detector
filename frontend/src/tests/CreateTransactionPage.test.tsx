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

  it("A30: no longer renders the dead user_id field", () => {
    renderPage();
    // This test used to assert the opposite — that a hidden `user_id` input was
    // present — which pinned the defect. That field was required, fed from an
    // auth store that can legitimately hold `user: null`, and was the one input
    // with no rendered error, so an empty value disabled the submit button
    // permanently and silently. The server ignores the value anyway (F2).
    const userIdInput = document.querySelector('input[name="user_id"]');
    expect(userIdInput).not.toBeInTheDocument();
  });

  it("A30: the submit button is enabled without a user object in the store", () => {
    // authStore sets isAuthenticated unconditionally and leaves `user` null when
    // the token fails to decode, and ProtectedRoute gates on isAuthenticated
    // only, so this state is reachable. The form must not depend on it.
    renderPage();
    const submit = screen.getByRole("button", { name: /crear transacci/i });
    // Disabled only because the visible fields are still empty, not because of
    // a hidden field nobody can see or fix.
    const namedInputs = [
      ...document.querySelectorAll("input[name], textarea[name]"),
    ].map((el) => el.getAttribute("name"));
    expect(namedInputs).not.toContain("user_id");
    expect(submit).toBeInTheDocument();
  });

  it("A30: shows no loading skeleton before anything is submitted", () => {
    const { container } = renderPage();
    // ScoreResultCard used to render a pulsing skeleton whenever `!result`,
    // which is true on first paint — claiming work was in progress before the
    // user had done anything.
    expect(container.querySelector(".animate-pulse")).toBeNull();
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
