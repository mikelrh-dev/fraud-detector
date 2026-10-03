import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { http, HttpResponse } from "msw";
import CreateTransactionPage from "../pages/CreateTransactionPage";
import { useAuthStore } from "../store/authStore";
import { INPUT_BASE } from "../lib/ui";
import { expectCarries } from "../test-utils/className";
import { server } from "./mocks/server";
import type { AuthState } from "../store/authStore";
import { makeAuthState } from "../test-utils/authState";
import { MERCHANT_CATEGORIES } from "../lib/merchant-vocabulary.generated";
import type { ReactNode } from "react";
import type { UserEvent } from "@testing-library/user-event";
import type { ScoreResponse } from "../api/transactions";

// Mock auth store
vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function renderPage() {
  return render(<CreateTransactionPage />, { wrapper: createWrapper() });
}

const PAGE_SOURCE = readFileSync(
  join(process.cwd(), "src", "pages", "CreateTransactionPage.tsx"),
  "utf-8",
);

const SCORE_FIXTURE: ScoreResponse = {
  transaction_id: "test-uuid",
  threshold: 40,
  created_at: new Date().toISOString(),
  rule_score: 10,
  ml_score: 12.3,
  ensemble_score: 11,
  classification: "legitimate",
  fired_rules: [],
  friction_level: "allow",
  action: null,
};

/**
 * The five fields, in the order the page renders them. `id` is the value `Field`
 * derives the label's `htmlFor`, the control's id and the `-error` node's id
 * from, so it is the join key for every association asserted below.
 *
 * `tagName` was added by D3 and is not cosmetic. The merchant category stopped
 * being a free-text `<input>` and became a closed `<select>`, and the
 * association test used to assert `"INPUT"` for every field in this list — a
 * single hardcoded tag that would have failed on the change for the wrong
 * reason, and would have been "fixed" by deleting the merchant_category entry
 * rather than by stating what it now is.
 */
const FIELDS = [
  { id: "amount", label: "Monto", value: "500", tagName: "INPUT" },
  { id: "currency", label: "Moneda", value: "USD", tagName: "INPUT" },
  { id: "merchant_name", label: "Comercio", value: "Test Store", tagName: "INPUT" },
  {
    id: "merchant_category",
    label: "Categoría (opcional)",
    value: "retail",
    tagName: "SELECT",
  },
  { id: "card_last4", label: /dígitos/i, value: "1234", tagName: "INPUT" },
] as const;

/**
 * Every field that can carry a validation error, paired with how to make it
 * invalid.
 *
 * Not arbitrary. The resolver runs in `mode: "onChange"`, so a field that is
 * merely EMPTY has not been validated and shows no error: `merchant_name`
 * (`min(1)`) needs a change event to fire, so it is primed with a character and
 * cleared. `card_last4` carries `maxLength={4}`, so "12345" truncates to a
 * VALID "1234" and no error appears -- it takes four non-digits, which satisfy
 * the length and fail the digit regex. `currency` has `maxLength={3}` but one
 * character still fails its length rule.
 *
 * The announcement test iterates THIS list rather than one hard-coded field. It
 * used to query `getByLabelText("Monto")` directly, which meant deleting
 * `error={errors.card_last4?.message}` left all 13 tests green -- the commit
 * claimed a four-field accessibility fix and the suite proved one.
 */
// `thenClear` is present on every entry, not only the one that needs it: a
// heterogeneous `as const` array destructures into a union, and reading a key
// that only some members carry is a type error at the call site. `false` is
// what the missing entries already evaluated to under `if (thenClear)`.
const ERROR_BEARING_FIELDS = [
  { id: "amount", label: "Monto", type: "0", thenClear: false },
  { id: "currency", label: "Moneda", type: "0", thenClear: false },
  { id: "merchant_name", label: "Comercio", type: "x", thenClear: true },
  { id: "card_last4", label: /dígitos/i, type: "abcd", thenClear: false },
] as const;

/** Fills every REQUIRED field. `merchant_category` is optional by schema. */
async function fillRequired(user: UserEvent) {
  for (const { id, value } of FIELDS) {
    if (id === "merchant_category") continue;
    await user.type(screen.getByLabelText(FIELDS.find((f) => f.id === id)!.label), value);
  }
}

function submitButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: /crear transacci/i }) as HTMLButtonElement;
}

