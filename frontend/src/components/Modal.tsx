import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
import { Button } from "./Button";
import { cn } from "../lib/ui";
import { FOCUSABLE, isFocusable } from "../lib/focusable";

export type ModalSize = "sm" | "md" | "lg";

export interface ModalProps {
  /** Dialog heading; also the accessible name via aria-labelledby. */
  title: string;
  /**
   * Called on Escape, on backdrop click, and on the built-in close button.
   * Deliberately ONE callback, not `onClose` + `onCancel`: for a generic
   * dialog every one of those is the same user intent, and two names for it
   * invites a call site to wire the backdrop to one and Escape to the other.
   */
  onClose: () => void;
  children?: ReactNode;
  /** Action row, rendered after `children` inside the scroll panel. */
  footer?: ReactNode;
  size?: ModalSize;
  /**
   * Selector for the element that should receive focus on open. Defaults to
   * the first focusable control.
   */
  initialFocusSelector?: string;
  /**
   * Opt out of the built-in close button — ONLY for a dialog that already
   * shows its own named dismiss control in `footer` (a "Cancelar" button).
   * See the decision on the close button below for why the default is the
   * other way round.
   */
  hideCloseButton?: boolean;
  closeLabel?: string;
  className?: string;
}

const MODAL_BACKDROP =
  "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4";

/**
 * The scrollable panel.
 *
 * `overscroll-contain` is the fix, and it is load-bearing in a way the other
 * two classes are not. `max-h-[85vh] overflow-y-auto` makes the panel a scroll
 * container — without them a long dialog just grows off-screen. But a scroll
 * container still CHAINS: once its content is scrolled to the end, the wheel
 * gesture and the touch drag keep going, and scroll the document behind the
 * overlay. With the body scroll-locked that is partly masked, but the lock is
 * a second mechanism, and a `position: fixed` body is not the only way to
 * stop the background moving. `overscroll-contain` stops the chaining at the
 * source, so the gesture that would otherwise walk the page behind the dialog
 * is consumed by the panel and goes nowhere.
 *
 * This is the one bug in the audit that a sighted mouse or touch user hits
 * without any assistive technology: open a dialog taller than the viewport,
 * scroll it to the bottom, keep scrolling, and the page behind drifts out from
 * under the overlay while the dialog appears to stay put.
 */
const MODAL_PANEL =
  "relative w-full rounded-xl border border-slate-800 bg-slate-900 p-5 " +
  "max-h-[85vh] overflow-y-auto overscroll-contain";

const MODAL_TITLE = "mb-3 pr-8 text-sm font-semibold text-slate-200";
const MODAL_FOOTER = "mt-4 flex justify-end gap-2";
/** Absolute so the button reads as a corner affordance, see the note below. */
const MODAL_CLOSE = "absolute top-2 right-2";

const MODAL_SIZES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
} as const;

/**
 * The general dialog.
 *
 * WHY A COMPONENT: the overlay was hand-rolled per call site, and the parts
 * that make a dialog a dialog were the parts most likely to be dropped. A
 * missing focus move silently strands a keyboard user on the page behind an
 * overlay; a missing Tab trap lets them Tab into it; a missing Escape leaves
 * touch users, who have no Escape key, with no way out at all. The contract
 * belongs in one place so the next dialog cannot ship without it.
 *
 * This is the promotion of `ConfirmDialog`'s overlay, and its focus handling
 * is ported unchanged — that part was already right. What is added is the
 * scroll containment and the body lock, neither of which `ConfirmDialog` had.
 *
 * DO IT RENDER ITS OWN CLOSE BUTTON — the decision, and the reasoning:
 * the default is the built-in button, not "caller supplies one".
 *
 * A dialog that traps focus and offers no visible dismiss control is a
 * keyboard trap in practice. The user Tabs in, the trap cycles them forever,
 * and the only exit is a key that (a) is invisible, (b) is not discoverable
 * without knowing the convention, and (c) does not exist on a touch device at
 * all. WCAG 2.1.2 (No Keyboard Trap) is nominally satisfied because Escape
 * still works, which is exactly why the failure survives review: the automated
 * check passes while the user is still stuck.
 *
 * The tempting inverse - "require the caller to bring a close button" - would
 * NOT be silent: a required prop is a compile error. So that is not the
 * argument, and claiming it was would be arguing against a straw man. The
 * real reason is consistency and reviewability. A built-in default keeps the
 * dismiss affordance identical across every dialog in the product, and the
 * legitimate opt-out has to be TYPED at the call site, which makes opting out
 * greppable in review instead of an omission nobody notices. A required prop
 * buys the compile-time safety and gives up the uniformity.
 *
 * DOM ORDER, NOT VISUAL ORDER, for that button: it is rendered LAST, after
 * `children` and `footer`, and positioned into the top-right corner with
 * `absolute`. Rendering it first would make it the first focusable element,
 * so opening a dialog would move focus to "Cerrar" instead of the first field
 * — a regression against `ConfirmDialog`, which focuses the reason textarea
 * at `AlertsPage`. Focus order following the reading order is also the WCAG
 * 2.4.3 expectation. The cost is that the corner X is last in the tab
 * sequence; that is the smaller of the two wrongs.
 *
 * KNOWN LIMITS, stated rather than papered over:
 * - No portal, and this is NOT a hypothetical. `position: fixed` is contained
 *   by any transformed ancestor, and `PageTransition` wraps EVERY page's
 *   content in `animate-fade-slide-up`, whose `animation-fill-mode: both`
 *   persists the `to` keyframe's transform as `matrix(1, 0, 0, 1, 0, 0)` --
 *   not `none`. So every page establishes a containing block for fixed
 *   descendants. Measured in headless Edge: a fixed element inside that wrapper
 *   is 1241x4000 and CLIPPED; the same element outside any transform is
 *   1241x581, the viewport.
 *
 *   The reason nothing breaks today is a non-obvious invariant: `Modal` and
 *   `ConfirmDialog` are rendered as SIBLINGS of `<PageTransition>`, not inside
 *   it. `AlertsPage` happens to place its dialog after the closing tag. Nothing
 *   tests that and no type enforces it, so the next person who renders a dialog
 *   next to its trigger gets a silent clip. The fix is `createPortal`, which
 *   changes the mount target and needs its own test; until then, keep dialogs
 *   outside `PageTransition`.
 * - The body lock is a plain save/restore, not a counter. Two modals open at
 *   once would restore each other out of order and leave the body locked. Not
 *   reachable from the current call sites (one dialog at a time), and a shared
 *   lock module is the right fix if that ever changes.
 */
