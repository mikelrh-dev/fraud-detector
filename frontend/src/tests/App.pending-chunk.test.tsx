import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

/**
 * The one thing App.routing.test.tsx cannot check: that the loading fallback
 * actually appears while a chunk is in flight.
 *
 * WHY A SEPARATE FILE: the fallback is only observable on a `React.lazy`
 * component's FIRST render attempt. `lazy` caches its resolved payload on the
 * component object, and those objects are module-level in `App.tsx`, so within
 * one test file the first test to reach a given route consumes that route's
 * suspension for the whole file. Verified, not assumed: with the fallback
 * assertions placed after the routing assertions in the same file, they failed
 * with "Unable to find role=status", because the routing test had already
 * loaded the chunk. Vitest gives each test file its own module registry, which
 * is exactly the isolation this needs. Declare a new fallback test for a route
 * in this file before the routing test in the other file and it will stop
 * suspending — that is the failure mode to expect, and it fails loudly.
 *
 * WHAT IS FAKED, EXACTLY: nothing. `React.lazy` unconditionally throws the
 * thenable returned by the dynamic import on the first render, so a lazy route
 * is necessarily suspended on the very first commit. The fallback is a real,
 * reachable state of the real component, not a simulated one. The only thing
 * that differs from production is its DURATION: a warmed test module resolves
 * in a microtask where a real chunk takes a network round trip. A test that
 * needed to control that duration would have to stub the dynamic import, and
 * then it would be testing the stub.
 *
 * FALSIFIABLE: delete the `<Suspense>` from App.tsx and the first assertion in
 * each test below fails, because React throws instead of rendering a fallback.
 * Narrow the boundary to the public routes and the guarded-route test fails.
 */

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

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
 * Warm the transform cache only. Measured at >2s cold, versus testing-library's
 * 1s default — an environment cost, not a routing fact. See the same note in
 * App.routing.test.tsx: this touches Vite's module registry, NOT React's
 * `lazy` payload, so the suspension this file is about still happens. The
 * 120s hook timeout covers the full-suite case, where vitest transforms this
 * alongside 40-odd other files on a loaded machine.
 */
beforeAll(async () => {
  await Promise.all([import("../pages/LoginPage"), import("../pages/AlertsPage")]);
}, 120_000);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = {
        user: { id: "test-user-id", role: "analista" },
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

describe("App — the Suspense boundary covers the lazy gap", () => {
  it("commits the fallback on the first render of a lazy route, then swaps in the page", async () => {
    renderAppAt("/login");

    // Synchronous assertion, immediately after mount. Whatever the chunk's
    // timing turns out to be, React has not resolved it yet at this point —
    // the boundary's fallback is on screen.
    expect(
      screen.getByRole("status", { name: "Cargando página" }),
    ).toBeInTheDocument();
    // And it is OUR fallback, not some other status region.
    expect(screen.getByTestId("route-fallback")).toBeInTheDocument();

    // ...and it is transient: the same node is gone once the chunk lands.
    expect(
      await screen.findByRole("heading", { name: "Iniciar sesión" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByTestId("route-fallback")).not.toBeInTheDocument();
  });

  it("covers a route that sits behind ProtectedRoute", async () => {
    renderAppAt("/alerts");

    // The boundary wraps the whole outlet, so a guarded route is covered too.
    // If someone later narrows the boundary to the public routes, the guard
    // renders a suspended lazy child with no boundary above it and this goes
    // red.
    expect(
      screen.getByRole("status", { name: "Cargando página" }),
    ).toBeInTheDocument();

    expect(
      await screen.findByRole("heading", { name: "Alertas" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
