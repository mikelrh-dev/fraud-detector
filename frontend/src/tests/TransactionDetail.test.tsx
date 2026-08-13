import { describe, it, expect } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

  it("renders the SHAP attribution section with Spanish labels and direction", async () => {
    renderDetail();

    await waitFor(() => {
      expect(
        screen.getByTestId("shap-attribution"),
      ).toBeInTheDocument();
    });
    const section = screen.getByTestId("shap-attribution");

    // Heading (FRD-SHP-002)
    expect(within(section).getByText("Atribución SHAP")).toBeInTheDocument();

    // Spanish feature labels from the detail fixture (5 rows, top-5 by |v|)
    expect(within(section).getByText("Monto")).toBeInTheDocument();
    expect(
      within(section).getByText("Transacciones última hora"),
    ).toBeInTheDocument();
    expect(
      within(section).getByText("Transacciones últimas 5 min"),
    ).toBeInTheDocument();
    expect(
      within(section).getByText("Riesgo del comercio"),
    ).toBeInTheDocument();
    expect(
      within(section).getByText("Monto redondo"),
    ).toBeInTheDocument();

    // Signed contributions (helper formats with +/- and one decimal)
    expect(within(section).getByText("+35.0")).toBeInTheDocument();
    expect(within(section).getByText("+18.0")).toBeInTheDocument();
    expect(within(section).getByText("+12.0")).toBeInTheDocument();
    expect(within(section).getByText("-5.0")).toBeInTheDocument();
    expect(within(section).getByText("-2.0")).toBeInTheDocument();

    // Direction: 3 positive rows push toward fraud, 2 negative toward legit
    expect(within(section).getAllByText("Hacia fraude")).toHaveLength(3);
    expect(within(section).getAllByText("Hacia legítimo")).toHaveLength(2);
  });

  it("hides the SHAP section when scoring.shap_contributions is null", async () => {
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
          risk_score: 62.0,
          classification: "review",
          scoring: {
            rule_score: 50,
            ml_score: 55,
            ensemble_score: 62,
            threshold: 60,
            classification: "review",
            shap_contributions: null,
          },
          user_id: "00000000-0000-0000-0000-000000000001",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      ),
    );

    renderDetail();

    await waitFor(() => {
      expect(screen.getByText("Resultado de Scoring")).toBeInTheDocument();
    });
    // Section must not render when the worker has not produced attribution
    expect(
      screen.queryByTestId("shap-attribution"),
    ).not.toBeInTheDocument();
  });
});
