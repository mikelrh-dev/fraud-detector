import type { InputHTMLAttributes } from "react";
import { INPUT_BASE, INVALID_INPUT, cn } from "../lib/ui";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

/**
 * WHY AN `aria-invalid:` VARIANT AND NOT A PROP-DRIVEN CLASS: two signals for
 * one state is a bug factory. `Field` owns the ARIA wiring and injects
 * `aria-invalid` into whatever control it is handed; had the red border hung
 * off a separate `invalid` prop, every call site would have to pass both, and
 * the two could diverge — an input painted red but never announced, or
 * announced but not painted. Driving the colour off the attribute makes the
 * visual and the announced state the same fact. `INVALID_INPUT` lives in
 * `lib/ui.ts` rather than here because it is keyed off the attribute, not the
 * element: a `<select>` or `<textarea>` gets it for free.
 *
 * It is also the only version that WINS the cascade, which is why the ring
 * override is written as an `aria-invalid:` variant instead of a plain
 * focus-visible ring in the risk tone. `INPUT_BASE` already carries a
 * focus-visible ring, so a plain override would TIE with it and be decided by
 * stylesheet order alone — the same dead-CSS class of bug Button just had,
 * where the loading state was computed and then silently shadowed. Prefix it
 * with `[aria-invalid="true"]` and it becomes an attribute selector, which
 * raises specificity from 0-2-0 to 0-3-0 and wins deterministically on
 * specificity rather than on Tailwind's internal sort.
 */

/**
 * A thin `<input>` over `INPUT_BASE`. The invalid treatment above is the whole
 * addition.
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
