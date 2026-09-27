import type { InputHTMLAttributes } from "react";
import { INPUT_BASE, cn } from "../lib/ui";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

/**
 * The invalid treatment.
 *
 * WHY AN `aria-invalid:` VARIANT AND NOT `invalid && "..."`: two signals for
 * one state is a bug factory. `Field` owns the ARIA wiring and injects
 * `aria-invalid` into whatever control it is handed; had the red border hung
 * off a separate `invalid` prop, every call site would have to pass both, and
 * the two could diverge — an input painted red but never announced, or
 * announced but not painted. Driving the colour off the attribute means the
 * visual and the announced state are the same fact.
 *
 * It is also the only version that WINS the cascade. `INPUT_BASE` already
 * carries `focus-visible:ring-focus-ring` (specificity 0-1-0), so an
 * `invalid && "focus-visible:ring-risk-critical"` would tie with it and lose
 * or win on stylesheet order alone — the same dead-CSS class of bug Button
 * just had, where the loaded state was computed and then silently shadowed.
 * `[aria-invalid="true"]` is an attribute selector, so
 * `aria-invalid:focus-visible:ring-risk-critical` is 0-2-0 and wins on
 * specificity, deterministically.
 *
 * Held as a contiguous literal: Tailwind scans raw source text, so an
 * interpolated class here would emit no CSS and raise no error (see lib/ui.ts).
 */
const INVALID_INPUT =
  "aria-invalid:border-risk-critical aria-invalid:focus-visible:ring-risk-critical";

/**
 * A thin `<input>` over `INPUT_BASE`. It adds no chrome of its own — the
 * invalid treatment above is the whole addition.
 */
export function Input({ invalid = false, className, ...rest }: InputProps) {
  return (
    <input
      // `invalid` is sugar for the caller's convenience. The DOM attribute is
      // the real signal, and `{...rest}` lands last ON PURPOSE: `Field` sets
      // `aria-invalid` through this spread, and a caller must be able to do the
      // same without also having to flip `invalid`. Explicit attributes beat
      // this default.
      aria-invalid={invalid || undefined}
      className={cn(INPUT_BASE, INVALID_INPUT, className)}
      {...rest}
    />
  );
}
