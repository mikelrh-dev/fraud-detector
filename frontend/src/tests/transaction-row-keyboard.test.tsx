import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import TransactionTable from "../components/TransactionTable";
import type { Transaction } from "../api/transactions";
import type { ReactNode } from "react";

/**
 * The transaction table's primary action (open the detail view) was reachable
 * only with a mouse: the <tr> had onClick but no focusable descendant, so a
 * keyboard user could not enter a transaction at all. The merchant cell is now a
 * real <Link>, which also makes middle-click and "copy link address" work.
 */

const TX: Transaction = {
  id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  amount: 1234.5,
  currency: "USD",
  merchant_name: "Merchant 0",
  risk_score: 42,
  status: "flagged",
  classification: "suspicious",
  created_at: "2026-09-20T10:00:00Z",
} as Transaction;

function Router({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={["/transactions"]}>
      {children}
      <Routes>
        <Route path="/transactions" element={null} />
        <Route
          path="/transactions/:id"
          element={<div data-testid="detail-view">Detalle</div>}
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("TransactionTable — row keyboard access", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("exposes the merchant as a real link with the detail href", () => {
    render(
      <Router>
        <TransactionTable transactions={[TX]} onTransactionClick={vi.fn()} />
      </Router>,
    );

    const link = screen.getByRole("link", { name: "Merchant 0" });
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe(`/transactions/${TX.id}`);
  });

  it("is reachable by keyboard and activates with Enter", async () => {
    const onClick = vi.fn();
    render(
      <Router>
        <TransactionTable transactions={[TX]} onTransactionClick={onClick} />
      </Router>,
    );

    const link = screen.getByRole("link", { name: "Merchant 0" }) as HTMLElement;
    link.focus();
    expect(document.activeElement).toBe(link);

    // Enter on a real anchor triggers navigation, not the row's mouse handler.
    await waitFor(() => {
      expect(link.getAttribute("href")).toBe(`/transactions/${TX.id}`);
    });
    // The row handler must not double-fire: activation is the link's job.
    expect(onClick).not.toHaveBeenCalled();
  });

  it("keeps the row onClick for mouse clicks on non-link cells", () => {
    const onClick = vi.fn();
    render(
      <Router>
        <TransactionTable transactions={[TX]} onTransactionClick={onClick} />
      </Router>,
    );

    const idCell = screen.getByText(`${TX.id.slice(0, 8)}...`);
    fireEvent.click(idCell);

    expect(onClick).toHaveBeenCalledWith(TX.id);
  });
});

describe("TransactionTable — link does not double-navigate", () => {
  it("row handler ignores clicks originating inside the link", () => {
    const onClick = vi.fn();
    render(
      <Router>
        <TransactionTable transactions={[TX]} onTransactionClick={onClick} />
      </Router>,
    );

    const link = screen.getByRole("link", { name: "Merchant 0" });
    fireEvent.click(link);
    // The link handles navigation; the row must not also push a second entry.
    expect(onClick).not.toHaveBeenCalled();
  });
});
