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

  it("does not treat the '2.' of a decimal as a list marker", () => {
    // Reachable now. The previous version of this test used
    // "El score fue de 1.5 sobre 100." — where the `1.5` sits MID-LINE. Both
    // patterns in the parser are `^`-anchored, so a line beginning with "El"
    // cannot match either one whatever they contain. The test passed because
    // the input was unreachable, not because the parser handled a decimal.
    //
    // This input starts with the number, so the anchors are satisfied and the
    // lookahead is what has to reject it: `1` then `.` then `5`, not a space.
    const blocks = parseReportLines("1.5 puntos sobre 100.");
    expect(blocks[0].type).toBe("paragraph");
    expect(blocks).toHaveLength(1);
  });

  it("requires a space after the number, so '2024.Sin' is not a list item", () => {
    // The reachable half of the original "Facturado en 2024. Sin incidencias."
    // case. A marker is digits, a dot, a SPACE. Drop the space requirement and
    // this becomes a list item whose text is "Sin incidencias." — the digit
    // swallowing the next token, which is the failure the test exists to catch.
    const blocks = parseReportLines("2024.Sin incidencias.");
    expect(blocks[0].type).toBe("paragraph");
    expect(blocks).toHaveLength(1);
  });

  it("never reads a bare year at the start of a line as a section heading", () => {
    // Reachable, and a real limit rather than an oversight: at the start of a
    // line `2024. Sin incidencias.` IS an ordered-list marker, and no amount of
    // regex distinguishes it from one. The parser reads it as a list item.
    //
    // What must hold, and is asserted here, is the narrower claim both original
    // tests were reaching for: it never becomes a HEADING. Headings additionally
    // require `**Label**:`, so a year cannot satisfy that however the marker
    // rules are tuned. If this starts producing a heading, the section structure
    // is being invented out of prose.
    const blocks = parseReportLines("2024. Sin incidencias.");
    expect(blocks.some((b) => b.type === "heading")).toBe(false);
  });
});

