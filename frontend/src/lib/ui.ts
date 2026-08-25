/**
 * Shared Tailwind class fragments for data-dense surfaces (tables, cards).
 *
 * WHY A MODULE: numeric alignment used to be re-typed per page and drifted
 * (some columns left-aligned, others mono-only). These constants are the
 * single source — import them, don't copy class strings.
 */

/**
 * Numeric cells (amounts, scores): right-aligned, monospace, fixed-width
 * digits so decimal points line up vertically when scanning a column.
 */
export const NUMERIC_CELL = "text-right font-mono tabular-nums";

/** Base chrome shared by every unified table header cell (DESIGN.md — Tables). */
const TABLE_HEADER_BASE =
  "px-4 py-3 text-[11px] font-medium uppercase tracking-wider text-slate-400";

/** Standard left-aligned table header cell. */
export const TABLE_HEADER_CELL = `text-left ${TABLE_HEADER_BASE}`;

/** Right-aligned table header cell for numeric columns. */
export const TABLE_HEADER_NUMERIC = `text-right ${TABLE_HEADER_BASE}`;
