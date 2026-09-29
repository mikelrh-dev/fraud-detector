/**
 * Light markdown handling for LLM report text.
 *
 * The local model emits loose markdown-ish prose, and the format it emits is
 * the format `src/services/llm.py` asks for. That prompt (a contract with the
 * model — NOT changed by this work) requests a NUMBERED shape with bold
 * section labels:
 *
 *   1. **Análisis de Puntajes**: Explica qué puntajes contribuyeron ...
 *
 * The parser at the time of `a657c53` recognized only `### `, `## ` and `- `,
 * so every one of those lines arrived as a paragraph carrying its literal
 * `**`. Three classes of styling in the report redesign were consequently dead
 * in production: the level-3 `uppercase tracking-wider`, the level-2
 * `mt-6 border-t`, and the `:first` reset that only ever matched a heading in
 * first position.
 *
 * What is recognized, all of it observable from the prompt's own output:
 *   - `## ` / `### `                     → level-2 / level-3 heading
 *   - `N. **Label**: rest`               → heading "Label" + paragraph
 *   - `1. ` / `2. ` … (no bold label)    → ordered list, consecutive items merge
 *   - `- `                               → bullet, consecutive items merge
 *   - `**text**`                         → bold, unwrapped everywhere
 * Everything else stays a plain paragraph (rendered whitespace-pre-wrap).
 *
 * Not implemented, deliberately: nesting (`> `, indented sub-items), tables,
 * and inline code. A partial implementation of a format the model does not
 * emit is code nothing exercises; anything unrecognized degrades to a
 * paragraph, which is what it did before.
 *
 * Pure function: string in, immutable block list out.
 */

export type ReportBlock =
  | { type: "heading"; level: 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] };

/** `12.` — one or more digits, a dot, then a single space. */
const ORDERED_ITEM = /^(\d+)\. (?=\S)/;

/** `**Label**: rest` — the prompt's own section shape. */
const NUMBERED_BOLD_HEADING = /^(\d+)\. \*\*([^*]+)\*\*: *([\s\S]*)$/;

/**
 * Unwrap `**text**` → `text`, globally.
 *
 * Only PAIRED spans are touched. An unpaired `*` is left exactly as it was:
 * deleting it would silently remove a character the model emitted, and "52 *
 * 100" must not become "52 100".
 */
function stripBold(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, "$1");
}

function pushItem(blocks: ReportBlock[], item: string): void {
  const last = blocks[blocks.length - 1];
  if (last?.type === "list") {
    last.items.push(item);
  } else {
    blocks.push({ type: "list", items: [item] });
  }
}

export function parseReportLines(raw: string): ReportBlock[] {
  const blocks: ReportBlock[] = [];

  for (const line of raw.split("\n")) {
    if (line.startsWith("### ")) {
      blocks.push({ type: "heading", level: 3, text: stripBold(line.slice(4).trim()) });
      continue;
    }
    if (line.startsWith("## ")) {
      blocks.push({ type: "heading", level: 2, text: stripBold(line.slice(3).trim()) });
      continue;
    }

    // The prompt's requested section shape. Checked before the ordered-list
    // rule because `1. ` is a prefix of `1. **`: read as a list item it would
    // leave the asterisks in the DOM and the line would be a bullet where the
    // model wrote a section heading.
    const boldHeading = NUMBERED_BOLD_HEADING.exec(line);
    if (boldHeading) {
      const [, , label, rest] = boldHeading;
      // A level-2-equivalent section: it divides the report, so it gets the
      // top rule and the size step. The model was told to number its three
      // top-level sections, and that is the structure being rendered.
      blocks.push({ type: "heading", level: 2, text: label.trim() });
      if (rest.trim() !== "") {
        blocks.push({ type: "paragraph", text: stripBold(rest.trim()) });
      }
      continue;
    }

    if (line.startsWith("- ")) {
      pushItem(blocks, stripBold(line.slice(2)));
      continue;
    }

    if (ORDERED_ITEM.test(line)) {
      pushItem(blocks, stripBold(line.replace(ORDERED_ITEM, "")));
      continue;
    }

    // Blank separator lines produce no block; visual rhythm comes from
    // block margins at render time. Plain lines keep their content verbatim,
    // minus bold markers.
    if (line.trim() === "") continue;
    blocks.push({ type: "paragraph", text: stripBold(line) });
  }

  return blocks;
}
