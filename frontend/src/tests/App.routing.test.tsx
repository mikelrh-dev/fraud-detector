import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

/**
 * Task 6: `App` lazily imports every page, and lazy loading is the kind of
 * change that silently breaks routing while every page test still passes — the
 * page components are still tested, just never through the router that mounts
 * them.
 *
 * Nothing here asserts on a lazy wrapper. Every case renders `<App>` at a real
 * path and waits for that page's own `h1`. If a path, the `*` redirect, the
 * `ProtectedRoute` guard or the route ORDER changed, the heading at that path
 * would change or vanish and the test would go red. `h1`, not a snapshot: a
 * snapshot records whatever tree happens to exist today, including a wrong one.
 *
 * Note the deliberate oddity: the Dashboard's heading is `sr-only`
 * (DashboardPage.tsx). It is still in the accessibility tree — `sr-only` clips
 * with `position`/`size`, it does not `display: none` — so `getByRole`
 * legitimately finds it.
 */

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function authState() {
  return {
    user: { id: "test-user-id", role: "analista" },
    logout: vi.fn(),
    isAuthenticated: true,
    token: "mock-token",
    refreshToken: null,
    login: vi.fn(),
  };
}

function renderAppAt(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Pull every page module into Vite's transform cache first.
 *
 * WHY: `App` now loads pages through `import()`, and the first time vitest sees
 * a page it has to transform that page plus its whole dependency tree. Measured
 * here, a cold dynamic import of a page takes >2s, which is longer than
 * testing-library's 1s default — the first test in the file failed on a timeout
 * while every later one passed, purely on cache warmth. That is an artefact of
 * the test runner, not a fact about routing, and a routing test should not
 * depend on it.
 *
 * This does NOT neutralise the route-splitting behaviour under test: it warms
 * the module registry, not React's `lazy` payload. A `React.lazy` component
 * always throws its pending promise on its first render attempt regardless of
 * whether the module is already loaded — which is exactly what
 * App.pending-chunk.test.tsx relies on and asserts.
 *
 * The 120s hook timeout is not slack for its own sake: under the full suite,
 * vitest runs files in parallel on a loaded machine and transforming seven page
 * trees took over vitest's 10s default. The cost is one-off per run.
 */
beforeAll(async () => {
  await Promise.all([
    import("../pages/LoginPage"),
    import("../pages/RegisterPage"),
    import("../pages/DashboardPage"),
    import("../pages/TransactionDetail"),
    import("../pages/AlertsPage"),
    import("../pages/TransactionsPage"),
    import("../pages/CreateTransactionPage"),
  ]);
}, 120_000);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = authState();
      return selector ? selector(state) : state;
    },
  );
});

describe("App — every path still resolves to its own page", () => {
  it("mounts LoginPage at /login", async () => {
    renderAppAt("/login");
    expect(
      await screen.findByRole("heading", { name: "Iniciar sesión" }),
    ).toBeInTheDocument();
  });

  it("mounts RegisterPage at /register", async () => {
    renderAppAt("/register");
    expect(
      await screen.findByRole("heading", { name: "Crear cuenta" }),
    ).toBeInTheDocument();
  });

  it("mounts DashboardPage at /dashboard", async () => {
    renderAppAt("/dashboard");
    expect(
      await screen.findByRole("heading", { name: "Dashboard de detección de fraude" }),
    ).toBeInTheDocument();
  });

  it("mounts AlertsPage at /alerts", async () => {
    renderAppAt("/alerts");
    expect(
      await screen.findByRole("heading", { name: "Alertas" }),
    ).toBeInTheDocument();
  });

  it("mounts TransactionsPage at /transactions", async () => {
    renderAppAt("/transactions");
    expect(
      await screen.findByRole("heading", { name: "Transacciones" }),
    ).toBeInTheDocument();
  });

  it("mounts TransactionDetail at /transactions/:id", async () => {
    renderAppAt("/transactions/test-uuid");
    expect(
      await screen.findByRole("heading", { name: "Detalle de Transacción" }),
    ).toBeInTheDocument();
  });

  it("still routes /transactions/new to the create form, not the list", async () => {
    // Two routes share the `/transactions` prefix, so this is the one place
    // where rewiring goes quietly wrong: point it at TransactionsPage and the
    // heading here says "Transacciones". Falsifiable — rename the path or swap
    // the page and this goes red.
    //
    // What it does NOT pin, because measurement contradicted the assumption:
    // declaration order. React Router v6 ranks routes by specificity, so
    // moving this declaration below `/transactions` leaves the whole suite
    // green (verified). The ordering in App.tsx is a readability choice, not a
    // correctness one, and this test should not imply otherwise.
    renderAppAt("/transactions/new");
    expect(
      await screen.findByRole("heading", { name: "Nueva Transacción" }),
    ).toBeInTheDocument();
  });

  it("still redirects an unknown path to the dashboard", async () => {
    renderAppAt("/no-existe");
    expect(
      await screen.findByRole("heading", { name: "Dashboard de detección de fraude" }),
    ).toBeInTheDocument();
  });
});

describe("App — the guard is unchanged", () => {
  it("redirects an unauthenticated visitor away from /dashboard to /login", async () => {
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = { ...authState(), isAuthenticated: false };
        return selector ? selector(state) : state;
      },
    );

    renderAppAt("/dashboard");

    // The dashboard chunk is requested before the guard runs, so it may well
    // arrive — but the guard wins and the dashboard must never be shown.
    expect(
      await screen.findByRole("heading", { name: "Iniciar sesión" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Dashboard de detección de fraude" }),
    ).not.toBeInTheDocument();
  });
});
