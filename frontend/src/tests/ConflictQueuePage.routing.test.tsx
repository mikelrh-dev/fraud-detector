import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import App from "../App";
import { Sidebar } from "../components/Sidebar";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import { makeAuthState } from "../test-utils/authState";

/**
 * The conflict queue's route and its navigation entry.
 *
 * A SEPARATE FILE, and deliberately not an addition to `App.routing.test.tsx`.
 * That file mounts every page through `<App>` and pins one heading per path;
 * extending it is the obvious place for this coverage, and the standing
 * instruction for this change was zero amendments to existing tests. So the
 * router-level claims live here instead, at the same standard: render the real
 * `<App>` at a real path and wait for the real heading.
 *
 * What is asserted beyond "the route exists":
 *
 *  * ONE main landmark, checked through the router rather than in a page test.
 *    The shell does not wrap the pages — `<Sidebar>` is a sibling of the
 *    content region — so a shell that later grows its own `<main>` would leave
 *    every page-level test green while producing two nested landmarks, and
 *    the skip link's target would become ambiguous.
 *  * The navigation entry exists and marks ITSELF current. `Sidebar.isActive`
 *    has one special case (a prefix match for `transactions`), so a new key
 *    that nobody wired up renders an entry that never highlights, and that is
 *    only visible at the router level.
 *  * The paths that were already there still resolve. Adding a route is the
 *    kind of change that quietly breaks a neighbour, and `/transactions/:id`
 *    is the neighbour most at risk from anything transaction-shaped.
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

function renderSidebarAt(path: string, activeItem: "dashboard" | "transactions" | "alerts" | "conflicts") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar activeItem={activeItem} />
    </MemoryRouter>,
  );
}

const HEADING = "Cola de Conflictos";

/**
 * Warm the transform cache for the new page, for the reason documented at
 * length in `App.routing.test.tsx`: a cold dynamic import of a page takes
 * longer than testing-library's 1s default on the first test in a file, and
 * that is an artefact of the runner rather than a fact about routing.
 */
beforeAll(async () => {
  await import("../pages/ConflictQueuePage");
}, 120_000);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = makeAuthState();
      return selector ? selector(state) : state;
    },
  );
  server.use(
    http.get("*/api/v1/transactions", () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 }),
    ),
  );
});

describe("the conflict queue route", () => {
  it("mounts ConflictQueuePage at /conflicts", async () => {
    renderAppAt("/conflicts");
    expect(
      await screen.findByRole("heading", { name: HEADING }),
    ).toBeInTheDocument();
  });

  it("has exactly one main landmark at /conflicts", async () => {
    renderAppAt("/conflicts");
    await screen.findByRole("heading", { name: HEADING });
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });

  it("still routes /transactions/:id to the detail page", async () => {
    // The neighbour most at risk from a new transaction-shaped path. If
    // `/conflicts` were ever nested under `/transactions`, this goes red.
    renderAppAt("/transactions/test-uuid");
    expect(
      await screen.findByRole("heading", { name: "Detalle de Transacción" }),
    ).toBeInTheDocument();
  });

  it("still redirects an unknown path to the dashboard", async () => {
    // Adding a route must not disturb the catch-all.
    renderAppAt("/conflicts-plus-more");
    expect(
      await screen.findByRole("heading", { name: "Dashboard de detección de fraude" }),
    ).toBeInTheDocument();
  });

  it("an unauthenticated visitor is redirected away from /conflicts", async () => {
    mockUseAuthStore.mockImplementation(
      (selector?: (state: AuthState) => unknown) => {
        const state = { ...makeAuthState(), isAuthenticated: false };
        return selector ? selector(state) : state;
      },
    );

    renderAppAt("/conflicts");

    expect(
      await screen.findByRole("heading", { name: "Iniciar sesión" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: HEADING }),
    ).not.toBeInTheDocument();
  });
});

/**
 * The nav entry, scoped to the sidebar.
 *
 * Scoped deliberately: the queue's label and the page's `<h1>` are the same
 * words — deliberately, so an analyst who reads one has read the other — which
 * means an unscoped `getByText` finds two nodes and throws. That collision is
 * the feature working, so the query has to name which one it means.
 */
function navEntry(): HTMLButtonElement | null {
  const aside = document.querySelector("aside");
  const label = aside
    ? Array.from(aside.querySelectorAll("button")).find(
        (b) => b.textContent?.trim() === HEADING,
      )
    : null;
  return label ?? null;
}

describe("the conflict queue navigation entry", () => {
  it("renders the entry on every page", async () => {
    renderSidebarAt("/dashboard", "dashboard");
    expect(navEntry()).not.toBeNull();
  });

  it("marks itself current while on the queue", () => {
    renderSidebarAt("/conflicts", "conflicts");
    expect(navEntry()?.getAttribute("aria-current")).toBe("page");
  });

  it("does not mark itself current on another page", () => {
    // The negative half, because `isActive` returns true on a key match OR a
    // hardcoded prefix rule — and an entry that highlights everywhere is as
    // broken as one that never does.
    renderSidebarAt("/dashboard", "dashboard");
    expect(navEntry()?.getAttribute("aria-current")).toBeNull();
  });

  it("the queue marks ITSELF current by path, not only by prop", async () => {
    // Mounted through `<App>`, so `activeItem` comes from the page itself. This
    // is what catches a page that forgot to pass its own key.
    renderAppAt("/conflicts");
    await screen.findByRole("heading", { name: HEADING });
    await waitFor(() => {
      expect(navEntry()?.getAttribute("aria-current")).toBe("page");
    });
  });
});