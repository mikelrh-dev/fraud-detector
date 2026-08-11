import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import TransactionDetail from "../pages/TransactionDetail";
import { server } from "./mocks/server";
import type { ReactNode } from "react";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/transactions/test-uuid"]}>
          <Routes>
            <Route path="/transactions/:id" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function renderDetail() {
  return render(<TransactionDetail />, { wrapper: createWrapper() });
}

describe("TransactionDetail", () => {
  it("renders scoring breakdown card when transaction has scoring", async () => {
    renderDetail();

    // ScoreResultCard is rendered with the persisted breakdown
    await waitFor(() => {
      expect(screen.getByText("Resultado de Scoring")).toBeInTheDocument();
    });
    // Rule score from the breakdown (rule_score: 50)
    expect(screen.getByText("50.0")).toBeInTheDocument();
    // Ensemble score appears in both gauge and ensemble card (62.0)
    expect(screen.getAllByText("62.0").length).toBeGreaterThanOrEqual(2);
    // Classification badge (Revisión) rendered from the card
    expect(screen.getAllByText("Revisión").length).toBeGreaterThanOrEqual(1);
  });

  it("renders fallback message when scoring is absent", async () => {
    server.use(
      http.get("*/api/v1/transactions/:id", () =>
        HttpResponse.json({
          id: "test-uuid",
          amount: 1500,
          currency: "USD",
          merchant_name: "Test Merchant",
          merchant_category: "retail",
          card_last4: "1234",
          status: "flagged",
          risk_score: null,
          classification: null,
          scoring: null,
          user_id: "00000000-0000-0000-0000-000000000001",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      ),
    );

    renderDetail();

    await waitFor(() => {
      expect(
        screen.getByText("Score no disponible para esta transacción."),
      ).toBeInTheDocument();
    });
    // The scoring card must NOT be rendered
    expect(
      screen.queryByText("Resultado de Scoring"),
    ).not.toBeInTheDocument();
  });
});
