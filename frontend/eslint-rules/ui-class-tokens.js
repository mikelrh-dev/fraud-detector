/**
 * Local ESLint rule: `ui/no-raw-class-tokens`.
 *
 * WHY A CUSTOM RULE AND NOT `no-restricted-syntax`
 * -------------------------------------------------
 * The core rule is a *value* rule, not a *syntax* rule. `no-restricted-syntax`
 * matches nodes and cannot look at what a string contains;
 * `no-restricted-imports` matches module specifiers, and the whole point here
 * is that the forbidden thing is a COPY rather than an import. Neither can see
 * that `"focus:ring-2"` was typed out by hand when `FOCUS_RING` exists.
 *
 * WHY THE RULE EXISTS AT ALL
 * --------------------------
 * `src/lib/ui.ts` is now the single source for the focus treatment, the button
 * base and the input chrome. Every class string that used to be re-typed
 * button by button was fixed by hand, once, across seven commits. Nothing in
 * the toolchain stopped the eighth hand-rolled button from arriving: copying
 * was always easier than importing, and Tailwind v4 emits no error for a class
 * that names a nonexistent token — a typo'd `ring-focus-rng` compiles to
 * nothing and nobody finds out until a keyboard user does. This rule is the
 * thing that makes the next one fail at lint time instead of at review time.
 *
 * WHERE IT LOOKS: CLASS POSITIONS, AND ONLY CLASS POSITIONS
 * ---------------------------------------------------------
 * A class string is a class list when it lands in one of two places:
 *
 *  1. a JSX `className` / `class` attribute value, however it is spelled — a
 *     string literal, a template literal, or an expression container holding
 *     either;
 *  2. an argument of `cn(...)`, the composition helper from `src/lib/ui`, at
 *     any scope. Module scope counts: `const BTN = cn("btn-motion …")` at the
 *     top of a file is exactly where a shared helper gets written, which is why
 *     the rule has to reach it. `cn` is resolved through its IMPORT, so an
 *     unrelated local function that happens to be called `cn` does not widen
 *     the scope by accident.
 *
 * Every check applies at both, because both are a call site — the place where
 * composition is supposed to happen, so a hand-rolled class list there IS the
 * drift.
 *
 * It looks NOWHERE ELSE, and that is a decision rather than a gap. An earlier
 * version applied the two focus checks to *every string literal in the file*,
 * on the theory that a focus ring is a correctness contract wherever it is
 * written. Measured, that theory was wrong in both directions: it read prose
 * (`"Invalid focus: the ring did not apply"`, an `aria-label` that mentions
 * focus) and it read non-class attributes (`data-x="focus:ring-2"`), because
 * `startsWith("focus:")` cannot tell a class from a message. The tree happened
 * to be clean — by luck, not by design.
 *
 * The honest boundary, stated rather than hidden: a class string written into a
 * constant and only ever REFERENCED is out of reach. A lint rule that follows
 * references is a type checker, and the heuristics that approximate one produce
 * false positives, which is a worse failure than a stated limit. Both recorded
 * divergences this rule was built alongside (`AUTH_INPUT_RING` in
 * `AuthSplitLayout.tsx`, the `<textarea>` in `AlertsPage.tsx`) are pinned by
 * TESTS in both directions instead, which is the mechanism this codebase uses
 * for a divergence that is deliberately kept.
 *
 * WHAT `bareFocus` ACTUALLY COVERS
 * --------------------------------
 * Not every bare `focus:`. Only one on a utility that PAINTS, because the
 * rationale is a focus *indicator* firing on mouse click — and `focus:z-10` or
 * `focus:scroll-mt-24` are layout and scroll-position adjustments that paint
 * nothing and are correct on any state. `FOCUS_PAINT_NAMESPACES` below is the
 * boundary, and the failure direction is deliberate: an unknown PAINTING
 * utility is missed until the list is extended, rather than a layout utility
 * being flagged for a reason that has nothing to do with focus. The house ring
 * itself does not depend on this list at all — `rawFocusRing` matches three
 * exact tokens, no vocabulary required.
 *
 * Comments are invisible to this rule by construction — it reads the AST, not
 * the raw text. That is the opposite of Tailwind's scanner, which DOES read
 * comments; see the note in `lib/ui.ts` about a comment that manufactured the
 * evidence against itself.
 *
 * IT IS TESTED, WHICH IS THE PART THAT USUALLY ISN'T
 * --------------------------------------------------
 * `ui-class-tokens.test.js` is a `RuleTester` suite, not a scratch file. A rule
 * whose checks are only ever validated by hand is a rule that inverts a
 * condition and nothing goes red.
 */

