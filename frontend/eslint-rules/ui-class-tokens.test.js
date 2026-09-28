import { RuleTester } from "eslint";
import { describe, it } from "vitest";
import * as tsParser from "@typescript-eslint/parser";
import ui from "./ui-class-tokens.js";

/**
 * `ui/no-raw-class-tokens`, the rule that exists because nothing else stopped
 * the class-string drift `src/lib/ui.ts` was written to end.
 *
 * WHY THESE TESTS EXIST AND NOT A SCRATCH FILE: the rule's five checks were
 * validated once, by hand, against a file that was then deleted. `RuleTester`
 * inverts a condition and nothing goes red, so none of `looksLikeBtnBase`,
 * `isBareFocus` or the `claimed` dedup had anything standing behind them. This
 * file is that standing. Every case below was watched fail against a
 * deliberately broken rule before the rule was allowed to keep its shape — the
 * mutations are named in the commits that introduced this file.
 *
 * Two things this file deliberately does NOT do:
 *
 *  - It does not lint `src/` and count errors. That number changes every time a
 *    page is migrated, so a test asserting it would fail on work that is
 *    correct. Scope is asserted per-CONSTRUCT instead, which is what the rule
 *    actually decides.
 *  - It does not compare a class name against a constant imported from
 *    `lib/ui.ts`. Every expectation below is the literal Tailwind spelling,
 *    because comparing against the constant is a tautology: move the constant
 *    and both sides of the assertion move with it.
 *
 * The literals here are exempt from Tailwind's scanner by location, not by
 * luck: this file lives outside `src/`, and `tailwindcss`'s automatic source
 * detection starts from the CSS entrypoint's project root and honours
 * `.gitignore` — `eslint-rules/` is not imported by anything, so none of these
 * strings can become a rule in `dist`. That is load-bearing, not incidental: a
 * test that names a class Tailwind can see would manufacture dead CSS, which is
 * the exact failure recorded in the note in `src/lib/ui.ts`.
 */

RuleTester.describe = describe;
RuleTester.it = it;

const ruleTester = new RuleTester({
  languageOptions: {
    parser: tsParser,
    ecmaVersion: 2022,
    sourceType: "module",
    parserOptions: {
      ecmaFeatures: { jsx: true },
    },
  },
});

const BARE_FOCUS =
  "Bare `focus:` paints on mouse click as well as keyboard. Import FOCUS_RING from src/lib/ui.ts — it is `focus-visible:`-prefixed for exactly this reason.";
const RAW_FOCUS_RING =
  "That token belongs to FOCUS_RING. Import FOCUS_RING from src/lib/ui.ts instead of re-typing the ring, so the focus treatment cannot drift from the constant.";
const RAW_INPUT_CHROME =
  "placeholder-slate-500 + bg-slate-800 + rounded-lg in one class list is INPUT_BASE re-typed. Render an <Input> (src/components/Input.tsx) or compose cn(INPUT_BASE, …).";
const RAW_BTN_BASE =
  "btn-motion + active:scale-[0.98] + touch-manipulation is BTN_BASE re-typed. Render a <Button> (src/components/Button.tsx) or compose cn(BTN_BASE, …).";
const RAW_HEX =
  "Raw hex in a class list. Add a token to the @theme block in src/index.css and use the utility — DESIGN.md sanctions hex in index.css, lib/chart-theme.ts, index.html and favicon.svg only.";
const RAW_SEMANTIC_COLOR =
  "Raw chromatic palette value where the design system defines a token. Pick the token that means this element's ROLE: risk-clean / risk-warn / risk-critical for a risk state, accent for brand or primary action, status-info for informational. The neutral slate ramp stays legal — DESIGN.md names it as its own values.";

