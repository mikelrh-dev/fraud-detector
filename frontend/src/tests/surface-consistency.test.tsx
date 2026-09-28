import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import TransactionTable from "../components/TransactionTable";
import { Badge } from "../components/Badge";
import { ScoreResultCard } from "../pages/ScoreResultCard";
import TransactionDetail from "../pages/TransactionDetail";
import TransactionsPage from "../pages/TransactionsPage";
import { server } from "./mocks/server";
import type { ReactNode } from "react";
import type { Transaction } from "../api/transactions";
import type { ScoreResponse } from "../api/transactions";

/**
 * Four status pills were hand-rolled instead of rendering the `Badge`
 * primitive, and this file is the layer that holds them there.
 *
 * WHY RUNTIME RENDERING AND NOT A SOURCE SCAN
 * -------------------------------------------
 * A source scan can prove a string is absent from a file. It cannot prove the
 * element still wears a pill, that the pill is the right tone, or that two
 * pills which mean the same thing stopped disagreeing — and disagreement
 * between two renderings is the whole defect. So these tests render.
 *
 * EVERY EXPECTATION IS A LITERAL
 * -----------------------------
 * No expectation here imports `TONE_CLASSES`, `classificationPillClass` or any
 * other constant. Importing the thing under test makes the assertion a
 * tautology: change the constant and both sides of the comparison move, so the
 * test stays green while the design changes under it. The tokens below are
 * spelled out, which is what makes them able to go red.
 *
 * That is also why writing these tests costs nothing in the bundle: every
 * literal here is a class the product genuinely uses, so it is emitted from
 * `src/` regardless. `@source not "./tests"` in `index.css` is what guarantees
 * that, and it is measured rather than assumed — see the note there.
 */

const T = "C:/Users/mikel/Documents/fraud-detector/fraud-detector/frontend/src";

/** The classification column in the transactions table. */
function renderTable(classification: string) {
  const tx = {
    id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    amount: 1234.5,
    currency: "USD",
    merchant_name: "Merchant 0",
    risk_score: 42,
    // `status` is deliberately an UNRECOGNISED value, so the STATUS pill
    // renders the raw string "escalated" and no status label can collide with
    // a classification label. An `approved` status would put a second
    // "Legítimo" in the same table and make `getByText` ambiguous, and
    // disambiguating by cell index would couple these tests to column order.
    status: "escalated",
    classification,
    created_at: "2026-09-20T10:00:00Z",
  } as unknown as Transaction;

  return render(
    <MemoryRouter initialEntries={["/transactions"]}>
      <TransactionTable
        transactions={[tx]}
        total={1}
        page={1}
        pageSize={10}
        onSort={vi.fn()}
        onPageChange={vi.fn()}
        onFilterChange={vi.fn()}
        onTransactionClick={vi.fn()}
      />
    </MemoryRouter>,
  );
}

/** The fired-rules chips on the scoring card. */
function renderChips(fired_rules: string[]) {
  const result: ScoreResponse = {
    transaction_id: "test-uuid",
    threshold: 40,
    created_at: new Date().toISOString(),
    classification: "fraud",
    rule_score: 90,
    ml_score: 88.0,
    ensemble_score: 91.0,
    fired_rules,
  };
  return render(<ScoreResultCard result={result} />);
}

