import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import RegisterPage from "../pages/RegisterPage";
import { register } from "../api/auth";

vi.mock("../api/auth", () => ({
  register: vi.fn(),
}));

const mockRegister = register as unknown as ReturnType<typeof vi.fn>;

const REGISTER_SOURCE = readFileSync(
  join(process.cwd(), "src", "pages", "RegisterPage.tsx"),
  "utf-8",
);

/**
 * Source with block comments removed, so the page's own notes about class
 * names it dropped are not counted as re-typing them. See the same helper's
 * note in LoginPage.test.tsx for why a raw-file scan here would never go
 * green.
 */
const REGISTER_CODE = REGISTER_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "");

function renderRegister() {
  return render(
    <MemoryRouter>
      <RegisterPage />
    </MemoryRouter>,
  );
}

describe("RegisterPage", () => {
  beforeEach(() => {
    mockRegister.mockReset();
  });

  it("renders the split-screen brand panel and form heading", () => {
    renderRegister();
    expect(screen.getByText(/antes de que ocurra/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Crear cuenta" })).toBeInTheDocument();
  });

  it("flips password visibility with the eye toggle", async () => {
    const user = userEvent.setup();
    renderRegister();

    const password = screen.getByLabelText("Contraseña");
    expect(password).toHaveAttribute("type", "password");

    await user.click(
      screen.getByRole("button", { name: "Mostrar contraseña" }),
    );
    expect(password).toHaveAttribute("type", "text");
    expect(
      screen.getByRole("button", { name: "Ocultar contraseña" }),
    ).toBeInTheDocument();
  });

  it("renders a 3-segment strength meter with one critical segment for weak passwords", async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText("Contraseña"), "corto");

    const meter = screen.getByTestId("password-strength");
    const segments = meter.querySelectorAll("span.rounded-full");
    expect(segments.length).toBe(3);
    // Weak -> exactly one filled segment, risk-critical tone
    const filled = Array.from(segments).filter((s) =>
      s.className.includes("bg-risk-critical"),
    );
    expect(filled.length).toBe(1);
    expect(meter.textContent).toContain("Débil");
  });

  it("fills two warn segments and three clean segments as strength grows", async () => {
    const user = userEvent.setup();
    renderRegister();

    const password = screen.getByLabelText("Contraseña");

    await user.type(password, "mediumpass1"); // 11 chars -> medium
    let meter = screen.getByTestId("password-strength");
    expect(
      Array.from(meter.querySelectorAll("span.rounded-full")).filter((s) =>
        s.className.includes("bg-risk-warn"),
      ).length,
    ).toBe(2);

    await user.type(password, "LongEnough1A"); // >12 chars mixed + number -> strong
    meter = screen.getByTestId("password-strength");
    expect(
      Array.from(meter.querySelectorAll("span.rounded-full")).filter((s) =>
        s.className.includes("bg-risk-clean"),
      ).length,
    ).toBe(3);
    expect(meter.textContent).toContain("Fuerte");
  });

  it("shows the reserved error line when the password is too short", async () => {
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText("Usuario"), "analyst");
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Contraseña"), "short");
    await user.click(screen.getByRole("button", { name: "Crear Cuenta" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "La contraseña debe tener al menos 8 caracteres.",
    );
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it("keeps the success state with a link back to login after registration", async () => {
    mockRegister.mockResolvedValue({});
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText("Usuario"), "analyst");
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Contraseña"), "Sup3rSecure!");
    await user.click(screen.getByRole("button", { name: "Crear Cuenta" }));

    expect(await screen.findByText("Cuenta creada exitosamente.")).toBeInTheDocument();
    // "Volver a Login" exists both as success CTA and footer link
    const backLinks = screen.getAllByText("Volver a Login");
    expect(backLinks.length).toBeGreaterThanOrEqual(2);
    expect(backLinks.every((l) => l.getAttribute("href") === "/login")).toBe(
      true,
    );
  });
});

/**
 * The Task 7 contract for this page. Class names are asserted as LITERALS:
 * comparing an element to `BTN_VARIANTS.primary` moves both sides when the
 * constant is edited, so the assertion would hold no matter what the page
 * rendered — including the hand-rolled `<button>` this replaced.
 */
describe("RegisterPage — primitives migration", () => {
  beforeEach(() => {
    mockRegister.mockReset();
  });

  it("the submit control is a submit-typed primary Button with the keyboard focus ring", () => {
    renderRegister();
    const submit = screen.getByRole("button", { name: "Crear Cuenta" });

    expect(submit.getAttribute("type")).toBe("submit");
    expect(submit.classList.contains("bg-accent")).toBe(true);
    expect(submit.classList.contains("enabled:hover:bg-action-hover")).toBe(true);
    // Falsifiable: the raw <button> this replaced had no focus ring at all.
    expect(submit.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(submit.classList.contains("focus-visible:ring-focus-ring")).toBe(true);
    expect(submit.classList.contains("h-11")).toBe(true);
    expect(submit.classList.contains("w-full")).toBe(true);
    // The one visual delta on this control, pinned.
    expect(submit.className).not.toContain("disabled:bg-red-800/50");
  });

  it("the submit control still registers, and still sends analyst", async () => {
    // `type="submit"` is the behaviour; the class assertions above are the
    // shape. A page can satisfy every class assertion and still never submit.
    const user = userEvent.setup();
    mockRegister.mockResolvedValue({});
    renderRegister();

    await user.type(screen.getByLabelText("Usuario"), "analyst");
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Contraseña"), "Sup3rSecure!");
    await user.click(screen.getByRole("button", { name: "Crear Cuenta" }));

    expect(mockRegister).toHaveBeenCalledWith({
      username: "analyst",
      email: "a@b.com",
      password: "Sup3rSecure!",
      role: "analyst",
    });
  });

  it("the success CTA stays a real link and picks up the shared treatment", async () => {
    mockRegister.mockResolvedValue({});
    const user = userEvent.setup();
    renderRegister();

    await user.type(screen.getByLabelText("Usuario"), "analyst");
    await user.type(screen.getByLabelText("Email"), "a@b.com");
    await user.type(screen.getByLabelText("Contraseña"), "Sup3rSecure!");
    await user.click(screen.getByRole("button", { name: "Crear Cuenta" }));
    await screen.findByText("Cuenta creada exitosamente.");

    // TWO links say "Volver a Login" (the success CTA and the footer), so
    // they are told apart by being inside the success panel.
    const links = screen.getAllByText("Volver a Login") as HTMLAnchorElement[];
    const cta = links.find((l) => l.classList.contains("bg-accent"))!;
    expect(cta, "no CTA carries the accent background").toBeDefined();

    // It is still an anchor. This is the load-bearing part: `Button` renders a
    // <button>, and swapping the element would drop middle-click and
    // "open in new tab" for no gain.
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", "/login");

    // Falsifiable: the hand-rolled class had a BARE `hover:bg-action-hover` and
    // no focus ring, so reverting drops these.
    expect(cta.classList.contains("enabled:hover:bg-action-hover")).toBe(true);
    expect(cta.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(cta.classList.contains("focus-visible:ring-focus-ring")).toBe(true);
    expect(cta.classList.contains("h-11")).toBe(true);
    expect(cta.classList.contains("w-full")).toBe(true);
  });

  it("the strength meter logic is untouched by the migration", async () => {
    // The meter is the one piece of real behaviour on this page that is NOT a
    // form control, and a refactor that quietly re-tuned it would still pass
    // every class assertion above. Pinned at its boundaries: 11 chars is
    // medium, 13 chars with mixed case and a digit is strong.
    const user = userEvent.setup();
    renderRegister();

    const password = screen.getByLabelText("Contraseña");
    await user.type(password, "mediumpass1");
    expect(screen.getByTestId("password-strength")).toHaveTextContent("Media");

    await user.type(password, "LongEnough1A");
    expect(screen.getByTestId("password-strength")).toHaveTextContent("Fuerte");
  });

  it("the source no longer re-types the treatments it migrated", () => {
    for (const token of [
      "disabled:bg-red-800/50",
      "hover:bg-action-hover",
      "btn-motion active:scale-[0.98] h-11",
    ]) {
      expect(REGISTER_CODE, `still re-types ${token}`).not.toContain(token);
    }
    expect(REGISTER_CODE).toContain("<Button");
    // The positive half for the link, so the negative half above cannot be
    // satisfied by the file simply not mentioning those strings.
    expect(REGISTER_CODE).toContain("BTN_VARIANTS.primary");
  });

  it("the auth field spec is left alone, divergence recorded", () => {
    // The counterpart to the note in the page: this was NOT migrated onto
    // `Input`/`Field`. Pinned so a later "while we are here" edit has to remove
    // this assertion in the same commit as the change it contradicts.
    expect(REGISTER_CODE).toContain("AUTH_INPUT_CLASS");
    const email = renderRegister().container.querySelector<HTMLInputElement>(
      'input[type="email"]',
    )!;
    // The hand-rolled `focus:` ring survives, deliberately: it paints on
    // mouse click, which is the defect `FOCUS_RING` fixes everywhere else.
    // It is a known-open item, and it is why the assertion lives here — to be
    // deleted together with its fix.
    expect(email.className).toContain("focus:ring-risk-critical/25");
    expect(email.className).not.toContain("focus-visible:ring-2");
  });
});
