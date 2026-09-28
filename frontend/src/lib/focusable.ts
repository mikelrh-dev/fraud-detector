/**
 * Selector for the focusable controls a dialog can trap focus between.
 *
 * SHARED, AND IT WAS NOT A COSMETIC DECISION. This lived duplicated in
 * `Modal.tsx` and `ConfirmDialog.tsx` — byte-identical, so no drift yet. But
 * when a real bug was found in one copy (below), duplication meant fixing one
 * and leaving the other live. One definition, two bugs gone.
 *
 * WHY `:not(:disabled)` AND NOT `[disabled]`: a form control inside a
 * `<fieldset disabled>` inherits the disabled state but carries no `disabled`
 * attribute of its own, so an attribute selector matches it and hands it focus.
 * The `:disabled` pseudo-class covers both cases. It matters because a
 * react-hook-form field disabled during a pending mutation is exactly the case a
 * dialog is likely to open around.
 *
 * `:disabled` cannot be used to filter elements that merely LOOK disabled, and
 * that is deliberate: opacity and colour are not state, and treating them as
 * state would make the trap depend on styling.
 */
export const FOCUSABLE =
  'textarea:not(:disabled), input:not(:disabled), select:not(:disabled), ' +
  'button:not(:disabled), [href], [tabindex]:not([tabindex="-1"])';

/**
 * The `id` carried by every page's `<main>` landmark, and the href target of
 * the skip link in `components/SkipLink.tsx`.
 *
 * WHY A SHARED CONSTANT AND NOT THE STRING "main" IN SIX FILES: this module
 * already exists to hold "one definition, two bugs gone" — `FOCUSABLE` was
 * duplicated byte-identically in `Modal.tsx` and `ConfirmDialog.tsx`, and when a
 * real focus bug turned up in one copy, duplication meant fixing one and leaving
 * the other live. The skip link has the same shape of hazard and a worse
 * failure mode: a skip link that targets an id nobody renders is a link that
 * goes nowhere, and a sighted keyboard user cannot tell, because the only
 * visible evidence is the URL fragment. One exported name, five imports.
 */
export const MAIN_LANDMARK_ID = "main";

/**
 * Whether a matched element can actually take focus right now.
 *
 * A control can match `FOCUSABLE` and still be a dead end, and there are TWO
 * independent reasons, so this checks both rather than picking one:
 *
 * - `aria-hidden="true"` on the element or an ancestor. `checkVisibility()` does
 *   NOT cover this -- it is a CSS question, and ARIA is not CSS. An early
 *   version of this function returned from `checkVisibility()` and therefore
 *   skipped the ARIA walk entirely, and the test for a control hidden from
 *   assistive tech caught focus landing on it.
 * - `display: none` / `visibility: hidden`, via `checkVisibility()` when the
 *   engine has it, and by walking ancestors otherwise.
 */
export function isFocusable(el: Element): boolean {
  for (let node: Element | null = el; node; node = node.parentElement) {
    if (node.getAttribute("aria-hidden") === "true") return false;
  }

  if (typeof el.checkVisibility === "function") {
    return el.checkVisibility({
      visibilityProperty: true,
      contentVisibilityAuto: true,
    });
  }

  for (let node: Element | null = el; node; node = node.parentElement) {
    const style = node.ownerDocument.defaultView?.getComputedStyle(node);
    if (style && (style.display === "none" || style.visibility === "hidden")) {
      return false;
    }
  }
  return true;
}
