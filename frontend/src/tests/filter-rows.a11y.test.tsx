import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import AlertsPage from "../pages/AlertsPage";
import DashboardPage from "../pages/DashboardPage";
import TransactionsPage from "../pages/TransactionsPage";
import TransactionDetailPage from "../pages/TransactionDetail";
import TransactionTable from "../components/TransactionTable";
import { Sidebar } from "../components/Sidebar";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import { makeAuthState } from "../test-utils/authState";

/**
 * WHY THIS FILE EXISTS: A MISSING CLASS IS A GAP NO LINTER CAN SEE.
 *
 * `ui/no-raw-class-tokens` fires on class strings that are PRESENT and wrong —
 * a hand-rolled copy of a token the design system owns. It has nothing to say
 * about a class that is simply ABSENT, and absence is how three of the four
 * filter rows in this product ended up with no focus treatment at all: nine
 * other call sites carried `FOCUS_RING`, three did not, and nothing anywhere
 * recorded the difference. A keyboard user tabbing those rows got no indicator
 * of any kind, on the one control a triage pass runs dozens of times.
 *
 * So this is the other half of the rule, and it is deliberately a TEST rather
 * than a lint check. A lint rule for absence has to read JSX, guess which
 * elements are interactive, and then either exempt every recorded divergence
 * with a suppression — the "ten suppressions and a rule nobody reads" outcome
 * this codebase's own notes warn against — or carry a new exemption vocabulary
 * that is its own rot. A test enumerates the controls that actually rendered
 * and asks the only question that matters.
 *
 * FALSIFIABILITY, since an assertion nobody can break is decoration:
 *
 *  - It reads the rendered DOM, never an imported constant. Asserting
 *    "carries FOCUS_RING" would be a tautology — mutating the constant would
 *    move both sides — and the eslint config says the same thing about why the
 *    page tests must name classes as literals.
 *  - It asserts the two house tokens as LITERALS, so deleting the ring from a
 *    call site is a red test, not a silent regression.
 *  - `expect(controls.length).toBeGreaterThan(0)` guards the whole file against
 *    the one failure mode that matters: a filter row that stops rendering, or a
 *    selector that stops matching, would otherwise make every assertion in the
 *    loop vacuously true. The count is asserted explicitly and per surface.
 *  - It also asserts the ring is NOT on a bare `focus:` prefix, which is the
 *    half that a `toContain("ring")` check would wave through: a ring that
 *    fires on mouse click is the defect `FOCUS_RING` was written to end.
 */

/** The two tokens `FOCUS_RING` is made of, as literals. See above on why. */
const HOUSE_RING = ["focus-visible:ring-2", "focus-visible:ring-focus-ring"];

const INTERACTIVE =
  "button, a[href], input, select, textarea, [role='button'], [role='link']";

vi.mock("../store/authStore", () => ({ useAuthStore: vi.fn() }));
const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function mockAuth() {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = makeAuthState();
      return selector ? selector(state) : state;
    },
  );
}

/**
 * Assert every interactive control in `row` carries the house ring.
 *
 * The control count is passed in rather than inferred, so a caller cannot
 * quietly enumerate an empty set and pass. `row` may itself be the control, in
 * which case it is included — otherwise a single-button call site would
 * enumerate zero descendants and the count assertion would be the only thing
 * standing between it and a vacuous pass.
 */
function expectEveryControlHasTheRing(
  row: HTMLElement,
  expectedControls: number,
  where: string,
) {
  const controls = [
    ...(row.matches(INTERACTIVE) ? [row] : []),
    ...Array.from(row.querySelectorAll<HTMLElement>(INTERACTIVE)),
  ];
  expect(controls.length, `${where}: the filter row rendered controls`).toBe(
    expectedControls,
  );

  for (const control of controls) {
    const label =
      control.getAttribute("aria-label") ??
      control.textContent?.trim().slice(0, 24) ??
      control.tagName;
    for (const token of HOUSE_RING) {
      expect(
        control.classList.contains(token),
        `${where}: "${label}" is missing ${token}`,
      ).toBe(true);
    }
    // The bare-prefix half. `focus:ring-2` would satisfy a naive "does it
    // mention a ring" check while reintroducing the mouse-click flash.
    for (const token of control.classList) {
      expect(
        token.startsWith("focus:"),
        `${where}: "${label}" paints on mouse click via ${token}`,
      ).toBe(false);
    }
  }
}

