/**
 * The list pages' filter and pagination state, read from and written to the
 * URL query string.
 *
 * WHY A MODULE: the state used to be `useState` in each page, so a filtered
 * view could not be linked, bookmarked, reopened after a reload, or reached
 * with the back button — and two pages meant two copies of the same parsing
 * rules. The URL is now the single source, and every rule about what a value in
 * it MEANS lives here rather than in a page.
 *
 * THE PARAMETER NAMES, and why these. They appear in a link a person pastes
 * into a chat, so they are short, and they are the product's own words rather
 * than the transport's:
 *
 * - `status` — one of `legitimate`, `review`, `fraud`. Those are the words the
 *   pills already show and the words the classification column already prints,
 *   so a link reads in the vocabulary of the screen it lands on. It is NOT the
 *   API's `approved` / `flagged` / `blocked`, which are a storage detail; the
 *   page translates on the way out. Naming the parameter after the API would
 *   have been one line shorter and would have leaked `?status=flagged` into
 *   every shared link for a screen whose own filter says "Revisión".
 * - `from` / `to` — a date range. Not `date_from` / `date_to`: the API's
 *   spelling is longer, and the pair is only ever read on a list page where
 *   "from" and "to" are unambiguous. Kept in sync with the value format an
 *   `<input type="date">` produces, so the control and the URL cannot disagree.
 * - `page` — one-based, as the API numbers it.
 *
 * A CLEARED FILTER IS ABSENT RATHER THAN EMPTY. `?status=` is noise, and the
 * clean URL is the one worth sharing: `/transactions` with no query at all is
 * the canonical unfiltered view, so there is exactly one URL per view and a
 * default view has none. `writeListParams` deletes; nothing here ever writes an
 * empty value.
 *
 * AN UNRECOGNISED VALUE FALLS BACK TO THE DEFAULT, and is left in the URL.
 * Someone will hand-edit a link, paste one from a stale bookmark, or arrive
 * from a colleague whose filters have since been renamed. Three reactions were
 * available and two of them are worse:
 *
 * - Forwarding the junk to the API, which is what the page used to do for every
 *   filter value: the list comes back empty, and on a fraud surface an empty
 *   list and a filtered list that found nothing look IDENTICAL. The analyst
 *   concludes there is nothing to review when the query was never applied.
 * - Rewriting the URL to strip it. That mutates a link the moment it is
 *   opened, so the URL stops matching the one that was shared, and a
 *   normalise-on-load rule is one more thing that has to be right about the
 *   back button.
 *
 * So: an unknown value is read as "no filter", the default renders, and the
 * value stays in the address bar. The UI and the URL then visibly DISAGREE,
 * which is the honest signal — a user who asked for `?status=banana` can see
 * that their filter did not take, because the pills say "Todas" while the
 * address bar still says otherwise. Falling back silently to "no filter" with
 * the junk stripped would have looked tidier and hidden exactly the thing the
 * user needed to notice.
 *
 * WHAT IS DELIBERATELY NOT HERE. There is no free-text search box on either
 * list page, and if one is added it must NOT go into the query string: a search
 * box is typed into character by character, and one address-bar write per
 * keystroke means one history entry per keystroke, so the back button becomes
 * a character-by-character rewind, every intermediate query is a fetchable link
 * nobody wants, and the shared URL carries whatever half-word the author was
 * on when they hit copy. A date range is the opposite case — it is committed
 * once per choice from a calendar, and "the flagged transactions from last
 * week" is precisely the thing people want to paste into a chat — so it is in.
 * Sorting, had this page had any, would also have been in: it changes what the
 * list MEANS rather than narrowing it, and a sorted view is the view someone
 * reports a discrepancy from.
 */

/** The query-parameter names. One place to change them, and one to grep. */
export const LIST_PARAMS = {
  status: "status",
  page: "page",
  from: "from",
  to: "to",
} as const;

/** The page every list starts on, and the page a cleared `page` returns to. */
export const DEFAULT_PAGE = 1;

/**
 * Read a value out of an enumerated set, or `null` for anything else.
 *
 * `null` MEANS "no filter", which is the point: the callers' defaults are
 * absence, so an unrecognised value and an absent one take the same path and
 * there is no separate "invalid" case to forget to handle.
 *
 * Case-sensitive and exact. `?status=Legitimate` and `?status=fraudulent` are
 * both rejected, which is the same rule as `?status=banana` — there is no
 * normalisation, because a normalised value would let a link mean something
 * its author did not type.
 */
export function parseChoice<T extends string>(
  raw: string | null | undefined,
  allowed: readonly T[],
): T | null {
  if (raw == null || raw === "") return null;
  return allowed.find((value) => value === raw) ?? null;
}

