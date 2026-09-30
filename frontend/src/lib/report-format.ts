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
 *   - `1. **Label**: rest`               → heading "Label" + paragraph
 *   - `1. ` / `2. ` … (no bold label)    → ordered list, consecutive items merge
 *   - `- `                               → bullet, consecutive items merge
 *   - `**text**`                         → bold, unwrapped everywhere
 * Everything else stays a plain paragraph (rendered whitespace-pre-wrap).
 *
 * The numbered-heading rule is deliberately NARROWER than its shape: only the
 * 1, 2, 3 the prompt asks for become headings, and only when they arrive
 * consecutively from a 1. A `N. **Label**: rest` outside that sequence is an
 * ordered-list item, because a bold-lead-in list and a section heading are the
 * same string and the model writes both. That restriction rests on an
 * UNVERIFIED assumption about model output — read the ASSUMPTION block above
 * `parseReportLines` before changing the rule, and do not widen it on a hunch.
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
 * How many top-level sections the prompt asks for.
 *
 * `_PROMPT_TEMPLATE` in `src/services/llm.py:41-45` contracts for exactly
 * three, numbered 1, 2 and 3, each with a bold label.
 */
const SECTION_COUNT = 3;

/**
 * ============================================================================
 * ASSUMPTION, NOT A FACT. This is a bet about output nobody has observed.
 * ============================================================================
 *
 * The heading rule below is narrower than its shape suggests, and the reason is
 * that the real output of the local model is UNOBSERVABLE in this repository:
 * there is no captured transcript of what `llama3` actually returns for any
 * prompt in `src/services/llm.py`. Nobody has watched it answer. So the shape of
 * the model output is a CONTRACT WE HOPE IT KEEPS, not an observation, and the
 * parser is written against the contract.
 *
 * WHAT IS BEING ASSUMED
 *   1. The report's sections are numbered 1, 2, 3 — starting at 1, with no gap.
 *   2. A line is a section heading only if its number is the next one expected.
 *   3. At most three such lines exist per report.
 *
 * WHY THE RULE IS NARROW RATHER THAN SHAPE-BASED
 *   The previous rule promoted ANY `N. **Label**: rest` to a level-2 heading.
 *   That is indistinguishable from a bold-lead-in ordered list, which is an
 *   ordinary thing for a language model to write. A five-item list with bold
 *   lead-ins became five section headings: five top rules and five size steps
 *   imposed on a list the model never intended as structure.
 *
 * WHY THE ERROR IS ASYMMETRIC, and which way it now fails
 *   Reading prose AS structure is the expensive mistake. It invents document
 *   outline that the model did not write, and the reader cannot tell, because
 *   the invented outline looks exactly like a real one. The opposite mistake —
 *   reading real structure as prose — costs a heading: the text still renders,
 *   still has its bold label, and is merely less separated.
 *
 *   So when this bet is wrong, it now fails toward LESS structure: a report the
 *   model formatted as `##` sections or as a numbered list with bold lead-ins
 *   renders its section titles as list items. No sentence is dropped, no
 *   asterisk leaks, nothing is reordered. That is the intended direction.
 *
 * WHAT WOULD OVERTURN IT
 *   One captured transcript of a real report. If the model reliably emits
 *   `##`-style headings instead, `## ` already handles that above and this
 *   rule is simply never reached. If it emits sections numbered from something
 *   other than 1, or with a gap, this rule under-reports and the fix is to
 *   widen it against evidence rather than to guess again.
 *
 * WHAT THE RULE DOES NOT SOLVE — the ambiguity it cannot remove
 *   A bold-lead-in list numbered 1, 2, 3 from a `1` is BYTE-FOR-BYTE the
 *   prompt's contract. Its first three items will be rendered as headings, and
 *   no rule distinguishes them from real sections without also demoting the
 *   real ones. This is the price of the bet and it is not small: a model that
 *   likes bold lead-ins and happens to start at 1 gets three section rules
 *   imposed on a list.
 *
 *   The rule caps that at three and rejects anything not starting at 1, so a
 *   list of any length cannot become an all-heading document. Beyond the cap
 *   the misreads go the safe way. `test_stops_promoting_at the third item`
 *   asserts the cap; nothing asserts the first three are safe, because they are
 *   not, and a test claiming otherwise would be the exact defect this whole
 *   exercise is about.
 *
 * WHAT IT DOES NOT ESTABLISH
 *   That the model complies. Compliance is unverified and unverifiable without
 *   the container, and no test in this file can reach it — these tests pin the
 *   parser's behaviour on hand-written strings, not the model's behaviour.
 */

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

  // The next number that would be accepted as a section heading. Starts at 1
  // and advances ONLY when a heading is actually taken, so a `2. **…**` that
  // arrives before any `1. **…**` is rejected and does not consume the `2`.
  let nextSectionNumber = 1;

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
    //
    // ...but only for the sequence the prompt actually asked for. See
    // SECTION_COUNT and the assumption block above the function: shape alone is
    // not enough to call a line a heading.
    const boldHeading = NUMBERED_BOLD_HEADING.exec(line);
    if (boldHeading) {
      const [, number, label, rest] = boldHeading;
      const expected = nextSectionNumber;
      if (Number(number) === expected && expected <= SECTION_COUNT) {
        // A level-2-equivalent section: it divides the report, so it gets the
        // top rule and the size step. The model was told to number its three
        // top-level sections, and that is the structure being rendered.
        blocks.push({ type: "heading", level: 2, text: label.trim() });
        if (rest.trim() !== "") {
          blocks.push({ type: "paragraph", text: stripBold(rest.trim()) });
        }
        nextSectionNumber = expected + 1;
        continue;
      }
      // Anything else — a number that did not start at 1, a gap in the
      // sequence, or an item past the third — falls through to the ordered-list
      // rule below and is rendered as a list item. The bold markers are
      // unwrapped there, so it reads as an emphasized list entry rather than as
      // a section divider.
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