/** Every chromatic raw palette value Tailwind could emit, as a live regex. */
const RAW_CHROMATIC =
  /(?:^|[\s"'`])(?:[a-z-]+:)*(?:bg|text|border|border-[trbl]|ring|outline|fill|stroke|from|via|to)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}(?:\/\d+)?(?=$|[\s"'`])/;

describe("status pills render the Badge primitive, not a hand-rolled one", () => {
  it("the transactions table's classification pill uses the Badge clean tone", () => {
    renderTable("legitimate");
    const pill = screen.getByText("Legítimo", { selector: "span" });

    // The Badge shape: full-round, a border, and the `/10` fill + `/30` border
    // + full-strength text pattern DESIGN.md specifies for badges.
    expect(pill.className).toContain("rounded-full");
    expect(pill.className).toContain("border-risk-clean/30");
    expect(pill.className).toContain("bg-risk-clean/10");
    expect(pill.className).toContain("text-risk-clean");
  });

  it("THE TWO-GREENS HALF: that pill is the SAME green as a Badge, not a second one", () => {
    // This is the assertion the brief's "two-greens bug" turns out to be about.
    // The two sites rendered "legitimate" in visibly different greens: the
    // table and the detail header painted an OPAQUE near-black forest
    // (`bg-fraud-legitimate-bg` = #052e16) while every <Badge tone="clean">
    // painted a 10%-alpha green. Same state, two pills, neither derived from
    // the other.
    //
    // The text greens were already byte-identical (#22c55e), so what differed
    // was the FILL: one from the `fraud-*-bg` opaque scale, one from
    // `risk-clean/10`. Asserting BOTH halves pins the pairing the design
    // system intends rather than just "the greens agree".
    renderTable("legitimate");
    const pill = screen.getByText("Legítimo", { selector: "span" });

    // The intended pairing, spelled out.
    expect(pill.className).toContain("bg-risk-clean/10");
    expect(pill.className).toContain("text-risk-clean");
    // And the retired opaque scale, which must not come back.
    expect(pill.className).not.toContain("fraud-legitimate");
    expect(pill.className).not.toContain("bg-fraud-legitimate-bg");
  });

  it("that pill and a <Badge tone=\"clean\"> agree, class for class", () => {
    // The strongest form of the same claim: render both and compare the
    // colour-carrying half of each class list. Falsifiable in the way that
    // matters — put the table back on the `fraud-*` scale and the two lists
    // stop matching, whatever the labels say.
    const { container } = render(
      <Badge tone="clean" size="sm">
        REFERENCE
      </Badge>,
    );
    const reference = (container.firstElementChild as HTMLElement).className;

    renderTable("legitimate");
    const pill = screen.getByText("Legítimo", { selector: "span" });

    // Only the colour half: padding and size are legitimately different
    // between a table cell and a standalone badge, and comparing them would
    // make this test fail for a reason that is not the defect.
    const colourOf = (cls: string) =>
      cls
        .split(/\s+/)
        .filter((c) => /^(bg|text|border)-(risk|fraud|status)-/.test(c))
        .sort()
        .join(" ");

    expect(colourOf(pill.className)).toBe(colourOf(reference));
    expect(colourOf(pill.className)).not.toBe("");
  });

  it.each([
    ["legitimate", "Legítimo", "risk-clean"],
    ["review", "Revisión", "risk-warn"],
    ["fraud", "Fraude", "risk-critical"],
  ])(
    "the classification pill for %s is the %s tone, not a raw colour",
    (classification, label, token) => {
      renderTable(classification);
      const pill = screen.getByText(label, { selector: "span" });
      expect(pill.className).toContain(`text-${token}`);
      expect(pill.className).toContain(`bg-${token}/10`);
      expect(pill.className).not.toMatch(RAW_CHROMATIC);
    },
  );

  it("an unknown classification stays neutral instead of guessing a risk colour", () => {
    // `classificationTone` returns `neutral` for anything unrecognised, and
    // `Badge`'s neutral is a slate pill. A hand-rolled ternary with no
    // default is exactly how an unknown state ends up painted green.
    //
    // The first version of this test only checked `rounded-full` and "no raw
    // chromatic", and a mutation proved that is not the same claim: flipping
    // the fallback from `neutral` to `clean` left it green, because `clean` is
    // a legitimate token and the "no raw chromatic" assertion cannot see the
    // difference. So the neutral PAIRING is asserted by name.
    renderTable("pending");
    const pill = screen.getByText("Pendiente", { selector: "span" });
    expect(pill.className).toContain("rounded-full");
    expect(pill.className).toContain("bg-slate-800");
    expect(pill.className).toContain("border-slate-700");
    expect(pill.className).toContain("text-slate-400");
    // And explicitly not any of the three risk tones, nor a hue.
    expect(pill.className).not.toMatch(/risk-(clean|warn|critical)/);
    expect(pill.className).not.toMatch(/fraud-(legitimate|review|fraud)/);
    expect(pill.className).not.toMatch(RAW_CHROMATIC);
  });

  it("the fired-rules chips use the Badge critical tone", () => {
    renderChips(["high_amount", "high_velocity"]);
    for (const rule of ["high_amount", "high_velocity"]) {
      const chip = screen.getByText(rule);
      expect(chip.className).toContain("rounded-full");
      expect(chip.className).toContain("bg-risk-critical/10");
      expect(chip.className).toContain("border-risk-critical/30");
      expect(chip.className).toContain("text-risk-critical");
      // The three raw reds this chip used to be built from.
      expect(chip.className).not.toContain("red-900");
      expect(chip.className).not.toContain("red-400");
      expect(chip.className).not.toContain("red-800");
    }
  });
});

describe("the transaction status pill on the list", () => {
  function renderPage() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(<TransactionsPage />, {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/transactions"]}>{children}</MemoryRouter>
        </QueryClientProvider>
      ),
    });
  }

  it("renders approved as the clean tone, on the Badge shape", async () => {
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({
          items: [
            {
              id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
              amount: 100,
              currency: "USD",
              merchant_name: "Merchant 0",
              risk_score: 10,
              status: "approved",
              // `review`, not `legitimate`: the STATUS column prints
              // "Legítimo" for `approved`, and a `legitimate` classification
              // would print a second "Legítimo" in the same row, making
              // `getByText` ambiguous about which pill is under test.
              classification: "review",
              created_at: "2026-09-20T10:00:00Z",
            },
          ],
          total: 1,
          page: 1,
          page_size: 10,
        }),
      ),
    );
    renderPage();

    const pill = await screen.findByText("Legítimo", { selector: "span" });
    expect(pill.className).toContain("rounded-full");
    expect(pill.className).toContain("bg-risk-clean/10");
    expect(pill.className).toContain("text-risk-clean");
  });

  it("an unrecognised status falls through to neutral, not to a risk tone", async () => {
    // The old four-armed ternary had a `bg-slate-800 text-slate-400` default.
    // It is kept — as `Badge`'s `neutral`, which is the same slate pairing —
    // because "a status nobody recognises" must not render as a verdict.
    server.use(
      http.get("*/api/v1/transactions", () =>
        HttpResponse.json({
          items: [
            {
              id: "b1b2c3d4-e5f6-7890-abcd-ef1234567890",
              amount: 100,
              currency: "USD",
              merchant_name: "Merchant 1",
              risk_score: 10,
              status: "escalated",
              classification: "legitimate",
              created_at: "2026-09-20T10:00:00Z",
            },
          ],
          total: 1,
          page: 1,
          page_size: 10,
        }),
      ),
    );
    renderPage();

    const pill = await screen.findByText("escalated", { selector: "span" });
    expect(pill.className).not.toMatch(RAW_CHROMATIC);
    expect(pill.className).toContain("rounded-full");
  });
});

