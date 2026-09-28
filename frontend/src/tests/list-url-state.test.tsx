import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import TransactionsPage from "../pages/TransactionsPage";
import AlertsPage from "../pages/AlertsPage";
import { useAuthStore } from "../store/authStore";
import type { AuthState } from "../store/authStore";
import { server } from "./mocks/server";
import type { ReactNode } from "react";

vi.mock("../store/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

/* ------------------------------------------------------------------ *
 * The fixture
 *
 * Local to this file, and it deliberately OVERRIDES the shared handlers
 * (msw's `server.use` takes precedence, and `afterEach` restores the shared
 * ones) for two reasons, both of which are about making the assertions
 * falsifiable rather than about the plumbing:
 *
 * 1. It HONOURS `status`. The shared fixture ignores the filter and returns the
 *    same ten rows whatever you ask for, so a page that forwarded a garbage
 *    value straight to the API would still render ten rows and every
 *    "the filter was applied" assertion would pass against an implementation
 *    that applied nothing. Here, filtering is real, so the row set moves.
 * 2. It RECORDS the outgoing query string. Whether the page sent `status=approved`
 *    or `status=legitimate` or `status=banana` is the whole difference between
 *    the URL vocabulary and the transport's, and only the wire can say.
 * ------------------------------------------------------------------ */

const TX_PAGE_SIZE = 10;
const TX_TOTAL = 50;
const ALERT_PAGE_SIZE = 20;
const ALERT_TOTAL = 60;

let txRequests: string[] = [];
let alertRequests: string[] = [];

function txRow(page: number, i: number) {
  const isReview = i % 3 === 0;
  return {
    id: `tx-${page}-${i}`,
    amount: 100 + i * 500,
    currency: "USD",
    merchant_name: `Merchant ${i}`,
    merchant_category: "retail",
    card_last4: "1234",
    status: isReview ? "flagged" : "approved",
    risk_score: isReview ? 62 : 15,
    classification: isReview ? "review" : "legitimate",
    scoring: null,
    user_id: "00000000-0000-0000-0000-000000000001",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

function alertRow(page: number, i: number) {
  const statuses = ["open", "reviewed", "resolved"];
  const status = statuses[i % 3];
  return {
    id: `alert-${page}-${i}`,
    transaction_id: `tx-alert-${i}`,
    status,
    score: 45 + i * 15,
    threshold: 40,
    classification: "fraud",
    reviewed_by: null,
    reviewed_at: null,
    created_at: new Date().toISOString(),
  };
}

/**
 * One page of results, or none when the page asked for does not exist.
 *
 * `total` is the unfiltered total when nothing is filtered, and the MATCHED
 * count when something is — so a filter that selects 7 of 10 reports 7 and has
 * one page, and asking for page 2 of it is genuinely out of range. That is what
 * makes the clamping test meaningful rather than a fixture that always has five
 * pages to give.
 */
function resolve<T>(
  candidates: T[],
  filtered: boolean,
  page: number,
  pageSize: number,
  unfilteredTotal: number,
) {
  const total = filtered ? candidates.length : unfilteredTotal;
  const totalPages = Math.ceil(total / pageSize);
  return {
    items: page <= totalPages ? candidates : [],
    total,
    page,
    page_size: pageSize,
  };
}

beforeEach(() => {
  txRequests = [];
  alertRequests = [];
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

  server.use(
    http.get("*/api/v1/transactions", ({ request }) => {
      const url = new URL(request.url);
      txRequests.push(url.search);
      const status = url.searchParams.get("status");
      const page = Number(url.searchParams.get("page") || "1");
      const all = Array.from({ length: TX_PAGE_SIZE }, (_, i) => txRow(page, i));
      const matched = status
        ? all.filter((row) => row.status === status)
        : all;
      return HttpResponse.json(
        resolve(matched, status !== null, page, TX_PAGE_SIZE, TX_TOTAL),
      );
    }),
    http.get("*/api/v1/alerts", ({ request }) => {
      const url = new URL(request.url);
      alertRequests.push(url.search);
      const status = url.searchParams.get("status");
      const page = Number(url.searchParams.get("page") || "1");
      const all = Array.from({ length: ALERT_PAGE_SIZE }, (_, i) =>
        alertRow(page, i),
      );
      const matched = status
        ? all.filter((row) => row.status === status)
        : all;
      return HttpResponse.json(
        resolve(matched, status !== null, page, ALERT_PAGE_SIZE, ALERT_TOTAL),
      );
    }),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

/* ------------------------------------------------------------------ *
 * Harness
 * ------------------------------------------------------------------ */

/**
 * Renders the router's current address, so "the URL changed" is a fact about
 * the DOM rather than a claim about which hook was called.
 *
 * A `<span data-testid>`, not an `<output>`: the latter carries an implicit
 * `role="status"`, which would make this probe an aria-live region that
 * announces the query string on every keystroke.
 */
function LocationProbe() {
  const location = useLocation();
  return (
    <span data-testid="address">
      {location.pathname + location.search}
    </span>
  );
}

/**
 * Real history navigation, driven the way a user drives it.
 *
 * `navigate(-1)` pops the router's own history stack, which is the same
 * mechanism the browser's back button uses: the router emits a POP and the
 * whole tree re-renders from the restored entry. Asserting that a component
 * "handled" a pop would be the tautology this exists to avoid.
 */
function BackControl() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>Atrás</button>;
}

function renderAt(path: string, page: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <LocationProbe />
          <BackControl />
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }
  return render(<Wrapper>{page}</Wrapper>);
}

const renderTransactions = (path = "/transactions") =>
  renderAt(path, <TransactionsPage />);

const renderAlerts = (path = "/alerts") => renderAt(path, <AlertsPage />);

/** The address the user would copy, as one string. */
function address() {
  return screen.getByTestId("address").textContent ?? "";
}

function addressParams() {
  return new URLSearchParams(address().split("?")[1] ?? "");
}

/** The first request the page made, as raw query text. */
function firstTxRequest() {
  return new URLSearchParams(txRequests[0] ?? "");
}

/**
 * The most recent request. After a history pop or a filter change the FIRST
 * request is the one for the previous view, so an assertion about "what the
 * page fetched now" has to read the last one.
 */
function lastTxRequest() {
  return new URLSearchParams(txRequests[txRequests.length - 1] ?? "");
}

function firstAlertRequest() {
  return new URLSearchParams(alertRequests[0] ?? "");
}

/** Which status pill/tab is selected, read from the selected treatment. */
function selectedLabel(name: string) {
  const control = screen.getByRole("button", { name });
  return control.classList.contains("bg-slate-700") ? name : null;
}

const dateInputs = () =>
  Array.from(document.querySelectorAll<HTMLInputElement>('input[type="date"]'));

/* ================================================================== *
 * URL -> view. The direction that makes a shared link work at all.
 * ================================================================== */

describe("TransactionsPage — a URL with a filter renders that filter applied", () => {
  it("applies the status a deep link names, in the API's own vocabulary", async () => {
    renderTransactions("/transactions?status=legitimate");

    // The wire. `legitimate` is the product's word; `approved` is what the
    // transport is asked for. Forwarding the raw value would send
    // `status=legitimate`, which the server does not know.
    await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));
    expect(firstTxRequest().get("status")).toBe("approved");

    // The view. `Merchant 0` is the fixture's flagged row, so it is exactly the
    // row a working `legitimate` filter removes. Asserting both directions
    // matters: an implementation that ignored the URL would still render
    // `legitimate` as the selected pill below, and one that forwarded the junk
    // would render an empty table and fail the row assertions.
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 1").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByText("Merchant 0")).not.toBeInTheDocument();
  });

  it("shows the deep-linked pill as the selected one", async () => {
    renderTransactions("/transactions?status=review");
    // Read from the SELECTED treatment as a literal, never from an imported
    // constant: the point is what the DOM carries, and the treatment is the
    // contract these controls have.
    await waitFor(() => {
      expect(selectedLabel("Revisión")).toBe("Revisión");
    });
    expect(selectedLabel("Todas")).toBeNull();
    expect(selectedLabel("Legítimo")).toBeNull();
    expect(selectedLabel("Fraude")).toBeNull();
  });

  it("applies the page a deep link names", async () => {
    renderTransactions("/transactions?page=3");

    await waitFor(() => {
      expect(screen.getByText(/Página 3 de 5/)).toBeInTheDocument();
    });
    expect(firstTxRequest().get("page")).toBe("3");
    // The rows are page 3's, not page 1's. The counter alone would survive an
    // implementation that labelled the current page correctly and then fetched
    // the first one anyway, and the row ids carry the page they came from.
    await waitFor(() => {
      expect(document.querySelector('a[href="/transactions/tx-3-0"]')).not.toBeNull();
    });
    expect(document.querySelector('a[href="/transactions/tx-1-0"]')).toBeNull();
  });

  it("applies a deep-linked date range to the date controls", async () => {
    renderTransactions("/transactions?from=2026-01-05&to=2026-01-31");
    await waitFor(() => {
      expect(dateInputs().map((input) => input.value)).toEqual([
        "2026-01-05",
        "2026-01-31",
      ]);
    });
  });

  it("leaves a deep link with no query on the default view", async () => {
    renderTransactions("/transactions");
    await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));

    // No filter reached the wire, which is what "no filter" means there.
    // `page` is deliberately not asserted: `listTransactions` has always sent
    // it, including `page=1`, and the canonical-form rule below is about the
    // address a person reads, not about the transport's own defaults.
    expect(firstTxRequest().has("status")).toBe(false);
    expect(firstTxRequest().has("from")).toBe(false);
    expect(firstTxRequest().has("to")).toBe(false);
    // And the default view has exactly one address, with no `?page=1` in it.
    expect(address()).toBe("/transactions");
  });
});

