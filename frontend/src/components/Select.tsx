import type { SelectHTMLAttributes } from "react";
import { INPUT_BASE, INVALID_INPUT, cn } from "../lib/ui";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

/**
 * A thin `<select>` over the same chrome `Input` uses.
 *
 * WHY IT EXISTS NOW. `lib/ui.ts` says `INVALID_INPUT` "lives here rather than in
 * `Input.tsx` precisely so the next control primitive does not have to rediscover
 * that", and this is the next control primitive: D3 replaced the merchant
 * category's free-text input with a closed select, and a `<select>` cannot wear
 * `Input`'s props.
 *
 * It is a separate component rather than a broadened `Input` on purpose. An
 * `<input>` has no notion of options, so accepting `<option>` children on it
 * would type-check happily and render nothing — the two elements share a class
 * list, not an interface.
 *
 * The `{...rest}`-last ordering and the `aria-invalid` handling are copied from
 * `Input` unchanged and for the same reason: `Field` injects `aria-invalid`
 * through this spread, so the attribute and the red border are the same fact
 * rather than two signals a call site could disagree about.
 */
export function Select({ invalid = false, className, ...rest }: SelectProps) {
  return (
    <select
      aria-invalid={invalid || undefined}
      className={cn(INPUT_BASE, INVALID_INPUT, className)}
      {...rest}
    />
  );
}