/**
 * One representative per chromatic family, as an INDEPENDENT literal list.
 *
 * Written out here rather than imported from the rule, because importing the
 * rule's own list would be the tautology this file exists to avoid: delete
 * `"rose"` from the rule and an imported list loses it too, so the test would
 * pass having checked one family fewer.
 *
 * It has to be one CASE PER FAMILY, not one case holding all sixteen, and a
 * mutation proved why: the rule reports once per VALUE, so sixteen families in
 * a single `className` still draw one report, and dropping `"rose"` from the
 * rule left that case green. Sixteen cases cannot hide a removal.
 *
 * The limitation this leaves, stated rather than hidden: it pins "each of these
 * sixteen is caught", not "nothing beyond these sixteen is caught". A family
 * ADDED to the rule would go unnoticed here until it met real code.
 */
const CHROMATIC_FAMILY_SAMPLES = [
  "text-red-500",
  "text-orange-500",
  "text-amber-500",
  "text-yellow-500",
  "text-lime-500",
  "text-green-500",
  "text-emerald-500",
  "text-teal-500",
  "text-cyan-500",
  "text-sky-500",
  "text-blue-500",
  "text-indigo-500",
  "text-violet-500",
  "text-purple-500",
  "text-fuchsia-500",
  "text-pink-500",
  "text-rose-500",
];

/** The neutral families, one per case, for the same reason as above. */
const NEUTRAL_FAMILY_SAMPLES = [
  "text-slate-400",
  "text-zinc-400",
  "text-stone-400",
  "text-neutral-400",
  "text-gray-400",
];

// --------------------------------------------------------------------------
// 1. bareFocus — a bare `focus:` PAINTING utility in a class position
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens — bareFocus", () => {
  ruleTester.run("bareFocus", ui.rules["no-raw-class-tokens"], {
    valid: [
      // `focus-visible:` is the HOUSE prefix, so it is never the offence. The
      // two tokens here are deliberately not `FOCUS_RING`'s own — a ring typed
      // by hand is `rawFocusRing`'s business, and asserting it here would be
      // asserting two checks at once.
      { code: `const a = <button className="focus-visible:ring-4 focus-visible:outline-2" />;` },
      // An unrelated state prefix, untouched by the rule.
      { code: `const a = <button className="hover:ring-2 active:ring-2" />;` },
      // SCOPE, decided deliberately. A bare `focus:` on a NON-painting utility
      // is allowed, because the rationale for this check is a focus INDICATOR
      // that fires on mouse click — and `focus:z-10` / `focus:scroll-mt-24` are
      // layout and scroll-position adjustments that paint nothing and are
      // correct on any state. `focus:not-sr-only` and `focus:absolute`, the two
      // the hand-written skip-link CSS exists to avoid, are in this same class:
      // a real bug, not a `focus:` bug.
      { code: `const a = <span className="focus:z-10 focus:scroll-mt-24" />;` },
      {
        // THE PREFIX BOUNDARY, tested rather than assumed. `focus:` must not
        // match a token that merely STARTS with `focus` — a naive
        // `startsWith("focus")` plus "take everything after the first colon"
        // reads `focus-visible:ring-4` as the utility `ring-4`, which paints,
        // and flags the house prefix. Two other pseudo-classes that do the
        // same thing if the guard is sloppy.
        code: `const a = <button className="focus-visible:ring-4 focus-within:ring-4" />;`,
      },
      {
        // AND THE OTHER SIDE OF IT: `touch-none` sets `touch-action`, which
        // paints nothing. It is in this test because `to` is in the painting
        // list for gradient stops, and a prefix match without a word boundary
        // would let `to` swallow `touch-…` and ban a legitimate class.
        code: `const a = <div className="focus:touch-none" />;`,
      },
    ],
    invalid: [
      {
        // The drift the rule was written for: the house ring with the wrong
        // pseudo-class, so the ring also paints on mouse click.
        code: `const a = <button className="focus:ring-2" />;`,
        errors: [{ message: BARE_FOCUS }],
      },
      {
        // `outline-none` with a bare `focus:` removes the indicator for
        // whichever state the other rule forgets to cover.
        code: `const a = <button className="focus:outline-none focus:ring-2 focus:ring-focus-ring" />;`,
        // One report per VALUE, not per token: three offenders, one complaint.
        errors: [{ message: BARE_FOCUS }],
      },
      {
        // A boundary colour on focus is still painting.
        code: `const a = <input className="focus:border-risk-critical" />;`,
        errors: [{ message: BARE_FOCUS }],
      },
      {
        // Inside a template literal, which is how most of this tree writes a
        // className: one value spanning two lines, one report.
        code: [
          `const a = <button className={\`focus:ring-2 px-3`,
          `  py-1.5\`} />;`,
        ].join("\n"),
        errors: [{ message: BARE_FOCUS }],
      },
      {
        // The `class` spelling, not just `className`.
        code: `const a = <div class="focus:ring-2" />;`,
        errors: [{ message: BARE_FOCUS }],
      },
    ],
  });
});

