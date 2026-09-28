import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";

/**
 * What happens when a chunk never arrives.
 *
 * Task 6 asked whether a `lazy` chunk that fails to load surfaces through the
 * existing `ErrorBoundary` or renders nothing. Answer, measured rather than
 * assumed: it surfaces through it. React's `lazy` retries the render once the
 * import settles and RE-THROWS the rejection during render, so the nearest
 * error boundary above `<Routes>` catches it — which in `App.tsx` is the
 * `ErrorBoundary` that already wrapped `<Routes>` before this change. The user
 * gets the route error UI — heading, "Reintentar", "Volver al dashboard" —
 * instead of a spinner that never resolves.
 *
 * The failure is simulated by a mock factory that throws, which is the closest
 * honest stand-in for a real one: a hashed chunk URL that 404s after a deploy,
 * or a network that drops mid-flight, both reject the same `import()` promise
 * with an error. It goes through the real `React.lazy`, the real boundary and
 * the real logger. What is NOT covered: a real network stack.
 *
 * FALSIFIABLE, and the mutation was actually run: delete the `<ErrorBoundary>`
 * from App.tsx and both tests here go red, with vitest reporting the throw as
 * unhandled. The other mutation I first tried — moving `<Suspense>` outside
 * the `<ErrorBoundary>` — did NOT go red, because the throw originates in the
 * lazy component's render, which sits under `<Routes>` either way. The
 * boundary's position relative to `<Suspense>` is irrelevant; only its
 * presence matters. Recorded here because the plausible-sounding version of
 * that claim was wrong.
 */

vi.mock("../store/authStore", () => ({ useAuthStore: vi.fn() }));

vi.mock("../pages/TransactionsPage", () => {
  throw new Error(
    "Failed to fetch dynamically imported module: /assets/TransactionsPage-deadbeef.js",
  );
});

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
      };
      return selector ? selector(state) : state;
    },
  );
});

/** React logs caught errors; silence it so the suite output stays readable. */
afterEach(() => {
  vi.restoreAllMocks();
});

describe("App — a lazy chunk that fails to load", () => {
  it("surfaces through the route ErrorBoundary, not a blank screen and not a stuck spinner", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    renderAppAt("/transactions");

    expect(
      await screen.findByText("Esta página no se pudo mostrar"),
    ).toBeInTheDocument();

    // Both recovery affordances the route boundary offers are present — that is
    // what makes "the boundary caught it" observable rather than assumed.
    expect(
      screen.getByRole("button", { name: "Reintentar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Volver al dashboard" }),
    ).toBeInTheDocument();

    // The loading fallback must NOT be left spinning underneath: a pending
    // state that outlives a rejected chunk is exactly the "renders nothing"
    // failure the question was about.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByTestId("route-fallback")).not.toBeInTheDocument();
  });

  it("keeps the internal failure detail out of the user's screen", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    renderAppAt("/transactions");

    await screen.findByText("Esta página no se pudo mostrar");

    // A chunk URL is an internal detail: it is noise to an analyst and it
    // describes the deployment's file layout. It goes to the logger.
    expect(document.body.textContent).not.toContain("deadbeef");
    expect(console.error).toHaveBeenCalled();
  });
});
