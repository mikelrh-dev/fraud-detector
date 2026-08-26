import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import LoginPage from "../pages/LoginPage";
import { login } from "../api/auth";

vi.mock("../api/auth", () => ({
  login: vi.fn(),
}));

const mockLogin = login as unknown as ReturnType<typeof vi.fn>;

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
