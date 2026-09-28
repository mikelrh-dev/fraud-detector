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
    setTokens: vi.fn(),
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

describe("App — every route exposes exactly one main landmark", () => {
  /**
   * WHY A ROUTER-LEVEL ASSERTION AND NOT SEVEN PAGE TESTS: the invariant is
   * about the assembled document, not about a component in isolation, and only
   * here can "exactly one" be checked across all seven routes at once. Each
   * page test renders one page in a harness; a shell that added its own
   * `<main>` would leave every one of them green.
   *
   * THE REASON, CORRECTED. An earlier version of this comment claimed the
   * router-level render was needed because a `<main>` nested in sectioning
   * content loses the implicit `main` role, so `getByRole("main")` would find
   * nothing. That mechanism is real in a BROWSER accessibility tree and
   * `@testing-library/dom` does not implement it — measured across twelve host
   * elements (`div`, `nav`, `section`, `aside`, `article`, `form`, `header`,
   * `footer`, `blockquote`, `li`, `dd`, `fieldset`), and a `<main>` inside every
   * one of them still resolves to role `main`. So the test could not have
   * caught what that paragraph said, and anyone reading it would have believed
   * a guarantee it does not provide.
   *
   * THE REAL REASON, which is narrower and actually load-bearing: the failure
   * this guards against is a SECOND landmark, not a hidden one. The shell does
   * not wrap the pages — `<Sidebar>` is a sibling of the content region, so
   * every page owns its own `<main>` — and the obvious future refactor is a
   * layout route with an `<Outlet/>`, which would make it natural to lift the
   * landmark into the shell. That is the change which produces two nested
   * `main` elements, and `toHaveLength(1)` is exactly the assertion that goes
   * red when it happens. Two pages were missing the landmark when the rule was
   * added (TransactionsPage and CreateTransactionPage rendered a plain `<div>`
   * where DashboardPage and AlertsPage already rendered `<main>`), so the
   * assertion is not theoretical.
   */
  const PATHS: Array<[string, string]> = [
    ["/login", "Iniciar sesión"],
    ["/register", "Crear cuenta"],
    ["/dashboard", "Dashboard de detección de fraude"],
    ["/alerts", "Alertas"],
    ["/transactions", "Transacciones"],
    ["/transactions/new", "Nueva Transacción"],
    ["/transactions/test-uuid", "Detalle de Transacción"],
  ];

  for (const [path, heading] of PATHS) {
    it(`has one main at ${path}`, async () => {
      renderAppAt(path);
      // Wait for the page itself first, or this would measure the Suspense
      // fallback instead of the route.
      await screen.findByRole("heading", { name: heading });
      expect(screen.getAllByRole("main")).toHaveLength(1);
    });
  }
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
