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

/**
 * Focus treatment, shared by every interactive primitive.
 *
 * WHY A CONSTANT: the audit found 15 sites writing `outline-none` followed by
 * `focus:ring-2`. `focus:` fires on mouse click as well as keyboard, so the
 * ring appeared when it should not have, and `outline-none` with nothing
 * replacing it removes the indicator entirely for anyone who lands on that
 * rule by accident. `focus-visible:` is the correct primitive-level fix:
 * ring on keyboard, silent on mouse, never absent.
 */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";

/** Shared chrome for every button. Variants supply colour, this supplies behaviour. */
export const BTN_BASE =
  `btn-motion active:scale-[0.98] inline-flex items-center justify-center gap-1.5 ` +
  `font-medium touch-manipulation disabled:opacity-50 disabled:cursor-not-allowed ` +
  FOCUS_RING;

export const BTN_VARIANTS = {
  primary: "bg-accent text-white hover:bg-action-hover",
  secondary: "bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700",
  ghost: "text-slate-300 hover:bg-slate-800",
  danger: "bg-risk-critical text-white hover:bg-risk-critical-hover",
} as const;

export const BTN_SIZES = {
  sm: "px-3 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2 text-sm rounded-lg",
} as const;

/** Shared chrome for every text input. */
export const INPUT_BASE =
  `w-full bg-slate-800 border border-slate-700 px-3 py-2 rounded-lg text-sm ` +
  `text-slate-100 placeholder-slate-500 disabled:opacity-50 ` +
  FOCUS_RING;

export const FIELD_LABEL = "block text-sm text-slate-300 mb-1";
export const FIELD_ERROR = "text-xs text-risk-critical mt-1";
export const FIELD_HINT = "text-xs text-slate-500 mt-1";
