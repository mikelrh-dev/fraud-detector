import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";
import TransactionsPage from "../pages/TransactionsPage";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import type { ReactNode } from "react";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

const TRANSACTIONS_SOURCE = readFileSync(
  join(process.cwd(), "src", "pages", "TransactionsPage.tsx"),
  "utf-8",
);

/**
 * Source with block comments removed, so the page's own notes about class
 * names it dropped are not counted as re-typing them, and the bare-`focus:`
 * scan does not match the word inside a comment.
 */
const TRANSACTIONS_CODE = TRANSACTIONS_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "");

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function renderPage() {
  return render(<TransactionsPage />, { wrapper: createWrapper() });
}

describe("TransactionsPage", () => {
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

  it("renders page title and transaction rows", async () => {
    renderPage();

    // Wait for data to load — Merchant 0 appears in both mobile card and desktop table
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });

    // Heading is an h1
    const heading = screen.getAllByText("Transacciones");
    expect(heading.length).toBeGreaterThanOrEqual(1);
  });

  it("renders filter status pills", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Todas")).toBeInTheDocument();
      expect(screen.getByText("Legítimo")).toBeInTheDocument();
      expect(screen.getByText("Revisión")).toBeInTheDocument();
      expect(screen.getByText("Fraude")).toBeInTheDocument();
    });
  });

  it("has a 'Nueva transacción' button that links to /transactions/new", async () => {
    renderPage();
    await waitFor(() => {
      const button = screen.getByRole("link", { name: /nueva transacción/i });
      expect(button).toBeInTheDocument();
      expect(button).toHaveAttribute("href", "/transactions/new");
    });
  });

  it("renders pagination controls", async () => {
    renderPage();
    await waitFor(() => {
      // Pagination should show page info (50 total / 10 per page = 5 pages)
      expect(screen.getByText(/50 transacciones/)).toBeInTheDocument();
    });
  });

  it("shows a classification column with live scores from deterministic fixtures", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Clasificación")).toBeInTheDocument();
    });

    // Merchant 0 is a review row (risk_score 62) — score rendered live
    const merchant0Elements = screen.getAllByText("Merchant 0");
    expect(merchant0Elements.length).toBeGreaterThanOrEqual(1);
    // The table row has the score
    const row0 = merchant0Elements[merchant0Elements.length - 1].closest("tr");
    expect(row0).toHaveTextContent("62.0");
    // Merchant 1 is legitimate (risk_score 15)
    const merchant1Elements = screen.getAllByText("Merchant 1");
    const row1 = merchant1Elements[merchant1Elements.length - 1].closest("tr");
    expect(row1).toHaveTextContent("15.0");
  });
});

/**
 * The Task 7 contract for this page. Class names are asserted as LITERALS:
 * comparing an element to `FOCUS_RING` or `BTN_VARIANTS.primary` moves both
 * sides when the constant is edited, so those assertions would hold no matter
 * what the page rendered — including the hand-rolled strings this replaced.
 */
