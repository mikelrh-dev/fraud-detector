import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../components/Sidebar";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function renderSidebar(activeItem: "dashboard" | "transactions" | "alerts" = "dashboard") {
  return render(
    <MemoryRouter>
      <Sidebar activeItem={activeItem} />
    </MemoryRouter>,
  );
}

describe("Sidebar — mobile drawer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = {
          user: { id: "test-user-123", role: "analista" },
          logout: vi.fn(),
          isAuthenticated: true,
          token: "mock-token",
          refreshToken: null,
          login: vi.fn(),
        };
        return selector ? selector(state) : state;
      },
    );
  });

  it("renders burger button with md:hidden", () => {
    renderSidebar();
    const burger = screen.getByRole("button", { name: /abrir menú/i });
    expect(burger).toBeInTheDocument();
    expect(burger.className).toContain("md:hidden");
  });

  it("burger button has aria-expanded=false initially", () => {
    renderSidebar();
    const burger = screen.getByRole("button", { name: /abrir menú/i });
    expect(burger).toHaveAttribute("aria-expanded", "false");
  });

  it("clicking burger opens drawer with role=dialog", () => {
    renderSidebar();
    const burger = screen.getByRole("button", { name: /abrir menú/i });
    fireEvent.click(burger);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-label", "Menú de navegación");
  });

  it("burger aria-expanded toggles to true when drawer is open", () => {
    renderSidebar();
    const burger = screen.getByRole("button", { name: /abrir menú/i });
    fireEvent.click(burger);
    expect(burger).toHaveAttribute("aria-expanded", "true");
  });

  it("Escape key closes the drawer", () => {
    renderSidebar();
    const burger = screen.getByRole("button", { name: /abrir menú/i });
    fireEvent.click(burger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("backdrop click closes the drawer", () => {
    renderSidebar();
    const burger = screen.getByRole("button", { name: /abrir menú/i });
    fireEvent.click(burger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // Backdrop is the fixed inset-0 element behind the drawer
    const backdrop = document.querySelector(".fixed.inset-0.bg-black\\/60");
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("desktop sidebar retains hidden md:flex", () => {
    renderSidebar();
    const aside = document.querySelector("aside");
    expect(aside).toBeTruthy();
    expect(aside!.className).toContain("hidden");
    expect(aside!.className).toContain("md:flex");
  });
});