// --------------------------------------------------------------------------
// 1b. The painting list, verified namespace by namespace.
// --------------------------------------------------------------------------

/**
 * `bareFocus`'s boundary is a LIST, and a list nobody tests is a list that
 * loses entries quietly — a namespace dropped "just to unblock a commit" is
 * indistinguishable from a namespace nobody needed, until a real `focus:ring-`
 * slips through.
 *
 * So the list is spelled out HERE rather than imported: importing it would make
 * this a tautology, because the test would move with whatever the rule says.
 * A new painting namespace added to the rule is a deliberate act and this list
 * is where it gets written down; a namespace REMOVED from the rule without
 * removing it here turns this red.
 *
 * The `-probe` suffix is arbitrary and not a real utility. `ring-probe` is not
 * a Tailwind class, which is the point: the check reads the property namespace
 * and nothing else, so it does not need a plausible value to fire.
 */
const FOCUS_PAINT_NAMESPACES = [
  "ring",
  "outline",
  "shadow",
  "drop-shadow",
  "border",
  "divide",
  "bg",
  "text",
  "fill",
  "stroke",
  "accent",
  "caret",
  "placeholder",
  "opacity",
  "filter",
  "backdrop",
  "mix-blend",
  "blur",
  "translate",
  "scale",
  "rotate",
  "skew",
  "from",
  "via",
  "to",
];

/** The other half of the contract: these are NOT paints, and stay legal. */
const NON_PAINTING_UNDER_FOCUS = [
  "z-10",
  "order-2",
  "scroll-mt-24",
  "p-4",
  "px-3",
  "w-32",
  "inset-0",
  "top-2",
  "overflow-auto",
  "cursor-pointer",
  "pointer-events-none",
  "absolute",
  "not-sr-only",
  "snap-x",
  "resize",
  "break-words",
];

describe("ui/no-raw-class-tokens — what counts as painting", () => {
  ruleTester.run(
    "painting namespaces",
    ui.rules["no-raw-class-tokens"],
    {
      valid: NON_PAINTING_UNDER_FOCUS.map((utility) => ({
        code: `const a = <div className="focus:${utility}" />;`,
      })),
      invalid: FOCUS_PAINT_NAMESPACES.map((namespace) => ({
        code: `const a = <div className="focus:${namespace}-probe" />;`,
        errors: [{ message: BARE_FOCUS }],
      })),
    },
  );
});

