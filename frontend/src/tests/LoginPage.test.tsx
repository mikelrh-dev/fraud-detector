import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import LoginPage from "../pages/LoginPage";
import { login } from "../api/auth";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
}));

const mockLogin = login as unknown as ReturnType<typeof vi.fn>;

const LOGIN_SOURCE = readFileSync(
  join(process.cwd(), "src", "pages", "LoginPage.tsx"),
  "utf-8",
);

/**
 * The page's source with its block comments removed.
 *
 * WHY: the duplication assertions below are about code, and the page's code
 * carries comments that legitimately quote the class names it used to type —
 * `disabled:bg-red-800/50` is named in the note explaining why it went away.
 * Scanning the raw file matched the comment, which is the assertion failing for
 * the wrong reason: it could never have gone green, so it proved nothing.
 *
 * The strip is a plain non-greedy block-comment removal. That is sound here
 * because the file contains no block-comment delimiters inside a string or a
 * regex — and if a future edit introduced one, the assertion would start
 * passing over a chunk of source it should not have, which is the safe
 * direction to fail in.
 */
const LOGIN_CODE = LOGIN_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "");

function renderLogin() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    mockLogin.mockReset();
  });

  it("renders the split-screen brand panel and form heading", () => {
    renderLogin();
    // Brand headline (desktop left panel)
    expect(screen.getByText(/antes de que ocurra/)).toBeInTheDocument();
    // Form heading
    expect(screen.getByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("renders email and password fields with labels above", () => {
    renderLogin();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña")).toHaveAttribute(
      "type",
      "password",
    );
  });

  it("flips password visibility with the eye toggle", async () => {
    const user = userEvent.setup();
    renderLogin();

    const password = screen.getByLabelText("Contraseña");
    expect(password).toHaveAttribute("type", "password");

    const toggle = screen.getByRole("button", { name: "Mostrar contraseña" });
    await user.click(toggle);

    expect(password).toHaveAttribute("type", "text");
    expect(
      screen.getByRole("button", { name: "Ocultar contraseña" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Ocultar contraseña" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("shows the reserved error line for an invalid email", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText("Email"), "no-es-un-email");
    await user.type(screen.getByLabelText("Contraseña"), "whatever123");
    await user.click(screen.getByRole("button", { name: "Ingresar" }));

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Ingrese un email válido.");
    expect(alert.className).toContain("text-risk-critical");
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it("links to the register page", () => {
    renderLogin();
    const link = screen.getByText("Crear cuenta aquí");
    expect(link).toHaveAttribute("href", "/register");
  });
});

/**
 * The Task 7 contract for this page: the two controls that genuinely fit the
 * primitives are built from them, and the ones that do not are left alone with
 * the divergence written down rather than bent to fit.
 *
 * Class names are asserted as LITERALS. Comparing an element to
 * `BTN_VARIANTS.primary` moves both sides when the constant is edited, so the
 * assertion would pass no matter what the page rendered — including the
 * hand-rolled `<button>` this replaced.
 */
describe("LoginPage — primitives migration", () => {
  beforeEach(() => {
    mockLogin.mockReset();
  });

  it("the submit control is a submit-typed primary Button with the keyboard focus ring", () => {
    renderLogin();
    const submit = screen.getByRole("button", { name: "Ingresar" });

    // `type="submit"` is the whole reason the click does anything: `Button`
    // defaults to `type="button"`, so dropping it makes the control inert
    // inside the form. The old hand-rolled button also said "submit", so this
    // alone cannot tell the migration apart — the ring and the variant can.
    expect(submit.getAttribute("type")).toBe("submit");
    expect(submit.classList.contains("bg-accent")).toBe(true);
    expect(submit.classList.contains("enabled:hover:bg-action-hover")).toBe(true);
    // Falsifiable: the raw <button> this replaced carried no focus ring at
    // all, so reverting the migration drops these two and this goes red.
    expect(submit.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(submit.classList.contains("focus-visible:ring-focus-ring")).toBe(true);
    // Layout the primitive does not supply, and therefore has to keep.
    expect(submit.classList.contains("h-11")).toBe(true);
    expect(submit.classList.contains("w-full")).toBe(true);
    // The one visual delta on this control, pinned: the hand-rolled disabled
    // FILL is gone in favour of `BTN_BASE`'s opacity dim.
    //
    // Reworded, because the old form named the class it was forbidding. This
    // file is no longer scanned by Tailwind (`@source not "./tests"`), so that
    // alone would have been enough — but the SAME class is still named in
    // prose comments in `src/pages/LoginPage.tsx` and `RegisterPage.tsx`, which
    // ARE scanned, so the rule survived the exclusion and the test was part of
    // the reason. Spelling the class here also made the assertion read as class
    // usage when it asserts the opposite.
    //
    // It is now STRONGER, not weaker, and in the direction that matters: it
    // forbids ANY hand-rolled `disabled:` background, not one specific red, and
    // it positively pins the sanctioned replacement. `disabled:bg-` is not a
    // utility, so nothing is emitted; `disabled:opacity-50` is a real class the
    // product already uses, so pinning it costs nothing.
    expect([...submit.classList].filter((c) => c.startsWith("disabled:bg-"))).toEqual(
      [],
    );
    expect(submit.classList.contains("disabled:opacity-50")).toBe(true);
  });

  it("the submit control still submits the form", async () => {
    // `type="submit"` is the behaviour; the class above is the shape. A page
    // can satisfy every class assertion above and still not submit, which is
    // exactly the defect `CreateTransactionPage` shipped with.
    const user = userEvent.setup();
    mockLogin.mockResolvedValue({ access_token: "t", refresh_token: "r" });
    renderLogin();

    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Contraseña"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "Ingresar" }));

    expect(mockLogin).toHaveBeenCalledWith({
      email: "a@b.com",
      password: "hunter2hunter2",
    });
  });

  it("the demo CTA is a secondary Button whose hover is gated on enabled", async () => {
    renderLogin();
    const demo = screen.getByRole("button", {
      name: /demo: probar con cuenta de prueba/i,
    });

    expect(demo.classList.contains("border-slate-700")).toBe(true);
    expect(demo.classList.contains("text-slate-300")).toBe(true);
    expect(demo.classList.contains("rounded-lg")).toBe(true);
    // The gate is the assertion. The old class had a BARE `hover:bg-slate-800`,
    // so this distinguishes the variant from the string it replaced instead of
    // matching both.
    expect(demo.classList.contains("enabled:hover:bg-slate-800")).toBe(true);
    expect(demo.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(demo.classList.contains("mt-4")).toBe(true);
  });

  it("the demo CTA still logs in", async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValue({ access_token: "t", refresh_token: "r" });
    renderLogin();

    await user.click(
      screen.getByRole("button", { name: /demo: probar con cuenta de prueba/i }),
    );

    expect(mockLogin).toHaveBeenCalledWith({
      email: "admin@frauddetector.dev",
      password: "admin123",
    });
  });

  it("the form error is still exactly one live region, so getByRole('alert') is unambiguous", () => {
    // WHY THIS IS ASSERTED AND NOT ASSUMED: if these two fields were migrated
    // to `Field`, the page would carry one always-rendered `role="alert"` per
    // field plus the form-level one, and `getByRole("alert")` — the query the
    // test above uses to read the error — would start throwing on multiple
    // matches. The count is the observable that would catch it, so it is
    // pinned here rather than left to be discovered later.
    renderLogin();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
  });

  it("the source no longer re-types the two button treatments it migrated", () => {
    // Asserted on the SOURCE, because a DOM assertion cannot see duplication:
    // the old string and the constants put the same tokens on the element.
    // Scanned against LOGIN_CODE, so the page's own notes about the class
    // names it dropped do not count as re-typing them.
    for (const token of [
      "disabled:bg-red-800/50",
      "hover:bg-action-hover",
      "enabled:hover:bg-slate-800",
    ]) {
      expect(LOGIN_CODE, `still re-types ${token}`).not.toContain(token);
    }
    // And the positive half, so the negative assertions above cannot be
    // satisfied by the file simply not containing any of these.
    expect(LOGIN_CODE).toContain("<Button");
  });

  it("the auth field spec is left alone, divergence recorded", () => {
    // The counterpart to the notes above: this page was NOT migrated onto
    // `Input`/`Field`, and the reason is written down in the source. Pinned so
    // that a later "while we are here" edit has to remove this assertion in
    // the same commit as the change it contradicts.
    expect(LOGIN_SOURCE).toContain("AUTH_INPUT_CLASS");
    // The hand-rolled `focus:` ring survives, deliberately. `focus:` fires on
    // mouse click, which is the defect `FOCUS_RING` fixes everywhere else, so
    // this is a known-open item rather than an oversight — and it is exactly
    // why the assertion is here, to be deleted together with its fix.
    const email = renderLogin().container.querySelector<HTMLInputElement>(
      'input[type="email"]',
    )!;
    expect(email.className).toContain("focus:ring-risk-critical/25");
    expect(email.className).not.toContain("focus-visible:ring-2");
  });
});