describe("TransactionsPage — primitives migration", () => {
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

  it("the header CTA stays an anchor and carries the shared primary treatment", () => {
    renderPage();
    const cta = screen.getByRole("link", { name: /nueva transacción/i });

    // The element is the load-bearing part. `Button` renders a `<button>`, and
    // turning a navigation into a button would drop middle-click, ctrl-click
    // and "open in new tab" for nothing.
    expect(cta.tagName).toBe("A");
    expect(cta).toHaveAttribute("href", "/transactions/new");

    expect(cta.classList.contains("bg-accent")).toBe(true);
    // The gate is what distinguishes the variant from the string it replaced:
    // the hand-rolled class had a BARE `hover:bg-action-hover`.
    expect(cta.classList.contains("enabled:hover:bg-action-hover")).toBe(true);
    // Falsifiable: the hand-rolled class carried no focus ring at all.
    expect(cta.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(cta.classList.contains("focus-visible:ring-focus-ring")).toBe(true);
    expect(cta.classList.contains("rounded-lg")).toBe(true);
    expect(cta.classList.contains("px-4")).toBe(true);
    expect(cta.classList.contains("py-2")).toBe(true);
    expect(cta.classList.contains("text-sm")).toBe(true);
    expect(cta.classList.contains("gap-1.5")).toBe(true);
  });

  it("both date filters' focus ring is keyboard-only, and the compact chrome survives", () => {
    // The landmine-3 half of this page: a bare `focus:` ring painted on mouse
    // click. Falsifiable in both directions — the ring must be `focus-visible`,
    // and no bare `focus:` variant may remain on either control.
    renderPage();
    const dates = Array.from(
      document.querySelectorAll<HTMLInputElement>('input[type="date"]'),
    );
    expect(dates).toHaveLength(2);

    for (const input of dates) {
      expect(input.classList.contains("focus-visible:ring-2")).toBe(true);
      expect(input.classList.contains("focus-visible:ring-focus-ring")).toBe(true);
      for (const cls of Array.from(input.classList)) {
        // The lookahead is what keeps this off `focus-visible:...`, which also
        // begins with the literal text `focus-`.
        expect(cls, `bare focus variant: ${cls}`).not.toMatch(/^focus:(?!-)/);
      }
      // These controls deliberately keep their own chrome, because
      // `INPUT_BASE` cannot express it. Tailwind resolves two utilities of one
      // property by stylesheet order rather than attribute order, and it emits
      // `w-auto` before `w-full`, and `px-2` before `px-3` — so in both pairs
      // the base sorts LATER, an override through `className` would lose, and
      // the fields would stretch to fill the row. Pinned so a later "just use
      // Input here" is a visible change.
      expect(input.classList.contains("px-2")).toBe(true);
      expect(input.classList.contains("py-1.5")).toBe(true);
      expect(input.classList.contains("text-xs")).toBe(true);
      expect(input.classList.contains("text-slate-300")).toBe(true);
      expect(input.className).not.toContain("w-full");
    }
  });

  it("both merchant links' focus ring is keyboard-only", async () => {
    // Two links per transaction (mobile card + table cell), so the set is
    // counted rather than assumed. These already used `focus-visible:`; the
    // change here is that the string now comes from the shared constant
    // instead of being re-typed, so the two sites can no longer drift apart.
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });

    const merchantLinks = Array.from(
      document.querySelectorAll<HTMLAnchorElement>('a[href^="/transactions/tx-"]'),
    );
    expect(merchantLinks.length).toBeGreaterThanOrEqual(2);
    for (const link of merchantLinks) {
      expect(link.classList.contains("focus-visible:ring-2")).toBe(true);
      expect(link.classList.contains("focus-visible:ring-focus-ring")).toBe(true);
      for (const cls of Array.from(link.classList)) {
        expect(cls, `bare focus variant: ${cls}`).not.toMatch(/^focus:(?!-)/);
      }
    }
  });

  it("the status pills keep their selected/unselected pair, which has no variant", () => {
    // Pinned as a NON-migration. A segmented filter needs a SELECTED state, and
    // `BTN_VARIANTS` defines none: the selected treatment is `bg-slate-700
    // text-slate-200` and the unselected is `bg-slate-800/50 text-slate-400`,
    // neither of which is `primary`, `secondary` or `ghost`. The size is not
    // the obstacle here — these are `rounded-lg px-3 py-1.5 text-xs`, which is
    // exactly `BTN_SIZES.sm` — so a selected/unselected pair is all that is
    // missing. If it is ever added to the design system, this test is the thing
    // that has to change with it.
    renderPage();
    const todas = screen.getByRole("button", { name: "Todas" });
    const fraude = screen.getByRole("button", { name: "Fraude" });

    // `sm`'s radius and padding, which the migration would keep.
    expect(todas.classList.contains("rounded-lg")).toBe(true);
    expect(todas.classList.contains("px-3")).toBe(true);
    expect(todas.classList.contains("py-1.5")).toBe(true);
    expect(todas.classList.contains("text-xs")).toBe(true);
    // The selected one is the lighter fill; the unselected is the translucent
    // one. Two distinct treatments, and no variant names either.
    expect(todas.classList.contains("bg-slate-700")).toBe(true);
    expect(todas.classList.contains("text-slate-200")).toBe(true);
    expect(fraude.classList.contains("bg-slate-800/50")).toBe(true);
    expect(fraude.classList.contains("text-slate-400")).toBe(true);
    // This used to read "and still no focus ring, which is the accessibility
    // cost of the gap", and assert the absence. That conflated the missing
    // VARIANT with the missing RING: they are independent, the ring is one
    // orthogonal token, and composing it changes no fill, radius or size. So
    // the variant is still owed and still not made -- which is what the rest of
    // this test pins -- while the ring half is closed. Flipped, not deleted, so
    // the flip is the record. `filter-rows.a11y.test.tsx` now enumerates every
    // control in this row, so a fifth pill without a ring goes red on its own.
    expect(todas.classList.contains("focus-visible:ring-2")).toBe(true);
    expect(todas.classList.contains("focus-visible:ring-focus-ring")).toBe(true);
  });

  it("the pagination controls keep the filled-neutral treatment, which has no variant", async () => {
    // Same reasoning as the pills. `secondary` is transparent-with-a-border at
    // rest and fills to slate-800 on hover; these are filled slate-800 at rest
    // and lighten to slate-700. Adopting `secondary` would INVERT both states.
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/50 transacciones/)).toBeInTheDocument();
    });

    const prev = screen.getByRole("button", { name: "Anterior" });
    expect(prev.classList.contains("bg-slate-800")).toBe(true);
    // A BARE hover, which is the defect `enabled:` exists to fix — asserted
    // here so the day a filled-neutral variant lands, the gate is added with it.
    expect(prev.classList.contains("hover:bg-slate-700")).toBe(true);
    expect(prev.classList.contains("enabled:hover:bg-slate-700")).toBe(false);
  });

  it("the page carries no bare focus: variant anywhere in its code", () => {
    // The file-level statement of landmine 3. Scanned on comment-stripped code
    // so the page's own notes about the pattern do not trip it, and with a
    // lookahead so `focus-visible:` is not caught.
    for (const cls of TRANSACTIONS_CODE.split(/[\s"'`]+/)) {
      expect(cls, `bare focus variant: ${cls}`).not.toMatch(/^focus:(?!-)/);
    }
  });

  it("the source no longer re-types the header CTA treatment", () => {
    expect(TRANSACTIONS_CODE).toContain("BTN_VARIANTS.primary");
    expect(TRANSACTIONS_CODE).not.toContain("hover:bg-action-hover");
  });

  it("a failed list request announces itself, and is not the empty state", async () => {
    // The list's own failure UI had no live region, so a screen reader announced
    // nothing when the query failed. TransactionDetail says in its own comment
    // why that matters: "could not ask" and "there is nothing there" are
    // different claims, and an analyst who filtered to one transaction and sees
    // an empty table would conclude there is nothing to review -- when the
    // truth is that the request never came back.
    //
    // The two failure UIs in this product were inconsistent with each other:
    // TransactionDetail's had `role="alert"`, this one did not.
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderPage();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Error al cargar transacciones");
    // The distinction the whole component exists to keep: this is NOT the empty
    // state, and must not be findable as one.
    expect(screen.queryByText("No hay transacciones")).toBeNull();
    expect(screen.queryByTestId("empty-state")).toBeNull();
  });
});