describe("parseReportLines — a bold-lead-in LIST is not a set of sections", () => {
  // The defect these guard: ANY `N. **Label**: rest` became a level-2 heading,
  // which is string-identical to a bold-lead-in ordered list. A five-item list
  // became five section headings — five top rules and size steps invented out
  // of a list the model never wrote as structure.
  //
  // The rule is now: only 1, 2, 3, arriving consecutively from a 1. See the
  // ASSUMPTION block above `parseReportLines` — these tests pin the PARSER's
  // behaviour on hand-written strings. They say nothing about whether the model
  // complies, which is unobservable without the container.

  const boldLeadInList = [
    "1. **Monto**: supera el umbral habitual del usuario.",
    "2. **Horario**: la operación ocurrió de madrugada.",
    "3. **Comercio**: el categoría es de riesgo alto.",
    "4. **Frecuencia**: segundo intento en cinco minutos.",
    "5. **Origen**: país distinto al habitual del titular.",
  ].join("\n");

  it("stops promoting at the third item, so a longer list cannot become all sections", () => {
    // HONEST LIMIT, asserted rather than wished away: the first THREE items of
    // this list ARE rendered as headings, and no rule can prevent that. They
    // are numbered 1, 2, 3 with bold lead-ins from a `1` — byte-for-byte the
    // prompt's contract. A parser that demoted them would also demote real
    // sections. This is the residual ambiguity the bet accepts, and the test
    // says so instead of asserting a protection that does not exist.
    //
    // What the rule DOES buy is the cap: items 4 and 5 cannot become headings,
    // so a list of any length stops being "all sections" at three.
    const blocks = parseReportLines(boldLeadInList);

    expect(blocks.filter((b) => b.type === "heading")).toHaveLength(3);
    const lists = blocks.filter((b) => b.type === "list");
    expect(lists).toHaveLength(1);
    if (lists[0].type !== "list") throw new Error("expected list");
    expect(lists[0].items).toHaveLength(2);
  });

  it("keeps the label text of a demoted item, with the bold markers unwrapped", () => {
    // The rejected lines fall through to the ordered-list rule, which strips
    // `**`. A demoted item that rendered as "****Monto****: ..." would be a new
    // leak of the same class the parser exists to prevent.
    const blocks = parseReportLines(boldLeadInList);
    const list = blocks.find((b) => b.type === "list");
    if (!list || list.type !== "list") throw new Error("expected list");

    expect(list.items[0]).toBe("Frecuencia: segundo intento en cinco minutos.");
    expect(list.items.join(" ")).not.toContain("*");
  });

  it("renders a bold-lead-in list that does NOT start at 1 as entirely a list", () => {
    // The fully protected case, and the one the "not starting at 1" half of the
    // rule buys. A list numbered 2..6 is unambiguous — no section sequence
    // starts at 2 — so every item stays a list item.
    const blocks = parseReportLines(
      [
        "2. **Monto**: supera el umbral habitual.",
        "3. **Horario**: la operación ocurrió de madrugada.",
        "4. **Comercio**: categoría de riesgo alto.",
        "5. **Frecuencia**: segundo intento en cinco minutos.",
        "6. **Origen**: país distinto al habitual.",
      ].join("\n"),
    );

    expect(blocks.some((b) => b.type === "heading")).toBe(false);
    const only = blocks[0];
    if (only.type !== "list") throw new Error("expected list");
    expect(only.items).toHaveLength(5);
  });

  it("does not read a heading out of a list that starts at 2", () => {
    // "Numbering begins at 1". A document whose first numbered bold lead-in is
    // 2 is not the prompt's shape, and the `2` must not consume the slot.
    const blocks = parseReportLines("2. **Puntajes**: treinta y cinco puntos.");

    expect(blocks.some((b) => b.type === "heading")).toBe(false);
    expect(blocks[0].type).toBe("list");
  });

  it("still finds 1 after a rejected 2, because a rejection consumes nothing", () => {
    // The counter advances only when a heading is TAKEN. If a stray `2. **` at
    // the top of a report consumed the 2, a real section 1 further down would
    // be demoted to a list item and the report would lose its opening heading.
    const blocks = parseReportLines(
      ["2. **Previsto**: no aplica.", "1. **Análisis**: treinta y cinco puntos."].join("\n"),
    );

    const headings = blocks.filter((b) => b.type === "heading");
    expect(headings).toHaveLength(1);
    if (headings[0].type !== "heading") throw new Error("expected heading");
    expect(headings[0].text).toBe("Análisis");
  });

  it("stops at three: a fourth and fifth are list items", () => {
    const blocks = parseReportLines(
      [
        "1. **Uno**: a.",
        "2. **Dos**: b.",
        "3. **Tres**: c.",
        "4. **Cuatro**: d.",
        "5. **Cinco**: e.",
      ].join("\n"),
    );

    expect(blocks.filter((b) => b.type === "heading")).toHaveLength(3);
    expect(blocks.filter((b) => b.type === "list")).toHaveLength(1);
  });

  it("rejects a gap in the sequence rather than skipping to fill it", () => {
    // 1, 2, 4 — "increments consecutively". The 4 is not the next number, so it
    // is a list item. It does not retroactively promote a later 4 either.
    const blocks = parseReportLines(
      ["1. **Uno**: a.", "2. **Dos**: b.", "4. **Cuatro**: d."].join("\n"),
    );

    const headings = blocks.filter((b) => b.type === "heading");
    expect(headings).toHaveLength(2);
    expect(blocks.filter((b) => b.type === "list")).toHaveLength(1);
  });

  it("counts across intervening prose and bullets", () => {
    // The sequence is a property of the DOCUMENT, not of adjacent lines. A
    // report that opens with prose and interleaves a bullet list must still
    // find its sections — this is the shape PROMPT_SHAPED_REPORT has, and the
    // rendering suite depends on it.
    const blocks = parseReportLines(
      [
        "La transacción requiere atención.",
        "",
        "1. **Análisis**: treinta y cinco puntos.",
        "",
        "- Regla disparada: monto",
        "- Regla disparada: horario",
        "",
        "2. **Decisión**: clasificada para revisión.",
      ].join("\n"),
    );

    expect(blocks.filter((b) => b.type === "heading")).toHaveLength(2);
  });

  it("leaves '## ' headings alone — that rule is independent of the counter", () => {
    // `## ` is a separate, shape-based branch. The narrowing must not have
    // touched it, and a `##` report with no numbered sections at all is common.
    const blocks = parseReportLines("## Resumen\nTexto.\n## Detalle\nMás texto.");

    const headings = blocks.filter((b) => b.type === "heading");
    expect(headings).toHaveLength(2);
  });

  it("does not invent a heading from a bold colon that is not a list marker", () => {
    // Bold lead-in prose, mid-line and line-start, with no number. Nothing
    // here may be promoted — this is the "structure out of prose" failure in
    // its purest form.
    const blocks = parseReportLines(
      ["**Nota importante**: el análisis es explicativo.", "Motivo: monto elevado."].join("\n"),
    );

    expect(blocks.some((b) => b.type === "heading")).toBe(false);
    expect(blocks.every((b) => b.type === "paragraph")).toBe(true);
  });
});