// --------------------------------------------------------------------------
// 2. rawFocusRing — a token that belongs to FOCUS_RING, typed by hand
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens — rawFocusRing", () => {
  ruleTester.run("rawFocusRing", ui.rules["no-raw-class-tokens"], {
    valid: [
      { code: `const a = <button className="focus-visible:ring-4 focus-visible:ring-offset-2" />;` },
      { code: `const a = <button className="ring-2 ring-accent" />;` },
    ],
    invalid: [
      {
        // All three of the constant's tokens, hand-typed: the exact copy the
        // rule exists to stop, and the reason the message names the import.
        code: `const a = <button className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring" />;`,
        errors: [{ message: RAW_FOCUS_RING }],
      },
      {
        // A single token is enough. The drift is not in the count, it is in
        // the fact that a ring is being spelled here at all.
        code: `const a = <button className="px-3 focus-visible:ring-focus-ring py-1.5" />;`,
        errors: [{ message: RAW_FOCUS_RING }],
      },
    ],
  });
});

// --------------------------------------------------------------------------
// 3. rawInputChrome — the INPUT_BASE COMBINATION
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens — rawInputChrome", () => {
  ruleTester.run("rawInputChrome", ui.rules["no-raw-class-tokens"], {
    valid: [
      {
        // Two of the three, which is what a card or a panel looks like. If the
        // check fired on a SUBSET it would ban the design system, because these
        // tokens are used all over it.
        code: `const a = <div className="bg-slate-800 rounded-lg p-4" />;`,
      },
      {
        // All three, spread across two elements. One class list is one
        // element, so a subset on each is not the drift.
        code: `const a = <div className="bg-slate-800 rounded-lg"><input className="placeholder-slate-500" /></div>;`,
      },
      {
        // The auth fields use `bg-slate-900` and a `placeholder:` variant, so
        // they are NOT a re-type of INPUT_BASE and stay legal.
        code: `const a = <input className="h-11 w-full rounded-lg bg-slate-900 border border-slate-800 px-3 text-sm text-slate-200 placeholder:text-slate-600" />;`,
      },
    ],
    invalid: [
      {
        // The combination, in one class list. `text-slate-200` rather than the
        // constant's `text-slate-100` is the visible half of the drift.
        code: `const a = <textarea className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />;`,
        errors: [{ message: RAW_INPUT_CHROME }],
      },
    ],
  });
});

// --------------------------------------------------------------------------
// 4. rawBtnBase — the BTN_BASE COMBINATION, and the four/six split
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens — rawBtnBase", () => {
  ruleTester.run("rawBtnBase", ui.rules["no-raw-class-tokens"], {
    valid: [
      {
        // The four chip/pill call sites. `touch-manipulation` is the token that
        // belongs to the base alone, so these are allowed — and the check
        // deliberately does NOT flag them, because forcing `inline-flex` +
        // `font-medium` onto a chip is a visual change dressed up as lint
        // compliance.
        code: `const a = <button className="btn-motion active:scale-[0.98] text-xs px-3 py-1.5 rounded-full bg-slate-800 text-slate-400" />;`,
      },
      {
        // The other pair, alone: a chip that never wanted the base at all.
        code: `const a = <button className="btn-motion active:scale-[0.98] rounded border px-2 py-1 text-[11px]" />;`,
      },
      {
        // `touch-manipulation` without the motion pair is not a reconstruction
        // of the base either. The check is a COMBINATION, deliberately.
        code: `const a = <div className="touch-manipulation" />;`,
      },
      {
        // Two of the three, which is the boundary from the other side: drop
        // `btn-motion` from the required set and this starts being reported,
        // and a class list carrying the press scale and the tap behaviour with
        // no motion transition is not a re-typed base. Pinning the exact set
        // matters because the set IS the rule.
        code: `const a = <button className="active:scale-[0.98] touch-manipulation px-3" />;`,
      },
    ],
    invalid: [
      {
        // The base, re-typed: all three discriminator tokens together.
        code: `const a = <button className="btn-motion active:scale-[0.98] inline-flex items-center justify-center gap-1.5 font-medium touch-manipulation px-3 py-2" />;`,
        errors: [{ message: RAW_BTN_BASE }],
      },
      {
        // Order is irrelevant: the check is set membership, not a sequence.
        code: `const a = <button className="touch-manipulation active:scale-[0.98] btn-motion" />;`,
        errors: [{ message: RAW_BTN_BASE }],
      },
    ],
  });
});

