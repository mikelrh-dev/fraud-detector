import type { ButtonHTMLAttributes } from "react";
import {
  BTN_BASE,
  BTN_SIZES,
  BTN_VARIANTS,
  cn,
  type ButtonSize,
  type ButtonVariant,
} from "../lib/ui";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

/**
 * The busy indicator.
 *
 * WHY A SEPARATE ELEMENT: the previous treatment put the wait state on the
 * button itself as `opacity-70 cursor-wait`. That was dead CSS. `loading`
 * implies `disabled`, so `disabled:opacity-50` (specificity 0-2-0) always beat
 * `opacity-70` (0-1-0), and `disabled:cursor-not-allowed` always beat
 * `cursor-wait`. Confirmed with getComputedStyle in a real engine: a loading
 * button rendered opacity=0.5 cursor=not-allowed, pixel-identical to a
 * disabled one, so the user never saw that anything was happening.
 *
 * Honest limit: the button is still dimmed to 0.5 by `disabled:opacity-50`,
 * and opacity on a parent composites onto children, so the spinner is dimmed
 * too. What changed is that it exists and moves — a disabled button has no
 * spinner at all, so the two states are no longer pixel-identical. Making the
 * button *not* dim while loading would mean replacing `disabled:opacity-50`
 * with an `enabled:opacity-100` rule, which is a wider change to `BTN_BASE`
 * and every consumer of it.
 *
 * It is `aria-hidden` because `aria-busy` on the button already carries the
 * state to assistive tech. Note that `aria-busy` on a *disabled* control is
 * weakly announced — a disabled button leaves the tab order — so the spinner
 * is the primary signal, not a secondary one.
 */
function Spinner() {
  return (
    <span
      data-loading-spinner
      aria-hidden="true"
      className="size-3.5 shrink-0 rounded-full border-2 border-current border-t-transparent animate-spin"
    />
  );
}

/**
 * The only button in this app.
 *
 * On `className` landing last: it does NOT override the variant. Tailwind
 * resolves competing utilities by stylesheet order, not attribute order, so
 * "the caller's class wins because it comes last" is false. A caller can still
 * add classes, but to actually change a colour they must change the `variant`
 * prop. The order is kept so nothing is silently dropped, not because it wins.
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      // Default to type="button": an unlabelled <button> inside a form submits
      // it, which is how the submit button on CreateTransactionPage was live
      // before anyone wanted it to be.
      type="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(BTN_BASE, BTN_VARIANTS[variant], BTN_SIZES[size], className)}
      {...rest}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}
