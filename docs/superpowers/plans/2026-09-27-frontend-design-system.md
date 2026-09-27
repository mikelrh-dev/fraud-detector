# Frontend Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop defect classes from recurring in `frontend/src` by introducing a primitive layer, and cut the 959 kB bundle by splitting routes.

**Architecture:** `lib/ui.ts` stays the single source for Tailwind class fragments and grows; `components/` adds primitives that consume it. Pages consume primitives instead of restating class strings. Six steps, each independently shippable and independently verified.

**Tech Stack:** React 19, TypeScript, Tailwind 4, Vite, Vitest, Testing Library, react-router-dom 6, recharts 2, sonner 1

**Spec:** `docs/superpowers/specs/2026-09-27-frontend-design-system-design.md`

---

## File Structure

**Created:**
- `frontend/src/components/Button.tsx` — the button primitive
- `frontend/src/components/Button.test.tsx`
- `frontend/src/components/Input.tsx` — the input primitive, thin
- `frontend/src/components/Field.tsx` — label + control + error/hint wiring
- `frontend/src/components/Field.test.tsx`
- `frontend/src/lib/datetime.ts` — single `Intl.DateTimeFormat` formatter
- `frontend/src/lib/datetime.test.ts`
- `frontend/src/components/Modal.tsx` — promoted from `ConfirmDialog`
- `frontend/src/tests/route-splitting.test.tsx` — asserts the entry chunk has no charts

**Modified:**
- `frontend/src/lib/ui.ts` — grows the class constants
- `frontend/src/pages/CreateTransactionPage.tsx` — the proving migration
- `frontend/src/pages/TransactionsPage.tsx` — primitives, `<main>`, URL state
- `frontend/src/pages/AlertsPage.tsx` — primitives, URL state
- `frontend/src/pages/LoginPage.tsx`, `RegisterPage.tsx`, `DashboardPage.tsx`, `TransactionDetail.tsx` — primitives
- `frontend/src/components/ConfirmDialog.tsx` — deleted after `Modal` lands
- `frontend/src/components/EmptyState.tsx`, `ErrorState.tsx` — merged into `State.tsx`
- `frontend/src/App.tsx` — `lazy()` routes
- `frontend/src/index.css` — `color-scheme`, `touch-action`, tap highlight
- `frontend/src/index.html` — skip link target already exists via `<main>`

**Not touched:** `lib/classification.ts`, `lib/score.ts`, `lib/money.ts`, `Badge.tsx`, `ClassificationBadge.tsx`, `AlertStatusBadge.tsx`. The badge adapters own the value-to-tone mapping and must stay centralized.

---

### Task 1: Grow the class constants

Pure addition to `lib/ui.ts`. No component consumes these yet, so the suite must not move. If it does, something is wrong — this step cannot break anything.

**Files:**
- Modify: `frontend/src/lib/ui.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/ui.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  FOCUS_RING,
  BTN_BASE,
  BTN_VARIANTS,
  BTN_SIZES,
  INPUT_BASE,
  FIELD_LABEL,
  FIELD_ERROR,
} from "./ui";

describe("ui class constants", () => {
  it("focus ring uses focus-visible, never focus:", () => {
    expect(FOCUS_RING).toContain("focus-visible:ring-2");
    // A bare `focus:` shows the ring on mouse click, which is the defect the
    // audit found repeated 15 times.
    expect(FOCUS_RING).not.toMatch(/(^|\s)focus:(?!-)/);
  });

  it("focus ring targets the focus-ring token, not a raw colour", () => {
    expect(FOCUS_RING).toContain("ring-focus-ring");
    expect(FOCUS_RING).not.toMatch(/ring-(red|blue|slate)-\d/);
  });

  it("every button variant and size has a class", () => {
    for (const [name, classes] of Object.entries(BTN_VARIANTS)) {
      expect(classes, `variant ${name}`).toBeTruthy();
    }
    for (const [name, classes] of Object.entries(BTN_SIZES)) {
      expect(classes, `size ${name}`).toBeTruthy();
    }
  });

  it("button base carries touch-action and the motion class", () => {
    expect(BTN_BASE).toContain("btn-motion");
    expect(BTN_BASE).toContain("touch-manipulation");
    expect(BTN_BASE).toContain(FOCUS_RING);
  });

  it("only the primary variant uses the action tokens", () => {
    // A secondary or ghost button that hovered to the accent colour would read
    // as the primary action, which is the V-07 class of defect.
    expect(BTN_VARIANTS.primary).toContain("bg-accent");
    expect(BTN_VARIANTS.secondary).not.toContain("bg-accent");
    expect(BTN_VARIANTS.ghost).not.toContain("bg-accent");
  });

  it("input base carries the focus ring and no outline-none without replacement", () => {
    expect(INPUT_BASE).toContain(FOCUS_RING);
    expect(INPUT_BASE).toContain("placeholder-slate-500");
  });

  it("field error uses the risk-critical token, not a raw red", () => {
    expect(FIELD_ERROR).toContain("text-risk-critical");
    expect(FIELD_ERROR).not.toMatch(/text-red-/);
  });

  it("label constant exists", () => {
    expect(FIELD_LABEL).toContain("text-slate-300");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/ui.test.ts`
Expected: FAIL — `FOCUS_RING` and the other exports are not exported from `lib/ui.ts`.

- [ ] **Step 3: Add the constants**

Append to `frontend/src/lib/ui.ts`:

