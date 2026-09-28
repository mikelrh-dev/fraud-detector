/**
 * Single timestamp formatter.
 *
 * WHY A MODULE: V-04 was three renderers for one amount, which drifted, and
 * the fix was a single `formatMoney` in `money.ts`. Timestamps were the same
 * class of problem and worse — the same record rendered three different ways
 * across the tree:
 *
 *   TransactionsPage / TransactionTable  `20/09/2026`          (date only)
 *   AlertsPage                          `20/09/2026, 02:30 p. m.`
 *   TransactionDetail                   `20/9/2026, 02:30:00`
 *
 * A fraud-investigation tool cannot have the list, the alert queue and the
 * detail page disagreeing about when a charge happened. Every call site now
 * goes through `formatTimestamp`.
 *
 * THE FORMAT — `DD/MM/AAAA, HH:MM`, ONE format, at every call site.
 *
 * Date-only is deliberately NOT offered as a second helper, and that is a
 * decision rather than an omission. `money.ts` already ruled on the identical
 * question: hiding the cents from an amount under review was "a data-fidelity
 * defect, not a cosmetic one". Dropping the hour from a fraud timestamp is the
 * same defect — on a list of charges, two transactions on the same day become
 * indistinguishable, and an alert triage pass cannot tell a 03:00 burst from a
 * 15:00 one. So the three date-only call sites gained the time they were
 * dropping.
 *
 * WHY `hourCycle: "h23"` AND NOT THE LOCALE DEFAULT. Measured, not assumed:
 * asking es-AR for `{hour: "2-digit", minute: "2-digit"}` resolves to `h12`,
 * so the alerts page was rendering `20/09/2026, 02:30 p. m.` — a 12-hour
 * clock, a dotted meridiem and U+00A0 before the "m.", inside a data table.
 * An analyst reading 02:30 p. m. cannot tell at a glance whether that is an
 * overnight event, and the non-breaking space is invisible in a diff. Forcing
 * `h23` is what makes this a format rather than whatever the runtime happens to
 * prefer. `hour12: false` was rejected for the same reason: its mapping to
 * h23-vs-h24 has shifted between ICU versions, and the tests pin the digits.
 *
 * No seconds. A seconds column in an incident review is noise, and the backend
 * timestamp is not the thing under dispute.
 *
 * LOCALE: `es-AR`, unchanged and never inferred. Every one of the seven call
 * sites already passed `"es-AR"`, `formatMoney` already uses it, and the copy is
 * Argentine Spanish ("Podés", "Nueva Transacción"). Switching it would change
 * `1.100,00` to `1,100.00` in every amount on screen — a locale change is a
 * product decision, not a refactor's to make quietly.
 *
 * HOURZONES: the formatter uses the viewer's local zone, as the hand-rolled
 * calls did. The backend sends ISO-8601 with an offset, so the absolute instant
 * is preserved; a viewer in another zone sees that zone's wall clock. The
 * tests build their Dates from LOCAL components for exactly this reason — a
 * test that formatted an ISO "Z" string and pinned the digits would pass on
 * this machine and fail in any other timezone, which is a test that only
 * appears to pin anything.
 *
 * Unparseable input returns an em dash rather than the string "Invalid Date",
 * matching `formatMoney` and the `—` this codebase already uses for absent
 * values.
 */

const TIMESTAMP_FORMAT = new Intl.DateTimeFormat("es-AR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** `DD/MM/AAAA, HH:MM` in the viewer's local zone. */
export function formatTimestamp(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "—";
  return TIMESTAMP_FORMAT.format(date);
}