describe("filter rows — every interactive control carries the focus ring", () => {
  beforeEach(() => {
    mockAuth();
  });

  it("AlertsPage: the four status filter tabs", async () => {
    render(<AlertsPage />, { wrapper: createWrapper() });

    const first = await screen.findByRole("button", { name: "Todas" });
    const row = first.parentElement as HTMLElement;
    // Unawaited siblings: the row is one `.map`, so one control proves the rest
    // mounted, and the count below proves all four did.
    expect(
      await screen.findByRole("button", { name: "Resueltas" }),
    ).toBeInTheDocument();

    expectEveryControlHasTheRing(row, 4, "AlertsPage status filter row");
  });

  it("TransactionsPage: the four status pills", async () => {
    render(<TransactionsPage />, { wrapper: createWrapper() });

    const first = await screen.findByRole("button", { name: "Todas" });
    const row = first.parentElement as HTMLElement;
    expect(
      await screen.findByRole("button", { name: "Fraude" }),
    ).toBeInTheDocument();

    expectEveryControlHasTheRing(row, 4, "TransactionsPage status pills");
  });

  it("TransactionTable: the four classification pills", () => {
    render(
      <MemoryRouter>
        <TransactionTable
          transactions={[]}
          total={0}
          page={1}
          pageSize={20}
          onSort={() => {}}
          onPageChange={() => {}}
          onFilterChange={() => {}}
          onTransactionClick={() => {}}
        />
      </MemoryRouter>,
    );

    const first = screen.getByRole("button", { name: "Todos" });
    const row = first.parentElement as HTMLElement;

    expectEveryControlHasTheRing(
      row,
      4,
      "TransactionTable classification filter row",
    );
  });

  it("AlertsPage: the alert-row action control, the fourth omission", async () => {
    // Found by the same inspection as the three filter rows and fixed with the
    // same one token. It is not a filter, so nothing would have caught it if
    // this file only covered filters.
    render(<AlertsPage />, { wrapper: createWrapper() });

    const first = (await screen.findAllByRole("button", { name: "Revisar" }))[0];
    expect(first).toBeDefined();

    expectEveryControlHasTheRing(
      first as HTMLElement,
      1,
      "AlertsPage action button",
    );
  });
});

/**
 * The touch floor, pinned in the same idiom and for the same reason: a
 * `min-h` that is missing is as invisible as a ring that is missing, and the
 * value is the house one every other raised control uses.
 */
const TOUCH_FLOOR = "max-md:min-h-[40px]";

describe("raised controls carry the house touch floor", () => {
  beforeEach(() => {
    mockAuth();
  });

  it("AlertsPage: both pagination buttons", async () => {
    // `total` has to exceed the page size or the control renders nothing, and
    // the assertion would then be about an absent element — which is why the
    // count is asserted before the classes, below.
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ items: [], total: 100, page: 2, page_size: 20 }),
      ),
    );
    render(<AlertsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: "Anterior" }).length,
      ).toBeGreaterThan(0);
    });
    // Rendered once per responsive mode (mobile card list + desktop table).
    for (const label of ["Anterior", "Siguiente"]) {
      for (const btn of screen.getAllByRole("button", { name: label })) {
        expect(btn.classList.contains(TOUCH_FLOOR), `${label}`).toBe(true);
        expect(btn.classList.contains("focus-visible:ring-2")).toBe(true);
      }
    }
  });

  it("TransactionsPage: both pagination buttons", async () => {
    // Non-empty on purpose: the pagination lives inside the "has rows" branch,
    // so an empty result set renders the empty state and the control never
    // mounts. `total: 50` is enough for `totalPages > 1` at this page size.
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({
          items: Array.from({ length: 10 }, (_, i) => ({
            id: `tx-${i}`,
            amount: 100 + i * 500,
            currency: "USD",
            merchant_name: `Merchant ${i}`,
            merchant_category: "retail",
            card_last4: "1234",
            status: "approved",
            risk_score: 15,
            classification: "legitimate",
            scoring: null,
            user_id: "00000000-0000-0000-0000-000000000001",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          })),
          total: 50,
          page: 2,
          page_size: 10,
        }),
      ),
    );
    render(<TransactionsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: "Anterior" }).length,
      ).toBeGreaterThan(0);
    });
    for (const label of ["Anterior", "Siguiente"]) {
      for (const btn of screen.getAllByRole("button", { name: label })) {
        expect(btn.classList.contains(TOUCH_FLOOR), `${label}`).toBe(true);
        expect(btn.classList.contains("focus-visible:ring-2")).toBe(true);
      }
    }
  });

  it("TransactionTable: both pagination buttons", () => {
    render(
      <MemoryRouter>
        <TransactionTable
          transactions={[]}
          total={100}
          page={2}
          pageSize={20}
          onSort={() => {}}
          onPageChange={() => {}}
          onFilterChange={() => {}}
          onTransactionClick={() => {}}
        />
      </MemoryRouter>,
    );
    for (const label of ["Anterior", "Siguiente"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.classList.contains(TOUCH_FLOOR), `${label}`).toBe(true);
      expect(btn.classList.contains("focus-visible:ring-2")).toBe(true);
    }
  });

  it("Sidebar: the burger reaches the floor on both axes", () => {
    // Unconditional, because the burger is `md:hidden` and therefore exists
    // only below the breakpoint where a `max-md:` prefix would apply.
    render(
      <MemoryRouter>
        <Sidebar activeItem="dashboard" />
      </MemoryRouter>,
    );
    const burger = screen.getByRole("button", {
      name: "Abrir menú de navegación",
    });
    expect(burger.classList.contains("min-h-[40px]")).toBe(true);
    // `min-h` alone would leave a 40x20 target, which does not clear the floor
    // on the axis the floor is about.
    expect(burger.classList.contains("min-w-[40px]")).toBe(true);
  });

  it("TransactionDetail: the back arrow reaches the floor without growing its glyph", async () => {
    // The page reads the id off the route, and the header only renders once the
    // transaction resolves, so both are set up here rather than asserted around.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    function DetailWrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/transactions/test-uuid"]}>
            <Routes>
              <Route path="/transactions/:id" element={children} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );
    }
    render(<TransactionDetailPage />, { wrapper: DetailWrapper });

    const back = await screen.findByRole("button", {
      name: "Volver al dashboard",
    });
    expect(back.classList.contains(TOUCH_FLOOR)).toBe(true);
    expect(back.classList.contains("max-md:min-w-[40px]")).toBe(true);
    // The glyph is the thing that must NOT have moved.
    expect(back.querySelector("svg")!.classList.contains("w-5")).toBe(true);
    expect(back.querySelector("svg")!.classList.contains("h-5")).toBe(true);
  });
});