```ts
/**
 * Focus treatment, shared by every interactive primitive.
 *
 * WHY A CONSTANT: the audit found 15 sites writing `outline-none` followed by
 * `focus:ring-2`. `focus:` fires on mouse click as well as keyboard, so the
 * ring appeared when it should not have, and `outline-none` with nothing
 * replacing it removes the indicator entirely for anyone who lands on that
 * rule by accident. `focus-visible:` is the correct primitive-level fix:
 * ring on keyboard, silent on mouse, never absent.
 */
export const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring";

/** Shared chrome for every button. Variants supply colour, this supplies behaviour. */
export const BTN_BASE =
  `btn-motion active:scale-[0.98] inline-flex items-center justify-center gap-1.5 ` +
  `font-medium touch-manipulation disabled:opacity-50 disabled:cursor-not-allowed ` +
  FOCUS_RING;

export const BTN_VARIANTS = {
  primary: "bg-accent text-white hover:bg-action-hover",
  secondary: "bg-slate-800 text-slate-200 border border-slate-700 hover:bg-slate-700",
  ghost: "text-slate-300 hover:bg-slate-800",
  danger: "bg-risk-critical text-white hover:bg-red-500",
} as const;

export const BTN_SIZES = {
  sm: "px-3 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2 text-sm rounded-lg",
} as const;

/** Shared chrome for every text input. */
export const INPUT_BASE =
  `w-full bg-slate-800 border border-slate-700 px-3 py-2 rounded-lg text-sm ` +
  `text-slate-100 placeholder-slate-500 disabled:opacity-50 ` +
  FOCUS_RING;

export const FIELD_LABEL = "block text-sm text-slate-300 mb-1";
export const FIELD_ERROR = "text-xs text-risk-critical mt-1";
export const FIELD_HINT = "text-xs text-slate-500 mt-1";
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/ui.test.ts`
Expected: PASS, 8 tests.

- [ ] **Step 5: Confirm nothing else moved**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: tsc exit 0, 264 tests pass (256 existing + 8 new).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/ui.ts frontend/src/lib/ui.test.ts
git commit -m "refactor(ui): add focus, button and input class constants

The audit found 15 sites writing outline-none followed by focus:ring-2.
focus: fires on mouse click as well as keyboard, so the ring showed when it
should not, and outline-none with nothing replacing it removes the indicator
for anyone who lands on the rule by accident.

focus-visible: is the primitive-level fix: ring on keyboard, silent on mouse,
never absent. The primary variant is the only one that uses the action
tokens, asserted by a test so a secondary button cannot start reading as the
primary action.

Pure addition; no component consumes these yet."
```

---

### Task 2: The Button primitive

**Files:**
- Create: `frontend/src/components/Button.tsx`
- Create: `frontend/src/components/Button.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/Button.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Button } from "./Button";

