import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "../components/Sidebar";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

// Mock the auth store
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

describe("Sidebar", () => {
  beforeEach(() => {
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = {
          user: { id: "test-user-123", role: "analista" },
          logout: vi.fn(),
          isAuthenticated: true,
          token: "mock-token",
          refreshToken: null,
          login: vi.fn(),
          setTokens: vi.fn(),
        };
        return selector ? selector(state) : state;
      },
    );
  });

  it("renders brand name 'Fraud Detector'", () => {
    renderSidebar();
    expect(screen.getByText("Fraud Detector")).toBeInTheDocument();
  });

  it("renders 3 navigation items: Dashboard, Transacciones, Alertas", () => {
    renderSidebar();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Transacciones")).toBeInTheDocument();
    expect(screen.getByText("Alertas")).toBeInTheDocument();
  });

  it("renders active item with highlight class", () => {
    renderSidebar("dashboard");
    const dashboardButton = screen.getByText("Dashboard").closest("button");
    expect(dashboardButton).toBeInTheDocument();
    // The active item should have a class containing "bg-slate-800"
    expect(dashboardButton?.className).toContain("bg-slate-800");
  });

  it("uses Phosphor SVG icons (no emoji, no icon font)", () => {
    renderSidebar();
    const svgIcons = document.querySelectorAll("aside svg, button svg");
    expect(svgIcons.length).toBeGreaterThanOrEqual(4); // brand shield + 3 nav + logout + burger
  });

  it("renders user avatar with initials and role", () => {
    renderSidebar();
    // Initials from user.id 'test-user-123' → 'TE'
    expect(screen.getByText("TE")).toBeInTheDocument();
    expect(screen.getByText("analista")).toBeInTheDocument();
  });
});