// --------------------------------------------------------------------------
// 5. rawHex — a raw colour literal at a class position
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens — rawHex", () => {
  ruleTester.run("rawHex", ui.rules["no-raw-class-tokens"], {
    valid: [
      { code: `const a = <div className="bg-slate-800 text-slate-200" />;` },
      // A token reference is the sanctioned form.
      { code: `const a = <div className="bg-accent text-text-primary" />;` },
      // Not a colour: `#` inside a name is legal in a CSS identifier and this
      // is not one of the four files DESIGN.md sanctions raw hex in, so the
      // check has to stay tight to `#` followed by hex digits.
      { code: `const a = <div className="grid-cols-[repeat(auto-fit,minmax(0,1fr))]" />;` },
      {
        // A `#` that is a URL FRAGMENT, not a colour. A URL in an arbitrary
        // value is a legitimate class, and the reason this predicate is
        // "hex digits" and not "a hash sign".
        code: `const a = <div className="bg-[url('/img/chart.svg#bars')]" />;` },
      {
        // A gradient reference. `g` is not a hex digit, so there is nothing
        // here for the predicate to read.
        code: `const a = <div className="fill-[url(#gradient)]" />;` },
      {
        // THE WORD BOUNDARY, and this case is admitted to be one the utility
        // vocabulary does not really produce: a ten-character hex-like run is
        // a hash or an id, never a colour. It is pinned anyway, because a
        // branch of a predicate that no test reaches is a claim nobody checked,
        // and the cost of a contrived case is much lower than the cost of a
        // silent false positive once someone writes a 9-digit run.
        code: `const a = <div className="bg-[#0f172aabb]" />;` },
    ],
    invalid: [
      {
        // Six-digit hex in an arbitrary value — the common form, and one that
        // compiles to real CSS, so nothing else would ever catch it.
        code: `const a = <div className="bg-[#0f172a]" />;`,
        errors: [{ message: RAW_HEX }],
      },
      {
        // Authored shorthand.
        code: `const a = <div className="text-[#fff]" />;`,
        errors: [{ message: RAW_HEX }],
      },
      {
        // UPPERCASE, which is legal CSS and byte-identical to the lowercase
        // spelling. A case-sensitive predicate would wave it through.
        code: `const a = <div className="bg-[#0F172A]" />;`,
        errors: [{ message: RAW_HEX }],
      },
    ],
  });
});