describe("the classification pill on the transaction detail header", () => {
  function renderDetail() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(<TransactionDetail />, {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/transactions/test-uuid"]}>
            <Routes>
              <Route path="/transactions/:id" element={children} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      ),
    });
  }

  it("renders the header pill on the Badge shape, with the table's green", async () => {
    // The detail header pill and the table pill are the same state rendered in
    // two files, which is why they drifted in the first place. Pinned in both
    // directions: this one, and `the two-greens half` above.
    renderDetail();
    const header = await waitFor(() => {
      const el = document.querySelector("header");
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });

    // The pill is the `rounded-full` span. It is NOT the outermost span in the
    // header: the migration left an `ml-auto` wrapper around it, because
    // `Badge` takes no `className` and the header's right-alignment has to
    // live somewhere. Selecting by shape rather than by text keeps the test
    // honest about WHICH element is the pill.
    const pill = header.querySelector("span.rounded-full");
    expect(pill).toBeTruthy();
    expect(pill!.textContent).toMatch(/Leg[ií]timo|Revisi[oó]n|Fraude/);
    expect(pill!.className).toContain("bg-risk-");
    expect(pill!.className).not.toMatch(RAW_CHROMATIC);
    // The stray bare `border` this pill used to carry ALONGSIDE the tone's own
    // border token — a duplicate that made the class list read as though the
    // border were unstyled. `Badge` puts `border` in the class list, so this
    // asserts exactly one and not two.
    expect(
      pill!.className.split(/\s+/).filter((c) => c === "border").length,
    ).toBe(1);
  });
});

describe("the four product sources carry no raw chromatic value at a class position", () => {
  // The lint rule is the real enforcement for this, and it is AST-based, so it
  // cannot see these files at all if they are in a test. This is the belt to
  // that rule's braces: it reads the same four sources as text and fails on
  // any chromatic utility, which is a second, independent witness.
  it.each([
    ["src/components/TransactionTable.tsx", "TransactionTable.tsx"],
    ["src/components/Badge.tsx", "Badge.tsx"],
    ["src/pages/TransactionsPage.tsx", "TransactionsPage.tsx"],
    ["src/pages/TransactionDetail.tsx", "TransactionDetail.tsx"],
    ["src/pages/ScoreResultCard.tsx", "ScoreResultCard.tsx"],
    ["src/lib/classification.ts", "classification.ts"],
  ])("%s", (rel) => {
    const code = readFileSync(join(T, rel.replace("src/", "")), "utf8");
    // Comments are stripped first: Tailwind's scanner reads them and so does a
    // naive regex, but a class named in prose is not a class a component uses,
    // and several of these files DISCUSS the raw values they used to carry.
    const stripped = code
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/(^|[^:])\/\/.*$/gm, "$1 ");
    expect(stripped, `${rel} has a raw chromatic utility in a class position`).not.toMatch(
      RAW_CHROMATIC,
    );
  });
});
