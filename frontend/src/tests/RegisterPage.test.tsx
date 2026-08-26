import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import RegisterPage from "../pages/RegisterPage";
import { register } from "../api/auth";

vi.mock("../api/auth", () => ({
  register: vi.fn(),
}));

const mockRegister = register as unknown as ReturnType<typeof vi.fn>;

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