export function Modal({
  title,
  onClose,
  children,
  footer,
  size = "md",
  initialFocusSelector,
  hideCloseButton = false,
  closeLabel = "Cerrar",
  className,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // Remember the opener so focus can be handed back on close. Captured on
  // mount, which happens synchronously after the interaction that opened us.
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    openerRef.current = document.activeElement as HTMLElement | null;

    const panel = panelRef.current;
    if (panel) {
      // Both paths filter through `isFocusable`, and that is not redundant with
      // the selector. `FOCUSABLE` matches by ATTRIBUTES, so an `aria-hidden` or
      // `display: none` control still matches and is still a dead end. An
      // earlier version filtered only inside the Tab trap, so opening a dialog
      // whose first control was hidden moved focus onto it while the trap itself
      // behaved correctly -- the two halves of the same feature disagreeing.
      const candidates = Array.from(
        panel.querySelectorAll<HTMLElement>(
          initialFocusSelector ?? FOCUSABLE,
        ),
      ).filter(isFocusable);
      const target = candidates[0];
      // Falling back to the panel keeps focus INSIDE the dialog. Leaving it on
      // the trigger is the failure the component exists to prevent.
      (target ?? panel).focus();
    }

    return () => {
      // Restore focus to the control that opened the dialog, so the user does
      // not get dropped at the top of the document.
      openerRef.current?.focus?.();
    };
    // Mount/unmount only: the dialog is created fresh per invocation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;

      // Filter on markup, never on layout — see FOCUSABLE above.
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter(isFocusable);

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
  }, [onClose]);

  useEffect(() => {
    // Save the value we are about to overwrite, not "" — a body already
    // carrying `overflow: auto` (or set by some other library) must come back
    // as it was. Restoring a hardcoded "" is the usual version of this bug.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Runs on unmount too, so a dialog torn down while still open — route
    // change, parent unmount, a thrown render — does not leave the page
    // permanently unscrollable behind an overlay that is no longer there.
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  return (
    <div
      className={MODAL_BACKDROP}
      // The target check is on the BACKDROP, not the panel. A click that
      // started inside the panel bubbles up here with `target` still pointing
      // at the panel or one of its descendants, so it does not match and the
      // dialog stays open — which is what a click on a text selection inside
      // the dialog must do. Only a click on the backdrop itself, where target
      // and currentTarget are the same node, closes it.
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      data-testid="modal-backdrop"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        // The one place fragments are actually merged: panel base + size +
        // caller's `className`, all in a single class list.
        className={cn(MODAL_PANEL, MODAL_SIZES[size], className)}
      >
        <h2 id={titleId} className={MODAL_TITLE}>
          {title}
        </h2>

        {children}

        {footer && <div className={MODAL_FOOTER}>{footer}</div>}

        {/* Last in the DOM, in the top-right corner visually — see the
            focus-order note in the component doc. */}
        {!hideCloseButton && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label={closeLabel}
            className={MODAL_CLOSE}
          >
            <span aria-hidden="true">×</span>
          </Button>
        )}
      </div>
    </div>
  );
}
