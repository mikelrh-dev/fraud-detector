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
      className={cn(
        BTN_BASE,
        BTN_VARIANTS[variant],
        BTN_SIZES[size],
        loading && "opacity-70 cursor-wait",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
