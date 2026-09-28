import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TransactionDetail from "../pages/TransactionDetail";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import type { Transaction } from "../api/transactions";

/**
 * A31: `fetchReport` returned `null` for every outcome that was not a 202 or a
 * 404, so a 500 from a dead worker rendered as "No hay reporte disponible para
 * esta transacción".
 *
 * "We could not ask" and "there is nothing there" are different claims, and on
 * a fraud investigation the second is the dangerous one: an analyst concludes
 * there is nothing to see when the system never looked.
 */

vi.mock("../store/authStore", () => ({ useAuthStore: vi.fn() }));
const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));
import apiClient from "../api/client";
const mockGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

const TX_ID = "11111111-2222-3333-4444-555555555555";

const TX = {
  id: TX_ID,
  amount: 1200,
  currency: "USD",
  merchant_name: "Test Merchant",
  status: "flagged",
  created_at: "2026-09-20T10:00:00Z",
  updated_at: "2026-09-20T10:00:00Z",
} as unknown as Transaction;

function httpError(status: number) {
  return { response: { status }, isAxiosError: true };
}

function renderDetail() {
  // TransactionDetail reads the transaction through react-query, so the
  // provider is required even though apiClient itself is mocked.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Wrapper() {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/transactions/${TX_ID}`]}>
          <Routes>
            <Route path="/transactions/:id" element={<TransactionDetail />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return render(<Wrapper />);
}

describe("A31 — a failed report request is not an absent report", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = {
          user: { id: "u1", role: "analista" },
          logout: vi.fn(),
          isAuthenticated: true,
          token: "mock-token",
          refreshToken: null,
          login: vi.fn(),
          setTokens: vi.fn(),
        };
        return selector ? selector(state) : state;
      },
    );
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/report")) return Promise.reject(httpError(500));
      return Promise.resolve({ data: TX });
    });
  });

  it("shows an error, not 'no report available', on a 500", async () => {
    renderDetail();

    await waitFor(() => {
      expect(screen.getByTestId("report-error")).toBeTruthy();
    });

    expect(document.body.textContent).not.toContain(
      "No hay reporte disponible",
    );
  });

  it("names the status code so the failure is actionable", async () => {
    renderDetail();
    await waitFor(() => expect(screen.getByTestId("report-error")).toBeTruthy());
    expect(screen.getByTestId("report-error").textContent).toContain("500");
  });

  it("announces the failure to assistive tech", async () => {
    renderDetail();
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
  });

  it("still says 'no report' on a genuine 404", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/report")) return Promise.reject(httpError(404));
      return Promise.resolve({ data: TX });
    });

    renderDetail();

    await waitFor(() => {
      expect(document.body.textContent).toContain("No hay reporte disponible");
    });
    expect(screen.queryByTestId("report-error")).toBeNull();
  });

  it("handles a network failure with no status code", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/report")) return Promise.reject(new Error("Network Error"));
      return Promise.resolve({ data: TX });
    });

    renderDetail();

    await waitFor(() => expect(screen.getByTestId("report-error")).toBeTruthy());
    expect(screen.getByTestId("report-error").textContent).toContain(
      "No se pudo contactar",
    );
  });

  it("keeps polling while the report is pending", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockGet.mockImplementation((url: string) => {
        if (url.includes("/report")) {
          return Promise.resolve({
            data: {
              transaction_id: TX_ID,
              report_text: null,
              model_name: null,
              status: "pending",
              generation_time_ms: null,
              created_at: null,
              error_detail: null,
            },
          });
        }
        return Promise.resolve({ data: TX });
      });

      renderDetail();

      await waitFor(() => {
        expect(document.body.textContent.toLowerCase()).toContain("generando");
      });

      const before = mockGet.mock.calls.length;
      await vi.advanceTimersByTimeAsync(5000);
      expect(mockGet.mock.calls.length).toBeGreaterThan(before);
    } finally {
      vi.useRealTimers();
    }
  });
});
