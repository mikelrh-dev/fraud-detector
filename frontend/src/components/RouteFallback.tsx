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
 * THE TEXT STAYS IN THE ACCESSIBILITY TREE, and an earlier version of this
 * comment argued the opposite -- that the `aria-label` is the name source and the
 * visible copy could therefore be hidden, so the string would not be "handed to
 * assistive tech twice". That reasoning is wrong, and the review that caught it
 * is worth recording because the claim sounds reasonable. A live region is
 * announced by its CONTENT. `aria-label` names the region for a name-and-role
 * query; it does not reliably become the announcement text. With every text node
 * inside one `aria-hidden` cluster, a screen reader announcing by content had
 * nothing at all to say -- the region was well named and mute.
 *
 * So: the SPINNER is `aria-hidden` (it is a pure decoration, and it is what the
 * `aria-label` stands in for), and the label text is left readable. One string,
 * no duplication, and the announcement actually has content.
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
      {/* Only the SPINNER is hidden from assistive tech. The label beside it
          stays in the accessibility tree, because a live region is announced by
          its content -- see the header. */}
      <div className="flex flex-col items-center gap-3">
        {/* Same busy idiom as Button's spinner, one size up. Track is the
            `slate-700` divider tone and the sweep is muted `slate-400`:
            deliberately NOT `risk-*` or `accent`, which DESIGN.md reserves
            for fraud states and brand actions. A loading indicator is neither.

            No `motion-reduce:animate-none` here on purpose: the global
            `prefers-reduced-motion` guard in index.css now covers
            `animate-spin`, so a per-call-site opt-out would be dead weight
            justified by a claim that stopped being true. */}
        <span
          aria-hidden="true"
          className="size-5 rounded-full border-2 border-slate-700 border-t-slate-400 animate-spin"
        />
        <span className="text-xs text-slate-400">{LOADING_LABEL}…</span>
      </div>
    </div>
  );
}
