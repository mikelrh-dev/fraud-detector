import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import ConflictQueuePage from "../pages/ConflictQueuePage";
import { server } from "./mocks/server";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import { makeAuthState } from "../test-utils/authState";
import type { ReactNode } from "react";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

/**
 * Two real disagreement rows, one per direction, with the exact numbers the
 * live database produced for `GET /transactions?conflict=true`.
 */
function twoConflicts() {
  server.use(
    http.get("*/api/v1/transactions", () =>
      HttpResponse.json({
        items: [
          {
            id: "aaaaaaaa-0000-0000-0000-000000000001",
            amount: 4200,
            currency: "EUR",
            merchant_name: "Acme Retail",
            merchant_category: "retail",
            card_last4: "4242",
            status: "flagged",
            risk_score: 56.28,
            rule_score: 85,
            ml_score: 27.554,
            classification: "review",
            user_id: "00000000-0000-0000-0000-000000000001",
            created_at: "2026-10-01T10:00:00Z",
            updated_at: "2026-10-01T10:00:00Z",
          },
          {
            id: "bbbbbbbb-0000-0000-0000-000000000002",
            amount: 900,
            currency: "EUR",
            merchant_name: "Night Owl",
            merchant_category: "travel",
            card_last4: "1881",
            status: "flagged",
            risk_score: 51.5,
            rule_score: 12,
            ml_score: 91,
            classification: "review",
            user_id: "00000000-0000-0000-0000-000000000001",
            created_at: "2026-10-01T11:00:00Z",
            updated_at: "2026-10-01T11:00:00Z",
          },
        ],
        total: 2,
        page: 1,
        page_size: 20,
      }),
    ),
  );
}

/** Many rows, so `totalPages > 1` at this page size and the pager renders. */
function fortyRows() {
  server.use(
    http.get("*/api/v1/transactions", ({ request }) => {
      const page = Number(new URL(request.url).searchParams.get("page") || "1");
      return HttpResponse.json({
        items: Array.from({ length: 20 }, (_, i) => ({
          id: `conflict-${page}-${i}`,
          amount: 100 + i,
          currency: "EUR",
          merchant_name: `Merchant ${i}`,
          merchant_category: "retail",
          card_last4: "4242",
          status: "flagged",
          risk_score: 50,
          rule_score: 85,
          ml_score: 12,
          classification: "review",
          user_id: "00000000-0000-0000-0000-000000000001",
          created_at: "2026-10-01T10:00:00Z",
          updated_at: "2026-10-01T10:00:00Z",
        })),
        total: 40,
        page,
        page_size: 20,
      });
    }),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuthStore.mockImplementation(
    (selector?: (state: AuthState) => unknown) => {
      const state = makeAuthState();
      return selector ? selector(state) : state;
    },
  );
});

/**
 * The touch floor and the dual-mode structure, checked the way the product
 * checks them: by finding the controls that exist and asking whether they meet
 * the floor, not by trusting a comment.
 */
describe("ConflictQueuePage — touch targets and dual-mode", () => {
  it("mobile card list sits under md:hidden", async () => {
    twoConflicts();
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(
        document.querySelectorAll("[data-testid^='conflict-card-']").length,
      ).toBeGreaterThan(0);
    });
    const card = document.querySelector("[data-testid^='conflict-card-']")!;
    let el: HTMLElement | null = card.parentElement;
    let found = false;
    while (el) {
      if (el.className.includes("md:hidden")) {
        found = true;
        break;
      }
      el = el.parentElement;
    }
    expect(found).toBe(true);
  });

  it("desktop table sits under hidden md:block", async () => {
    twoConflicts();
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    const table = await waitFor(() => {
      const found = document.querySelector("table");
      expect(found).toBeTruthy();
      return found!;
    });
    let el: HTMLElement | null = table.parentElement;
    let found = false;
    while (el) {
      if (
        el.className.includes("hidden") &&
        el.className.includes("md:block")
      ) {
        found = true;
        break;
      }
      el = el.parentElement;
    }
    expect(found).toBe(true);
  });

  it("every interactive control carries the house max-md:min-h-[40px] floor", async () => {
    // Enumerated rather than named: a control added later without the floor
    // goes red on its own, which is the whole point of walking the DOM instead
    // of asserting on two known buttons.
    twoConflicts();
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(
        document.querySelectorAll("[data-testid^='conflict-card-']").length,
      ).toBeGreaterThan(0);
    });

    const controls = Array.from(
      document.querySelectorAll("main button, main a"),
    ).filter((node) => (node.textContent ?? "").trim().length > 0);
    expect(controls.length).toBeGreaterThan(0);

    for (const control of controls) {
      expect(
        control.className,
        `"${control.textContent}" has no touch floor`,
      ).toContain("max-md:min-h-[40px]");
    }
  });

  it("the pager controls carry the floor too", async () => {
    // Asserted separately because the pager is behind `totalPages > 1`, so it
    // does not exist in the two-row fixture at all — a walk over a page with no
    // pager would pass without ever looking at it.
    fortyRows();
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    const next = await screen.findByRole("button", { name: "Siguiente" });
    expect(next.className).toContain("max-md:min-h-[40px]");
  });

  it("both layer scores are reachable in BOTH modes", async () => {
    // The desktop table and the mobile cards are separate JSX branches, not a
    // media query on one subtree, so an action or a column added to one and not
    // the other is invisible in a browser and green in a test that only reads
    // the whole document. Each mode is asserted on its own subtree.
    twoConflicts();
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(
        document.querySelectorAll("[data-testid^='conflict-card-']").length,
      ).toBeGreaterThan(0);
    });

    const mobile = document.querySelector("main .md\\:hidden") as HTMLElement;
    const desktop = document.querySelector("main .md\\:block") as HTMLElement;

    for (const mode of [mobile, desktop]) {
      const ruleCells = mode.querySelectorAll("[data-testid^='rule-score-']");
      const mlCells = mode.querySelectorAll("[data-testid^='ml-score-']");
      expect(ruleCells.length, "rule score cells missing").toBe(2);
      expect(mlCells.length, "ml score cells missing").toBe(2);
    }
  });
});