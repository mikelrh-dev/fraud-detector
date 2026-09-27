import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Input } from "./Input";
import { Field } from "./Field";
import { FIELD_ERROR, FIELD_HINT, FIELD_LABEL } from "../lib/ui";

/** Token-wise comparison, as in Button.test.tsx. Duplicated rather than shared
 *  because this task is scoped to two components and their own test files. */
function expectCarries(el: Element, fragment: string) {
  for (const cls of fragment.split(" ").filter(Boolean)) {
    expect(el.classList.contains(cls), `missing class ${cls}`).toBe(true);
  }
}

/** Plain DOM assertions, not jest-dom matchers — `tsconfig.json` excludes
 *  `src/tests`, so the matcher types are invisible under `src/components`. */
function control(): HTMLElement {
  return screen.getByRole("textbox");
}

function node(id: string): HTMLElement | null {
  return document.getElementById(id);
}

function describedBy(): string[] {
  return (control().getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
}

describe("Field", () => {
  it("points the label at the control, and the control at the label's id", () => {
    // Both halves, because either one alone is a broken association. The audit
    // found these relationships implicit per call site; here they are
    // structural — `id` is required and both sides are derived from it.
    render(
      <Field id="amount" label="Monto">
        <Input />
      </Field>,
    );
    const label = screen.getByText("Monto") as HTMLLabelElement;
    expect(label.getAttribute("for")).toBe("amount");
    expect(control().getAttribute("id")).toBe("amount");
    expect(node(label.getAttribute("for")!)).toBe(control());
  });

  it("injects its id onto the control, so the wiring cannot be forgotten", () => {
    // The call site passes one `id`, not two. A caller who forgets to set
    // `id` on the control gets a working label instead of a silently orphaned
    // one.
    render(
      <Field id="merchant" label="Comercio">
        <Input />
      </Field>,
    );
    expect(control().getAttribute("id")).toBe("merchant");
  });

  it("its id wins over an id the child already carried", () => {
    // Documented precedence, not an accident: the label wiring depends on this
    // value, so the alternative is a label pointing at nothing.
    render(
      <Field id="amount" label="Monto">
        <Input id="amount-from-register" />
      </Field>,
    );
    expect(control().getAttribute("id")).toBe("amount");
    expect(node("amount-from-register")).toBeNull();
  });

  it("with no error and no hint it advertises no state and no description", () => {
    render(
      <Field id="currency" label="Moneda">
        <Input />
      </Field>,
    );
    expect(control().hasAttribute("aria-invalid")).toBe(false);
    expect(control().hasAttribute("aria-describedby")).toBe(false);
  });

  it("an error marks the control invalid and describes it with the error node", () => {
    render(
      <Field id="amount" label="Monto" error="El importe es obligatorio">
        <Input />
      </Field>,
    );
    expect(control().getAttribute("aria-invalid")).toBe("true");
    expect(describedBy()).toEqual(["amount-error"]);
    expect(node("amount-error")!.textContent).toBe("El importe es obligatorio");
  });

  it("a hint describes the control without marking it invalid", () => {
    render(
      <Field id="currency" label="Moneda" hint="Tres letras ISO">
        <Input />
      </Field>,
    );
    expect(control().hasAttribute("aria-invalid")).toBe(false);
    expect(describedBy()).toEqual(["currency-hint"]);
    expect(node("currency-hint")!.textContent).toBe("Tres letras ISO");
  });

  it("with BOTH, aria-describedby lists both ids — the error does not replace the hint", () => {
    // The regression this component exists for. Order-agnostic on purpose: the
    // bug being guarded is a dropped id, not a reordering, and an unrelated
    // reorder should not report as this failure.
    render(
      <Field
        id="amount"
        label="Monto"
        hint="Máximo 5000"
        error="El importe es obligatorio"
      >
        <Input />
      </Field>,
    );
    const ids = describedBy();
    expect(ids).toHaveLength(2);
    expect(ids).toContain("amount-error");
    expect(ids).toContain("amount-hint");
    expect(control().getAttribute("aria-invalid")).toBe("true");
  });

  it("with BOTH, the hint is still rendered next to the error", () => {
    // The other half of the same bug: a description that survives in the
    // attribute but is gone from the document turns `aria-describedby` into a
    // reference to a node that does not exist.
    render(
      <Field id="amount" label="Monto" hint="Máximo 5000" error="Importe requerido">
        <Input />
      </Field>,
    );
    expect(node("amount-hint")).not.toBeNull();
    expect(node("amount-error")).not.toBeNull();
  });

  it("every id it puts in aria-describedby resolves to a real element", () => {
    // The strongest form of the fix: not "the attribute has the right string"
    // but "a screen reader can follow it to the text". Checked across all
    // three combinations, because that wiring is built three different ways.
    const cases = [
      { props: { label: "Monto" }, expected: 0 },
      { props: { label: "Monto", error: "Importe requerido" }, expected: 1 },
      { props: { label: "Monto", hint: "Máximo 5000" }, expected: 1 },
      {
        props: { label: "Monto", hint: "Máximo 5000", error: "Importe requerido" },
        expected: 2,
      },
    ] as const;

    for (const { props, expected } of cases) {
      const { unmount } = render(
        <Field id="amount" {...props}>
          <Input />
        </Field>,
      );
      const ids = describedBy();
      expect(ids).toHaveLength(expected);
      for (const id of ids) {
        expect(node(id), `aria-describedby points at a missing node: ${id}`)
          .not.toBeNull();
      }
      unmount();
    }
  });

  it("lists the error before the hint, matching the visual order", () => {
    // A deliberate choice, pinned so a reorder is a conscious act: the error
    // is the actionable part, and what is spoken should be what is on screen.
    render(
      <Field id="amount" label="Monto" hint="Máximo 5000" error="Importe requerido">
        <Input />
      </Field>,
    );
    expect(control().getAttribute("aria-describedby")).toBe(
      "amount-error amount-hint",
    );
    const field = control().closest("div")!;
    expect(field.textContent!.indexOf("Importe requerido")).toBeLessThan(
      field.textContent!.indexOf("Máximo 5000"),
    );
  });

  it("gives the error node role=alert, so a failure is announced on appearance", () => {
    // Without a live region the text only reaches a screen reader when the
    // user happens to focus the field — which, on a submit-triggered
    // validation, they may never do.
    render(
      <Field id="amount" label="Monto" error="Importe requerido">
        <Input />
      </Field>,
    );
    expect(node("amount-error")!.getAttribute("role")).toBe("alert");
  });

  it("tells error and hint apart by colour, and nothing else", () => {
    render(
      <Field id="amount" label="Monto" hint="Máximo 5000" error="Importe requerido">
        <Input />
      </Field>,
    );
    const error = node("amount-error")!;
    const hint = node("amount-hint")!;
    expectCarries(error, FIELD_ERROR);
    expectCarries(hint, FIELD_HINT);
    // The colour is the entire signal (see FIELD_ERROR in lib/ui.ts), so assert
    // the discriminating class lands on one and not the other.
    expect(error.classList.contains("text-risk-critical")).toBe(true);
    expect(hint.classList.contains("text-risk-critical")).toBe(false);
  });

  it("the label uses the shared field label, never an error colour", () => {
    render(
      <Field id="amount" label="Monto" error="Importe requerido">
        <Input />
      </Field>,
    );
    const label = screen.getByText("Monto");
    expectCarries(label, FIELD_LABEL);
    expect(label.classList.contains("text-risk-critical")).toBe(false);
  });

  it("wires a control that is not an Input", () => {
    // Field is ARIA wiring, not Input styling. If this needed Input to work,
    // the wiring would be coupled to one component instead of to the DOM.
    render(
      <Field id="category" label="Categoría" error="Categoría desconocida">
        <select>
          <option value="">—</option>
        </select>
      </Field>,
    );
    const select = screen.getByRole("combobox");
    expect(select.getAttribute("id")).toBe("category");
    expect(select.getAttribute("aria-invalid")).toBe("true");
    expect(select.getAttribute("aria-describedby")).toBe("category-error");
  });

  it("an empty error string renders nothing and marks nothing", () => {
    // Form libraries routinely hand over `""` where they mean "no error".
    render(
      <Field id="amount" label="Monto" error="">
        <Input />
      </Field>,
    );
    expect(control().hasAttribute("aria-invalid")).toBe(false);
    expect(control().hasAttribute("aria-describedby")).toBe(false);
    expect(node("amount-error")).toBeNull();
  });
});