const JSX_CLASS_ATTRS = new Set(["className", "class"]);

/**
 * Which module's `cn` counts. Resolved by module path rather than by bare name
 * so a local `cn` in some unrelated file cannot widen the scope by accident.
 */
const UI_MODULE_PATH = /(^|\/)lib\/ui$/;

/**
 * The Tailwind property namespaces whose utilities change how the element
 * PAINTS. A bare `focus:` on one of these is `bareFocus`; a bare `focus:` on
 * anything else — `z`, `order`, `scroll-mt`, `cursor`, `pointer-events`,
 * `absolute`, layout spacing — is a legitimate class.
 *
 * `not-sr-only` and `absolute` are the two utilities the hand-written skip
 * link exists to avoid, and they are deliberately NOT here. That bug is an
 * ordering trap between three rules that all set `position`; it has nothing to
 * do with the pseudo-class, and pretending otherwise would have the rule
 * claiming a correctness it does not have.
 */
const FOCUS_PAINT_NAMESPACES = [
  // The indicator itself.
  "ring",
  "outline",
  "shadow",
  "drop-shadow",
  "border",
  "divide",
  // Everything else that changes what the user sees.
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

/**
 * Namespace match on a BOUNDARY, not a bare prefix. Without it `to` would
 * swallow `touch-…` and `from` would swallow `form-…`; with it, only the exact
 * name or `name-…` matches.
 */
const isPaintingUtility = (utility) =>
  FOCUS_PAINT_NAMESPACES.some(
    (ns) => utility === ns || utility.startsWith(`${ns}-`),
  );

/**
 * @param {string} token one whitespace-separated class
 * @returns {boolean}
 */
const isBareFocus = (token) => {
  if (!token.startsWith("focus:")) return false;
  return isPaintingUtility(token.slice("focus:".length));
};

/** The three tokens that make up `FOCUS_RING` in `lib/ui.ts`. */
const isHouseFocusRing = (token) =>
  token === "focus-visible:outline-none" ||
  token === "focus-visible:ring-2" ||
  token === "focus-visible:ring-focus-ring";

/** `#[rgb]` / `#rrggbb` / `#rrggbbaa`, loose enough for authored shorthand. */
const isRawHex = (token) => /#[0-9a-fA-F]{3,8}\b/.test(token);

/**
 * The input-chrome check needs more than one token to be safe: `bg-slate-800`,
 * `rounded-lg` and `px-3` are each used by cards, panels and buttons, so
 * banning any of them alone would ban the design system. What identifies a
 * hand-rolled INPUT_BASE is the COMBINATION — the muted placeholder AND the
 * raised surface AND the field radius, together, in one class list. All three
 * must be present. One class list is one element, so they must come from the
 * same value; two separate elements each carrying a subset are not the drift.
 */
const INPUT_CHROME_TOKENS = ["placeholder-slate-500", "bg-slate-800", "rounded-lg"];
const looksLikeInputChrome = (tokens) =>
  INPUT_CHROME_TOKENS.every((t) => tokens.includes(t));

/**
 * `BTN_BASE` check. Same reasoning as the input chrome: `btn-motion` and
 * `active:scale-[0.98]` are a PAIR, and ten call sites in this tree carry
 * exactly that pair without the rest of the base.
 *
 * THOSE TEN ARE NOT TEN OF THE SAME THING, and the difference is the whole
 * story of this check:
 *
 *  - FOUR are chips and pills — `AlertsPage.tsx:161` and `:643`,
 *    `TransactionTable.tsx:89`, `TransactionsPage.tsx:137`. They are not
 *    buttons and must not be made into them. The harm of forcing the base on a
 *    chip is smaller than it was first claimed to be, too: for a single short
 *    label, `inline-flex items-center justify-center gap-1.5` changes nothing
 *    that a reader can see, and only `font-medium` is a real visual delta —
 *    which `TransactionsPage.tsx:137` already carries.
 *  - SIX are real buttons that re-type most of `BTN_BASE` — `ConfirmDialog.tsx`
 *    `:201` and `:212`, `ErrorBoundary.tsx:118`, `TransactionDetail.tsx:178`,
 *    `TransactionsPage.tsx:379` and `:386`. They are the drift this check
 *    exists to catch, and they escape it, because each of them omits
 *    `touch-manipulation` — one token out of fourteen.
 *
 * So the discriminator is weak, and that is a measured property of it rather
 * than an accident: `touch-manipulation` is the only token that belongs to the
 * base alone, and a partial copy does not include the whole base.
 *
 * The check is KEPT anyway, because every alternative is worse. Dropping
 * `touch-manipulation` and firing on the PAIR would flag all ten sites the
 * moment the rule landed, which is ten suppressions and a rule nobody reads —
 * and a new chip would need one too. Tightening it to catch the six means six
 * more suppressions, or six call sites rewritten onto `<Button>` where no
 * `BTN_SIZES` entry fits (an icon-only `h-8 w-8`, a filled-neutral pagination
 * button) and no `BTN_VARIANTS` entry exists for two of them. Those are DESIGN
 * additions, already recorded as debt at their call sites; the fix for the six
 * is the missing primitives, not a wider net here.
 */
const BTN_BASE_TOKENS = ["btn-motion", "active:scale-[0.98]", "touch-manipulation"];
const looksLikeBtnBase = (tokens) =>
  BTN_BASE_TOKENS.every((t) => tokens.includes(t));

/**
 * @typedef {{ id: string, scope: "token" | "value", message: string,
 *             test: (tokens: string[], token: string) => boolean }} Check
 */

/** @type {Check[]} All five checks; all of them apply at a class position. */
const CHECKS = [
  {
    id: "bareFocus",
    scope: "token",
    // Reported per value so one class list draws one complaint, but tested
    // per token so the test can name a specific utility.
    test: (_tokens, token) => isBareFocus(token),
    message:
      "Bare `focus:` paints on mouse click as well as keyboard. Import FOCUS_RING from src/lib/ui.ts — it is `focus-visible:`-prefixed for exactly this reason.",
  },
  {
    id: "rawFocusRing",
    scope: "token",
    test: (_tokens, token) => isHouseFocusRing(token),
    message:
      "That token belongs to FOCUS_RING. Import FOCUS_RING from src/lib/ui.ts instead of re-typing the ring, so the focus treatment cannot drift from the constant.",
  },
  {
    id: "rawInputChrome",
    scope: "value",
    test: (tokens) => looksLikeInputChrome(tokens),
    message:
      "placeholder-slate-500 + bg-slate-800 + rounded-lg in one class list is INPUT_BASE re-typed. Render an <Input> (src/components/Input.tsx) or compose cn(INPUT_BASE, …).",
  },
  {
    id: "rawBtnBase",
    scope: "value",
    test: (tokens) => looksLikeBtnBase(tokens),
    message:
      "btn-motion + active:scale-[0.98] + touch-manipulation is BTN_BASE re-typed. Render a <Button> (src/components/Button.tsx) or compose cn(BTN_BASE, …).",
  },
  {
    id: "rawHex",
    scope: "token",
    test: (_tokens, token) => isRawHex(token),
    message:
      "Raw hex in a class list. Add a token to the @theme block in src/index.css and use the utility — DESIGN.md sanctions hex in index.css, lib/chart-theme.ts, index.html and favicon.svg only.",
  },
];

/** @type {import("eslint").Rule.RuleModule} */
const rule = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Forbid hand-rolled copies of the class strings owned by src/lib/ui.ts.",
      recommended: true,
    },
    schema: [],
    messages: {
      bareFocus: "{{message}}",
      rawFocusRing: "{{message}}",
      rawInputChrome: "{{message}}",
      rawBtnBase: "{{message}}",
      rawHex: "{{message}}",
    },
  },
  create(context) {
    /** Local names bound to `cn` itself, and to a namespace holding it. */
    const cnBindings = new Set();
    const uiNamespaceBindings = new Set();

    /**
     * Every string a node contributes, in source order.
     *
     * Walks CHILD NODES only (anything carrying a `type`), never every object
     * key, so it cannot wander into `loc`/`range` and cannot re-visit a node it
     * has already descended past. `parent` is skipped for the same reason and
     * more forcefully: it points back UP, so following it is not a slow walk,
     * it is an infinite one.
     *
     * @param {import("estree").Node} node
     * @returns {string[]}
     */
    function stringPartsOf(node) {
      const out = [];
      const visit = (n) => {
        if (!n || typeof n !== "object" || typeof n.type !== "string") return;
        if (n.type === "Literal" && typeof n.value === "string") out.push(n.value);
        // Template quasis only. The expressions between them are their own
        // nodes (a nested literal, or a `cn()` call) and their tokens are
        // checked on their own terms.
        if (n.type === "TemplateElement" && n.value?.cooked) out.push(n.value.cooked);
        for (const [key, value] of Object.entries(n)) {
          if (key === "parent") continue;
          if (Array.isArray(value)) value.forEach(visit);
          else if (value && typeof value === "object") visit(value);
        }
      };
      visit(node);
      return out;
    }

    /**
     * Report at most once per check per VALUE. A class list is one value, so a
     * template literal spanning three lines — or a class list with three
     * offending tokens — draws one complaint, not three.
     *
     * @param {import("estree").Node} node
     */
    function check(node) {
      const tokens = stringPartsOf(node)
        .join(" ")
        .split(/\s+/)
        .filter(Boolean);
      if (tokens.length === 0) return;
      for (const c of CHECKS) {
        if (c.scope === "value") {
          if (c.test(tokens, "")) context.report({ node, messageId: c.id, data: { message: c.message } });
          continue;
        }
        if (tokens.some((token) => c.test(tokens, token))) {
          context.report({ node, messageId: c.id, data: { message: c.message } });
        }
      }
    }

    /**
     * A value is checked as ONE unit, so the literals and template quasis
     * nested inside it must not be re-checked on their own: that would
     * double-report, and would split a template's class list across its quasis
     * so a composition check could no longer see the whole list.
     */
    const claimed = new WeakSet();
    function claimSubtree(root) {
      const visit = (n) => {
        if (!n || typeof n !== "object" || typeof n.type !== "string") return;
        claimed.add(n);
        for (const [key, value] of Object.entries(n)) {
          // `parent` points back up the tree; following it never terminates.
          if (key === "parent") continue;
          if (Array.isArray(value)) value.forEach(visit);
          else if (value && typeof value === "object") visit(value);
        }
      };
      visit(root);
    }

    /**
     * Resolve `cn` through its import. `Program` is entered before any of its
     * children, so a call that appears textually before an `import` is still
     * resolved — ESM hoists the binding either way.
     * @param {import("estree").Program} node
     */
    function collectCnBindings(node) {
      for (const statement of node.body) {
        if (statement.type !== "ImportDeclaration") continue;
        if (typeof statement.source.value !== "string") continue;
        if (!UI_MODULE_PATH.test(statement.source.value)) continue;
        for (const specifier of statement.specifiers) {
          if (specifier.type === "ImportNamespaceSpecifier") {
            uiNamespaceBindings.add(specifier.local.name);
          } else if (specifier.type === "ImportSpecifier") {
            if (specifier.imported.name === "cn") cnBindings.add(specifier.local.name);
          }
        }
      }
    }

    /** @param {import("estree").Node} callee */
    function isCnCall(callee) {
      if (callee.type === "Identifier") return cnBindings.has(callee.name);
      if (
        callee.type === "MemberExpression" &&
        !callee.computed &&
        callee.object.type === "Identifier" &&
        callee.property.type === "Identifier" &&
        callee.property.name === "cn"
      ) {
        return uiNamespaceBindings.has(callee.object.name);
      }
      return false;
    }

    return {
      Program(node) {
        collectCnBindings(node);
      },
      JSXAttribute(node) {
        const name = node.name?.type === "JSXIdentifier" ? node.name.name : null;
        if (!name || !JSX_CLASS_ATTRS.has(name)) return;
        if (!node.value) return;
        claimSubtree(node.value);
        check(node.value);
      },
      // Module scope included: a top-level `cn("btn-motion …")` is where a
      // shared helper gets written, which is the drift this rule exists for.
      CallExpression(node) {
        if (!isCnCall(node.callee)) return;
        if (claimed.has(node)) return;
        claimSubtree(node);
        check(node);
      },
    };
  },
};

export default {
  meta: { name: "eslint-plugin-ui" },
  rules: { "no-raw-class-tokens": rule },
};