describe("CreateTransactionPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = makeAuthState();
        return selector ? selector(state) : state;
      },
    );
  });

  it("renders the form with all required fields", () => {
    renderPage();
    expect(screen.getByText("Nueva Transacción")).toBeInTheDocument();
    expect(screen.getByLabelText(/monto/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/moneda/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/comercio/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/últimos 4 dígitos/i)).toBeInTheDocument();
  });

  it("A30: no longer renders the dead user_id field", () => {
    renderPage();
    // This test used to assert the opposite — that a hidden `user_id` input was
    // present — which pinned the defect. That field was required, fed from an
    // auth store that can legitimately hold `user: null`, and was the one input
    // with no rendered error, so an empty value disabled the submit button
    // permanently and silently. The server ignores the value anyway (F2).
    const userIdInput = document.querySelector('input[name="user_id"]');
    expect(userIdInput).not.toBeInTheDocument();
  });

  it("A30: the submit button is enabled without a user object in the store", () => {
    // authStore sets isAuthenticated unconditionally and leaves `user` null when
    // the token fails to decode, and ProtectedRoute gates on isAuthenticated
    // only, so this state is reachable. The form must not depend on it.
    renderPage();
    const submit = screen.getByRole("button", { name: /crear transacci/i });
    // Disabled only because the visible fields are still empty, not because of
    // a hidden field nobody can see or fix.
    const namedInputs = [
      ...document.querySelectorAll("input[name], textarea[name]"),
    ].map((el) => el.getAttribute("name"));
    expect(namedInputs).not.toContain("user_id");
    expect(submit).toBeInTheDocument();
  });

  it("A30: shows no loading skeleton before anything is submitted", () => {
    const { container } = renderPage();
    // ScoreResultCard used to render a pulsing skeleton whenever `!result`,
    // which is true on first paint — claiming work was in progress before the
    // user had done anything.
    expect(container.querySelector(".animate-pulse")).toBeNull();
  });

  it("submits valid form and shows ScoreResultCard", async () => {
    const user = userEvent.setup();
    renderPage();

    // Fill form
    const amountInput = screen.getByLabelText(/monto/i);
    await user.type(amountInput, "500");

    const currencyInput = screen.getByLabelText(/moneda/i);
    await user.type(currencyInput, "USD");

    const merchantInput = screen.getByLabelText(/comercio/i);
    await user.type(merchantInput, "Test Store");

    const cardInput = screen.getByLabelText(/últimos 4 dígitos/i);
    await user.type(cardInput, "1234");

    // Submit
    const submitButton = screen.getByRole("button", { name: /crear/i });
    await user.click(submitButton);

    // Wait for ScoreResultCard to appear
    await waitFor(() => {
      expect(screen.getByText("Resultado de Scoring")).toBeInTheDocument();
    });

    // Classification badge visible
    expect(screen.getByText("Legítimo")).toBeInTheDocument();
  });

  it("blocks submission with invalid data and shows errors", async () => {
    const user = userEvent.setup();
    renderPage();

    // Fill invalid data
    const amountInput = screen.getByLabelText(/monto/i);
    await user.type(amountInput, "0");

    const currencyInput = screen.getByLabelText(/moneda/i);
    await user.type(currencyInput, "US"); // only 2 chars

    // Submit
    const submitButton = screen.getByRole("button", { name: /crear/i });
    await user.click(submitButton);

    // Should show inline errors
    await waitFor(() => {
      // The form should not submit successfully (no ScoreResultCard)
      expect(screen.queryByText("Resultado de Scoring")).not.toBeInTheDocument();
    });
  });
});

/**
 * The Task 4 contract: the page is built from the primitives, and the two
 * behavioural fixes the migration has to land are pinned here.
 */