// --------------------------------------------------------------------------
// 6. rawSemanticColor — a raw CHROMATIC value where a token is defined
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens - rawSemanticColor", () => {
  ruleTester.run("rawSemanticColor", ui.rules["no-raw-class-tokens"], {
    valid: [
      // THE NEUTRAL RAMP IS LEGAL, and this is the load-bearing case in the
      // whole check. DESIGN.md's own Surfaces and Text tables NAME these
      // spellings, and line 419 says the default palette is not re-declared.
      // A check that flagged `bg-slate-800` would need a suppression on every
      // one of the ~200 neutral values in this tree.
      { code: `const a = <div className="bg-slate-900 border border-slate-800 text-slate-200" />;` },
      { code: `const a = <div className="text-slate-400 hover:text-slate-100" />;` },
      { code: `const a = <div className="bg-zinc-900 text-stone-400 text-neutral-500" />;` },
      // One case per neutral family, so adding a chromatic family that happens
      // to be one of these, or removing a neutral carve-out, is visible here.
      ...NEUTRAL_FAMILY_SAMPLES.map((cls) => ({
        code: `const a = <div className="${cls}" />;`,
      })),
      // The sanctioned form: every token the project actually defines.
      { code: `const a = <div className="text-risk-critical bg-risk-clean/10 border-risk-warn/30" />;` },
      { code: `const a = <div className="text-accent hover:bg-action-hover" />;` },
      { code: `const a = <div className="text-status-info bg-page-bg border-divider text-text-muted" />;` },
      // A family-looking name that is not a Tailwind family.
      { code: `const a = <div className="text-burgundy-400 bg-forest-100" />;` },
      // No numeric step: `red` alone is not a colour step, and a bare `red`
      // is not a utility this project emits.
      { code: `const a = <div className="text-red border-red" />;` },
      {
        // THE NUMERIC-STEP GUARD, and this case is admitted to be contrived,
        // on the same terms as the hex word-boundary case in the `rawHex`
        // suite: no real Tailwind utility pairs a chromatic family with a
        // non-numeric step, because every colour step is a number.
        //
        // It is pinned anyway because a mutation showed the guard is otherwise
        // unobservable. With it removed, `text-risk-critical` still does not
        // report — `risk` is not a chromatic family either — so the guard
        // changes nothing any other case in this file can see, and a branch of
        // a predicate that no test reaches is a claim nobody checked. The cost
        // of a contrived valid case is far lower than the cost of a false
        // positive the day someone hand-writes a colour-shaped token.
        code: `const a = <div className="bg-red-500x" />;`,
      },
      // Non-class positions, for the same reason every other check has them.
      { code: `const a = <div data-x="text-red-400" />;` },
      { code: `const a = <div aria-label="text-red-400" />;` },
      { code: `const t = "text-red-400";` },
    ],
    invalid: [
      {
        // The plain form, and the reason the check exists: an error message in
        // raw red-400 sitting in a file whose other error message uses the
        // risk token.
        code: `const a = <p className="text-red-400" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // A variant prefix. `hover:text-red-400` is what a hand-rolled
        // destructive hover looked like.
        code: `const a = <button className="hover:text-red-400" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // `focus-visible:` is a state, and the colour after it is still the
        // offence. This is the case a naive `startsWith("hover:")`-style
        // stripper gets wrong in the other direction.
        code: `const a = <input className="focus-visible:ring-green-500" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // TWO variants stacked. Each segment is a state or breakpoint.
        code: `const a = <div className="md:enabled:hover:bg-green-600" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // An alpha modifier, which is the shape the fired-rules chip used:
        // `bg-red-900/30 text-red-400 border-red-800/30`.
        code: `const a = <span className="bg-red-900/30 text-red-400 border border-red-800/30" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // A SIDE-SPECIFIC border, where the namespace is `border-t` and not
        // `border`. `border-t-red-400` must not be read as family `t-red`.
        code: `const a = <div className="border-t-red-400" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // A variant that is a MOTION or breakpoint modifier rather than a
        // state. The variant is orthogonal to the colour, so a raw red under
        // `motion-safe:` is still a raw red. This case is here because the
        // obvious implementation — strip only the segments it recognises as
        // states — would either wave this through or crash on it.
        code: `const a = <div className="motion-safe:text-red-400" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      // Every chromatic family, ONE PER CASE, to pin the LIST rather than one
      // member of it. See `CHROMATIC_FAMILY_SAMPLES` for why one case each.
      ...CHROMATIC_FAMILY_SAMPLES.map((cls) => ({
        code: `const a = <div className="${cls}" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      })),
      {
        // ONE report for fifteen tokens, because a class list is one VALUE and
        // the rule reports per value — the same de-duplication every other
        // check has, pinned here so this check cannot quietly grow a
        // fifteen-line report for one element.
        code: `const a = <div className="text-orange-500 text-amber-500 text-yellow-500 text-lime-500 text-emerald-500 text-teal-500 text-cyan-500 text-sky-500 text-blue-500 text-indigo-500 text-violet-500 text-purple-500 text-fuchsia-500 text-pink-500 text-rose-500" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // A non-`text` namespace, so the namespace list is pinned and not just
        // the one the project's own code happened to use.
        code: `const a = <div className="fill-red-500 stroke-blue-300 from-green-200 via-yellow-300 to-orange-400" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // The `!` important prefix.
        code: `const a = <div className="!text-red-400" />;`,
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
      {
        // A `cn(...)` argument at module scope — the second class position,
        // so the new check is proved at the same places as the other five.
        code: [
          `import { cn } from "./lib/ui";`,
          `const BAD = cn("text-green-500", x);`,
        ].join("\n"),
        errors: [{ message: RAW_SEMANTIC_COLOR }],
      },
    ],
  });
});