describe("parseReportLines — a restarted bold-lead-in list is a list, not a torn one", () => {
  // W-2: the ASSUMPTION block claimed the narrowing "fails toward LESS
  // structure". It did not, and the case below is how it failed.
  //
  // `nextSectionNumber` was a document-global counter with no notion of the
  // run having ended. Once `1. **A**` was spent the counter sat at 2, so a
  // bold-lead-in list that RESTARTED at 1 further down had its first item
  // demoted (1 !== 2) and its second item PROMOTED (2 === 2):
  //
  //   1. **A**: a        -> heading
  //   - nota             -> list
  //   1. **B**: b        -> list item
  //   2. **C**: c        -> heading, with mt-6 border-t
  //
  // One list, rendered as a list item, then a section divider, then more of
  // the same list. That is structure read out of a list, which is the exact
  // direction the comment said the rule failed in.
  //
  // The fix is the restart rule: a number at or below one already spent means
  // the document started numbering over, so the section run closes and the
  // whole restart goes to the list.
  //
  // What this is NOT is contiguity from the first block, which is the obvious
  // stronger rule and was measured before being rejected: it takes the
  // prompt's own output — a paragraph, then 1., 2., 3. — to ZERO headings,
  // and that is the D6-1 defect this file exists to fix. `mt-6 border-t` and
  // the numbered-section styling would go dead in production again. Prose
  // before the first section, and bullets between sections, are the shape the
  // prompt produces, so they cannot be what closes the run. A restart can.

  it("does not promote the second item of a list that restarted at 1", () => {
    // The exact traced input, unchanged.
    const blocks = parseReportLines(
      ["1. **A**: a", "- nota", "1. **B**: b", "2. **C**: c"].join("\n"),
    );

    const headings = blocks.filter((b) => b.type === "heading");
    expect(headings).toHaveLength(1);
    if (headings[0].type !== "heading") throw new Error("expected heading");
    expect(headings[0].text).toBe("A");
  });

  it("keeps the restarted list whole — no item is split off into a heading", () => {
    // The tear is not "one heading too many", it is a list cut in half. The
    // items that belong to the restart must arrive together, in one list, in
    // order, with the bullet that was already there.
    const blocks = parseReportLines(
      ["1. **A**: a", "- nota", "1. **B**: b", "2. **C**: c"].join("\n"),
    );

    const lists = blocks.filter((b) => b.type === "list");
    expect(lists).toHaveLength(1);
    if (lists[0].type !== "list") throw new Error("expected list");
    expect(lists[0].items).toEqual(["nota", "B: b", "C: c"]);
  });

  it("closes the run for the rest of the document once a number repeats", () => {
    // The run does not recover. `1. **C**` repeats a spent number, so from
    // there nothing is a section again — including a `3.` that would
    // otherwise have been the prompt's third and final heading.
    const blocks = parseReportLines(
      [
        "1. **A**: a.",
        "2. **B**: b.",
        "1. **C**: c.",
        "2. **D**: d.",
        "3. **E**: e.",
      ].join("\n"),
    );

    const headings = blocks.filter((b) => b.type === "heading");
    expect(headings.map((h) => (h.type === "heading" ? h.text : "")).join(",")).toBe(
      "A,B",
    );
    const lists = blocks.filter((b) => b.type === "list");
    expect(lists).toHaveLength(1);
    if (lists[0].type !== "list") throw new Error("expected list");
    expect(lists[0].items).toEqual(["C: c.", "D: d.", "E: e."]);
  });

  it("is discriminating: the SAME shape with no restart still yields both sections", () => {
    // The control, and the reason the pair above is a test rather than a
    // tautology. These two documents differ only in whether the numbering
    // restarts. If the rule above were "any number mismatch ends the run", or
    // "prose and bullets end the run", this would fail — and with it the
    // prompt's own output, which is prose, then 1., 2., 3.
    const withRestart = parseReportLines(
      ["1. **A**: a.", "1. **B**: b.", "2. **C**: c."].join("\n"),
    );
    const withoutRestart = parseReportLines(
      ["1. **A**: a.", "2. **B**: b.", "3. **C**: c."].join("\n"),
    );

    expect(withRestart.filter((b) => b.type === "heading")).toHaveLength(1);
    expect(withoutRestart.filter((b) => b.type === "heading")).toHaveLength(3);
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