/* ================================================================== *
 * view -> URL. The direction that makes a view shareable.
 * ================================================================== */

describe("TransactionsPage — a filter applied in the UI updates the URL", () => {
  it("writes the status pill the user clicked", async () => {
    renderTransactions();
    await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Fraude" }));

    await waitFor(() => {
      expect(addressParams().get("status")).toBe("fraud");
    });
    expect(addressParams().has("page")).toBe(false);
  });

  it("writes a date the user picked", async () => {
    renderTransactions();
    await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));

    const [from, to] = dateInputs();
    fireEvent.change(from, { target: { value: "2026-02-01" } });

    await waitFor(() => {
      expect(addressParams().get("from")).toBe("2026-02-01");
    });
    // The value comes back from the URL, so the control and the link agree.
    expect(from.value).toBe("2026-02-01");
    expect(to.value).toBe("");
  });

  it("writes the page the pagination control moved to", async () => {
    renderTransactions();
    await waitFor(() => {
      expect(screen.getByText(/Página 1 de 5/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => {
      expect(addressParams().get("page")).toBe("2");
    });
    // In a `waitFor` and not a bare expect, because the address updates
    // synchronously on the click while the counter is not rendered again until
    // the new page's rows arrive — the table is replaced by the loading
    // skeleton in between, so the counter is genuinely absent for a moment.
    await waitFor(() => {
      expect(screen.getByText(/Página 2 de 5/)).toBeInTheDocument();
    });
  });

  it("returns to the first page when a filter changes, instead of stranding it", async () => {
    // Page 4 of an unfiltered list, then a filter that leaves one page of
    // results. Carrying `page=4` across would land on a page that does not
    // exist, and the counter would claim "page 4 of 1".
    renderTransactions("/transactions?page=4");
    await waitFor(() => {
      expect(screen.getByText(/Página 4 de 5/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Revisión" }));

    await waitFor(() => {
      expect(addressParams().has("page")).toBe(false);
    });
    // The filtered result fits on one page, so the counter is gone rather than
    // stale. Both halves are the same rule: nothing in the view refers to a
    // page the new filter has no meaning for.
    await waitFor(() => {
      expect(screen.queryByText(/Página/)).not.toBeInTheDocument();
    });
  });
});

/* ================================================================== *
 * Clearing
 * ================================================================== */

describe("TransactionsPage — a cleared filter is absent, not empty", () => {
  it("clearing every filter returns the address to the bare path", async () => {
    // The whole point of the parameter contract: the unfiltered view has ONE
    // address, and it is the one a person would share. `?status=&from=&to=`
    // would be three more spellings of the same view.
    renderTransactions("/transactions?status=fraud&from=2026-01-01&page=2");
    await waitFor(() => {
      expect(addressParams().get("status")).toBe("fraud");
    });

    fireEvent.click(screen.getByRole("button", { name: "Todas" }));
    await waitFor(() => {
      expect(selectedLabel("Todas")).toBe("Todas");
    });
    expect(selectedLabel("Fraude")).toBeNull();
    fireEvent.change(dateInputs()[0], { target: { value: "" } });

    await waitFor(() => {
      expect(address()).toBe("/transactions");
    });
  });

  it("going back to page one removes the page parameter", async () => {
    // `?page=1` is the same view as no parameter at all, and a canonical URL
    // per view means a shared link never carries a redundant parameter.
    renderTransactions("/transactions?page=2");
    await waitFor(() => {
      expect(screen.getByText(/Página 2 de 5/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Anterior" }));

    await waitFor(() => {
      expect(address()).toBe("/transactions");
    });
  });
});

/* ================================================================== *
 * History
 * ================================================================== */

describe("TransactionsPage — the back control restores the previous state", () => {
  it("walks back through the filters the user applied, in order", async () => {
    renderTransactions();
    await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Fraude" }));
    await waitFor(() => {
      expect(selectedLabel("Fraude")).toBe("Fraude");
    });
    fireEvent.click(screen.getByRole("button", { name: "Revisión" }));
    await waitFor(() => {
      expect(selectedLabel("Revisión")).toBe("Revisión");
    });

    // Pop back to the fraud filter.
    fireEvent.click(screen.getByRole("button", { name: "Atrás" }));
    await waitFor(() => {
      expect(addressParams().get("status")).toBe("fraud");
    });
    // The RENDERED selection is the assertion that matters. A page that seeded
    // `useState` from the URL and then read nothing would show the right
    // address bar and the wrong table — the address bar is not the view.
    await waitFor(() => {
      expect(selectedLabel("Fraude")).toBe("Fraude");
    });
    expect(selectedLabel("Revisión")).toBeNull();
    // The LAST request, not the first: the fetch that matters is the one made
    // after the pop, and the first one belongs to the unfiltered view this test
    // started from. The value is the API's, so `fraud` arrives as `blocked`.
    await waitFor(() => {
      expect(lastTxRequest().get("status")).toBe("blocked");
    });

    // And back again to the unfiltered view.
    fireEvent.click(screen.getByRole("button", { name: "Atrás" }));
    await waitFor(() => {
      expect(address()).toBe("/transactions");
    });
    expect(selectedLabel("Todas")).toBe("Todas");
    expect(selectedLabel("Fraude")).toBeNull();
  });

  it("walks back through the pages the user paged through", async () => {
    renderTransactions();
    await waitFor(() => {
      expect(screen.getByText(/Página 1 de 5/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      expect(screen.getByText(/Página 2 de 5/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      expect(screen.getByText(/Página 3 de 5/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Atrás" }));

    await waitFor(() => {
      expect(screen.getByText(/Página 2 de 5/)).toBeInTheDocument();
    });
    expect(addressParams().get("page")).toBe("2");
  });

  it("a reloaded deep link reproduces the same view from the address alone", async () => {
    // The "bookmark it" case: no interaction, no in-memory state, the address
    // is the whole input. Two independent renders of one URL must agree.
    const first = renderTransactions("/transactions?status=review&page=2");
    await waitFor(() => {
      expect(screen.getAllByText("Merchant 0").length).toBeGreaterThanOrEqual(1);
    });
    const firstAddress = address();
    const firstRows = document.querySelectorAll("tbody tr").length;
    first.unmount();

    renderTransactions("/transactions?status=review&page=2");
    await waitFor(() => {
      expect(document.querySelectorAll("tbody tr").length).toBe(firstRows);
    });
    expect(address()).toBe(firstAddress);
    expect(firstRows).toBeGreaterThan(0);
  });
});

/* ================================================================== *
 * A hand-edited URL
 * ================================================================== */

describe("TransactionsPage — a hand-edited query string degrades to the default", () => {
  const cases: [string, string][] = [
    ["an unknown status", "status=banana"],
    ["the transport's word for one of them", "status=flagged"],
    ["the default written out", "status=all"],
    ["a differently cased status", "status=Fraude"],
    ["an empty status", "status="],
    ["a status that is a superset of a valid one", "status=fraudulent"],
  ];

  it.each(cases)("renders the unfiltered list for %s", async (_label, query) => {
    renderTransactions(`/transactions?${query}`);
    await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));

    // The junk is NOT forwarded. This is the falsifiable half: an
    // implementation that passed the raw value through would put it on the
    // wire, and this fixture honours `status`, so the table would come back
    // empty — indistinguishable, on a fraud surface, from a filter that
    // legitimately matched nothing.
    expect(firstTxRequest().has("status")).toBe(false);
    expect(selectedLabel("Todas")).toBe("Todas");
    // An empty table is the failure this rule exists to prevent.
    await waitFor(() => {
      expect(document.querySelectorAll("tbody tr").length).toBeGreaterThan(0);
    });
  });

  it.each(cases)(
    "leaves the rejected value visible in the address for %s",
    async (_label, query) => {
      // Not a silent repair. The address keeps saying what was asked for while
      // the pills say "Todas", and that visible disagreement is the only
      // signal the user gets that their filter did not take.
      renderTransactions(`/transactions?${query}`);
      await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));
      expect(address()).toBe(`/transactions?${query}`);
    },
  );

  it.each([
    ["not a number", "page=abc"],
    ["zero", "page=0"],
    ["negative", "page=-3"],
    ["a fraction", "page=1.5"],
    ["exponent notation", "page=1e3"],
    ["empty", "page="],
  ])("falls back to the first page for a page that is %s", async (_l, query) => {
    renderTransactions(`/transactions?${query}`);
    await waitFor(() => {
      expect(screen.getByText(/Página 1 de 5/)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.querySelectorAll("tbody tr").length).toBeGreaterThan(0);
    });
  });

  it.each([
    ["not a date", "from=yesterday"],
    ["a day the month does not have", "from=2026-02-31"],
    ["a locale format", "from=01%2F01%2F2026"],
    ["a timestamp", "to=2026-01-01T00%3A00%3A00Z"],
  ])("clears a date that is %s", async (_label, query) => {
    renderTransactions(`/transactions?${query}`);
    await waitFor(() => expect(txRequests.length).toBeGreaterThan(0));
    expect(firstTxRequest().has("from")).toBe(false);
    expect(firstTxRequest().has("to")).toBe(false);
    expect(dateInputs().map((input) => input.value)).toEqual(["", ""]);
  });

  it("a page past the end of the result set lands on the last page", async () => {
    // A link shared from a bigger week. Falling through here renders an EMPTY
    // table beside a counter reading "page 99 of 5", and to a person that is
    // the same as a filter that matched nothing — the one reading a fraud
    // analyst must not be left with.
    renderTransactions("/transactions?page=99");

    await waitFor(() => {
      expect(screen.getByText(/Página 5 de 5/)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.querySelectorAll("tbody tr").length).toBeGreaterThan(0);
    });
    // The re-request is visible, and the URL is left alone: the user asked for
    // page 99, and rewriting their address would make the back button lie.
    await waitFor(() => expect(txRequests.length).toBe(2));
    expect(new URLSearchParams(txRequests[1]).get("page")).toBe("5");
    expect(addressParams().get("page")).toBe("99");
  });

  it("an empty result set is left alone rather than clamped", async () => {
    // Nothing matches the filter, so there is no last page to move to, and
    // moving would hide the reason the list is empty.
    renderTransactions("/transactions?status=fraud&page=99");
    await waitFor(() => {
      expect(screen.getByText("No hay transacciones")).toBeInTheDocument();
    });
    expect(addressParams().get("page")).toBe("99");
  });
});

/* ================================================================== *
 * The other list page
 * ================================================================== */

describe("AlertsPage — its filters and pagination live in the URL too", () => {
  it("applies a deep-linked status and reflects it in the selected tab", async () => {
    renderAlerts("/alerts?status=open");
    await waitFor(() => expect(alertRequests.length).toBeGreaterThan(0));
    expect(firstAlertRequest().get("status")).toBe("open");
    await waitFor(() => {
      expect(selectedLabel("Abiertas")).toBe("Abiertas");
    });
    expect(selectedLabel("Todas")).toBeNull();
  });

  it("writes a clicked tab to the URL", async () => {
    renderAlerts();
    await waitFor(() => expect(alertRequests.length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Resueltas" }));

    await waitFor(() => {
      expect(addressParams().get("status")).toBe("resolved");
    });
  });

  it("writes the page to the URL and reads it back on load", async () => {
    renderAlerts();
    await waitFor(() => {
      expect(screen.getByText(/Pág\. 1 de 3/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
    await waitFor(() => {
      expect(addressParams().get("page")).toBe("2");
    });
  });

  it("restores the previous tab with the back control", async () => {
    renderAlerts();
    await waitFor(() => expect(alertRequests.length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Revisadas" }));
    await waitFor(() => {
      expect(selectedLabel("Revisadas")).toBe("Revisadas");
    });
    fireEvent.click(screen.getByRole("button", { name: "Atrás" }));

    await waitFor(() => {
      expect(selectedLabel("Todas")).toBe("Todas");
    });
    expect(address()).toBe("/alerts");
  });

  it("falls back to every alert for a status it does not know", async () => {
    renderAlerts("/alerts?status=archived");
    await waitFor(() => expect(alertRequests.length).toBeGreaterThan(0));
    expect(firstAlertRequest().has("status")).toBe(false);
    await waitFor(() => {
      expect(selectedLabel("Todas")).toBe("Todas");
    });
  });
});

/* ================================================================== *
 * One source of truth
 *
 * The PROOF is the back-control test above: a POP re-renders the page with no
 * click on it, and the pills, the table and the counter all follow. A mirrored
 * `useState` either re-syncs — in which case it is not a second source but a
 * cache of the first — or it does not, and the back test goes red.
 *
 * What is here is the cheap guard that catches the mirror being ADDED, because
 * "invisible from the DOM" is exactly the property that made the duplication
 * worth removing in the first place.
 * ================================================================== */

const pageSource = (name: string) =>
  readFileSync(join(process.cwd(), "src", "pages", `${name}.tsx`), "utf-8")
    // Block comments stripped, so a page's own notes about the rule do not
    // satisfy or trip it.
    .replace(/\/\*[\s\S]*?\*\//g, "");

describe("TransactionsPage — the filter state is not kept twice", () => {
  const code = pageSource("TransactionsPage");

  it("holds no component state at all, so the URL cannot disagree with it", () => {
    // This page has nothing else to hold, so the whole hook is available as the
    // assertion. Falsifiable: a mirror of the filter, or a `useState` seeded
    // once from the query string, puts the hook back and fails this. Reading
    // the URL into a plain local is fine, which is why the check names the hook
    // rather than the word "state".
    expect(code, "must not call useState").not.toMatch(/\buseState\b/);
  });

  it("reads and writes the address through the router, not through history", () => {
    // Asserts the dependency, so the page cannot quietly stop consulting the
    // address bar while every behavioural test still passes.
    expect(code).toMatch(/useSearchParams\(\)/);
  });
});

describe("AlertsPage — the filter state is not kept twice", () => {
  const code = pageSource("AlertsPage");

  it("no longer owns a page counter or a status filter", () => {
    // Named rather than pattern-matched for "no state at all", because this
    // page legitimately keeps some: the confirm dialog's draft reason is typed
    // character by character and belongs in the same place a search box would
    // be kept, which is React state and not the URL. Forbidding the hook here
    // would push someone to move a half-typed reason into a shareable link.
    expect(code).not.toMatch(/\bsetPage\b/);
    expect(code).not.toMatch(/\bsetStatusFilter\b/);
  });

  it("still keeps the confirm dialog's own state, deliberately out of the URL", () => {
    // The counterpart to the assertion above, so "we moved the filter to the
    // URL" does not quietly become "we moved everything to the URL".
    expect(code).toMatch(
      /const \[actionAlertId, setActionAlertId\] = useState/,
    );
    expect(code).toMatch(/const \[actionReason, setActionReason\] = useState/);
  });

  it("reads and writes the address through the router", () => {
    expect(code).toMatch(/useSearchParams\(\)/);
  });
});