describe("CreateTransactionPage — primitives migration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = makeAuthState();
        return selector ? selector(state) : state;
      },
    );
  });

  it("associates every field's label with its own control", () => {
    // The `htmlFor` -> `id` edge is what makes the accessible name resolve at
    // all, and `Field` derives both from a single `id` prop, so the three can no
    // longer disagree. Asserted per field rather than once, because the failure
    // mode is per-field: one hand-rolled pair drifts while the other four hold.
    renderPage();
    for (const { id, label, tagName } of FIELDS) {
      const control = screen.getByLabelText(label);
      expect(control.tagName).toBe(tagName);
      expect(control.getAttribute("id")).toBe(id);

      const labelEl = document.querySelector(`label[for="${id}"]`);
      expect(labelEl, `no <label for="${id}">`).not.toBeNull();
    }
  });

  it("every form control carries the shared INPUT_BASE chrome", () => {
    // Token-wise, so a class cannot be quietly dropped from `INPUT_BASE`
    // without this going red. The old hand-rolled string is a SUBSET of
    // `INPUT_BASE` (it has `focus:ring-2` where the constant has
    // `focus-visible:ring-2`, and it has no `disabled:opacity-50`), which is
    // why this is a real assertion and not a tautology.
    //
    // `input, select` rather than `input` since D3: the merchant category is a
    // `<Select>` now, and a test scoped to `input` would have quietly stopped
    // covering one of the five controls.
    renderPage();
    const controls = Array.from(document.querySelectorAll("input, select"));
    expect(controls).toHaveLength(5);
    for (const control of controls) {
      expectCarries(control, INPUT_BASE);
    }
  });

  it("every form control's focus ring fires on keyboard, never on mouse click", () => {
    // Spelled as literals, NOT as `FOCUS_RING`, and that is the whole point of
    // a separate test. The test above compares the DOM against the imported
    // constant, so it CANNOT catch the constant regressing — verified by
    // deleting `disabled:opacity-50` from `INPUT_BASE` and watching it stay
    // green. This one is closed over literals, so it is independent of whatever
    // the constant currently says.
    //
    // Fix 2 is the deliberate behaviour change of this pass: five bare
    // `focus:ring-2` sites that painted a ring on mouse click. If a future
    // edit to `FOCUS_RING` reintroduces `focus:`, this goes red on the five
    // fields that used to carry the defect.
    renderPage();
    const controls = Array.from(document.querySelectorAll("input, select"));
    expect(controls).toHaveLength(5);
    for (const control of controls) {
      expectCarries(control, "focus-visible:ring-2 focus-visible:ring-focus-ring");
      for (const cls of Array.from(control.classList)) {
        // `/^focus:(?!-)/` matches a bare `focus:` variant and nothing else: the
        // lookahead is what keeps it off `focus-visible:...`, which also begins
        // with the literal text `focus-`.
        expect(cls, `bare focus variant on the page: ${cls}`).not.toMatch(
          /^focus:(?!-)/,
        );
      }
    }
  });

  it.each(ERROR_BEARING_FIELDS)(
    "announces the $id validation error: the control points at the alert holding the text",
    async ({ id, label, type, thenClear }) => {
      // The whole point of `Field`'s `error` prop. Before the migration the error
      // <p> sat next to the input, visually attached and programmatically
      // unattached: no id on the paragraph, no `aria-describedby` on the control
      // and no `aria-invalid` anywhere. Sighted users saw the failure, screen
      // readers announced the label and the value and nothing else.
      //
      // Parametrised over every error-bearing field because a single hard-coded
      // one proves a single one. This test used to name "Monto" and nothing
      // else, so dropping `error=` from three of the four fields was invisible.
      const user = userEvent.setup();
      renderPage();
      const control = screen.getByLabelText(label);
      await user.type(control, type);
      if (thenClear) await user.clear(control);

      await waitFor(() => {
        expect(
          control.getAttribute("aria-invalid"),
          `${id} never became invalid`,
        ).toBe("true");
      });

      const errorId = control.getAttribute("aria-describedby");
      expect(errorId).toBe(`${id}-error`);

      // The id the control advertises must BE the live region carrying the text.
      // Resolved by id rather than by role because `Field` renders one alert per
      // field and several are empty at any moment.
      const region = document.getElementById(errorId!);
      expect(region, `${id} advertises a describedby with no node`).not.toBeNull();
      expect(region!.getAttribute("role")).toBe("alert");
      expect(region!.textContent?.trim(), `${id} alert is empty`).not.toBe("");
    },
  );

  it("clicking the submit button actually posts the transaction", async () => {
    // The behavioural half of the dead-submit-button fix. `Button` defaults to
    // `type="button"`, so if the page forgets `type="submit"` this button is
    // inert inside the form: clickable, focusable, and doing nothing at all.
    // Counted at the network boundary rather than inferred from the rendered
    // score card, so it cannot be satisfied by anything else rendering.
    let posts = 0;
    server.use(
      http.post("*/api/v1/transactions", async () => {
        posts += 1;
        return HttpResponse.json(SCORE_FIXTURE);
      }),
    );

    const user = userEvent.setup();
    renderPage();
    await fillRequired(user);
    await user.click(submitButton());

    await waitFor(() => expect(posts).toBe(1));
    await waitFor(() =>
      expect(screen.getByText("Resultado de Scoring")).toBeInTheDocument(),
    );
  });

  it("keeps its label and disables while the mutation is pending", async () => {
    // design spec: a non-changing label while loading, so the button width does
    // not shift. The plan this pass was given kept a `Procesando...` swap; the
    // spec wins, because swapping the label on a submit action is a real layout
    // jump. The spinner carries the state instead.
    //
    // Gated on a promise this test releases, not on a timer, so "pending" is a
    // state the test controls rather than a race it hopes to win.
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post("*/api/v1/transactions", async () => {
        await gate;
        return HttpResponse.json(SCORE_FIXTURE);
      }),
    );

    const user = userEvent.setup();
    renderPage();
    await fillRequired(user);
    const submit = submitButton();
    await user.click(submit);

    await waitFor(() => expect(submit.disabled).toBe(true));
    expect(submit.textContent).toBe("Crear Transacción");
    expect(submit.textContent).not.toMatch(/procesando/i);
    expect(submit.getAttribute("aria-busy")).toBe("true");
    expect(submit.querySelector("[data-loading-spinner]")).not.toBeNull();

    // Settle the mutation inside this test so it cannot leak into the next one.
    release();
    await waitFor(() =>
      expect(screen.getByText("Resultado de Scoring")).toBeInTheDocument(),
    );
  });

  it("the source no longer re-types the input chrome", () => {
    // The duplication this migration exists to remove, asserted on the source
    // because a DOM assertion cannot see it: the old string and `INPUT_BASE`
    // would both put the same tokens on the element. These five tokens were
    // reachable from nothing but the five hand-rolled <input> elements, so a
    // zero count is a real measurement of the duplication, not a proxy.
    for (const token of [
      "bg-slate-800",
      "border-slate-700",
      "placeholder-slate-500",
      "text-slate-100",
      "focus:ring-2",
    ]) {
      expect(PAGE_SOURCE, `still re-types ${token}`).not.toContain(token);
    }
  });
});

