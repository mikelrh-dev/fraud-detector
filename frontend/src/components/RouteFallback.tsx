/**
 * The loading state for a route whose code chunk has not arrived yet.
 *
 * WHY A COMPONENT AND NOT A SPINNER AT THE CALL SITE: the same surface has to
 * appear for seven lazy pages, and every one of them needs the accessibility
 * contract below to hold. Repeating it per route is how a third of them end up
 * unlabelled.
 *
 * WHY `role="status"` MATTERS: without it a route transition is a silent wait.
 * The previous page stays on screen doing nothing and a screen-reader user
 * gets no signal that the app is working at all. `aria-live="polite"` is
 * technically implied by `role="status"`, but it is stated explicitly on
 * purpose: the implicit value is a property of the ARIA spec, and a future
 * edit that swaps the role for a bare `div` would silently remove the
 * announcement. A test can see the attribute; it cannot see the implication.
 *
 * `aria-label` is the name source, NOT visually hidden text. `role="status"`
 * takes its accessible name from the author only — it does not compute one from
 * its contents — so a region containing only a glyph has an empty accessible
 * name and the announcement carries nothing useful. The visible copy below is
 * therefore wrapped in one `aria-hidden` cluster: the string exists once in the
 * source, sighted users read it, and assistive tech is not handed the same
 * sentence twice.
 *
 * Honest limit on live regions: a live region is only announced reliably when
 * it is in the DOM *before* the content that changed. This one is mounted at the
 * same moment as the pending state, because it is the pending state. Most
 * screen readers do announce the insertion; some do not. Making it bulletproof
 * would mean keeping a permanently-mounted status node in the shell and only
 * swapping its text — a structural change to the route tree, out of scope here.
 *  That is still strictly better than the unlabelled spinner it replaces.
 *
 *  Measured while writing this, and worth writing down because the plausible
 *  version of the claim is false: whether App.tsx nests this inside the
 *  `ErrorBoundary` or outside it makes NO difference to a chunk that fails to
 *  load. React re-throws the rejected import during the lazy component's own
 *  render, which sits under `<Routes>` either way, so the route boundary
 *  catches it in both arrangements. Nesting is a slot decision — the fallback
 *  and the error UI then occupy the same place — not a safety one.
 */

/** Single source for the string, so name and visible copy cannot drift. */
const LOADING_LABEL = "Cargando página";

export function RouteFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={LOADING_LABEL}
      data-testid="route-fallback"
      // `min-h-screen bg-slate-950` is the SAME surface every page it replaces
      // already occupies (Sidebar pages: `min-h-screen bg-slate-950` /
      // `bg-page-bg`; TransactionDetail: `min-h-screen bg-slate-950`; auth:
      // `min-h-dvh bg-slate-950`, which is >= this). So swapping this in and
      // swapping it back out moves nothing: the page body never changes
      // height and the dark background never flashes white. Pinned by
      // RouteFallback.test.tsx — drop `min-h-screen` and that test goes red.
      className="min-h-screen bg-slate-950 flex flex-col items-center justify-center gap-3"
    >
      {/* Decorative: the region's `aria-label` already carries this. */}
      <div aria-hidden="true" className="flex flex-col items-center gap-3">
        {/* Same busy idiom as Button's spinner, one size up. Track is the
            `slate-700` divider tone and the sweep is muted `slate-400`:
            deliberately NOT `risk-*` or `accent`, which DESIGN.md reserves
            for fraud states and brand actions. A loading indicator is neither. */}
        <span className="size-5 rounded-full border-2 border-slate-700 border-t-slate-400 animate-spin motion-reduce:animate-none" />
        <span className="text-xs text-slate-400">{LOADING_LABEL}…</span>
      </div>
    </div>
  );
}
