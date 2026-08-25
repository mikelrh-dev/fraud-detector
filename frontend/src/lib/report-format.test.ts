import { describe, expect, it } from "vitest";
import { parseReportLines } from "./report-format";

describe("parseReportLines", () => {
  it("maps '### ' prefixed lines to level-3 headings", () => {
    expect(parseReportLines("### Detalle")).toEqual([
      { type: "heading", level: 3, text: "Detalle" },
    ]);
  });

  it("maps '## ' prefixed lines to level-2 headings", () => {
    expect(parseReportLines("## Resumen")).toEqual([
      { type: "heading", level: 2, text: "Resumen" },
    ]);
  });

  it("does not treat marker prefixes without a space as headings", () => {
    // "###No-space" and "##No-space" fall through to plain paragraphs
    expect(parseReportLines("###Sin espacio")).toEqual([
      { type: "paragraph", text: "###Sin espacio" },
    ]);
    expect(parseReportLines("##Sin espacio")).toEqual([
      { type: "paragraph", text: "##Sin espacio" },
    ]);
  });

  it("does not promote deeper hashes (#### stays plain)", () => {
    expect(parseReportLines("#### cuatro")).toEqual([
      { type: "paragraph", text: "#### cuatro" },
    ]);
  });

  it("groups consecutive '- ' bullets into a single list block", () => {
    expect(parseReportLines("- primero\n- segundo\n- tercero")).toEqual([
      { type: "list", items: ["primero", "segundo", "tercero"] },
    ]);
  });

  it("starts a NEW list after an intervening paragraph", () => {
    expect(
      parseReportLines("- a\n- b\nTexto intermedio\n- c"),
    ).toEqual([
      { type: "list", items: ["a", "b"] },
      { type: "paragraph", text: "Texto intermedio" },
      { type: "list", items: ["c"] },
    ]);
  });

  it("keeps plain lines as paragraphs and drops blank separator lines", () => {
    expect(parseReportLines("Primera línea\n\nSegunda línea")).toEqual([
      { type: "paragraph", text: "Primera línea" },
      { type: "paragraph", text: "Segunda línea" },
    ]);
  });

  it("parses a full LLM-style report end to end", () => {
    const raw = [
      "## Resumen",
      "",
      "La transacción presenta patrones inusuales.",
      "",
      "### Factores de riesgo",
      "- Monto elevado",
      "- Comercio nuevo",
      "",
      "Recomendación: revisión manual.",
    ].join("\n");

    expect(parseReportLines(raw)).toEqual([
      { type: "heading", level: 2, text: "Resumen" },
      { type: "paragraph", text: "La transacción presenta patrones inusuales." },
      { type: "heading", level: 3, text: "Factores de riesgo" },
      { type: "list", items: ["Monto elevado", "Comercio nuevo"] },
      { type: "paragraph", text: "Recomendación: revisión manual." },
    ]);
  });

  it("returns an empty array for empty input", () => {
    expect(parseReportLines("")).toEqual([]);
  });
});
