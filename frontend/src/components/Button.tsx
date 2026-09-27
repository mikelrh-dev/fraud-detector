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
 * The only button in this app. `className` still lands last so a caller can
 * override, but the variant and size are the parts worth naming.
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