// --------------------------------------------------------------------------
// 7. Scope. The part of the rule that was wrong.
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens — what counts as a class string", () => {
  ruleTester.run("scope", ui.rules["no-raw-class-tokens"], {
    valid: [
      {
        // A class position, and legal. A card is not an input.
        code: `const a = <div className="bg-slate-800 rounded-lg p-4" />;`,
      },
    ],
    invalid: [],
  });

  ruleTester.run("scope — non-class positions", ui.rules["no-raw-class-tokens"], {
    valid: [
      {
        // A JSX text child. `startsWith("focus:")` cannot tell a class from a
        // sentence, and this is the shape of sentence that trips it.
        code: `const a = <p>{"Invalid focus: the ring did not apply"}</p>;`,
      },
      {
        // A data attribute. It is a string, it is not a class, and the rule has
        // no business reading it — even when the string happens to be a real
        // class name, because nothing applies it to an element.
        code: `const a = <span data-x="focus:ring-2" />;`,
      },
      {
        // An accessible name. "focus:" mid-sentence is prose.
        code: `const a = <button aria-label="Press to focus: retry the failed ring" />;`,
      },
      {
        // A plain string constant, not a class constant.
        code: `export const SCRATCH = "focus:";`,
      },
      {
        // A URL.
        code: `export const URL_PATH = "/api/v1/focus:retry";`,
      },
      {
        // A LOCAL function that happens to be called `cn`, at module scope.
        // `cn` is resolved through its import from `src/lib/ui`, precisely so a
        // joiner defined three lines above cannot widen the scope by accident.
        code: [
          `function cn(...parts) { return parts.join(" "); }`,
          `export const X = cn("focus:ring-2 bg-[#0f172a]");`,
        ].join("\n"),
      },
      {
        // The same name, imported from somewhere that is not the design
        // system. A `clsx` aliased to `cn` is still a `clsx`.
        code: [
          `import { cn } from "./string-utils";`,
          `export const X = cn("focus:ring-2");`,
        ].join("\n"),
      },
      {
        // A namespace import of something else entirely, called through a
        // member expression.
        code: [
          `import * as clsx from "clsx";`,
          `export const X = clsx("focus:ring-2");`,
        ].join("\n"),
      },
    ],
    invalid: [
      {
        // A `cn(...)` argument at module scope. This is where a shared helper
        // gets written, so it is a class position even though no JSX is
        // involved — the promised scope, which the implementation did not have.
        code: [
          `import { cn } from "./lib/ui";`,
          `export const BTN = cn(`,
          `  "btn-motion active:scale-[0.98] inline-flex items-center justify-center gap-1.5 font-medium touch-manipulation",`,
          `);`,
        ].join("\n"),
        errors: [{ message: RAW_BTN_BASE }],
      },
      {
        // A `cn(...)` argument, module scope, raw hex.
        code: [
          `import { cn } from "./lib/ui";`,
          `export const SURFACE = cn("bg-[#0f172a]");`,
        ].join("\n"),
        errors: [{ message: RAW_HEX }],
      },
      {
        // A `cn(...)` argument, module scope, INPUT_BASE re-typed.
        code: [
          `import { cn } from "./lib/ui";`,
          `export const FIELD = cn(`,
          `  "w-full bg-slate-800 border border-slate-700 px-3 py-2 rounded-lg placeholder-slate-500",`,
          `);`,
        ].join("\n"),
        errors: [{ message: RAW_INPUT_CHROME }],
      },
      {
        // A `cn(...)` argument, module scope, bare focus.
        code: [
          `import { cn } from "./lib/ui";`,
          `export const RING = cn("focus:ring-2");`,
        ].join("\n"),
        errors: [{ message: BARE_FOCUS }],
      },
      {
        // INSIDE a className, the callee's identity is irrelevant: the
        // attribute is a class position, so a bare `focus:` in it is a real
        // finding whether a `clsx` or a `join` or nothing at all assembled the
        // string. This is the one case where a same-named local function does
        // not buy an exemption, and it is the important half of the rule.
        code: [
          `function cn(...parts) { return parts.join(" "); }`,
          `const a = <div className={cn("focus:ring-2")} />;`,
        ].join("\n"),
        errors: [{ message: BARE_FOCUS }],
      },
      {
        // The `ui` namespace spelling of the same helper, so the import
        // resolution is not a single hard-coded string comparison.
        code: [
          `import * as ui from "../lib/ui";`,
          `export const RING = ui.cn("focus:ring-2");`,
        ].join("\n"),
        errors: [{ message: BARE_FOCUS }],
      },
    ],
  });
});