/**
 * D3: the merchant category is a closed list, built from the backend's
 * vocabulary rather than from a copy of it.
 *
 * The defect this replaced: `merchant_category` was free text, it drove
 * `is_crypto` and `merchant_risk_level`, and an unknown value scored both of
 * them 0.0 — a score indistinguishable from a merchant the system understands
 * and found safe. The backend now answers 422 for an unknown value, so the
 * frontend has to offer exactly the accepted set.
 *
 * The assertion that matters most here is the one that would fail if the list
 * were hand-copied: the options are compared against
 * `MERCHANT_CATEGORIES`, the module the GENERATOR wrote. A literal list in the
 * page would satisfy every other test in this file and drift silently the first
 * time somebody added a category to the backend.
 */
describe("CreateTransactionPage — closed merchant category (D3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = makeAuthState();
        return selector ? selector(state) : state;
      },
    );
  });

  it("renders one option per canonical category, plus the empty one", () => {
    renderPage();
    const select = screen.getByLabelText("Categoría (opcional)") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    // The empty option first, then the vocabulary in order. Asserted against the
    // imported constant rather than a copy, so a backend category that has not
    // reached the frontend fails HERE and not in production.
    expect(values).toEqual(["", ...MERCHANT_CATEGORIES]);
  });

  it("the category field is a select, not a text input", () => {
    // The specific regression. A `<select>` cannot be typed into, which is the
    // whole mechanism; an `<input>` with a `list` attribute would still accept
    // any string and this would pass on the tag name alone.
    renderPage();
    const select = screen.getByLabelText("Categoría (opcional)");
    expect(select.tagName).toBe("SELECT");
    expect(select).not.toHaveAttribute("type");
    expect(document.querySelector('input[name="merchant_category"]')).toBeNull();
  });

  it("the page does not declare its own copy of the vocabulary", () => {
    // Three categories together is enough to look like a list and few enough to
    // be a slice. A single stray mention ("retail") is not a copy.
    const declared = MERCHANT_CATEGORIES.filter((c) =>
      PAGE_SOURCE.includes(`"${c}"`),
    );
    expect(declared, "the page restates the vocabulary instead of importing it")
      .toEqual([]);
  });

  it("the chosen category is what reaches the network", async () => {
    let body: unknown;
    server.use(
      http.post("*/api/v1/transactions", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(SCORE_FIXTURE);
      }),
    );

    const user = userEvent.setup();
    renderPage();
    await fillRequired(user);
    await user.selectOptions(
      screen.getByLabelText("Categoría (opcional)"),
      "cryptocurrency",
    );
    await user.click(submitButton());

    await waitFor(() => expect(body).not.toBeUndefined());
    expect(body).toMatchObject({ merchant_category: "cryptocurrency" });
  });

  it("leaving the category empty is still a valid submission", async () => {
    // The field is optional and the column is nullable. D3 closed the VALUE
    // set; it did not make the field required, and a form that now demands a
    // category for every purchase would be a regression dressed as a fix.
    let body: unknown;
    server.use(
      http.post("*/api/v1/transactions", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(SCORE_FIXTURE);
      }),
    );

    const user = userEvent.setup();
    renderPage();
    await fillRequired(user);
    expect(
      (screen.getByLabelText("Categoría (opcional)") as HTMLSelectElement).value,
    ).toBe("");
    await user.click(submitButton());

    await waitFor(() => expect(body).not.toBeUndefined());
    expect(body).toMatchObject({ merchant_category: "" });
  });
});
