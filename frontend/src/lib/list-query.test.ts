import { describe, it, expect, vi } from "vitest";
import {
  DEFAULT_PAGE,
  LIST_PARAMS,
  clampPage,
  fetchClampedPage,
  parseChoice,
  parseIsoDate,
  parsePage,
  writeListParams,
} from "./list-query";

const STATUSES = ["legitimate", "review", "fraud"] as const;

describe("parseChoice — the URL value must be one of the enumerated ones", () => {
  it("returns the value when it is in the set", () => {
    for (const value of STATUSES) {
      expect(parseChoice(value, STATUSES)).toBe(value);
    }
  });

  it.each([
    ["absent", null],
    ["empty", ""],
    ["unknown", "banana"],
    ["the internal default name, which is not a wire value", "all"],
    ["the transport's own name for the same filter", "flagged"],
    ["a different case", "Legitimate"],
    ["leading whitespace", " fraud"],
    ["a prefix of a valid value", "fraudulent"],
  ])("returns null for a value that is %s", (_label, raw) => {
    // `all` and `flagged` are the two near-misses worth pinning by name: `all`
    // is this module's own default, and `flagged` is the API's word for what
    // the UI calls `review`. If either ever leaked in as valid, a shared link
    // would quietly mean something different from what the UI shows.
    expect(parseChoice(raw as string | null, STATUSES)).toBeNull();
  });

  it("does not coerce: a Set membership test cannot be satisfied by a prefix", () => {
    // Guards the implementation, not the outcome: `allowed.includes(raw as T)`
    // and `allowed.some(a => raw.startsWith(a))` agree on every case above,
    // and this is the shape that would let them drift apart later.
    expect(parseChoice("legitimate2", STATUSES)).toBeNull();
  });
});

describe("parsePage — a positive integer, or the default", () => {
  it.each(["1", "2", "3", "12", "007"])("accepts the plain digits of %s", (raw) => {
    expect(parsePage(raw)).toBe(Number(raw));
  });

  it.each([
    ["absent", null],
    ["empty", ""],
    ["words", "abc"],
    ["zero", "0"],
    ["negative", "-2"],
    ["a fraction", "1.5"],
    ["exponent notation", "1e3"],
    ["a sign prefix", "+5"],
    ["padded with whitespace", " 5 "],
    ["digits followed by a letter", "3abc"],
    ["NaN", "NaN"],
    ["Infinity", "Infinity"],
  ])("falls back to the default when the value is %s", (_label, raw) => {
    // "a plain run of digits" is the whole rule, so every rejection below is
    // the same rule: nothing that is not literally `1` or `2` or `007` counts.
    // `1e3` is here because `Number("1e3")` is the perfectly good integer
    // 1000, and a shareable link should never contain exponent notation.
    expect(parsePage(raw as string | null)).toBe(DEFAULT_PAGE);
  });
});

describe("parseIsoDate — the value format a date input produces", () => {
  it.each(["2026-01-01", "2026-12-31", "2024-02-29", "0001-01-01"])(
    "accepts %s",
    (raw) => {
      expect(parseIsoDate(raw)).toBe(raw);
    },
  );

  it.each([
    ["absent", null],
    ["empty", ""],
    ["a locale date", "01/01/2026"],
    ["a timestamp", "2026-01-01T00:00:00Z"],
    ["a slash-separated ISO", "2026/01/01"],
    ["day out of range for the month", "2026-02-31"],
    ["month out of range", "2026-13-01"],
    ["day zero", "2026-01-00"],
    ["month zero", "2026-00-01"],
    ["non-leap February 29th", "2025-02-29"],
    ["words", "yesterday"],
  ])("returns null when the value is %s", (_label, raw) => {
    // The shape check alone is not enough: `2026-02-31` is a perfectly
    // well-formed run of digits that names a day the calendar does not have,
    // and `new Date("2026-02-31")` silently rolls it to March 3rd. These cases
    // are what the round-trip is for.
    expect(parseIsoDate(raw as string | null)).toBeNull();
  });

  it("is not shifted by the runner's timezone", () => {
    // A `new Date("2026-01-01")` parse is UTC midnight, which in any negative
    // UTC offset is the previous day locally. Anything that formats the result
    // back out would report the 31st of December.
    expect(parseIsoDate("2026-01-01")).toBe("2026-01-01");
  });
});

describe("clampPage", () => {
  it("leaves an in-range page alone", () => {
    expect(clampPage(3, 5)).toBe(3);
  });

  it("pulls an out-of-range page back to the last one", () => {
    expect(clampPage(99, 5)).toBe(5);
  });

  it("leaves the page alone when there is nothing to clamp to", () => {
    // No results at all is not a page-range problem, and moving the page would
    // hide the reason the list is empty.
    expect(clampPage(7, 0)).toBe(7);
  });
});

