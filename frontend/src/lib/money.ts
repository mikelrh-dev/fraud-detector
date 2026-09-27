/**
 * Single money formatter.
 *
 * WHY THIS FILE EXISTS
 * The same amount was rendered three different ways:
 *
 *   TransactionsPage (mobile card)  `$${tx.amount.toFixed(2)}`  -> $1234.56
 *   TransactionTable / Detail      `$${tx.amount.toLocaleString("es-AR")}`
 *                                                                -> $1.235
 *
 * The second form drops the cents: a $1,234.56 charge displayed as $1.235. On
 * a fraud-investigation tool, hiding cents from the amount under review is a
 * data-fidelity defect, not a cosmetic one — and the two pages disagreed about
 * the same record, so the mobile card read "$1100.00" while its own desktop
 * table read "$1.100".
 *
 * The symbol was also hardcoded even though `currency` travels in the payload
 * and is rendered in its own column.
 */

const formatterCache = new Map<string, Intl.NumberFormat>();

function formatterFor(currency: string): Intl.NumberFormat {
  let fmt = formatterCache.get(currency);
  if (!fmt) {
    // Unknown/malformed codes fall back to a plain 2-decimal number rather
    // than throwing inside a render.
    try {
      fmt = new Intl.NumberFormat("es-AR", {
        style: "currency",
        currency,
        // narrowSymbol keeps the familiar "$1.100,00". The default in es-AR
        // renders "US$ 1.100,00", which is unambiguous but changes how every
        // amount in the product looks — a visual regression traded for
        // precision the backend already guarantees.
        currencyDisplay: "narrowSymbol",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    } catch {
      fmt = new Intl.NumberFormat("es-AR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
    formatterCache.set(currency, fmt);
  }
  return fmt;
}

/**
 * Format an amount for display, preserving cents.
 *
 * @param amount  Transaction amount.
 * @param currency ISO 4217 code; defaults to USD (the historical hardcoded `$`).
 */
export function formatMoney(amount: number, currency = "USD"): string {
  if (!Number.isFinite(amount)) return "—";
  return formatterFor(currency).format(amount);
}
