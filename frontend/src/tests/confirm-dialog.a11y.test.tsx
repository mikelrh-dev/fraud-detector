import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";

/**
 * Regression tests for the destructive-action confirmation dialog.
 *
 * The overlay used to be a bare `<div className="fixed inset-0">`: no role, no
 * aria-modal, no focus move, no focus trap, no Escape. These lock the contract
 * so it cannot silently regress.
 */
describe("ConfirmDialog — accessibility contract", () => {
  function Harness({
    withReason = false,
    onCancel = vi.fn(),
  }: {
    withReason?: boolean;
    onCancel?: () => void;
  }) {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="trigger"
        >
          Abrir
        </button>
        {open && (
          <ConfirmDialog
            title="Marcar como Falso Positivo"
            onConfirm={vi.fn()}
            onCancel={() => {
              setOpen(false);
              onCancel();
            }}
            error={null}
          >
            {withReason ? <textarea aria-label="Razón" /> : null}
          </ConfirmDialog>
        )}
      </>
    );
  }

  it("exposes role=dialog, aria-modal and an accessible name", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeTruthy();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    // Name comes from aria-labelledby pointing at the heading.
    expect(
      screen.getByRole("dialog", { name: "Marcar como Falso Positivo" }),
    ).toBeTruthy();
  });

  it("moves focus into the dialog on open", () => {
    render(<Harness withReason />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));

    // First focusable control is the reason field.
    expect(document.activeElement).toBe(screen.getByLabelText("Razón"));
  });

  it("moves focus to the first control when there is no field", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));

    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Cancelar" }),
    );
  });

  it("closes on Escape and does not call onConfirm", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        title="Revertir Alerta"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("traps Tab: from the last control it wraps to the first", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));

    const cancel = screen.getByRole("button", { name: "Cancelar" });
    const confirm = screen.getByRole("button", { name: "Confirmar" });
    confirm.focus();

    fireEvent.keyDown(document, { key: "Tab" });

    // Prevented the default wrap and moved focus back to the first control.
    expect(document.activeElement).toBe(cancel);
  });

  it("traps Shift+Tab: from the first control it wraps to the last", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));

    const cancel = screen.getByRole("button", { name: "Cancelar" });
    const confirm = screen.getByRole("button", { name: "Confirmar" });
    cancel.focus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(confirm);
  });

  it("restores focus to the opener when it closes", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Abrir" });
    trigger.focus();

    fireEvent.click(trigger);
    expect(document.activeElement).not.toBe(trigger);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(document.activeElement).toBe(trigger);
  });

  it("cancels on backdrop click but not on inner panel click", () => {
    const onCancel = vi.fn();
    const { rerender } = render(
      <ConfirmDialog
        title="Revisar Alerta"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole("dialog"));
    expect(onCancel).not.toHaveBeenCalled();

    rerender(
      <ConfirmDialog
        title="Revisar Alerta"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId("confirm-dialog-backdrop"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("announces an error with role=alert and wires aria-describedby", () => {
    render(
      <ConfirmDialog
        title="Revertir Alerta"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        error="Razón requerida"
      />,
    );

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Razón requerida");
    expect(screen.getByRole("dialog").getAttribute("aria-describedby")).toBe(
      alert.getAttribute("id"),
    );
  });
});
