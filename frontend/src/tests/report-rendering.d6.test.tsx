/**
 * D6-1 / D6-2 / D6-3, asserted on the RENDERED page rather than the parser.
 *
 * `report-format.d6.test.ts` proves the parser understands the prompt's shape.
 * This proves the consequence reaches the DOM, which is what the audit's
 * finding was about: the redesign's `mt-6 border-t`, `uppercase tracking-wider`
 * and `first:mt-0` were dead CSS, and `**` reached the reader as asterisks.
 *
 * A parser test cannot see any of that. A parser can be correct while the
 * component still never routes a block into the branch that carries the class.
 *
 * The classes are asserted on the element, not on a computed style: jsdom has
 * no stylesheet, and the real stylesheet is a Tailwind build. What is provable
 * without a browser is that the utility is PRESENT on the element that is
 * supposed to carry it. That is the boundary of this claim, stated here rather
 * than left for a reader to assume.
 */

import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import TransactionDetail from "../pages/TransactionDetail";
import { server } from "./mocks/server";
import type { ReactNode } from "react";

/** The shape `_PROMPT_TEMPLATE` in src/services/llm.py asks the model for. */
const PROMPT_SHAPED_REPORT = [
  "La transacción presenta un patrón que requiere atención.",
  "",
  "1. **Análisis de Puntajes**: El motor de reglas aportó 35 puntos por monto elevado.",
  "",
  "2. **Explicación de la Decisión**: El sistema la clasificó como **REQUIERE REVISIÓN**.",
].join("\n");

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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

/** Serves `text` as the completed report for every test in the file. */
function givenReport(text: string) {
  server.use(
    http.get("*/api/v1/transactions/:id/report", () =>
      HttpResponse.json({
        transaction_id: "test-uuid",
        report_text: text,
        model_name: "llama3",
        status: "completed",
        generation_time_ms: 120,
        created_at: new Date().toISOString(),
        error_detail: null,
      }),
    ),
  );
}

async function renderReportBody(text: string): Promise<HTMLElement> {
  givenReport(text);
  render(<TransactionDetail />, { wrapper: createWrapper() });
  await waitFor(() => {
    expect(screen.getByTestId("report-body")).toBeInTheDocument();
  });
  return screen.getByTestId("report-body");
}

describe("D6-1 — the prompt's shape produces styled blocks in the DOM", () => {
  it("renders a numbered bold section as a heading element's text, without asterisks", async () => {
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    const heading = within_(body, "Análisis de Puntajes");
    expect(heading).toBeInTheDocument();
    expect(heading.textContent).toBe("Análisis de Puntajes");
  });

  it("puts the level-2 treatment on the heading the prompt asked for", async () => {
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    const heading = within_(body, "Análisis de Puntajes");
    // `mt-6 border-t` — dead CSS before this fix, because the prompt's shape
    // never produced a heading for these classes to apply to.
    expect(heading.className).toContain("border-t");
    expect(heading.className).toContain("mt-6");
    expect(heading.className).toContain("text-lg");
  });

  it("keeps the prose after the section label as its own paragraph", async () => {
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    const prose = within_(
      body,
      "El motor de reglas aportó 35 puntos por monto elevado.",
    );
    expect(prose.tagName).toBe("P");
  });

  it("no rendered text anywhere in the report contains a literal '**'", async () => {
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    expect(body.textContent).not.toContain("**");
  });

  it("strips inline bold from prose too, not only from headings", async () => {
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    const prose = within_(
      body,
      "El sistema la clasificó como REQUIERE REVISIÓN.",
    );
    expect(prose).toBeInTheDocument();
    expect(prose.textContent).not.toContain("*");
  });
});

describe("D6-2 — the measure is on the container, so it covers every block type", () => {
  it("caps the report container, not the paragraph", async () => {
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    expect(body.className).toContain("max-w-[68ch]");
  });

  it("does not cap individual paragraphs, which is what left a ragged edge", async () => {
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    const paragraphs = Array.from(body.querySelectorAll("p"));
    expect(paragraphs.length).toBeGreaterThan(0);
    for (const paragraph of paragraphs) {
      expect(paragraph.className).not.toContain("max-w-");
    }
  });

  it("applies to a list-bearing report as well", async () => {
    const body = await renderReportBody("## Resumen\n- Monto elevado\n- Nocturno");

    expect(body.className).toContain("max-w-[68ch]");
    expect(body.querySelector("ul")).toBeInTheDocument();
  });
});

describe("D6-3 — the first-block reset survives a prose-first report", () => {
  it("strips the top rule from a level-2 heading that IS first", async () => {
    const body = await renderReportBody(
      "## Análisis de Puntajes\nDetalle del análisis.",
    );

    const heading = within_(body, "Análisis de Puntajes");
    expect(heading.className).toContain("border-t-0");
    expect(heading.className).toContain("mt-0");
  });

  it("keeps the top rule when the report opens with prose", async () => {
    // The defect: `first:mt-0` matched the first CHILD, and a prose-first
    // report's first child is a paragraph. Nothing about the CSS could
    // distinguish "no rule needed at the top of the report" from "this
    // paragraph happens to be first".
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    const heading = within_(body, "Análisis de Puntajes");
    expect(heading.className).toContain("border-t");
    expect(heading.className).not.toContain("border-t-0");
    expect(heading.className).toContain("mt-6");
  });

  it("keeps the rule on a second section even when the first is a heading", async () => {
    const body = await renderReportBody(
      "## Primero\nTexto.\n## Segundo\nMás texto.",
    );

    expect(within_(body, "Primero").className).toContain("border-t-0");
    // `toContain("border-t")` cannot make this assertion. `border-t` is a
    // substring of `border-t-0`, and `border-t` is in the BASE class of every
    // level-2 heading — so it is present whether or not the reset was applied.
    // The claim this test exists to make is that `Segundo` does not carry the
    // reset, and only a negative assertion can say that.
    expect(within_(body, "Segundo").className).not.toContain("border-t-0");
  });

  it("no longer relies on a CSS :first selector at all", async () => {
    // A `:first` variant cannot express "first section"; its presence is the
    // shape of the bug.
    const body = await renderReportBody(PROMPT_SHAPED_REPORT);

    expect(body.innerHTML).not.toContain("first:");
  });
});

/** `within` from testing-library, narrowed for the single-node lookups here. */
function within_(root: HTMLElement, text: string): HTMLElement {
  const found = Array.from(root.querySelectorAll("p, li, h2, h3")).find(
    (el) => el.textContent?.trim() === text,
  );
  if (!found) {
    throw new Error(
      `no block with text ${JSON.stringify(text)}; body was ${JSON.stringify(root.textContent)}`,
    );
  }
  return found as HTMLElement;
}
