import type { ReactNode } from "react";
import { Button } from "./Button";

export type StateTone = "empty" | "error" | "success";

interface StateCommonProps {
  /** Icon slot — caller supplies inline SVG line-art (~64px). */
  icon?: ReactNode;
  /** One-line supporting hint, text-slate-500. Omitted entirely when absent. */
  hint?: string;
  /** Optional CTA (link or button) rendered below the hint. Caller's node. */
  action?: ReactNode;
  /** Retry callback. When omitted no retry control is rendered. */
  onRetry?: () => void;
  retryLabel?: string;
  /** Compact padding for embedding inside a card or table cell. */
  compact?: boolean;
}

/**
 * WHY `title` IS OPTIONAL ON ONE TONE AND REQUIRED ON THE OTHERS.
 *
 * The two components this replaces disagreed, and the disagreement was real.
 * The failure state had default copy — and one call site (the global error
 * boundary) depends on it, because it passes neither a title nor a hint and
 * would otherwise render a blank block on the worst possible page. The empty
 * state had no defaults and required a title.
 *
 * Encoding that as a union puts the guarantee in the type checker: a caller
 * cannot forget the error copy, and a caller cannot hand an empty state a
 * blank title. There is no default empty or success copy anywhere in this
 * product, and minting some would be inventing voice the design system has not
 * written.
 */
export type StateProps = StateCommonProps &
  (
    | { tone?: "empty"; title: string }
    | { tone: "error"; title?: string }
    | { tone: "success"; title: string }
  );

/**
 * Icon colour per tone.
 *
 * Held as contiguous literals, never interpolated: Tailwind scans raw source
 * text, so `text-${tone}-600` would emit no CSS and raise no error, and no
 * class-name assertion can see the difference.
 */
const ICON_TONE: Record<StateTone, string> = {
  empty: "text-slate-600",
  error: "text-risk-critical",
  success: "text-risk-clean",
};

/**
 * The three tones differ SEMANTICALLY, which is the point of the merge.
 *
 * Colour alone would have been a weak contract on a product where red is both
 * the brand action colour and the fraud colour — the two are deliberately
 * independent (`--color-accent` vs `--color-risk-critical`) precisely because
 * sharing a colour is not the same as sharing a meaning. So the live-region
 * politeness carries the state, and the colour only reinforces it:
 *
 *   - `alert`   — assertive. A failure INTERRUPTS. It existed as a separate
 *                  component because a failed query used to be
 *                  indistinguishable from an empty one: `data?.total || 0`
 *                  rendered "0 alertas", and on a fraud dashboard that is the
 *                  most dangerous possible misread — "no risk detected" when
 *                  the truth is "we could not ask".
 *   - `status`  — polite. A success is perceivable but never interrupts
 *                  whatever is being read.
 *   - (none)    — an empty list is the absence of something, not news. Putting
 *                  it in any live region would make every page load announce
 *                  "nothing to see here".
 */
const TONE_ROLE: Record<StateTone, "alert" | "status" | undefined> = {
  empty: undefined,
  error: "alert",
  success: "status",
};

const ERROR_DEFAULT_TITLE = "No se pudieron cargar los datos";
const ERROR_DEFAULT_HINT =
  "Revisá tu conexión o intentá de nuevo en unos segundos.";

/**
 * One composed state for the three things a panel can be instead of data.
 *
 * WHY ONE COMPONENT: the empty and failure states were near-copies of each
 * other with a different frame attribute, which is how a third thing — a
 * success state — never got written. There was no way to render "it worked" in
 * the same idiom as "there is nothing here" and "we could not ask", and the
 * absence of the third is why the second was easy to get wrong.
 *
 * The retry is the shared `Button` so it matches the hand-written retry a page
 * renders beside it. On `DashboardPage` both appear in the same view — the
 * failure state for the failed metrics request, plus a retry on the empty
 * table — and they were a text-colour step apart, so the same label read as
 * two different actions. It also gains what the raw button never had: the
 * keyboard-only focus ring, `touch-manipulation`, and the `enabled:` gate that
 * stops the hover firing on a disabled retry.
 *
 * DELIBERATELY NO `className` PROP. Tailwind resolves two utilities of one
 * property by stylesheet order, not attribute order, so a caller could not use
 * it to change a colour or a size — the primitive would silently win. The two
 * call sites that need a border and a background already wrap this in a
 * sibling `div`, which is the honest way to say "this is a panel" without
 * pretending the caller can restyle the state inside it.
 *
 * `onRetry` and `action` are independent slots, both in their own `mt-4` row,
 * and the API does not arbitrate between them. No call site supplies both; a
 * future one that does gets two rows, which is visible in review rather than
 * silently resolved.
 */
export function State({
  tone = "empty",
  icon,
  title,
  hint,
  action,
  onRetry,
  retryLabel = "Reintentar",
  compact = false,
}: StateProps) {
  const resolvedTitle =
    title ?? (tone === "error" ? ERROR_DEFAULT_TITLE : undefined);
  const resolvedHint =
    hint ?? (tone === "error" ? ERROR_DEFAULT_HINT : undefined);

  return (
    <div
      role={TONE_ROLE[tone]}
      data-testid={`${tone}-state`}
      className={`flex flex-col items-center justify-center px-6 text-center ${
        compact ? "py-6" : "py-12"
      }`}
    >
      {icon && (
        <div aria-hidden="true" className={`mb-4 ${ICON_TONE[tone]}`}>
          {icon}
        </div>
      )}
      {resolvedTitle && (
        <p className="text-sm font-medium text-slate-300">{resolvedTitle}</p>
      )}
      {resolvedHint && (
        <p className="mt-1 max-w-xs text-xs text-slate-500">{resolvedHint}</p>
      )}
      {onRetry && (
        <div className="mt-4">
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Minimal receipt line-art for transaction empty states. */
export function ReceiptLineArt() {
  return (
    <svg
      width={64}
      height={64}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 3h14v18l-2.33-1.75L14.33 21 12 19.25 9.67 21l-2.34-1.75L5 21V3Z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
      <path d="M9 16h3" />
    </svg>
  );
}

/** Minimal alert-bell line-art for alert empty states. */
export function BellLineArt() {
  return (
    <svg
      width={64}
      height={64}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z" />
      <path d="M10.3 20a1.9 1.9 0 0 0 3.4 0" />
    </svg>
  );
}

/** Minimal warning line-art for failure states. */
export function AlertLineArt() {
  return (
    <svg
      width={64}
      height={64}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}
