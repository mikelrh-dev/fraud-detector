import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { State } from "../components/State";

/**
 * LITERALS, NOT IMPORTS.
 *
 * Every class name below is written out by hand. Asserting against the
 * imported constant would be a tautology: mutating the constant moves both
 * sides of the assertion and the test stays green. These strings are the
 * contract, so the contract is spelled out. That is also why the strings
 * below are all classes the build already emits — Tailwind scans test files,
 * so a typo here would silently ADD a rule to the stylesheet.
 */

/** The two layouts, from the pre-merge markup. Byte-for-byte. */
const FULL_FRAME = "flex flex-col items-center justify-center px-6 text-center py-12";
const COMPACT_FRAME =
  "flex flex-col items-center justify-center px-6 text-center py-6";

const TITLE_CLASS = "text-sm font-medium text-slate-300";
const HINT_CLASS = "mt-1 max-w-xs text-xs text-slate-500";
const ACTION_ROW_CLASS = "mt-4";

/**
 * The retry control's whole class list, as one literal.
 *
 * Long, and deliberately not `cn(BTN_BASE, BTN_VARIANTS.secondary, ...)`.
 * This string is the thing commit e30bd8b fixed: the retry inside the failure
 * state was a text-colour step away from the hand-written retry a page renders
 * beside it, and the same label read as two different actions. Pinning it here
 * means a future edit to either constant that changes the pixels turns this
 * test red instead of shipping a mismatch nobody sees.
 */
const RETRY_BUTTON_CLASS =
  "btn-motion active:scale-[0.98] inline-flex items-center justify-center " +
  "gap-1.5 font-medium touch-manipulation disabled:opacity-50 " +
  "disabled:cursor-not-allowed focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-focus-ring bg-transparent " +
  "text-slate-300 border border-slate-700 enabled:hover:bg-slate-800 " +
  "px-3 py-1.5 text-xs rounded-lg";

const frame = (el: Element) => el.className;
const iconSlot = (el: Element) =>
  el.querySelector("[aria-hidden='true']") as HTMLElement;
const titleEl = (el: Element) => el.querySelectorAll("p")[0] as HTMLElement;
const hintEl = (el: Element) => el.querySelectorAll("p")[1] as HTMLElement;
const actionRow = (el: Element) =>
  el.querySelector(`div.${ACTION_ROW_CLASS}`) as HTMLElement | null;