/**
 * A page number: a plain run of decimal digits whose value is at least one.
 *
 * STRICT ON PURPOSE. Every rejection below is one rule — the characters must be
 * digits and nothing else — rather than a list of special cases, so the parser
 * has no behaviour that a hand-edited URL can reach and the function is small
 * enough to be right by inspection.
 *
 * Notably NOT accepted: exponent notation, which `Number("1e3")` would happily
 * turn into the integer 1000, and a sign, and surrounding whitespace, which a
 * `+` in the query decodes into. All three spell a page the way a human would
 * not type it, and a shareable link should not carry them.
 *
 * There is no upper bound here. A page beyond the end of the result set is
 * well-formed but unanswerable, and it is `fetchClampedPage`'s job to resolve
 * it, because only the response knows how many pages there are.
 *
 * EXCEPT THE ONE THAT IS NOT WELL-FORMED, which cost a 422 to find. A run of 21
 * or more digits passes `/^\d+$/`, and then `Number()` returns a float or
 * `Infinity`. The API client serialises with `String()`, so a 21-digit page left
 * the browser as `1e+21`, and FastAPI declares `page: int` — so the request came
 * back 422 and the user got the error screen instead of the documented graceful
 * fallback. `fetchClampedPage` could not rescue it either: the clamp resolves the
 * *response*, and this value was malformed on the wire before any response
 * existed. The regex was right; the conversion was the leak.
 */
export function parsePage(raw: string | null | undefined): number {
  if (raw == null || !/^\d+$/.test(raw)) return DEFAULT_PAGE;
  const page = Number(raw);
  if (!Number.isSafeInteger(page)) return DEFAULT_PAGE;
  return page >= DEFAULT_PAGE ? page : DEFAULT_PAGE;
}

/**
 * A calendar date in the exact format an `<input type="date">` produces.
 *
 * Two checks, and both are needed. The shape check alone accepts
 * `2026-02-31`, which is a well-formed run of digits naming a day that does not
 * exist — and `new Date("2026-02-31")` rolls it to 3 March without complaining.
 * So the parsed date is also read back out and compared field by field.
 *
 * `Date.UTC`, not `new Date(string)`: a bare date string parses as UTC
 * midnight, which in every negative UTC offset is the previous day locally, and
 * a filter that silently shifted a day would be worse than one that rejected
 * the value.
 */
export function parseIsoDate(raw: string | null | undefined): string | null {
  if (raw == null || !/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
  const [year, month, day] = raw.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  // `Date.UTC` maps a year of 0-99 onto 1900-1999, so `0001-01-01` came back as
  // 1901 and the comparison below rejected it as a day that does not exist. A
  // date input CAN produce that year, so the year the caller wrote is restored
  // rather than the value narrowed to four digits and back.
  if (year < 100) parsed.setUTCFullYear(year);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return null;
  }
  return raw;
}

/**
 * Bring a page into the range the server actually has.
 *
 * `totalPages < 1` means the result set is empty, which is not a page-range
 * problem: there is no last page to move to, and moving would hide the reason
 * the list is empty.
 */
export function clampPage(page: number, totalPages: number): number {
  if (totalPages < DEFAULT_PAGE) return page;
  return Math.min(page, totalPages);
}

/**
 * The next query string, from the current one plus a patch.
 *
 * A `null` or empty value DELETES the key; anything else sets it. Deleting is
 * what makes a cleared filter a clean URL rather than `?status=`, and it makes
 * the default view reachable by exactly one address.
 *
 * `resetPage` exists because changing a filter changes the result set, and
 * leaving `page=4` on a filter that has two pages of results is the "page 4 of
 * 2" dead end. Paging is deliberately NOT the same call: it must not reset
 * itself.
 *
 * Returns a new `URLSearchParams`; the one passed in is never mutated, so a
 * caller cannot half-apply a patch and then fail.
 */
export function writeListParams(
  current: URLSearchParams,
  patch: Readonly<Record<string, string | null>>,
  options: { resetPage?: boolean } = {},
): URLSearchParams {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
  }
  if (options.resetPage) next.delete(LIST_PARAMS.page);
  return next;
}

/**
 * Fetch a page, re-requesting the last one if the page asked for does not exist.
 *
 * WHY: a shared link outlives the result set that produced it. A URL from a
 * week with 40 pages lands on a week with 5, and without this the list renders
 * EMPTY next to a counter reading "page 40 of 5" — which is indistinguishable,
 * to a person, from a filter that legitimately matched nothing.
 *
 * The re-request is a SECOND round trip, and that is the cost, paid only on a
 * stale URL. It is not folded into the query key because the page count is not
 * knowable before the response arrives, so a query key depending on it would be
 * circular; doing it here keeps one query, one key, and one render path.
 *
 * The returned page is the one that was served, so the caller can label the
 * counter with it. Callers must NOT write it back to the URL: the URL is what
 * the user asked for, and rewriting it would make the back button mean
 * something other than "where I was".
 */
export async function fetchClampedPage<T extends { total: number; page_size: number }>(
  page: number,
  fetchPage: (page: number) => Promise<T>,
): Promise<T> {
  const first = await fetchPage(page);
  const totalPages = Math.ceil(first.total / first.page_size);
  if (totalPages >= DEFAULT_PAGE && page > totalPages) {
    return fetchPage(totalPages);
  }
  return first;
}
