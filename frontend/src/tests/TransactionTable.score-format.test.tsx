import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TransactionTable from "../components/TransactionTable";
import type { Transaction } from "../api/transactions";

/**
 * The shared dashboard table rendered `risk_score` as a bare JS number.
 *
 * The backend stores the ensemble score at full float precision, so a row that
 * classified as FRAUDE at 76.46 printed as `76.45876543209877` in the Score
 * column — a number that is both unreadable and, worse, visibly different from
 * the `76.5` the same record shows on `/transactions` (which already routed it
 * through `formatScore`). Two surfaces, one record, two numbers: an analyst
 * comparing the dashboard against the list could not tell whether they were
 * looking at the same score.
 *
 * These assertions name the LITERAL expected text rather than importing
 * `formatScore`, for the reason `surface-consistency.test.tsx` states: a test
 * that imports the formatter under test moves both sides when the formatter is
 * edited, so it stays green while the defect returns.
 */
function renderTable(risk_score: number | null) {
  const tx = {
    id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    amount: 1234.5,
    currency: "USD",
    merchant_name: "Merchant 0",
    risk_score,
    status: "blocked",
    classification: "fraud",
    created_at: "2026-09-20T10:00:00Z",
  } as unknown as Transaction;

  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
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

describe("TransactionTable — the Score column", () => {
  it("renders one decimal, not the raw stored float", () => {
    // The value the backend actually produces: an ensemble blend of three
    // layers, so it carries far more precision than a score has meaning at.
    const { container } = renderTable(76.45876543209877);

    expect(screen.getByText("76.5")).toBeInTheDocument();
    // The falsifiable half: the raw float must not be anywhere in the row.
    // Deleting the `formatScore` call puts this string back and it goes red.
    expect(container.textContent).not.toContain("76.45876543209877");
  });

  it("rounds to one decimal rather than truncating", () => {
    // `toFixed` rounds; a `Math.floor`-style truncation would read 76.4 here.
    renderTable(0.96);
    expect(screen.getByText("1.0")).toBeInTheDocument();
  });

  it("shows the em-dash placeholder for an unscored row, not a zero", () => {
    // A null score means "the model has not scored this", which is not the
    // same claim as "this transaction is risk 0".
    renderTable(null);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("agrees with the transactions list, which already formatted the score", () => {
    // The reason this is a defect and not a preference: the SAME record renders
    // two different numbers on two screens. This pins the shared cell to the
    // one-decimal form `/transactions` uses.
    renderTable(15);
    expect(screen.getByText("15.0")).toBeInTheDocument();
  });
});
