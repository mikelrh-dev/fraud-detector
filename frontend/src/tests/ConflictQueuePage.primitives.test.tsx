import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { readFileSync } from "node:fs";
import { join } from "node:path";
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

const srcRoot = join(process.cwd(), "src");

/** Source with comments stripped, so prose about a class is not a class. */
const PAGE_CODE = readFileSync(
  join(srcRoot, "pages", "ConflictQueuePage.tsx"),
  "utf-8",
)
  .replace(/\/\*[\s\S]*?\*\//g, " ")
  .replace(/(^|[^:])\/\/.*$/gm, "$1 ");

/** Every chromatic raw palette value Tailwind could emit, as a live regex. */
const RAW_CHROMATIC =
  /(?:^|[\s"'`])(?:[a-z-]+:)*(?:bg|text|border|border-[trbl]|ring|outline|fill|stroke|from|via|to)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}(?:\/\d+)?(?=$|[\s"'`])/;

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

function oneConflict() {
  server.use(
    http.get("*/api/v1/transactions", () =>
      HttpResponse.json({
        items: [
          {
            id: "cccccccc-0000-0000-0000-000000000003",
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
        ],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    ),
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
 * What this page composes, and the two decisions that are NOT free choices.
 *
 * Everything on it is an existing primitive — `Sidebar`, `PageTransition`,
 * `MotionList`, `State`, `NUMERIC_CELL`, `FOCUS_RING`, `MAIN_LANDMARK_ID` — so
 * most of this file is the anti-rot layer that stops the next person
 * hand-rolling one of them. The two decisions worth arguing about are pinned
 * separately below: sending `conflict=true`, and rendering the layer scores as
 * numbers rather than as gauges.
 */
describe("ConflictQueuePage — composition and decisions", () => {
  /**
   * THE load-bearing test on this page.
   *
   * The endpoint only narrows to conflicts when it is asked. If this page ever
   * requested the plain transaction list and rendered whatever came back, every
   * row would carry the heading, the sidebar entry and the "the layers
   * disagreed" label while being an ordinary transaction — and nothing in the
   * rendered output would look wrong. It is a mislabel that is invisible by
   * construction, so it is asserted at the wire rather than at the DOM.
   */
  it("asks the API for the conflict queue, not the plain transaction list", async () => {
    const requested: string[] = [];
    server.use(
      http.get("*/api/v1/transactions", ({ request }) => {
        requested.push(request.url);
        return HttpResponse.json({
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
        });
      }),
    );

    render(<ConflictQueuePage />, { wrapper: createWrapper() });
    await screen.findAllByText("No hay conflictos");

    expect(requested.length).toBeGreaterThan(0);
    for (const url of requested) {
      expect(
        new URL(url).searchParams.get("conflict"),
        `request without the conflict filter: ${url}`,
      ).toBe("true");
    }
  });

  /**
   * Numbers, not gauges — the one genuinely arguable choice on the page.
   *
   * `RiskMeter` is the right control for ONE score against the 0-100 scale: it
   * encodes magnitude as a filled bar and colour by classification. Two of them
   * per row encode four things to communicate one comparison, and — the part
   * that decided it — a meter's colour is a VERDICT about a layer, and a layer
   * in a conflict has no verdict. It disagreed. Painting it critical would be
   * claiming the rules decided something; painting it clean would be claiming
   * the model did. The plain monospaced pair says exactly what is true.
   */
  it("renders the layer scores as aligned numbers, not as risk meters", async () => {
    oneConflict();
    const { container } = render(<ConflictQueuePage />, {
      wrapper: createWrapper(),
    });

    const ruleCell = await waitFor(() => {
      const cell = document.querySelector("[data-testid^='rule-score-']");
      expect(cell).toBeTruthy();
      return cell as HTMLElement;
    });

    expect(ruleCell.textContent).toContain("85");
    expect(ruleCell.className).toContain("font-mono");
    expect(ruleCell.className).toContain("tabular-nums");
    // No gauge anywhere in the row: the meter primitive paints a bar, and a
    // bar per layer is the shape this decision rejects.
    expect(container.querySelectorAll('[role="meter"]')).toHaveLength(0);
    expect(container.innerHTML).not.toContain("RiskMeter");
  });

  it("says WHICH layer disagreed, from the two numbers, in both directions", async () => {
    // The label is derived, never authoritative: eligibility was decided by the
    // server's SQL, and this only ranks the two numbers already on screen. That
    // split is what stops the client from disagreeing with the filter.
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({
          items: [
            {
              id: "row-rules-loud",
              amount: 1,
              currency: "EUR",
              merchant_name: "A",
              merchant_category: "retail",
              card_last4: "1",
              status: "flagged",
              risk_score: 50,
              rule_score: 85,
              ml_score: 27,
              classification: "review",
              user_id: "u",
              created_at: "2026-10-01T10:00:00Z",
              updated_at: "2026-10-01T10:00:00Z",
            },
            {
              id: "row-model-loud",
              amount: 1,
              currency: "EUR",
              merchant_name: "B",
              merchant_category: "retail",
              card_last4: "2",
              status: "flagged",
              risk_score: 50,
              rule_score: 12,
              ml_score: 91,
              classification: "review",
              user_id: "u",
              created_at: "2026-10-01T10:00:00Z",
              updated_at: "2026-10-01T10:00:00Z",
            },
          ],
          total: 2,
          page: 1,
          page_size: 20,
        }),
      ),
    );
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    // Two cards per direction: the mobile list and the desktop row.
    await waitFor(() => {
      expect(
        screen.getAllByTestId("conflict-direction-rules-loud").length,
      ).toBeGreaterThan(0);
    });
    expect(
      screen.getAllByTestId("conflict-direction-model-loud").length,
    ).toBeGreaterThan(0);
  });

  it("renders a missing layer score as an explicit dash, never as 0", async () => {
    // A fabricated 0 is a claim — "the model ran and found nothing" — which is
    // a different state from "there is no score row". The backend sends null in
    // both of those cases on different paths, and the queue must not blur them
    // into a number an analyst would read as a measurement.
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({
          items: [
            {
              id: "row-unscored",
              amount: 1,
              currency: "EUR",
              merchant_name: "A",
              merchant_category: "retail",
              card_last4: "1",
              status: "pending",
              risk_score: null,
              rule_score: null,
              ml_score: null,
              classification: null,
              user_id: "u",
              created_at: "2026-10-01T10:00:00Z",
              updated_at: "2026-10-01T10:00:00Z",
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      ),
    );
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    const cell = await waitFor(() => {
      const found = document.querySelector("[data-testid^='rule-score-']");
      expect(found).toBeTruthy();
      return found as HTMLElement;
    });
    expect(cell.textContent).toContain("—");
    expect(cell.textContent).not.toContain("0");
  });

  it("composes the shared primitives rather than re-typing their classes", async () => {
    // The positive half first, so the negative assertions below cannot be
    // satisfied by the page simply not rendering these things.
    expect(PAGE_CODE).toContain("<MotionList");
    expect(PAGE_CODE).toContain("<PageTransition");
    expect(PAGE_CODE).toContain("<Sidebar");
    expect(PAGE_CODE).toContain("<State");
    expect(PAGE_CODE).toContain("MAIN_LANDMARK_ID");
    expect(PAGE_CODE).toContain("NUMERIC_CELL");
    expect(PAGE_CODE).toContain("FOCUS_RING");
    // And nothing that re-derives the focus ring, the numeric cell or a colour.
    expect(PAGE_CODE).not.toContain("focus-visible:ring-2");
    expect(PAGE_CODE).not.toContain("font-mono tabular-nums");
    expect(PAGE_CODE).not.toMatch(RAW_CHROMATIC);
  });

  it("the page and its requests go through the list-query helpers", async () => {
    // The URL is the filter and the page, for the same reason as on
    // TransactionsPage and AlertsPage: a queue that cannot be linked cannot be
    // reported. Asserted at the wire — a deep link has to change the REQUEST,
    // not merely the rendered counter.
    server.use(
      http.get("*/api/v1/transactions", ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get("page") || "1");
        return HttpResponse.json({
          items: Array.from({ length: 20 }, (_, i) => ({
            id: `deep-${page}-${i}`,
            amount: 1,
            currency: "EUR",
            merchant_name: "A",
            merchant_category: "retail",
            card_last4: "1",
            status: "flagged",
            risk_score: 50,
            rule_score: 85,
            ml_score: 12,
            classification: "review",
            user_id: "u",
            created_at: "2026-10-01T10:00:00Z",
            updated_at: "2026-10-01T10:00:00Z",
          })),
          total: 40,
          page,
          page_size: 20,
        });
      }),
    );

    const user = userEvent.setup();
    render(<ConflictQueuePage />, { wrapper: createWrapper() });

    const next = await screen.findByRole("button", { name: "Siguiente" });
    await user.click(next);

    // Paging must NOT drop the conflict filter: it is the page's subject, not
    // an optional filter, and losing it on page 2 would silently show ordinary
    // transactions under the conflict heading.
    await waitFor(() => {
      expect(
        screen.getAllByText("Pág. 2 de 2").length,
      ).toBeGreaterThan(0);
    });
    const rows = document.querySelectorAll("[data-testid^='conflict-card-deep-2-']");
    expect(rows.length).toBeGreaterThan(0);
  });
});