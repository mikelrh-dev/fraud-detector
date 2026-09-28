import { cloneElement } from "react";
import type { InputHTMLAttributes, ReactElement, ReactNode } from "react";
import { FIELD_ERROR, FIELD_HINT, FIELD_LABEL } from "../lib/ui";

/**
 * The three attributes `Field` injects into the control it is handed, lifted
 * from the DOM typings so this list cannot drift from what a control can take.
 *
 * WHY THE `Pick` RATHER THAN `ReactElement`: `cloneElement`'s fallback
 * overload is `cloneElement<P>(element: ReactElement<P>, props?: Partial<P> &
 * Attributes)`, so a bare `children: ReactElement` means `P = unknown` and
 * `Partial<unknown>` is `{}` — the injected attributes would then be checked
 * against nothing at all. `Pick` at least constrains the injected literal
 * against real DOM attribute names and types.
 *
 * WHAT IT DOES NOT DO — and this is the important part: pinning `P` does NOT
 * make the compiler reject a child that cannot accept these attributes.
 * `JSX.Element` is `ReactElement<any, any>`, which is bidirectionally
 * assignable, so a component taking zero props type-checks clean. Verified.
 * This type is a guard on what `Field` SENDS, not a check on what the child
 * ACCEPTS.
 *
 * THE HOLE, stated plainly, because for components it is the whole surface:
 * three of four misuses fail SILENTLY. A control that destructures only the
 * props it knows about, instead of spreading the rest onto its DOM node, drops
 * all three attributes with no error. So does a component that takes no props
 * at all, and so does a Fragment. Only a non-element child throws. The tests
 * assert the wiring reached the real DOM element, which is the only thing that
 * catches this — no type can.
 */
type FieldControlProps = Pick<
  InputHTMLAttributes<HTMLInputElement>,
  "id" | "aria-invalid" | "aria-describedby"
>;

export interface FieldProps {
  /**
   * Required, and injected onto the control. The label's `htmlFor`, the
   * control's `id` and the `-hint`/`-error` ids are all derived from it, so
   * the three relationships cannot be wired inconsistently at the call site.
   */
  id: string;
  /**
   * A node, not a string, because a label is often more than its text.
   * `CreateTransactionPage` dims "(opcional)" on its merchant-category label;
   * typing this as `string` forced that page to either drop the annotation or
   * cast around the primitive. Widening costs nothing: a label's accessible
   * name is the sum of its text-bearing descendants, so a node gives the same
   * name plus whatever the markup adds.
   *
   * That last clause is the limit, not a loophole. A node can carry
   * `aria-label` or hide text, and then the accessible name diverges from the
   * visible label. The one call site here was checked to be consistent; nothing
   * in the type prevents the next one from being careless.
   */
  label: ReactNode;
  hint?: string;
  error?: string;
  children: ReactElement<FieldControlProps>;
}

/**
 * Label + control + hint/error, with the ARIA wiring done once, here.
 *
 * WHAT THIS FIXES: the audit found the error text visually adjacent to its
 * input but not programmatically associated with it — `<p className="text-xs
 * text-red-400 mt-1">` under an `<input>` with no id on the paragraph, no
 * `aria-describedby` on the control, and no `aria-invalid` anywhere. A sighted
 * user saw the failure; a screen reader announced the label, the value and
 * nothing else, so the validation failure was never spoken.
 */
export function Field({ id, label, hint, error, children }: FieldProps) {
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;

  // The error is listed before the hint, and rendered before it below, so the
  // order spoken and the order on screen agree. Error first because it is the
  // thing the user has to act on; the hint is supporting detail.
  //
  // The nested ternary is the load-bearing part: with both present the two ids
  // are BOTH listed. Letting the error overwrite the hint is the common bug —
  // the user is then never told the format the field wants.
  const describedBy = error
    ? hint
      ? `${errorId} ${hintId}`
      : errorId
    : hint
      ? hintId
      : undefined;

  return (
    <div>
      <label htmlFor={id} className={FIELD_LABEL}>
        {label}
      </label>

      {cloneElement(children, {
        // `Field`'s id wins over one the child already carries. The label
        // wiring depends on this value, so it cannot be negotiable — and a
        // call site that passes both gets one consistent id, not a dangling
        // reference to the child's.
        id,
        // Omitted rather than `aria-invalid="false"`, matching Button's
        // `aria-busy`: absent and "false" are equivalent to assistive tech, and
        // a field with no error has no invalid state to advertise.
        "aria-invalid": error ? "true" : undefined,
        "aria-describedby": describedBy,
      })}

      {/* The live region is ALWAYS rendered, and only its content toggles.
          W3C ARIA19 requires the region to exist in the DOM *before* its
          content changes; a node mounted already-populated generally does not
          announce. Mounting this conditionally meant the announcement we were
          claiming to provide never actually happened. The spacing class is
          applied with the content so an empty region costs no vertical gap. */}
      <p id={errorId} role="alert" className={error ? FIELD_ERROR : undefined}>
        {error}
      </p>
      {/* The hint is NOT hidden by an error. It stays rendered so the format
          requirement survives the failure, and so the id in `aria-describedby`
          is never a reference to a node that does not exist. */}
      {hint && <p id={hintId} className={FIELD_HINT}>{hint}</p>}
    </div>
  );
}
