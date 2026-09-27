import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";

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

const FOCUSABLE =
  'textarea, input, select, button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

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
      const target = initialFocusSelector
        ? panel.querySelector<HTMLElement>(initialFocusSelector)
        : panel.querySelector<HTMLElement>(FOCUSABLE);
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
            className="btn-motion active:scale-[0.98] px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={disabled}
            className="btn-motion active:scale-[0.98] px-3 py-1.5 text-xs rounded bg-accent text-white hover:bg-action-hover disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