describe("writeListParams — a cleared filter is ABSENT, never empty", () => {
  it("writes a value", () => {
    const next = writeListParams(new URLSearchParams(), { status: "fraud" });
    expect(next.get("status")).toBe("fraud");
  });

  it("deletes the key when the value is null", () => {
    const next = writeListParams(new URLSearchParams("status=fraud"), {
      status: null,
    });
    expect(next.has("status")).toBe(false);
    // And not as an empty pair either, which is the noise the default avoids.
    expect(next.toString()).toBe("");
  });

  it("deletes the key when the value is an empty string", () => {
    const next = writeListParams(new URLSearchParams("from=2026-01-01"), {
      from: "",
    });
    expect(next.has("from")).toBe(false);
  });

  it("leaves the parameters it was not asked about alone", () => {
    const next = writeListParams(new URLSearchParams("status=fraud&page=2"), {
      page: null,
    });
    expect(next.get("status")).toBe("fraud");
  });

  it("does not mutate the params it was given", () => {
    const current = new URLSearchParams("status=fraud");
    writeListParams(current, { status: null });
    expect(current.get("status")).toBe("fraud");
  });

  it("resets the page when asked, because a new filter changes the result set", () => {
    const next = writeListParams(
      new URLSearchParams("status=fraud&page=4"),
      { status: "review" },
      { resetPage: true },
    );
    expect(next.get("status")).toBe("review");
    expect(next.has(LIST_PARAMS.page)).toBe(false);
  });

  it("leaves the page alone when not asked", () => {
    const next = writeListParams(
      new URLSearchParams("status=fraud&page=4"),
      { status: "review" },
    );
    expect(next.get(LIST_PARAMS.page)).toBe("4");
  });
});

describe("fetchClampedPage", () => {
  interface PageResult {
    total: number;
    page_size: number;
    page: number;
  }

  const pageOf = (n: number, total: number): PageResult => ({
    total,
    page_size: 10,
    page: n,
  });

  // Typed at the mock rather than inferred from `mockResolvedValue`, so the
  // generic on `fetchClampedPage` has a shape to bind to and a response that
  // forgets `page` is a compile error instead of an `any`.
  const fetcher = () => vi.fn<(p: number) => Promise<PageResult>>();

  it("makes one request when the page is in range", async () => {
    const fetchPage = fetcher();
    fetchPage.mockResolvedValue(pageOf(3, 50));
    const result = await fetchClampedPage(3, fetchPage);
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(fetchPage).toHaveBeenCalledWith(3);
    expect(result.page).toBe(3);
  });

  it("re-requests the last page when the requested one does not exist", async () => {
    // The stale-link case: a URL shared from a bigger result set. Without the
    // second request the view would render an empty list and a page counter
    // reading "page 99 of 5".
    const fetchPage = fetcher();
    fetchPage
      .mockResolvedValueOnce(pageOf(99, 50))
      .mockResolvedValueOnce(pageOf(5, 50));
    const result = await fetchClampedPage(99, fetchPage);
    expect(fetchPage.mock.calls).toEqual([[99], [5]]);
    expect(result.page).toBe(5);
  });

  it("does not re-request when the result set is empty", async () => {
    // There is no page 1 of nothing to show, and clamping here would make the
    // second request return the same empty page anyway.
    const fetchPage = fetcher();
    fetchPage.mockResolvedValue(pageOf(99, 0));
    const result = await fetchClampedPage(99, fetchPage);
    expect(fetchPage).toHaveBeenCalledTimes(1);
    expect(result.total).toBe(0);
  });

  it("does not re-request when the page size is nonsense", async () => {
    // A zero page size makes the page count Infinity, and `page > Infinity` is
    // false, so this holds without a special case. Pinned so a refactor that
    // compares the other way round cannot start looping.
    const fetchPage = fetcher();
    fetchPage.mockResolvedValue({ total: 50, page_size: 0, page: 3 });
    await fetchClampedPage(3, fetchPage);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it("rejects a digit run too long to survive the round trip to the wire", () => {
    // The one page value that is well-FORMED to this parser and malformed to the
    // API. 21 nines pass `/^\d+$/`; `Number()` gives 1e21; the API client
    // serialises with `String()`, which writes it in exponent form; FastAPI
    // declares `page: int` and answers 422. The user saw the error screen
    // instead of the fallback this module promises.
    //
    // `fetchClampedPage` could not rescue it: the clamp resolves a RESPONSE, and
    // this value was already bad before any response existed. The regex was
    // correct; the `Number()` conversion was the leak.
    const huge = "9".repeat(21);
    expect(parsePage(huge)).toBe(DEFAULT_PAGE);
    // And the value that is merely enormous but still safe is KEPT, so this is
    // not a "reject anything big" rule in disguise — it is a range check.
    expect(parsePage("99999")).toBe(99999);
    // Number.MAX_SAFE_INTEGER itself is representable, so the boundary is
    // inclusive where JS says it is.
    expect(parsePage(String(Number.MAX_SAFE_INTEGER))).toBe(Number.MAX_SAFE_INTEGER);
    // One digit past it is not.
    expect(parsePage("9007199254740992")).toBe(DEFAULT_PAGE);
  });
});
