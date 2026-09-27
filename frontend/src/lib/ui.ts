/**
 * Shared Tailwind class fragments — the single source for class strings that
 * more than one component needs.
 *
 * WHY A MODULE: these were re-typed per page and drifted. Numeric alignment
 * was the first instance (some columns left-aligned, others mono-only), but
 * the same copy-paste rot produced a focus ring that fired on mouse click and
 * two button variants whose colours were the inverse of the real design.
 * Import them, don't copy class strings.
 *
 * The file is organised in three sections — tables, interactive, form fields.
 * It is deliberately NOT split into three modules: there is no logic, state or
 * I/O here to isolate, so splitting would only multiply the import sites
 * without reducing any coupling.
 */

/** Merge class fragments, dropping falsy entries. */
export const cn = (...parts: (string | false | null | undefined)[]): string =>
  parts.filter(Boolean).join(" ");

// --- tables ---

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

// --- interactive ---

/**
 * Focus treatment, shared by every interactive primitive.
 *
 * WHY A CONSTANT: the audit found 9 sites writing `outline-none` followed by
 * `focus:ring-2`, across four files: `AuthSplitLayout.tsx` (1),
 * `AlertsPage.tsx` (1), `CreateTransactionPage.tsx` (5) and
 * `TransactionsPage.tsx` (2). `focus:` fires on mouse click as well as
 * keyboard, so the ring appeared when it should not have, and `outline-none`
 * with nothing replacing it removes the indicator entirely for anyone who
 * lands on that rule by accident. `focus-visible:` is the correct
 * primitive-level fix: ring on keyboard, silent on mouse, never absent.
 *
 * Known deviation from DESIGN.md (Focus ring: "2px offset"): the constants
 * carry no ring offset. Adding one is a visual change and belongs to the
 * visual pass, so this pass deliberately leaves the value alone.
 */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";

// Class strings here must stay CONTIGUOUS literals. Tailwind scans raw source
// text, so `hover:bg-${tone}-500` would emit no CSS at all — no build error,
// and no test failure, because a string assertion cannot see the output.
export const BTN_BASE =
  `btn-motion active:scale-[0.98] inline-flex items-center justify-center gap-1.5 ` +
  `font-medium touch-manipulation disabled:opacity-50 disabled:cursor-not-allowed ` +
  FOCUS_RING;

export const BTN_VARIANTS = {
  primary: "bg-accent text-white enabled:hover:bg-action-hover",
  secondary:
    "bg-transparent text-slate-300 border border-slate-700 enabled:hover:bg-slate-800",
  ghost: "text-slate-400 enabled:hover:text-slate-100",
  // Known divergence from DESIGN.md ("Danger: same as primary"), deferred to
  // the visual pass. `bg-risk-critical` is #ef4444, which is LIGHTER than
  // `bg-accent` #dc2626 — so today a destructive control reads as weaker than
  // the primary action it sits beside. Keeping it on the risk family is the
  // deliberate call: DESIGN.md keeps risk and accent semantically independent,
  // and that independence is worth more than the weight match. The weight is
  // the thing to fix in the visual pass, not by re-colouring danger into the
  // accent family.
  danger: "bg-risk-critical text-white enabled:hover:bg-risk-critical-hover",
} as const;

export type ButtonVariant = keyof typeof BTN_VARIANTS;
export type ButtonSize = keyof typeof BTN_SIZES;

export const BTN_SIZES = {
  sm: "px-3 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2 text-sm rounded-lg",
} as const;

// --- form fields ---

/** Shared chrome for every text input. */
export const INPUT_BASE =
  `w-full bg-slate-800 border border-slate-700 px-3 py-2 rounded-lg text-sm ` +
  `text-slate-100 placeholder-slate-500 disabled:opacity-50 ` +
  FOCUS_RING;

/** Block-level so the label stacks above its input; never an error colour. */
export const FIELD_LABEL = "block text-sm text-slate-300 mb-1";

/** Error and hint share every class but the colour — that is the whole signal. */
export const FIELD_ERROR = "text-xs text-risk-critical mt-1";
export const FIELD_HINT = "text-xs text-slate-500 mt-1";