// --------------------------------------------------------------------------
// 7. The internals, which nothing else exercises on their own.
// --------------------------------------------------------------------------

describe("ui/no-raw-class-tokens — the claimed WeakSet", () => {
  ruleTester.run("no double-reporting", ui.rules["no-raw-class-tokens"], {
    valid: [
      // A className whose value is a template literal with three quasis. Each
      // quasi is a separate `TemplateElement`, so without the `claimed`
      // dedup the outer template and its quasis would each be checked and the
      // same drift would be reported three times.
      {
        code: [
          `const a = <button className={\`px-3 \${x} \${y}\`} />;`,
        ].join("\n"),
      },
    ],
    invalid: [
      {
        // Same shape, with a real offence: exactly ONE report for the whole
        // className, at the attribute's value.
        code: [
          `const a = <button className={\`focus:ring-2 \${x} \${y}\`} />;`,
        ].join("\n"),
        errors: [
          {
            message: BARE_FOCUS,
            // Reported on the className's own VALUE node, which for a
            // `{…}` attribute is the expression container — not a nested
            // literal. That is what makes the suppression land on the
            // attribute line rather than inside a string.
            type: "JSXExpressionContainer",
          },
        ],
      },
      {
        // A `cn(...)` call inside a className: the outer attribute owns the
        // class list, so the nested literals are claimed and the composition
        // check sees them all in one bucket. Reported once, on the container.
        code: [
          `import { cn } from "./lib/ui";`,
          `const a = <button className={cn("btn-motion active:scale-[0.98] touch-manipulation", x)} />;`,
        ].join("\n"),
        errors: [{ message: RAW_BTN_BASE, type: "JSXExpressionContainer" }],
      },
    ],
  });
});

describe("ui/no-raw-class-tokens — the reported node", () => {
  ruleTester.run("node kinds", ui.rules["no-raw-class-tokens"], {
    valid: [
      {
        // An expression attribute (`className={x}`) has no string of its own,
        // so there is nothing to read and nothing to report. What a variable
        // holds is not this rule's business, and pretending otherwise would be
        // a guess dressed as a check.
        code: `const a = <button className={SOME_VARIABLE} />;`,
      },
      {
        // A spread, likewise: the rule cannot see through it, and says so.
        code: `const a = <button className={cn(...parts)} />;`,
      },
    ],
    invalid: [
      {
        // A plain string attribute: the report lands on the string Literal, so
        // an `eslint-disable-next-line` above the attribute silences it.
        code: `const a = <button className="focus:ring-2" />;`,
        errors: [{ message: BARE_FOCUS, type: "Literal" }],
      },
    ],
  });
});
