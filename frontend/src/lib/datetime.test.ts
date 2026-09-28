import { describe, it, expect } from "vitest";
import { formatTimestamp } from "./datetime";

/**
 * Every expectation below is a LITERAL, never the output of the formatter
 * compared against itself. A test that rebuilt the expected string from the
 * same `Intl` options would move both sides when the format changed, and the
 * change would ship silently — which is the entire defect this module exists
 * to close.
 *
 * The Dates are built from LOCAL components (`new Date(2026, 8, 20, 14, 30)`),
 * not from an ISO "Z" string. `formatTimestamp` renders in the viewer's zone,
 * so a local-component Date has the same wall clock in every timezone: these
 * literals hold on this machine and in CI. A test that formatted
 * `"2026-09-20T14:30:00Z"` and pinned the digits would depend on the runner's
 * TZ and would be a test that only appears to pin anything.
 */
describe("formatTimestamp", () => {
  it("renders DD/MM/AAAA, HH:MM in a 24-hour clock", () => {
    expect(formatTimestamp(new Date(2026, 8, 20, 14, 30))).toBe("20/09/2026, 14:30");
  });

  it("uses 00 for midnight, not 12 — the meridiem regression guard", () => {
    // es-AR resolves `{hour: "2-digit"}` to h12, which would render this as
    // "12:07 a. m." and put a 12-hour clock in a data table. Forcing h23 in
    // datetime.ts is what makes it 00:07; if that option is ever dropped, this
    // assertion is what notices.
    expect(formatTimestamp(new Date(2026, 0, 5, 0, 7))).toBe("05/01/2026, 00:07");
  });

  it("keeps 23:59 rather than rolling into the next day", () => {
    expect(formatTimestamp(new Date(2026, 11, 31, 23, 59))).toBe("31/12/2026, 23:59");
  });

  it("zero-pads a single-digit day and month", () => {
    expect(formatTimestamp(new Date(2026, 8, 1, 9, 5))).toBe("01/09/2026, 09:05");
  });

  it("carries a four-digit year", () => {
    expect(formatTimestamp(new Date(2049, 5, 30, 18, 45))).toBe("30/06/2049, 18:45");
  });

  it("parses the ISO-8601 strings the API sends to the same instant", () => {
    // The backend sends `2026-09-20T14:30:00Z`; new Date() applies the offset,
    // so the string path and the Date path are the same instant and must agree.
    // Exact, and timezone-independent, which an ISO literal would not be.
    const local = new Date(2026, 8, 20, 14, 30);
    expect(formatTimestamp(local.toISOString())).toBe(formatTimestamp(local));
    expect(formatTimestamp(local.toISOString())).toBe("20/09/2026, 14:30");
  });

  it("returns an em dash for unparseable input instead of 'Invalid Date'", () => {
    expect(formatTimestamp("not-a-date")).toBe("—");
    expect(formatTimestamp("")).toBe("—");
    expect(formatTimestamp(new Date("nope"))).toBe("—");
  });
});
