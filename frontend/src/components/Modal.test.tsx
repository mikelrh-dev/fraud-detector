import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { Button } from "./Button";
import { Modal } from "./Modal";

/**
 * The general dialog contract.
 *
 * Focus and keyboard behaviour is asserted against the real
 * `document.activeElement` and the real event target. A test that asserts
 * "onCancel was called" passes whether or not focus ever moved, so it cannot
 * see the defect this component exists to prevent.
 *
 * Class names are asserted as LITERALS, never against an imported constant.
 * Comparing an element's class to `MODAL_PANEL` moves both sides of the
 * assertion when the constant is edited, so it passes no matter what the
 * component renders — including if it renders nothing.
 */
describe("Modal", () => {
  afterEach(() => {
    // The body lock writes to a global; a leaked `hidden` would silently
    // satisfy the "locked" assertion in the next test.
    document.body.style.overflow = "";
  });

  function Harness({
    onClose = vi.fn(),
    withCloseButton = true,
  }: {
    onClose?: () => void;
    withCloseButton?: boolean;
  }) {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Abrir
        </button>
        {/* Outside the dialog. A focus trap that leaks lands here, which is
            the exact failure the trap exists to prevent. */}
        <input aria-label="Fuera del diálogo" />
        {open && (
          <Modal
            title="Editar alerta"
            onClose={() => {
              setOpen(false);
              onClose();
            }}
            hideCloseButton={!withCloseButton}
            // The footer is caller-wired: `Modal` does not attach behaviour to
            // it. Left inert so a test can click inside the panel and still
            // find a dialog to assert on.
            footer={
              <>
                <Button onClick={vi.fn()}>Cancelar</Button>
                <Button onClick={vi.fn()}>Confirmar</Button>
              </>
            }
          >
            <textarea aria-label="Razón" />
          </Modal>
        )}
      </>
    );
  }

  const openIt = () => fireEvent.click(screen.getByRole("button", { name: "Abrir" }));

  it("renders role=dialog with aria-modal and a name from aria-labelledby", () => {
    render(<Harness />);
    openIt();

    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");

    // The name is resolved THROUGH aria-labelledby, not just present: this
    // query fails if the id is missing, points nowhere, or the heading is not
    // the element it names.
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy!)?.textContent).toBe("Editar alerta");
    expect(screen.getByRole("dialog", { name: "Editar alerta" })).toBe(dialog);
  });

  it("moves focus into the dialog on open", () => {
    render(<Harness />);
    openIt();

    // The first focusable control, NOT the built-in close button — the close
    // button is last in the DOM for exactly this reason.
    expect(document.activeElement).toBe(screen.getByLabelText("Razón"));
  });

  it("honours initialFocusSelector over the first focusable", () => {
    function SelectorHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Abrir
          </button>
          {open && (
            <Modal
              title="Con selector"
              onClose={() => setOpen(false)}
              initialFocusSelector="#jump"
            >
              <textarea aria-label="Razón" />
              <input id="jump" aria-label="Ir" />
            </Modal>
          )}
        </>
      );
    }

    render(<SelectorHarness />);
    openIt();

    expect(document.activeElement).toBe(screen.getByLabelText("Ir"));
  });

  it("returns focus to the trigger when it closes", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Abrir" });
    trigger.focus();

    openIt();
    expect(document.activeElement).not.toBe(trigger);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(document.activeElement).toBe(trigger);
  });

  it("traps forward Tab from the last control back to the first", () => {
    render(<Harness />);
    openIt();

    // The close button is the last focusable in the panel.
    const close = screen.getByRole("button", { name: "Cerrar" });
    close.focus();

    // The handler must also CANCEL the event, and that is a separate contract
    // from moving focus. In a real browser the native Tab moves focus by
    // itself, so without `preventDefault` the explicit `.focus()` here would
    // race the browser's own advance and the trap would land in the wrong
    // place. jsdom performs no default tabbing whatsoever, so the
    // `activeElement` assertion above CANNOT see the difference — deleting
    // `preventDefault()` leaves this test green (verified). `dispatchEvent`
    // returns false exactly when a handler called `preventDefault`, and
    // `keyDown` is dispatched cancelable, so this is the one signal in this
    // environment that actually observes the cancellation.
    expect(fireEvent.keyDown(document, { key: "Tab" })).toBe(false);

    expect(document.activeElement).toBe(screen.getByLabelText("Razón"));
  });

  it("traps Shift+Tab from the first control to the last", () => {
    render(<Harness />);
    openIt();

    const reason = screen.getByLabelText("Razón");
    reason.focus();

    expect(fireEvent.keyDown(document, { key: "Tab", shiftKey: true })).toBe(false);

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cerrar" }));
  });

  it("keeps focus on the panel itself when it has no focusable children", () => {
    // A dialog with only text and no controls would otherwise have an empty
    // trap: `first` and `last` would both be undefined and the wrap would
    // throw or focus nothing, dumping the user outside the dialog with no way
    // back in.
    render(
      <Modal title="Sin controles" onClose={vi.fn()} hideCloseButton>
        <p>Solo texto.</p>
      </Modal>,
    );

    const panel = screen.getByRole("dialog");
    expect(document.activeElement).toBe(panel);

    expect(fireEvent.keyDown(document, { key: "Tab" })).toBe(false);
    expect(document.activeElement).toBe(panel);
  });

  it("never lets Tab reach a control outside the dialog", () => {
    render(<Harness />);
    openIt();

    const outside = screen.getByLabelText("Fuera del diálogo");
    const last = screen.getByRole("button", { name: "Cerrar" });
    last.focus();

    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).not.toBe(outside);

    const first = screen.getByLabelText("Razón");
    first.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).not.toBe(outside);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    openIt();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on a backdrop click but not on a panel click", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    openIt();

    // The panel and everything inside it: clicking a dialog must not dismiss
    // it, whether the click lands on the panel itself, on its text, or on a
    // control inside it.
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Razón"));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onClose).not.toHaveBeenCalled();

    // The backdrop itself.
    fireEvent.click(screen.getByTestId("modal-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("contains overscroll on the scrollable panel", () => {
    render(<Harness />);
    openIt();

    const panel = screen.getByRole("dialog");
    // Literals, because the whole point is that these exact utilities exist
    // in the built stylesheet. `max-h`/`overflow-y-auto` are what make the
    // panel a scroll container at all; `overscroll-contain` is what stops the
    // gesture chaining onward to the page behind the overlay.
    expect(panel.classList.contains("overflow-y-auto")).toBe(true);
    expect(panel.classList.contains("overscroll-contain")).toBe(true);
    expect(panel.classList.contains("max-h-[85vh]")).toBe(true);
  });

  it("locks body scroll while open and restores it on close", () => {
    render(<Harness />);
    expect(document.body.style.overflow).toBe("");

    openIt();
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.body.style.overflow).toBe("");
  });

  it("restores the body's previous overflow rather than clearing it", () => {
    document.body.style.overflow = "auto";
    render(<Harness />);
    openIt();
    expect(document.body.style.overflow).toBe("hidden");

    fireEvent.keyDown(document, { key: "Escape" });

    // A hardcoded `""` on restore — the usual version of this — leaves the body
    // scrollable but no longer matches whatever set `auto` in the first place.
    expect(document.body.style.overflow).toBe("auto");
  });

  it("releases the body lock when unmounted while still open", () => {
    // The leak case: the dialog goes away without ever being closed — a route
    // change, a parent unmounting, a re-render that drops it. If the lock were
    // only released by onClose, the page would stay unscrollable forever
    // behind an overlay that no longer exists.
    const { unmount } = render(<Harness />);
    openIt();
    expect(document.body.style.overflow).toBe("hidden");

    unmount();

    expect(document.body.style.overflow).toBe("");
  });

  it("uses the Button primitive for its close control", () => {
    render(<Harness />);
    openIt();

    const close = screen.getByRole("button", { name: "Cerrar" });
    expect(close.tagName).toBe("BUTTON");
    // `type="button"` so it can never submit an enclosing form, and the focus
    // ring from the shared primitive — a raw <button> in this file would carry
    // neither, which is what makes this assertion falsifiable.
    expect(close.getAttribute("type")).toBe("button");
    expect(close.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(close.classList.contains("inline-flex")).toBe(true);
  });

  it("closes via its own close button", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    openIt();

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("omits the close button when the caller already supplies a dismiss control", () => {
    render(<Harness withCloseButton={false} />);
    openIt();

    // The opt-out exists so a dialog with a named "Cancelar" does not get a
    // redundant X, and it has to be written down to be used.
    expect(screen.queryByRole("button", { name: "Cerrar" })).toBeNull();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeTruthy();
  });

  it("merges the size fragment into the same class list as the panel base", () => {
    function Sized({ size }: { size: "sm" | "lg" }) {
      return (
        <Modal title="Sized" onClose={vi.fn()} size={size}>
          <p>contenido</p>
        </Modal>
      );
    }

    const { rerender } = render(<Sized size="sm" />);
    const panel = screen.getByRole("dialog");
    expect(panel.classList.contains("max-w-sm")).toBe(true);
    // Two fragments land in ONE class list, rather than one replacing the
    // other — the observable difference between `cn` and concatenation.
    expect(panel.classList.contains("overscroll-contain")).toBe(true);

    rerender(<Sized size="lg" />);
    expect(screen.getByRole("dialog").classList.contains("max-w-lg")).toBe(true);
    expect(screen.getByRole("dialog").classList.contains("max-w-sm")).toBe(false);
  });

  it("pins the close button as absolutely positioned", () => {
    // THE LOAD-BEARING CSS BEHIND THE DOM-ORDER DECISION. The close button is
    // last in the DOM so opening a dialog focuses the first CONTENT control
    // rather than "Cerrar" -- and that only works because the panel is
    // `relative` and the button is `absolute`, decoupled from flow order. Make
    // the button static and it visually renders first, which looks like a bug
    // and is one, even though every focus test still passes. Asserted as
    // literals: comparing to a constant moves both sides of the assertion.
    render(<Harness />);
    openIt();

    const close = screen.getByRole("button", { name: /cerrar/i });
    expect(close.classList.contains("absolute")).toBe(true);
    expect(close.classList.contains("top-2")).toBe(true);
    expect(close.classList.contains("right-2")).toBe(true);
    // Static would defeat the ordering; assert its absence explicitly.
    expect(close.classList.contains("static")).toBe(false);

    expect(screen.getByRole("dialog").classList.contains("relative")).toBe(true);
  });

  it("traps Shift+Tab from the panel itself", () => {
    // The trap's own escape hatch, and the one branch nothing tested. Focus can
    // land on the panel when `initialFocusSelector` misses, or when the user
    // clicks the panel padding rather than a control. Without the
    // `active === panel` guard, Shift+Tab from there is not intercepted at all
    // and the native browser walks focus OUT of the dialog -- the exact failure
    // the trap exists to prevent.
    render(<Harness />);
    openIt();

    const panel = screen.getByRole("dialog");
    panel.focus();
    expect(document.activeElement).toBe(panel);

    const notCancelled = fireEvent.keyDown(panel, { key: "Tab", shiftKey: true });

    expect(notCancelled, "Shift+Tab from the panel was not intercepted").toBe(
      false,
    );
    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("skips a control hidden from assistive tech", () => {
    // `aria-hidden` removes a control from the tab order without changing its
    // attributes, so the selector still matches it. Without the visibility
    // filter the trap would try to focus an element the user cannot reach.
    function HiddenHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Abrir
          </button>
          {open && (
            <Modal title="Editar" onClose={() => setOpen(false)}>
              <div aria-hidden="true">
                <input aria-label="Oculto" />
              </div>
              <textarea aria-label="Motivo" />
            </Modal>
          )}
        </>
      );
    }
    render(<HiddenHarness />);
    openIt();

    expect(document.activeElement).toBe(screen.getByLabelText("Motivo"));
  });
});