describe("State — the three tones differ semantically, not only in colour", () => {
  it("an error announces itself", () => {
    render(<State tone="error" title="No se pudieron cargar los datos" />);

    // `alert` is the assertive live region: the failure interrupts. This is the
    // whole reason the failure state exists — a failed query once rendered as a
    // confident zero, and on a fraud dashboard that is the most dangerous
    // possible misread.
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("an empty state does not announce itself", () => {
    const { container } = render(<State title="No hay alertas" />);

    // Not "less assertive" — NO role at all. An empty list is the absence of
    // something, not news, and putting it in a live region would make every
    // page load announce "nothing to see here".
    const root = container.firstElementChild as HTMLElement;
    expect(root.getAttribute("role")).toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("a success state is quiet but still perceivable", () => {
    render(<State tone="success" title="Listo" />);

    // `status` is the polite live region: it reaches assistive tech without
    // interrupting whatever is being read. Alerting on a success would be the
    // mirror-image bug, and dropping the role entirely would make a confirmed
    // action indistinguishable from an empty page.
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("the three tones carry three different icon colours", () => {
    // A colour change alone would not have been enough, and the roles above
    // are what make it safe — but the tones are also meant to be told apart at
    // a glance, and this is what the eye actually uses.
    const { container: e } = render(<State tone="error" title="a" icon={<svg />} />);
    const { container: m } = render(<State title="b" icon={<svg />} />);
    const { container: s } = render(<State tone="success" title="c" icon={<svg />} />);

    expect(iconSlot(e.firstElementChild!).className).toBe("mb-4 text-risk-critical");
    expect(iconSlot(m.firstElementChild!).className).toBe("mb-4 text-slate-600");
    expect(iconSlot(s.firstElementChild!).className).toBe("mb-4 text-risk-clean");
  });
});

describe("State — the retry affordance", () => {
  it("an error with a callback gets the shared retry control, and fires it", async () => {
    const onRetry = vi.fn();
    const { container } = render(
      <State tone="error" title="Falló" onRetry={onRetry} />,
    );

    const retry = screen.getByRole("button", { name: "Reintentar" });
    expect(retry.className).toBe(RETRY_BUTTON_CLASS);

    await userEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);

    // …inside the same action row every other action uses, so the retry and a
    // caller-supplied CTA sit at identical distance from the hint.
    expect(frame(actionRow(container.firstElementChild!)!)).toBe(ACTION_ROW_CLASS);
  });

  it("the retry label is overridable without losing the control", () => {
    render(
      <State tone="error" title="Falló" onRetry={() => {}} retryLabel="Cargar de nuevo" />,
    );
    expect(screen.getByRole("button", { name: "Cargar de nuevo" })).toBeInTheDocument();
  });

  it("no tone invents a retry control that was not asked for", () => {
    // The tone does not decide. If it did, the error row below would keep
    // drawing a button whose handler is undefined.
    const noRetry = render(<State tone="error" title="Sin reintento" />);
    const empty = render(<State title="Sin reintento" />);
    const success = render(<State tone="success" title="Sin reintento" />);

    for (const r of [noRetry, empty, success]) {
      expect(
        r.container.querySelector("button, a"),
      ).toBeNull();
    }
  });

  it("an empty state given a retry gets one", () => {
    // "Absent unless the state is given one" — so the retry is NOT error-only.
    // A failed filter that lands on an empty result is still a failure the user
    // has to be able to clear, and it has no other way out.
    render(<State title="Sin coincidencias" onRetry={() => {}} />);
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("a success state given a retry gets one", () => {
    render(
      <State tone="success" title="Todo listo" onRetry={() => {}} retryLabel="Otra vez" />,
    );
    expect(screen.getByRole("button", { name: "Otra vez" })).toBeInTheDocument();
  });

  it("an empty state that offers a retry announces itself", () => {
    // The review found the hole in the tone design: `onRetry` is legal on every
    // tone, so an empty state can be the RESULT OF SOMETHING THE USER JUST DID
    // -- filters applied, a retry pressed -- and with no live region it
    // announced nothing at all. The user pressed a button and got silence.
    //
    // It is the same shape as the `data?.total || 0` rendering "0 alertas" on a
    // failed query, which is the bug the error tone was created to fix: absence
    // of an announcement is not the same as absence of a result, when the
    // absence is the answer to something the user asked.
    render(<State title="Sin coincidencias" onRetry={() => {}} />);

    // `status`, not `alert`: nothing failed, so nothing should interrupt.
    const region = screen.getByRole("status");
    expect(region.textContent).toContain("Sin coincidencias");
  });

  it("an empty state with no retry stays silent, so a page load is not chatty", () => {
    // The other half of the rule, and the reason it is safe. Every list page
    // mounts an empty state on load; if those announced, navigating would talk
    // over whatever the user was reading.
    render(<State title="Sin transacciones" />);

    // No role at all, so no live region, so nothing is announced.
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("the error tone is unaffected by the empty-with-retry rule", () => {
    // `onRetry` is common on error. If the new rule had leaked into the other
    // tones it would downgrade an interruption to a courtesy, which is the
    // wrong way round.
    render(<State tone="error" onRetry={() => {}} />);

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("State — the error copy is a component guarantee, not a call-site habit", () => {
  it("falls back to the default failure title and hint", () => {
    // The global error boundary passes neither. If the fallback were dropped
    // rather than moved, that page would render an empty block.
    render(<State tone="error" onRetry={() => {}} />);

    expect(screen.getByText("No se pudieron cargar los datos")).toBeInTheDocument();
    expect(
      screen.getByText("Revisá tu conexión o intentá de nuevo en unos segundos."),
    ).toBeInTheDocument();
  });

  it("a caller-supplied title and hint win over the defaults", () => {
    render(
      <State tone="error" title="No se pudieron cargar las alertas" hint="Reintentá la carga." />,
    );
    expect(screen.getByText("No se pudieron cargar las alertas")).toBeInTheDocument();
    expect(screen.queryByText("No se pudieron cargar los datos")).not.toBeInTheDocument();
  });

  it("no other tone invents fallback copy", () => {
    // There is no default empty or success copy anywhere in this product, and
    // minting some would be inventing voice the design system has not written.
    // The types require a title for those two tones; this is the runtime
    // backstop for a JS consumer.
    const { container } = render(<State hint="sólo un hint" />);
    expect(container.querySelectorAll("p").length).toBe(1);
  });

  it("a state given no hint renders no hint paragraph at all", () => {
    // Not the same assertion as the one above, and the gap it leaves is the
    // reason it exists. Every call site today passes a hint, so rendering an
    // EMPTY paragraph for the ones that do not would change nothing anybody
    // can see — which is exactly why it needs a test rather than a code
    // review. It would not be an empty block: the paragraph carries a top
    // margin, so it also pushes everything below it down by 4px.
    const { container } = render(<State title="Sin hint" />);

    expect(container.querySelectorAll("p").length).toBe(1);
    expect(titleEl(container.firstElementChild!).className).toBe(TITLE_CLASS);
  });
});

describe("State — the rendered frame is byte-identical to what it replaced", () => {
  it("an empty state, full height, with a caller action", () => {
    const { container } = render(
      <State
        icon={<svg data-testid="icon-slot" />}
        title="No hay transacciones"
        hint="Registra una transacción para comenzar a monitorear su riesgo."
        action={<a href="/transactions/new">Crear primera transacción</a>}
      />,
    );

    const root = container.firstElementChild as HTMLElement;
    expect(frame(root)).toBe(FULL_FRAME);
    expect(iconSlot(root).className).toBe("mb-4 text-slate-600");
    expect(titleEl(root).className).toBe(TITLE_CLASS);
    expect(hintEl(root).className).toBe(HINT_CLASS);
    expect(frame(actionRow(root)!)).toBe(ACTION_ROW_CLASS);
    // The caller's node passes through untouched — the slot is theirs.
    expect(actionRow(root)!.firstElementChild!.tagName).toBe("A");
  });

  it("an empty state, compact, with no action", () => {
    const { container } = render(
      <State
        icon={<svg />}
        title="No se encontraron transacciones"
        hint="Ajusta los filtros activos o crea una nueva transacción."
        compact
      />,
    );

    const root = container.firstElementChild as HTMLElement;
    expect(frame(root)).toBe(COMPACT_FRAME);
    expect(actionRow(root)).toBeNull();
  });

  it("an error, compact, with the retry", () => {
    const { container } = render(
      <State
        tone="error"
        icon={<svg />}
        title="No se pudieron cargar las métricas"
        hint="Los valores mostrados pueden estar incompletos. Reintentá la carga."
        onRetry={() => {}}
        compact
      />,
    );

    const root = container.firstElementChild as HTMLElement;
    expect(frame(root)).toBe(COMPACT_FRAME);
    expect(iconSlot(root).className).toBe("mb-4 text-risk-critical");
    expect(titleEl(root).className).toBe(TITLE_CLASS);
    expect(hintEl(root).className).toBe(HINT_CLASS);
    expect(
      screen.getByRole("button", { name: "Reintentar" }).className,
    ).toBe(RETRY_BUTTON_CLASS);
  });

  it("compact is the only difference between the two heights", () => {
    const { container: tall } = render(<State title="a" />);
    const { container: short } = render(<State title="b" compact />);

    expect(frame(tall.firstElementChild!)).not.toBe(frame(short.firstElementChild!));
    expect(frame(tall.firstElementChild!)).toBe(FULL_FRAME);
    expect(frame(short.firstElementChild!)).toBe(COMPACT_FRAME);
  });

  it("keeps the testid the old failure state published", () => {
    // `data-testid="error-state"` is asserted seven times in
    // error-boundary.test.tsx. Renaming it is a break; the id names the STATE,
    // not the component, so it survives the merge unchanged — and the other two
    // tones get the same spelling for free.
    render(<State tone="error" title="a" />);
    render(<State title="b" />);
    render(<State tone="success" title="c" />);

    expect(screen.getByTestId("error-state")).toBeInTheDocument();
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByTestId("success-state")).toBeInTheDocument();
  });
});
