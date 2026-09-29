/**
 * D6-1 / D6-2 / D6-3 — the parser must understand the format the prompt asks for.
 *
 * `src/services/llm.py` (the prompt template, which is a contract with the
 * model and is NOT changed by this fix) asks for a numbered shape:
 *
 *   1. **Análisis de Puntajes**: Explica qué puntajes contribuyeron ...
 *
 * and names three sections with bold labels. The parser at the time of
 * `a657c53` recognized exactly three things: `### `, `## ` and `- `. So:
 *
 *   - `1. **Análisis de Puntajes**: ...` parsed as a PARAGRAPH, literal `**`
 *     included. The redesign's level-3 `uppercase tracking-wider` styling never
 *     fired, and a reader saw asterisks.
 *   - `## Análisis` as an inline lead-in was a paragraph, not a heading, so
 *     `mt-6 border-t` never fired either.
 *
 * The audit's finding is that `mt-6 border-t`, `uppercase tracking-wider` and
 * `first:mt-0` are DEAD CSS in production. This file proves the format the
 * prompt actually requests produces headings and lists, and that no literal
 * `**` survives to the DOM.
 */

import { describe, it, expect } from "vitest";
import { parseReportLines } from "./report-format";

/**
 * The shape `LLMService.build_prompt` asks for, transcribed from
 * `_PROMPT_TEMPLATE` in src/services/llm.py:38-47. Copied rather than
 * generated: a test that derives its fixture from the parser proves nothing.
 */
const PROMPT_REQUESTED_REPORT = `La transacción presenta un patrón que requiere atención.

1. **Análisis de Puntajes**: El motor de reglas aportan 35 puntos por monto elevado, mientras el modelo ML no aportó señal. La combinación risultante fue 52 sobre 100.

2. **Explicación de la Decisión**: El sistema clasificó esta transacción como **REQUIERE REVISIÓN** porque el puntaje ensemble de 52.0 se encuentra por debajo del umbral de 70.0.

3. **Factores Contextuales**: La operación ocurrió a las 03:14, fuera del horario habitual del comercio, y se trata del segundo intento de cobro en cinco minutos.

Nota: el análisis es explicativo y no modifica la decisión ya tomada.`;

describe("parseReportLines — the format the prompt requests", () => {
  it("reads a numbered bold section heading as a heading, not a paragraph", () => {
    const blocks = parseReportLines(
      "1. **Análisis de Puntajes**: Explica qué puntajes contribuyeron.",
    );
    expect(blocks[0].type).toBe("heading");
  });

  it("strips the bold markers from the heading text", () => {
    const blocks = parseReportLines("1. **Análisis de Puntajes**: detalle");
    const heading = blocks[0];
    expect(heading.type).toBe("heading");
    if (heading.type !== "heading") throw new Error("expected heading");
    expect(heading.text).toBe("Análisis de Puntajes");
    expect(heading.text).not.toContain("*");
  });

  it("keeps the prose after the colon as a paragraph", () => {
    const blocks = parseReportLines(
      "1. **Análisis de Puntajes**: Explica qué puntajes contribuyeron al resultado.",
    );
    expect(blocks.map((b) => b.type)).toEqual(["heading", "paragraph"]);
  });

  it("produces three headings from the prompt's three requested sections", () => {
    const blocks = parseReportLines(PROMPT_REQUESTED_REPORT);
    const headings = blocks.filter((b) => b.type === "heading");
    expect(headings).toHaveLength(3);
  });

  it("no block anywhere in the prompt's own output contains a literal '**'", () => {
    const blocks = parseReportLines(PROMPT_REQUESTED_REPORT);
    for (const block of blocks) {
      const text =
        block.type === "list" ? block.items.join(" ") : (block as { text: string }).text;
      expect(text).not.toContain("**");
    }
  });

  it("does not treat the '2.' of a decimal or a list number as a heading", () => {
    // '1.5' must not parse as heading '1' with a stray '.5'.
    const blocks = parseReportLines("El score fue de 1.5 sobre 100.");
    expect(blocks[0].type).toBe("paragraph");
  });

  it("requires a space after the number so '2024.' is not a heading", () => {
    const blocks = parseReportLines("Facturado en 2024. Sin incidencias.");
    expect(blocks.every((b) => b.type === "paragraph")).toBe(true);
  });
});

describe("parseReportLines — the formats that already worked", () => {
  it("still reads '## ' as a level-2 heading", () => {
    const blocks = parseReportLines("## Análisis de Puntajes");
    expect(blocks[0]).toEqual({ type: "heading", level: 2, text: "Análisis de Puntajes" });
  });

  it("still reads '### ' as a level-3 heading", () => {
    const blocks = parseReportLines("### Detalle");
    expect(blocks[0]).toEqual({ type: "heading", level: 3, text: "Detalle" });
  });

  it("still merges consecutive '- ' lines into one list", () => {
    const blocks = parseReportLines("- uno\n- dos");
    expect(blocks).toEqual([{ type: "list", items: ["uno", "dos"] }]);
  });

  it("reads a numbered list as a list, so the styling has something to style", () => {
    const blocks = parseReportLines("1. primero\n2. segundo");
    expect(blocks).toEqual([{ type: "list", items: ["primero", "segundo"] }]);
  });

  it("keeps a prose-first report's first block a paragraph", () => {
    const blocks = parseReportLines(PROMPT_REQUESTED_REPORT);
    expect(blocks[0].type).toBe("paragraph");
  });
});

describe("parseReportLines — inline bold does not leak asterisks", () => {
  it("strips bold from a paragraph", () => {
    const blocks = parseReportLines("El sistema lo marcó como **REQUIERE REVISIÓN** hoy.");
    const paragraph = blocks[0];
    if (paragraph.type !== "paragraph") throw new Error("expected paragraph");
    expect(paragraph.text).toBe("El sistema lo marcó como REQUIERE REVISIÓN hoy.");
  });

  it("strips bold from a list item", () => {
    const blocks = parseReportLines("- **Regla 1**: monto elevado");
    expect(blocks[0]).toEqual({ type: "list", items: ["Regla 1: monto elevado"] });
  });

  it("does not eat text between two bold spans", () => {
    const blocks = parseReportLines("**uno** y **dos** y tres");
    const paragraph = blocks[0];
    if (paragraph.type !== "paragraph") throw new Error("expected paragraph");
    expect(paragraph.text).toBe("uno y dos y tres");
  });

  it("leaves an unpaired asterisk alone rather than deleting content", () => {
    const blocks = parseReportLines("El score fue de 52 * 100.");
    const paragraph = blocks[0];
    if (paragraph.type !== "paragraph") throw new Error("expected paragraph");
    expect(paragraph.text).toBe("El score fue de 52 * 100.");
  });
});
