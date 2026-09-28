import { MAIN_LANDMARK_ID } from "../lib/focusable";

/**
 * "Skip to content", as the first focusable element in the document.
 *
 * WHY IT LIVES IN `App.tsx` AND NOT IN A LAYOUT ROUTE: it has to be the first
 * focusable element on EVERY route, and the app shell does not wrap the pages —
 * `App.tsx` renders `<Routes>` directly, and each page mounts its own
 * `<Sidebar>`. A layout route with an `<Outlet/>` would be the tidier home, but
 * introducing one changes the element tree, which is a different change wearing
 * this one's commit message. Rendering it as the first child inside the route
 * `ErrorBoundary` and BEFORE `<Suspense>` gets the guarantee without the
 * restructuring, and putting it outside `Suspense` is deliberate: a skip link
 * that disappears while a lazy chunk is in flight is useless exactly when a
 * keyboard user is most likely to be tabbing.
 *
 * WHY THE GEOMETRY IS HAND-WRITTEN CSS AND NOT UTILITIES: there is a
 * conventional three-utility spelling for a hide-then-reveal skip link — one
 * that clips a screen-reader element to 1px, and two attached to the bare
 * focus state that undo the clip and take the element out of the flow. All
 * three set `position`, and the two focus-state ones set it to different
 * values, so which declaration applies is decided by Tailwind's internal
 * stylesheet order and nothing else. It works today (measured) and would stop
 * working silently on an upgrade. `index.css` authors one rule per state
 * instead, and only the at-rest one declares a position, so there is no second
 * declaration to compete. The note there has the full argument.
 *
 * The three utilities are described rather than written out, deliberately: this
 * comment used to spell them, and Tailwind's scanner reads raw source text —
 * comments included — so spelling them made the build emit two rules that no
 * element in the product can match. The reasoning is worth keeping; the
 * scannable form of it is not.
 *
 * WHY `href` IS KEPT ALONGSIDE THE CLICK HANDLER. The handler exists because
 * "skip to content" has to *move focus*, and that is two separate mechanisms:
 * the `href` gives the real browser behaviour — scroll, URL fragment,
 * middle-click, ctrl-click, "copy link address", and a working link with JS
 * disabled — while the handler makes the focus move explicit and therefore
 * testable. jsdom implements fragment navigation (it updates the hash) but does
 * not move focus, so without the handler the one assertion that matters —
 * "activating it puts focus on the content" — could not be written at all.
 * Deliberately NOT `preventDefault()`: in a real engine both run and both land
 * on the same element, and suppressing the default would throw away the URL
 * fragment and the open-in-new-tab affordance for no gain.
 */
export function SkipLink() {
  function handleActivate() {
    // The target is `tabIndex={-1}`: programmatically focusable, which is what
    // a skip link needs, and NOT in the tab order, which is what it must not do
    // — otherwise the landmark becomes a second stop between the shell and the
    // first control. `focus()` is a no-op when the id is missing, so a page
    // that forgets the id degrades to the browser's fragment behaviour instead
    // of throwing inside a click handler.
    document.getElementById(MAIN_LANDMARK_ID)?.focus();
  }

  return (
    <a
      href={`#${MAIN_LANDMARK_ID}`}
      onClick={handleActivate}
      // eslint-disable-next-line ui/no-raw-class-tokens -- a skip link reveals on ANY focus, and its ring must match that state; see the note in index.css
      className="skip-link focus:outline-none focus:ring-2 focus:ring-focus-ring"
    >
      Saltar al contenido
    </a>
  );
}