/**
 * NO NESTED ASSERTIVE LIVE REGIONS.
 *
 * `State`'s error tone renders `role="alert"`, which is its contract. Three
 * wrapper `<div>`s also carried `role="alert"` because they predate the merge
 * and were the live region before `<State>` existed. The result was two
 * assertive live regions nested inside one another: the subtree is announced
 * twice, and the outer one re-announces whenever anything inside it changes --
 * including the retry button the failure state renders.
 *
 * The fix is that the wrapper is a PANEL, not a message, so it carries no role.
 * Asserted structurally rather than by naming the three sites, so a fourth
 * wrapper with the same habit goes red on its own.
 *
 * Note the direction this is NOT claiming: nothing here says the failure must
 * announce. A hand-rolled block that is the only announcement on a page is
 * correct and several still are. The defect is specifically two assertive
 * regions claiming the same subtree.
 */
describe("a failure panel wraps the live region, it does not add one", () => {
  beforeEach(() => {
    mockAuth();
  });

  function expectNoNestedAlerts(where: string) {
    const alerts = Array.from(
      document.querySelectorAll<HTMLElement>('[role="alert"]'),
    );
    // Anti-vacuity: a surface that renders no alert at all would make the loop
    // below trivially true, which is exactly the silent-passing failure.
    expect(alerts.length, `${where}: rendered a failure region`).toBeGreaterThan(
      0,
    );

    for (const outer of alerts) {
      const inner = outer.querySelectorAll('[role="alert"]').length;
      expect(
        inner,
        `${where}: a role="alert" contains ${inner} more, so the failure is announced twice`,
      ).toBe(0);
    }
  }

  it("AlertsPage, on a failed alerts request, in both responsive modes", async () => {
    server.use(
      http.get("*/api/v1/alerts", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    render(<AlertsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(
        document.querySelectorAll('[role="alert"]').length,
      ).toBeGreaterThan(0);
    });
    expectNoNestedAlerts("AlertsPage failure block");
  });

  it("DashboardPage, on a failed chart query", async () => {
    // Only the CHART query: the recent-transactions table has its own banner,
    // and failing both would put two failure blocks on the page.
    server.use(
      http.get("*/api/v1/transactions", ({ request }) => {
        const size = new URL(request.url).searchParams.get("page_size");
        if (size === "100") {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 10 });
      }),
    );
    render(<DashboardPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(
        document.querySelectorAll('[role="alert"]').length,
      ).toBeGreaterThan(0);
    });
    expectNoNestedAlerts("DashboardPage chart failure");
  });
});
