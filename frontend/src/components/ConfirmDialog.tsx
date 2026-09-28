import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { FOCUSABLE, isFocusable } from "../lib/focusable";
import { FOCUS_RING, cn } from "../lib/ui";

export interface ConfirmDialogProps {
  /** Dialog heading; also the accessible name via aria-labelledby. */
  title: string;
  /** Called when the user confirms. */
  onConfirm: () => void;
  /** Called on Cancel, Escape, or backdrop click. */
  onCancel: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  disabled?: boolean;
  /** Inline error text, announced via role="alert". */
  error?: string | null;
  /** Rendered between the heading and the buttons (e.g. a reason field). */
  children?: ReactNode;
  /**
   * Selector for the element that should receive focus on open. Defaults to
   * the first focusable control, which is the reason field when present.
   */
  initialFocusSelector?: string;
}


/**
 * Accessible confirmation dialog.
 *
 * WHY THIS IS A COMPONENT
 * Confirming "Marcar como Falso Positivo" is a destructive, state-changing
 * action, but the overlay was a bare `<div className="fixed inset-0">`: no
 * role, no aria-modal, no focus move, no focus trap, no Escape. A keyboard user
 * who opened it could Tab indefinitely into the page behind the overlay, and
 * the only way out was the Cancel button. Screen readers announced the whole
 * thing as ordinary page content.
 *
 * Handles the full contract: role + labelling, focus moved in on open, Tab
 * contained, Escape to dismiss, and focus restored to whatever opened it.
 *
 * WHY THIS IS NOT COMPOSED OVER `Modal` — the shapes LOOK alike (same overlay,
 * same panel, same heading) and the shared parts are already shared, via
 * `lib/focusable.ts`. But three of the differences are the parts that matter,
 * and every one of them would have to be resolved by CHANGING `Modal` rather
 * than by changing this file:
 *
 * - THE ERROR SLOT. This component takes an `error` and does two things with
 *   it: renders it as a `role="alert"` paragraph, and points the panel's
 *   `aria-describedby` at it. `Modal` has no `error` prop, so the error would
 *   have to travel as `children` — which loses the `aria-describedby` and
 *   leaves the dialog with an empty description. That is an a11y REGRESSION
 *   traded for deduplication, and the only fix is a new prop on `Modal`.
 *
 * - THE FOOTER GAP. This component's button row has no margin of its own and
 *   relies on the preceding node's `mb-3` for 12px. `Modal`'s `MODAL_FOOTER` is
 *   `mt-4` — 16px — and is not overridable from the call site. In the common
 *   case (a reason field plus the footer) those two nodes are ADJACENT SIBLINGS
 *   in normal flow, so their vertical margins COLLAPSE to the larger of the two:
 *   composing would make the gap 16px, not the 28px a naive sum suggests.
 *   Visible on every dialog, but 4px of change rather than 16px.
 *
 * - THE CANCEL BUTTON. It is FILLED: `bg-slate-800` resting, `bg-slate-700`
 *   hover, `rounded`. `BTN_VARIANTS.secondary` is the opposite relationship —
 *   transparent with a slate-700 border at rest, filling to `bg-slate-800` on
 *   hover — and `BTN_SIZES.sm` would take the radius from `rounded` (4px) to
 *   `rounded-lg` (8px). Adopting it would invert both states of a control the
 *   user reaches for in order to back out.
 *
 * There is also a mechanical cost: `Modal` renames the backdrop's test id to
 * `modal-backdrop`, which `confirm-dialog.a11y.test.tsx` asserts on.
 *
 * All four are smaller than the deduplication is worth, and all four are
 * `Modal` changes. So the composition is recorded as a design-system decision
 * — a shared overlay with an error slot, a caller-settable footer gap, and a
 * choice of cancel treatment — rather than made unilaterally inside a page
 * migration. `Modal` is now portaled; this component is not, so its callers
 * must keep rendering it OUTSIDE any `PageTransition` subtree. See
 * `AlertsPage.tsx` for what that costs.
 */
export function ConfirmDialog({
  title,
  onConfirm,
  onCancel,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  disabled = false,
  error = null,
  children,
  initialFocusSelector,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const errorId = useId();

  // Remember the opener so focus can be handed back on close. Captured on
  // mount, which happens synchronously after the click that opened us.
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    openerRef.current = document.activeElement as HTMLElement | null;

    const panel = panelRef.current;
    if (panel) {
      // Filtered, not a bare querySelector. FOCUSABLE matches by ATTRIBUTES, so
      // a control that is aria-hidden or display:none still matches, and
      // focusing it is a no-op -- which leaves focus on the opener, outside the
      // dialog. The Tab trap below already filtered; this path did not, so the
      // two halves of the same feature could disagree.
      const target = Array.from(
        panel.querySelectorAll<HTMLElement>(initialFocusSelector ?? FOCUSABLE),
      ).filter(isFocusable)[0];
      (target ?? panel).focus();
    }

    return () => {
      // Restore focus to the control that opened the dialog, so the user does
      // not get dropped at the top of the document.
      openerRef.current?.focus?.();
    };
    // Mount/unmount only: the dialog is recreated per invocation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCancel();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;

      // Filter on markup, never on layout: `offsetParent` is null for
      // position:fixed elements in real browsers (and always in jsdom), so
      // using it here silently collapsed the trap to a single element.
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((el) => !el.hidden && el.getAttribute("aria-hidden") !== "true");

      if (focusable.length === 0) {
        // Nothing to move to; keep focus on the panel itself.
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && (active === first || active === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [onCancel]);

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={onCancel}
      data-testid="confirm-dialog-backdrop"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={error ? errorId : undefined}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="bg-slate-900 rounded-xl border border-slate-800 p-5 w-full max-w-sm"
      >
        <h2 id={titleId} className="text-sm font-semibold text-slate-200 mb-3">
          {title}
        </h2>

        {children}

        {error && (
          <p id={errorId} role="alert" className="text-xs text-risk-critical mb-3">
            {error}
          </p>
        )}

        <div className="flex gap-2 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className={cn(
              "btn-motion active:scale-[0.98] px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700",
              FOCUS_RING,
            )}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={disabled}
            className={cn(
              "btn-motion active:scale-[0.98] px-3 py-1.5 text-xs rounded bg-accent text-white hover:bg-action-hover disabled:opacity-50 disabled:cursor-not-allowed",
              FOCUS_RING,
            )}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
