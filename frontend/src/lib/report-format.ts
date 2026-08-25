/**
 * Light markdown handling for LLM report text (Phase 2).
 *
 * The local model emits loose markdown-ish prose. This parser recognizes
 * ONLY the three conventions the UI styles — nothing else is interpreted:
 *   - lines starting with "### " → level-3 heading
 *   - lines starting with "## "  → level-2 heading
 *   - lines starting with "- "   → bullet item (consecutive bullets merge
 *     into one list block; a non-bullet line closes the list)
 * Everything else stays a plain paragraph (rendered whitespace-pre-wrap).
 *
 * Pure function: string in, immutable block list out.
 */

export type ReportBlock =
  | { type: "heading"; level: 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] };

export function parseReportLines(raw: string): ReportBlock[] {
  const blocks: ReportBlock[] = [];

  for (const line of raw.split("\n")) {
    if (line.startsWith("### ")) {
      blocks.push({ type: "heading", level: 3, text: line.slice(4).trim() });
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push({ type: "heading", level: 2, text: line.slice(3).trim() });
      continue;
    }
    if (line.startsWith("- ")) {
      const last = blocks[blocks.length - 1];
      if (last?.type === "list") {
        last.items.push(line.slice(2));
      } else {
        blocks.push({ type: "list", items: [line.slice(2)] });
      }
      continue;
    }
    // Blank separator lines produce no block; visual rhythm comes from
    // block margins at render time. Plain lines keep their content verbatim.
    if (line.trim() === "") continue;
    blocks.push({ type: "paragraph", text: line });
  }

  return blocks;
}