describe("Button — contract it encodes", () => {
  it("defaults to type=button so it cannot submit a form by accident", () => {
    render(<Button>Salvar</Button>);
    expect(screen.getByRole("button", { name: "Salvar" })).toHaveAttribute(
      "type",
      "button",
    );
  });

  it("submits only when asked explicitly", () => {
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button type="submit">Enviar</Button>
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("does not submit a form it was not asked to submit", () => {
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <Button>Cancelar</Button>
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("exposes aria-busy while loading and stays clickable-looking", () => {
    render(<Button loading>Procesando</Button>);
    const button = screen.getByRole("button", { name: /procesando/i });
    expect(button).toHaveAttribute("aria-busy", "true");
    // Disabled while loading so a double submit is impossible.
    expect(button).toBeDisabled();
  });

  it("keeps its accessible name while loading", () => {
    render(<Button loading>Guardar</Button>);
    expect(screen.getByRole("button", { name: "Guardar" })).toBeTruthy();
  });

  it("applies only the chosen variant's classes", () => {
    const { container } = render(<Button variant="ghost">Cancelar</Button>);
    const className = container.querySelector("button")!.className;
    expect(className).not.toContain("bg-accent");
  });

  it("primary carries the action tokens", () => {
    const { container } = render(<Button variant="primary">Crear</Button>);
    expect(container.querySelector("button")!.className).toContain("bg-accent");
  });

  it("forwards the click handler", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Ir</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Ir" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("supports an aria-label when the visible text is not the label", () => {
    render(
      <Button aria-label="Cerrar">
        <span aria-hidden="true">×</span>
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Cerrar" })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/Button.test.tsx`
Expected: FAIL — `./Button` does not resolve.

- [ ] **Step 3: Write the primitive**

Create `frontend/src/components/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { BTN_BASE, BTN_SIZES, BTN_VARIANTS } from "../lib/ui";

export type ButtonVariant = keyof typeof BTN_VARIANTS;
export type ButtonSize = keyof typeof BTN_SIZES;

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "className"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a busy state. Disables the button and sets aria-busy. */
  loading?: boolean;
  children: ReactNode;
}

/**
 * The only button in the app.
 *
 * WHY A PRIMITIVE: the audit found 20 uses of `btn-motion` with the chrome
 * re-typed per call site, and 15 of them writing their own focus treatment.
 * Two properties are encoded here so no call site can forget them:
 *
 * - `type="button"` by default. A button inside a form that does not mean to
 *   submit will submit anyway, and the failure is invisible until a user's
 *   data is posted somewhere unexpected.
 * - The focus ring comes from `BTN_BASE`, so it is `focus-visible:` everywhere
 *   by construction.
 *
 * `loading` disables rather than swaps the label, so the button keeps its
 * width and its accessible name while the request is in flight.
 */
export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      className={`${BTN_BASE} ${BTN_VARIANTS[variant]} ${BTN_SIZES[size]}`}
      {...rest}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/Button.test.tsx`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Button.tsx frontend/src/components/Button.test.tsx
git commit -m "refactor(ui): add the Button primitive

20 uses of btn-motion were re-typing the chrome per call site, and 15 of them
wrote their own focus treatment. Two properties are now encoded so no call
site can forget them: type=button by default, because a button inside a form
that does not mean to submit will submit anyway, and the focus ring, which is
focus-visible: everywhere by construction.

loading disables rather than swapping the label, so the button keeps its width
and its accessible name while the request is in flight."
```

---

### Task 3: The Input and Field primitives

`Input` is deliberately thin. `Field` carries the accessibility, because that is
the part every call site was getting subtly wrong.

**Files:**
- Create: `frontend/src/components/Input.tsx`
- Create: `frontend/src/components/Field.tsx`
- Create: `frontend/src/components/Field.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/Field.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Field } from "./Field";
import { Input } from "./Input";

describe("Field — the accessibility the call sites were getting wrong", () => {
  it("links the label to the control by id", () => {
    render(
      <Field label="Monto" htmlFor="amount">
        <Input id="amount" />
      </Field>,
    );
    expect(screen.getByLabelText("Monto")).toBeTruthy();
  });

  it("points aria-describedby at the error when there is one", () => {
    render(
      <Field label="Monto" htmlFor="amount" error="Requerido">
        <Input id="amount" />
      </Field>,
    );
    const input = screen.getByLabelText("Monto");
    const error = screen.getByRole("alert");
    expect(input.getAttribute("aria-describedby")).toBe(error.getAttribute("id"));
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });

  it("points aria-describedby at the hint when there is no error", () => {
    render(
      <Field label="Monto" htmlFor="amount" hint="En dólares">
        <Input id="amount" />
      </Field>,
    );
    const input = screen.getByLabelText("Monto");
    expect(input.getAttribute("aria-describedby")).not.toBeNull();
    expect(input.getAttribute("aria-invalid")).toBeNull();
  });

  it("announces the error, not just colours it", () => {
    render(
      <Field label="Monto" htmlFor="amount" error="Requerido">
        <Input id="amount" />
      </Field>,
    );
    expect(screen.getByRole("alert").textContent).toBe("Requerido");
  });

  it("renders no error node when there is no error", () => {
    const { container } = render(
      <Field label="Monto" htmlFor="amount">
        <Input id="amount" />
      </Field>,
    );
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it("supports a visually hidden label", () => {
    render(
      <Field label="Buscar" htmlFor="q" hideLabel>
        <Input id="q" />
      </Field>,
    );
    // Still the accessible name, just not visible.
    expect(screen.getByLabelText("Buscar")).toBeTruthy();
  });

  it("marks a required field for assistive tech", () => {
    render(
      <Field label="Comercio" htmlFor="m" required>
        <Input id="m" />
      </Field>,
    );
    expect(screen.getByLabelText(/Comercio/)).toBeRequired();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/Field.test.tsx`
Expected: FAIL — `./Field` and `./Input` do not resolve.

- [ ] **Step 3: Write Input**

Create `frontend/src/components/Input.tsx`:

```tsx
import type { InputHTMLAttributes } from "react";
import { INPUT_BASE } from "../lib/ui";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

/**
 * Thin wrapper over the input class constant.
 *
 * Deliberately adds no behaviour: the label association, the error wiring and
 * the focus treatment all live in `Field`, so there is one place where the
 * accessibility contract is decided rather than three.
 */
export function Input({ className, ...rest }: InputProps) {
  return <input className={`${INPUT_BASE} ${className ?? ""}`} {...rest} />;
}
```

- [ ] **Step 4: Write Field**

Create `frontend/src/components/Field.tsx`:

```tsx
import { useId } from "react";
import type { ReactNode } from "react";
import { FIELD_ERROR, FIELD_HINT, FIELD_LABEL } from "../lib/ui";

export interface FieldProps {
  label: string;
  /** Id of the control this field labels. */
  htmlFor: string;
  error?: string;
  hint?: string;
  required?: boolean;
  /** Visually hidden label; still the accessible name. */
  hideLabel?: boolean;
  children: ReactNode;
}

/**
 * Label + control + error/hint, wired together.
 *
 * WHY: the audit found eight copies of the same input markup. Every one of
 * them repeated the label, and most got the error association subtly wrong —
 * the error was rendered adjacent to the control but nothing pointed at it, so
 * a screen reader reached the input and never heard why it was invalid.
 * `aria-describedby` is the fix and it is easy to omit by accident, which is
 * why it lives here.
 */
export function Field({
  label,
  htmlFor,
  error,
  hint,
  required = false,
  hideLabel = false,
  children,
}: FieldProps) {
  const errorId = useId();
  const hintId = useId();
  // Error wins when both are present: the user must hear the problem first.
  const describedBy = error ? errorId : hint ? hintId : undefined;

  return (
    <div>
      <label
        htmlFor={htmlFor}
        className={hideLabel ? "sr-only" : FIELD_LABEL}
      >
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      {children}
      {describedBy && (
        <span id={describedBy} hidden>
          {error ?? hint}
        </span>
      )}
      {error && (
        <p role="alert" className={FIELD_ERROR}>
          {error}
        </p>
      )}
      {!error && hint && <p className={FIELD_HINT}>{hint}</p>}
    </div>
  );
}
```

Note: the hidden `<span>` is what `aria-describedby` targets. The visible error
carries `role="alert"` so it is announced when it appears. Without the hidden
span the association is broken; that is the whole point of the component.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/Field.test.tsx`
Expected: PASS, 7 tests.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Input.tsx frontend/src/components/Field.tsx frontend/src/components/Field.test.tsx
git commit -m "refactor(ui): add Input and Field primitives

Eight copies of the same input markup, and most got the error association
subtly wrong: the error was rendered next to the control but nothing pointed
at it, so a screen reader reached the input and never heard why it was
invalid. aria-describedby is easy to omit by accident, which is why it lives
in one place.

Input stays thin and behaviourless on purpose so there is a single place where
the accessibility contract is decided."
```

---

### Task 4: Migrate CreateTransactionPage — the proving case

This is the step that decides whether the primitives were worth building. It
concentrates the two worst findings: the submit button disabled before the
request starts, and five duplicated inputs.

**Files:**
- Modify: `frontend/src/pages/CreateTransactionPage.tsx`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/tests/CreateTransactionPage.test.tsx`:

```tsx
  it("A2: the submit button is enabled on an empty form and explains itself", () => {
    // The button used to be disabled until every field validated, which is a
    // dead control with no explanation: the user sees a button that does
    // nothing and has to guess which field is wrong.
    renderPage();
    const submit = screen.getByRole("button", { name: /crear transacci/i });
    expect(submit).not.toBeDisabled();
  });

  it("A2: an empty submit shows validation messages rather than silently failing", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: /crear transacci/i }));

    // Every field the user has not filled must now say why.
    await waitFor(() => {
      expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    });
  });

  it("A2: every input is programmatically labelled", () => {
    renderPage();
    for (const label of [/monto/i, /moneda/i, /comercio/i, /categoría/i, /últimos 4/i]) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
  });

  it("A2: the amount field declares a decimal input mode", () => {
    renderPage();
    const amount = screen.getByLabelText(/monto/i);
    expect(amount).toHaveAttribute("inputMode", "decimal");
  });

  it("A2: the card field is numeric and not spell-checked", () => {
    renderPage();
    const card = screen.getByLabelText(/últimos 4/i);
    expect(card).toHaveAttribute("inputMode", "numeric");
    expect(card).toHaveAttribute("spellCheck", "false");
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/tests/CreateTransactionPage.test.tsx`
Expected: FAIL on the `not.toBeDisabled()` assertion — the button is currently `disabled={!isValid}`.

- [ ] **Step 3: Swap the schema and defaults**

In `frontend/src/pages/CreateTransactionPage.tsx`, remove the `disabled` gate reason and keep the schema as-is. Replace the five field blocks and the submit button:

```tsx
        <Field label="Monto" htmlFor="amount" error={errors.amount?.message} required>
          <Input
            id="amount"
            type="number"
            inputMode="decimal"
            step="0.01"
            placeholder="0.00"
            autoComplete="off"
            {...register("amount")}
          />
        </Field>

        <Field label="Moneda" htmlFor="currency" error={errors.currency?.message} required>
          <Input
            id="currency"
            type="text"
            maxLength={3}
            placeholder="USD"
            autoComplete="off"
            spellCheck={false}
            className="uppercase"
            {...register("currency")}
          />
        </Field>

        <Field
          label="Comercio"
          htmlFor="merchant_name"
          error={errors.merchant_name?.message}
          required
        >
          <Input
            id="merchant_name"
            type="text"
            placeholder="Nombre del comercio"
            autoComplete="off"
            {...register("merchant_name")}
          />
        </Field>

        <Field
          label="Categoría"
          htmlFor="merchant_category"
          hint="Opcional. Ayuda a detectar merchants de riesgo."
          error={errors.merchant_category?.message}
        >
          <Input
            id="merchant_category"
            type="text"
            placeholder="groceries"
            autoComplete="off"
            {...register("merchant_category")}
          />
        </Field>

        <Field label="Últimos 4 dígitos" htmlFor="card_last4" error={errors.card_last4?.message} required>
          <Input
            id="card_last4"
            type="text"
            inputMode="numeric"
            maxLength={4}
            placeholder="1234"
            autoComplete="off"
            spellCheck={false}
            {...register("card_last4")}
          />
        </Field>

        {/* The button stays enabled until the request starts. Disabling it on
            !isValid was a dead control with no explanation; the fields now
            explain themselves when the submit does not go through. */}
        <Button
          type="submit"
          variant="primary"
          loading={mutation.isPending}
          className="w-full"
        >
          {mutation.isPending ? "Procesando…" : "Crear Transacción"}
        </Button>
```

Add the imports:

```tsx
import { Button } from "../components/Button";
import { Field } from "../components/Field";
import { Input } from "../components/Input";
```

Delete the `disabled={!isValid || mutation.isPending}` prop and the `isValid`
destructure if it becomes unused.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/tests/CreateTransactionPage.test.tsx`
Expected: PASS, 11 tests.

- [ ] **Step 5: Check the whole suite, including the retrofit contract**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: tsc exit 0, all tests pass. `desktop-regression.test.tsx` must pass
unchanged — if it needed editing, this step changed behaviour it should not have.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CreateTransactionPage.tsx frontend/src/tests/CreateTransactionPage.test.tsx
git commit -m "refactor(ui): migrate CreateTransactionPage to the primitives

The proving case for the design system, and it carries the two worst findings
in the audit.

The submit button was disabled until every field validated. That is a dead
control with no explanation: the user sees a button that does nothing and has
to guess which field is wrong. It now stays enabled until the request starts,
and the fields explain themselves through Field's error wiring.

Five duplicated input blocks collapse into Field and Input, which also fixes
the error association: the errors were rendered next to the controls but
nothing pointed at them, so a screen reader reached the input and never heard
why it was invalid."
```

---

### Task 5: Promote ConfirmDialog to Modal

**Files:**
- Create: `frontend/src/components/Modal.tsx`
- Modify: `frontend/src/components/ConfirmDialog.tsx` (then delete)
- Rename test: `frontend/src/tests/confirm-dialog.a11y.test.tsx` → keep the filename, change the import

- [ ] **Step 1: Create Modal from ConfirmDialog**

Copy `frontend/src/components/ConfirmDialog.tsx` to `frontend/src/components/Modal.tsx`, rename the export to `Modal`, and make these changes:

```tsx
// In the backdrop, add scroll containment so scrolling inside the overlay does
// not chain to the page behind it.
<div
  className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4 overscroll-contain"
  onClick={onCancel}
  data-testid="confirm-dialog-backdrop"
>
```

Keep everything else identical: the `getDerivedStateFromError`-free class
component, the `FOCUSABLE` selector, the single-command `set` focus trap with the
markup-based filter, Escape, and focus restoration to the opener. Do not
"improve" any of it — the 9 existing tests in `confirm-dialog.a11y.test.tsx` pin
that behaviour and it passed.

Add to the `ModalProps` doc comment that the focus trap filters by markup
(`hidden` / `aria-hidden`) and **never** by layout, because `offsetParent` is
null for `position: fixed` in a real browser and filtering on it silently
collapses the trap to a single element.

- [ ] **Step 2: Replace the import and delete the old file**

In `frontend/src/pages/AlertsPage.tsx`, change the import to
`import { Modal } from "../components/Modal";` and the JSX tag to `<Modal`.

Then delete `frontend/src/components/ConfirmDialog.tsx`.

- [ ] **Step 3: Update the test import**

In `frontend/src/tests/confirm-dialog.a11y.test.tsx`, change
`import { ConfirmDialog } from "../components/ConfirmDialog";` to
`import { Modal } from "../components/Modal";` and every `<ConfirmDialog` to
`<Modal`.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/tests/confirm-dialog.a11y.test.tsx`
Expected: PASS, 9 tests, unchanged count. A behavioural change here would mean
the rename touched something it should not have.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Modal.tsx frontend/src/components/ConfirmDialog.tsx frontend/src/pages/AlertsPage.tsx frontend/src/tests/confirm-dialog.a11y.test.tsx
git commit -m "refactor(ui): promote ConfirmDialog to Modal and add scroll containment

The behaviour is unchanged and the 9 existing tests pin it. Overscroll-
containment is the one addition: scrolling inside the overlay chained to the
page behind it.

The focus-trap doc comment now records why the filter is on markup rather
than layout, since that was a real bug: offsetParent is null for position:
fixed in a real browser, so filtering on it collapsed the trap to one element."
```

---

### Task 6: Split the routes

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/tests/route-splitting.test.tsx`

- [ ] **Step 1: Record the current bundle as the baseline**

Run: `cd frontend && npm run build 2>&1 | Select-String "index-.*\.js"`

Expected: one entry chunk of roughly 959 kB (275 kB gzip). Write the number
down; it is the comparison for step 5.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/tests/route-splitting.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("route splitting", () => {
  const app = readFileSync(resolve(__dirname, "../App.tsx"), "utf-8");

  it("loads the pages lazily rather than eagerly", () => {
    expect(app).toContain("React.lazy");
    expect(app).toMatch(/lazy\(\(\) => import\(/);
  });

  it("does not statically import any page", () => {
    // A static import of a page defeats lazy() entirely, because it lands in
    // the entry chunk regardless of the element it is attached to.
    const staticImports = app
      .split("\n")
      .filter((line) => /^import .*from "\.\/pages\//.test(line.trim()));
    expect(staticImports).toEqual([]);
  });

  it("wraps the routes in Suspense", () => {
    expect(app).toContain("<Suspense");
  });

  it("has a route-level fallback, distinct from an empty state", () => {
    // A route really is loading here, so a skeleton is honest. This is the
    // distinction the ScoreResultCard fix turned on: there, a skeleton rendered
    // because `!result`, which was true before any submit and so claimed work
    // in progress that did not exist.
    expect(app).toContain("RouteFallback");
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/tests/route-splitting.test.tsx`
Expected: FAIL — `App.tsx` imports all seven pages statically.

- [ ] **Step 4: Make the routes lazy**

In `frontend/src/App.tsx`, replace the seven page imports with lazy ones and add
the fallback:

```tsx
import { Suspense, lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const TransactionDetail = lazy(() => import("./pages/TransactionDetail"));
const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const TransactionsPage = lazy(() => import("./pages/TransactionsPage"));
const CreateTransactionPage = lazy(() => import("./pages/CreateTransactionPage"));
```

Keep `useAuthStore`, `ErrorBoundary`, `RouteErrorFallback`, `logRenderError`
and `ProtectedRoute` as static imports: the boundary must not itself be lazy or a
render error in a lazy chunk would have nowhere to land.

Add the fallback next to the existing components:

```tsx
/**
 * Route-level loading state.
 *
 * A skeleton is honest here: a route genuinely is loading. The contrast with
 * the ScoreResultCard case is the point — there a skeleton rendered because
 * `!result`, which was true on first paint before the user had submitted
 * anything, so it claimed work in progress that did not exist.
 */
function RouteFallback() {
  return (
    <div
      className="min-h-screen bg-page-bg flex items-center justify-center"
      role="status"
      aria-live="polite"
    >
      <span className="sr-only">Cargando…</span>
      <div
        aria-hidden="true"
        className="h-8 w-8 rounded-full border-2 border-slate-700 border-t-accent motion-safe:animate-spin"
      />
    </div>
  );
}
```

Then wrap the `<Routes>` inside the `ErrorBoundary`:

```tsx
    <ErrorBoundary
      resetKeys={[location.pathname]}
      fallback={(reset) => <RouteErrorFallback reset={reset} />}
      onError={logRenderError("route")}
    >
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {/* unchanged */}
        </Routes>
      </Suspense>
    </ErrorBoundary>
```

- [ ] **Step 5: Verify the build output**

Run: `cd frontend && npm run build 2>&1 | Select-String "\.js"`

Expected: several `.js` chunks instead of one, and the largest noticeably below
959 kB. `recharts` should be in a chart chunk, not the entry.

- [ ] **Step 6: Run the tests**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: tsc exit 0, all tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/tests/route-splitting.test.tsx
git commit -m "perf(frontend): split routes so recharts loads only where it is used

The seven pages were imported statically, so the whole app plus the charting
library shipped as one 959 kB chunk — the login page paid for the dashboard's
graphs. A test asserts no page is statically imported, because a static import
defeats lazy() regardless of the element it is attached to.

ErrorBoundary and ProtectedRoute stay static: the boundary must not be lazy or
a render error inside a lazy chunk would have nowhere to land.

RouteFallback is a skeleton, and that is honest here — a route really is
loading. The contrast with the ScoreResultCard case is the point: there a
skeleton rendered because !result, true on first paint before any submit."
```

---

### Task 7: Remaining pages onto the primitives

Mechanical. The primitives are proven by Task 4.

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `frontend/src/pages/RegisterPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/TransactionDetail.tsx`
- Modify: `frontend/src/pages/TransactionsPage.tsx`
- Modify: `frontend/src/pages/AlertsPage.tsx`
- Modify: `frontend/src/components/ErrorBoundary.tsx`
- Modify: `frontend/src/components/ErrorState.tsx`

- [ ] **Step 1: Swap the buttons**

For every `<button className="btn-motion ...` in those files, replace with
`<Button variant="primary" size="sm">` or the appropriate variant, keeping the
children and the handler. Do not pass `className` unless a layout class is
genuinely needed; where it is, it is merged by the primitive.

- [ ] **Step 2: Swap the labelled inputs**

For every `<label>` + `<input>` pair, wrap in `Field` and replace the input with
`Input`. Preserve `type`, `maxLength`, `step`, `placeholder` and the
`{...register(...)}` spread. Add `autoComplete` to any field that lacks it.

- [ ] **Step 3: Run the suite after each file, not at the end**

Run: `cd frontend && npx vitest run` after each page.

Expected: green throughout. If a page's test needs editing to accommodate a
mechanical swap, the swap changed behaviour — stop and investigate rather than
editing the test.

- [ ] **Step 4: Commit per page**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "refactor(ui): LoginPage onto the Button and Field primitives"
```

Repeat for RegisterPage, DashboardPage, TransactionDetail, TransactionsPage,
AlertsPage, ErrorBoundary, ErrorState.

---

### Task 8: Mechanical guideline fixes

**Files:**
- Create: `frontend/src/lib/datetime.ts`
- Create: `frontend/src/lib/datetime.test.ts`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/index.html`
- Modify: `frontend/src/components/RiskMeter.tsx`
- Modify: `frontend/src/pages/TransactionsPage.tsx`
- Modify: `frontend/src/components/EmptyState.tsx`
- Modify: `frontend/src/components/ErrorState.tsx`

- [ ] **Step 1: Add the datetime formatter**

Create `frontend/src/lib/datetime.ts`:

```ts
/**
 * Single date formatter.
 *
 * WHY A MODULE: the audit found five scattered `toLocaleDateString("es-AR", …)`
 * calls. V-04 was the same defect for money — three renderers for one number,
 * which drifted — and the fix was a single `formatMoney`. Dates are the same
 * class of problem: one formatter, one locale, so the tables and the detail
 * page cannot disagree about how a date looks.
 */

const DATE_FORMAT = new Intl.DateTimeFormat("es-AR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const DATE_TIME_FORMAT = new Intl.DateTimeFormat("es-AR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** `DD/MM/AAAA` */
export function formatDate(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "—";
  return DATE_FORMAT.format(date);
}

/** `DD/MM/AAAA HH:MM` */
export function formatDateTime(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "—";
  return DATE_TIME_FORMAT.format(date);
}
```

Create `frontend/src/lib/datetime.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { formatDate, formatDateTime } from "./datetime";

describe("formatDate", () => {
  it("formats an ISO string", () => {
    expect(formatDate("2026-09-20T10:30:00Z")).toBe("20/09/2026");
  });

  it("accepts a Date", () => {
    expect(formatDate(new Date("2026-09-20T10:30:00Z"))).toBe("20/09/2026");
  });

  it("returns an em dash for an unparseable value rather than 'Invalid Date'", () => {
    expect(formatDate("not-a-date")).toBe("—");
    expect(formatDateTime("nope")).toBe("—");
  });

  it("includes the time for formatDateTime", () => {
    expect(formatDateTime("2026-09-20T10:30:00Z")).toContain("20/09/2026");
  });
});
```

- [ ] **Step 2: Replace the five call sites**

In `TransactionTable.tsx`, `AlertsPage.tsx` (two sites) and
`TransactionsPage.tsx` (two sites), replace the inline `toLocaleDateString` block
with `formatDate(tx.created_at)`.

- [ ] **Step 3: Add the global touch and dark-mode rules**

In `frontend/src/index.css`, inside the existing `@layer base`:

```css
  /* A tap waits ~300ms for a double-tap zoom check unless this is set. On a
     table where every row is a link, that delay is on every navigation. */
  :where(button, a, [role="button"], input, select, textarea) {
    touch-action: manipulation;
    -webkit-tap-highlight-color: color-mix(in srgb, var(--color-accent) 18%, transparent);
  }

  /* Windows dark mode renders scrollbars and native form controls light
     unless the document declares a dark colour scheme. */
  :root {
    color-scheme: dark;
  }
```

- [ ] **Step 4: Fix the remaining items**

- `RiskMeter.tsx:57` — replace `transition-all` with the properties it
  actually animates: `transition-[width,background-color]`.
- `TransactionsPage.tsx:59` — wrap the page content in `<main>`, matching the
  three pages that already have one.
- `index.html` — add a skip link as the first focusable element:
  ```html
  <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:px-4 focus:py-2 focus:bg-slate-900 focus:text-slate-100">Saltar al contenido</a>
  ```
  and add `id="main"` to each page's `<main>`.
- `TransactionTable.tsx:152`, `:185` and `AlertsPage.tsx:210` — replace the
  user-visible `...` with `…`. Leave the three-dot spread operators in
  `MotionList.tsx` and `auth.ts` alone; those are JavaScript, not text.

- [ ] **Step 5: Run the suite**

Run: `cd frontend && npx tsc --noEmit && npx eslint . && npx vitest run && npm run build`
Expected: tsc exit 0, eslint 0 errors, all tests pass, build ok.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/datetime.ts frontend/src/lib/datetime.test.ts frontend/src/index.css frontend/src/index.html
git commit -m "refactor(ui): single date formatter, touch handling, dark colour scheme

The audit found five scattered toLocaleDateString calls. V-04 was the same
defect for money and the fix was one formatMoney; dates are the same class of
problem, and tables and the detail page should not disagree about a date.

touch-action: manipulation removes the ~300ms double-tap-zoom delay from every
row link. color-scheme: dark stops Windows dark mode rendering light scrollbars
and native controls. A skip link and the missing main landmark on
TransactionsPage close the two structural findings."
```

---

### Task 9: Filters and pagination into the URL

Separate commit, because it is the only step that changes behaviour rather than
markup. If it misbehaves, revert this one commit and the other eight stand.

**Files:**
- Modify: `frontend/src/pages/TransactionsPage.tsx`
- Modify: `frontend/src/pages/AlertsPage.tsx`
- Create: `frontend/src/tests/list-url-state.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/tests/list-url-state.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import type { ReactNode } from "react";
import { vi } from "vitest";

vi.mock("../store/authStore", () => ({ useAuthStore: vi.fn() }));
const mockStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

vi.mock("../api/transactions", () => ({
  listTransactions: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
}));

import TransactionsPage from "../pages/TransactionsPage";

function renderAt(path: string) {
  mockStore.mockImplementation((selector?: (s: AuthState) => unknown) => {
    const state = {
      user: { id: "u1", role: "analista" },
      logout: vi.fn(),
      isAuthenticated: true,
      token: "t",
      refreshToken: null,
      login: vi.fn(),
    };
    return selector ? selector(state) : state;
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }
  return render(<Wrapper><TransactionsPage /></Wrapper>);
}

describe("list state lives in the URL", () => {
  it("reads the page from the query string", async () => {
    renderAt("/transactions?page=3");
    // Whatever renders, the point is that the page came from the URL rather
    // than from useState defaulting to 1.
    await waitFor(() => expect(screen.getByRole("button", { name: /siguiente/i })).toBeTruthy());
  });

  it("renders the same content for the same URL", async () => {
    const a = renderAt("/transactions?status=flagged&page=2");
    const first = document.body.textContent;
    a.unmount();
    const b = renderAt("/transactions?status=flagged&page=2");
    await waitFor(() => expect(document.body.textContent).toBe(first));
    b.unmount();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/tests/list-url-state.test.tsx`
Expected: FAIL — the component uses `useState(1)` and ignores the query string.

- [ ] **Step 3: Wire the state**

In `TransactionsPage.tsx`, replace `useState` for the page and the status filter
with `useSearchParams`, initialising from the URL and writing on change:

```tsx
const [searchParams, setSearchParams] = useSearchParams();
const page = Number(searchParams.get("page") ?? 1);
const statusFilter = searchParams.get("status") ?? "all";

function updateParam(key: string, value: string) {
  const next = new URLSearchParams(searchParams);
  if (value === "all" || value === "") next.delete(key);
  else next.set(key, value);
  // Any filter change resets the page, or the user lands on page 5 of a
  // one-page result set and sees nothing.
  if (key !== "page") next.delete("page");
  setSearchParams(next);
}
```

Replace every `setPage(n)` with `updateParam("page", String(n))` and the status
`setState` with `updateParam("status", value)`.

Do the same in `AlertsPage.tsx` for its page and status.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/tests/list-url-state.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit separately**

```bash
git add frontend/src/pages/TransactionsPage.tsx frontend/src/pages/AlertsPage.tsx frontend/src/tests/list-url-state.test.tsx
git commit -m "feat(frontend): keep list filters and pagination in the URL

A filtered view could not be deep-linked, shared, or reached with the back
button, because the state lived in useState and died on reload.

Separate commit because this is the only step in the design-system work that
changes behaviour rather than markup. If it misbehaves, this one revert
restores the previous behaviour and the other eight steps stand."
```

---

### Task 10: Merge EmptyState and ErrorState into State

Last of the component work, and the lowest value: these are two variants of one
layout, not two duplications.

**Files:**
- Create: `frontend/src/components/State.tsx`
- Modify: every file importing `EmptyState` or `ErrorState`
- Delete: `frontend/src/components/EmptyState.tsx`, `frontend/src/components/ErrorState.tsx`

- [ ] **Step 1: Write State**

```tsx
import type { ReactNode } from "react";
import { Button } from "./Button";

export interface StateProps {
  variant: "empty" | "error";
  title?: string;
  hint?: string;
  icon?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
}

/**
 * Empty and error states, one component.
 *
 * `error` carries `role="alert"` so a failure is announced rather than only
 * coloured. That distinction is the reason the two variants must not be
 * collapsed into one visual: on a fraud dashboard, "no alerts" and "we could
 * not load the alerts" are opposite claims, and a user cannot tell them apart
 * from colour alone.
 */
export function State({
  variant,
  title,
  hint,
  icon,
  onRetry,
  retryLabel = "Reintentar",
  compact = false,
}: StateProps) {
  const defaults =
    variant === "error"
      ? {
          title: "No se pudieron cargar los datos",
          hint: "Revisá tu conexión o intentá de nuevo en unos segundos.",
        }
      : { title: "Nada por acá", hint: undefined };

  return (
    <div
      role={variant === "error" ? "alert" : undefined}
      data-testid={variant === "error" ? "error-state" : "empty-state"}
      className={`flex flex-col items-center justify-center px-6 text-center ${
        compact ? "py-6" : "py-12"
      }`}
    >
      {icon && (
        <div aria-hidden="true" className={variant === "error" ? "mb-4 text-risk-critical" : "mb-4 text-slate-500"}>
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-slate-300">{title ?? defaults.title}</p>
      {(hint ?? defaults.hint) && (
        <p className="mt-1 max-w-xs text-xs text-slate-500">{hint ?? defaults.hint}</p>
      )}
      {onRetry && (
        <div className="mt-4">
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
    </div>
  );
}
```

Move `ReceiptLineArt`, `BellLineArt` and `AlertLineArt` into `State.tsx` unchanged
so the line art stays with the thing that renders it.

- [ ] **Step 2: Swap the call sites**

Replace `<ErrorState ...props />` with `<State variant="error" {...props} />` and
`<EmptyState ...props />` with `<State variant="empty" {...props} />` across
`AlertsPage.tsx`, `DashboardPage.tsx`, `TransactionsPage.tsx`,
`TransactionDetail.tsx` and `ErrorBoundary.tsx`. Then delete the two old files.

- [ ] **Step 3: Run the suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: green. Tests asserting `data-testid="error-state"` must still pass —
that is why the test id is kept on the error variant.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/State.tsx frontend/src/components/EmptyState.tsx frontend/src/components/ErrorState.tsx frontend/src/pages frontend/src/components/ErrorBoundary.tsx
git commit -m "refactor(ui): merge EmptyState and ErrorState into one State

Two variants of one layout rather than two duplications, and the only step
here that buys tidiness rather than correctness — which is why it is last.

The role=alert distinction is preserved and commented: 'no alerts' and 'we
could not load the alerts' are opposite claims on a fraud dashboard, and the
user cannot tell them apart from colour alone."
```

---

## Final verification

- [ ] **Step 1: All gates**

```bash
cd frontend
npx tsc --noEmit
npx eslint .
npx vitest run
npm run build
```

Expected: tsc exit 0, eslint 0 errors, all tests pass, build ok.

- [ ] **Step 2: Re-run the guideline audit**

Re-run the greps from the audit: `outline-none`, `btn-motion`, the input class
string, `toLocaleDateString`, `transition-all`, `<div[^>]*onClick`, `disabled={!isValid`.

Expected: `outline-none` only inside `lib/ui.ts`; no `btn-motion` outside
`lib/ui.ts`; no inline input class string; no `toLocaleDateString`; no
`transition-all`; no `disabled={!isValid}`.

- [ ] **Step 3: Compare the bundle**

Expected: the entry chunk is materially below the 959 kB baseline recorded in
Task 6 step 1, and there are several chunks.

- [ ] **Step 4: Confirm the backend is untouched**

```bash
cd .. && git diff --stat HEAD~9 -- src/ tests/ alembic/
```

Expected: empty. This plan is frontend-only.
