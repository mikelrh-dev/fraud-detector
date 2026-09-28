import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { readFileSync } from "node:fs";
import { join } from "node:path";
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

  const completedReport = {
    transaction_id: "test-uuid",
    report_text: "## Resumen\n- Monto elevado\nTexto final.",
    model_name: "llama3",
    status: "completed",
    generation_time_ms: 120,
    created_at: new Date().toISOString(),
    error_detail: null,
  };

  function useCompletedReport() {
    server.use(
      http.get("*/api/v1/transactions/:id/report", () =>
        HttpResponse.json(completedReport),
      ),
    );
  }

  it("renders a completed report with light markdown and a copy button", async () => {
    useCompletedReport();
    renderDetail();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Copiar reporte" }),
      ).toBeInTheDocument();
    });
    // Light markdown: '## ' line becomes a heading block
    expect(screen.getByText("Resumen")).toBeInTheDocument();
    // '- ' line becomes a list item
    expect(screen.getByText("Monto elevado")).toBeInTheDocument();
    // Plain lines stay paragraphs
    expect(screen.getByText("Texto final.")).toBeInTheDocument();
    // Model metadata still shown
    expect(screen.getByText(/Modelo: llama3/)).toBeInTheDocument();
  });

  it("copies the report text to the clipboard and flips to Copiado", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    useCompletedReport();
    renderDetail();

    const button = await screen.findByRole("button", {
      name: "Copiar reporte",
    });
    await userEvent.click(button);

    expect(writeText).toHaveBeenCalledWith(
      "## Resumen\n- Monto elevado\nTexto final.",
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Copiado" }),
      ).toBeInTheDocument();
    });
  });
});

/**
 * The Task 7 contract for this page, which is entirely a NON-migration: both of
 * its interactive controls are icon-only, and the design system has no
 * icon-only size and no variant whose resting/hover text matches either of
 * them. Minting one is a DESIGN change, so it is reported rather than made.
 *
 * What the tests do is pin the two treatments so the day a variant lands, the
 * change is visible as a change, and pin the accessibility cost they carry
 * today so it cannot become the accepted state by being nobody's decision.
 */
describe("TransactionDetail — primitives migration (non-migration, pinned)", () => {
  const completedReport = {
    transaction_id: "test-uuid",
    report_text: "## Resumen\n- Monto elevado\nTexto final.",
    model_name: "llama3",
    status: "completed",
    generation_time_ms: 120,
    created_at: new Date().toISOString(),
    error_detail: null,
  };

  it("the copy control keeps its square icon box, which no BTN_SIZES entry can express", async () => {
    server.use(
      http.get("*/api/v1/transactions/:id/report", () =>
        HttpResponse.json(completedReport),
      ),
    );
    renderDetail();

    const copy = await screen.findByRole("button", { name: "Copiar reporte" });
    // `h-8 w-8` is the point: at 32px with `px-3` (12px a side) the content box
    // would be 8px and the 16px glyph would overflow it, so the box would stop
    // being square. Both `BTN_SIZES` entries set horizontal padding.
    expect(copy.classList.contains("h-8")).toBe(true);
    expect(copy.classList.contains("w-8")).toBe(true);
    // Its own resting/hover text, which `secondary` would overwrite: it says
    // `text-slate-300` where this says `text-slate-400`, and the built CSS has
    // `.text-slate-300` (315) after `.text-slate-400` (316), so the variant
    // wins and a `className` override would be silently dropped.
    expect(copy.classList.contains("text-slate-400")).toBe(true);
    expect(copy.classList.contains("hover:text-slate-200")).toBe(true);
    // And the hover-on-text half, which no variant provides at all.
    expect(copy.classList.contains("enabled:hover:text-slate-200")).toBe(false);
    // The touch-target floor from the mobile retrofit, which must survive
    // whatever the eventual icon size is.
    expect(copy.classList.contains("max-md:min-h-[40px]")).toBe(true);
  });

  it("the not-found back control has an accessible name", async () => {
    // This test used to assert the OPPOSITE — that the control has no name —
    // on the reasoning that reporting a defect is better than quietly changing
    // the accessibility tree inside a tokenisation commit. It was the right call
    // about the COMMIT and the wrong call about the TEST: asserting a defect is
    // still asserting it, so it became the pinned expected state and would have
    // turned the fix into a red build.
    //
    // The fix landed in its own commit, which is what the original comment
    // actually asked for. So the defect is now recorded as fixed, and the
    // "report, do not fix" discipline is kept for the migrations that are
    // genuinely blocked.
    //
    // Why it matters: the control is an icon with no text, on the not-found
    // path. Without a name a screen reader announces "button" and stops — on
    // the only way out of the page.
    renderDetail();
    await screen.findByText("Detalle de Transacción");

    const back = screen.getByRole("button", { name: /volver al dashboard/i });
    expect(back).toBeTruthy();
    // Still icon-only visually: the name is not duplicated as visible text.
    expect(back.textContent?.trim()).toBe("");
    // The graphic itself is not read as content, and is not a tab stop.
    const svg = back.querySelector("svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(svg?.getAttribute("focusable")).toBe("false");
  });


  it("neither icon control carries a focus ring, and that is the cost of the gap", async () => {
    server.use(
      http.get("*/api/v1/transactions/:id/report", () =>
        HttpResponse.json(completedReport),
      ),
    );
    renderDetail();

    const copy = await screen.findByRole("button", { name: "Copiar reporte" });
    const header = document.querySelector("header")!;
    const back = header.querySelector("button")!;

    // Both rely on whatever the user agent draws, because the treatments they
    // carry were hand-rolled without `FOCUS_RING`. Focus IS still indicated —
    // just not by this design system, and not consistently with the eight
    // other sites that were fixed. Pinned so an `icon` size can add the ring in
    // the same change that introduces it.
    for (const el of [copy, back]) {
      expect(el.classList.contains("focus-visible:ring-2")).toBe(false);
      for (const cls of Array.from(el.classList)) {
        // A bare `focus:` would be worse: it paints on mouse click.
        expect(cls, `bare focus variant: ${cls}`).not.toMatch(/^focus:(?!-)/);
      }
    }
  });

  it("the page's own code carries no bare focus: variant", () => {
    for (const cls of DETAIL_CODE.split(/[\s"'`]+/)) {
      expect(cls, `bare focus variant: ${cls}`).not.toMatch(/^focus:(?!-)/);
    }
  });
});

const DETAIL_SOURCE = readFileSync(
  join(process.cwd(), "src", "pages", "TransactionDetail.tsx"),
  "utf-8",
);

/**
 * Source with block comments removed, so the page's own notes about the
 * treatments it kept are not counted as re-typing them, and the bare-`focus:`
 * scan does not match the word inside a comment.
 */
const DETAIL_CODE = DETAIL_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "");
