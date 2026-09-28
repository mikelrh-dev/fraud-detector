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
 * HOW IT IS SCOPED
 * ----------------
 * Two scopes, because the checks mean different things in different places:
 *
 *  1. `className` values (JSX attribute, template literal, or a string handed
 *     to `cn(...)` inside one). Every check applies: a call site is where
 *     composition is supposed to happen, so a hand-rolled class list there is
 *     the drift.
 *  2. Every other string literal in the file. Only the two focus checks apply.
 *     A focus ring is a correctness contract — wrong pseudo-class means it
 *     fires on mouse click, wrong colour token means the keyboard indicator
 *     diverges from every other control — and that contract has to hold
 *     wherever a class string is WRITTEN, including in a module-level constant
 *     that call sites import. The composition checks (input chrome, raw hex)
 *     are meaningless away from a call site, and hex is legitimately allowed
 *     in `lib/chart-theme.ts` and `index.css` per DESIGN.md.
 *
 * Comments are invisible to this rule by construction — it reads the AST, not
 * the raw text. That is the opposite of Tailwind's scanner, which DOES read
 * comments; see the note in `lib/ui.ts` about a comment that manufactured the
 * evidence against itself.
 */

const JSX_CLASS_ATTRS = new Set(["className", "class"]);

/**
 * @param {string} token one whitespace-separated class
 * @returns {boolean}
 */
const isBareFocus = (token) => token.startsWith("focus:");

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
 * `active:scale-[0.98]` are a PAIR, and ten chip/pill/toggle call sites in this
 * tree legitimately want exactly that pair without the rest of the base — a
 * filter chip is not a button, and forcing `inline-flex` + `font-medium` onto
 * it would be a visual change dressed up as lint compliance.
 *
 * What separates a re-typed BTN_BASE from a chip is `touch-manipulation`,
 * which exists nowhere else in the product: it is the base's tap behaviour and
 * nothing else needed it. A hand-rolled button that carries it is
 * reconstructing the base and should import it.
 */
const BTN_BASE_TOKENS = ["btn-motion", "active:scale-[0.98]", "touch-manipulation"];
const looksLikeBtnBase = (tokens) => BTN_BASE_TOKENS.every((t) => tokens.includes(t));

/**
 * @typedef {{ id: string, message: string, test: (tokens: string[], token: string) => boolean }} Check
 */

/** @type {Check[]} Checks that apply to every string literal in a file. */
const FOCUS_CHECKS = [
  {
    id: "bareFocus",
    // Reported per token so the message can name the offending class.
    test: (_tokens, token) => isBareFocus(token),
    message:
      "Bare `focus:` paints on mouse click as well as keyboard. Import FOCUS_RING from src/lib/ui.ts — it is `focus-visible:`-prefixed for exactly this reason.",
  },
  {
    id: "rawFocusRing",
    test: (_tokens, token) => isHouseFocusRing(token),
    message:
      "That token belongs to FOCUS_RING. Import FOCUS_RING from src/lib/ui.ts instead of re-typing the ring, so the focus treatment cannot drift from the constant.",
  },
];

/** @type {Check[]} Extra checks that apply to `className` values only. */
const COMPOSITION_CHECKS = [
  {
    id: "rawInputChrome",
    test: (tokens) => looksLikeInputChrome(tokens),
    message:
      "placeholder-slate-500 + bg-slate-800 + rounded-lg in one class list is INPUT_BASE re-typed. Render an <Input> (src/components/Input.tsx) or compose cn(INPUT_BASE, …).",
  },
  {
    id: "rawBtnBase",
    test: (tokens) => looksLikeBtnBase(tokens),
    message:
      "btn-motion + active:scale-[0.98] + touch-manipulation is BTN_BASE re-typed. Render a <Button> (src/components/Button.tsx) or compose cn(BTN_BASE, …).",
  },
  {
    id: "rawHex",
    test: (_tokens, token) => isRawHex(token),
    message:
      "Raw hex in a className. Add a token to the @theme block in src/index.css and use the utility — DESIGN.md sanctions hex in index.css, lib/chart-theme.ts, index.html and favicon.svg only.",
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
    /**
     * Collect every string a node contributes, in source order.
     * @param {import("estree").Node} node
     * @returns {string[]}
     */
    function stringPartsOf(node) {
      const out = [];
      const visit = (n) => {
        if (!n || typeof n !== "object") return;
        if (Array.isArray(n)) {
          n.forEach(visit);
          return;
        }
        if (n.type === "Literal" && typeof n.value === "string") out.push(n.value);
        // Template quasis only. The expressions between them are already
        // visited as their own nodes (a nested literal, or a `cn()` call), and
        // their tokens are checked on their own terms.
        if (n.type === "TemplateElement" && n.value?.cooked) out.push(n.value.cooked);
        if (n.type === "TemplateLiteral") n.quasis.forEach(visit);
        for (const [key, value] of Object.entries(n)) {
          if (key === "parent") continue;
          if (key === "quasis" || key === "expressions") {
            if (Array.isArray(value)) value.forEach(visit);
            continue;
          }
          if (value && typeof value === "object") visit(value);
        }
      };
      visit(node);
      return out;
    }

    /** @param {import("estree").Node} node @param {Check[]} checks */
    function check(node, checks) {
      const parts = stringPartsOf(node);
      if (parts.length === 0) return;
      // One class list per reported value: composition checks reason about a
      // single element's classes, so they must see them in one bucket. A
      // template literal spanning three lines is still one class list.
      const tokens = parts.join(" ").split(/\s+/).filter(Boolean);
      for (const c of checks) {
        if (c.id === "rawInputChrome" || c.id === "rawBtnBase") {
          if (c.test(tokens, "")) {
            context.report({ node, messageId: c.id, data: { message: c.message } });
          }
          continue;
        }
        for (const token of tokens) {
          if (c.test(tokens, token)) {
            context.report({ node, messageId: c.id, data: { message: c.message } });
            break;
          }
        }
      }
    }

    // A className is checked as one unit, so its nested literals and template
    // quasis must not be re-checked on their own — that would double-report
    // and would split a template's class list across its quasis.
    const claimed = new WeakSet();
    function claimSubtree(root) {
      const visit = (n) => {
        if (!n || typeof n !== "object" || typeof n.type !== "string") return;
        claimed.add(n);
        for (const [key, value] of Object.entries(n)) {
          if (key === "parent") continue;
          if (Array.isArray(value)) value.forEach(visit);
          else if (value && typeof value === "object") visit(value);
        }
      };
      visit(root);
    }

    return {
      JSXAttribute(node) {
        const name = node.name?.type === "JSXIdentifier" ? node.name.name : null;
        if (!name || !JSX_CLASS_ATTRS.has(name)) return;
        if (!node.value) return;
        claimSubtree(node.value);
        check(node.value, [...FOCUS_CHECKS, ...COMPOSITION_CHECKS]);
      },
      // Everything else: only the focus contract, which has to hold wherever a
      // class string is written — a module-level constant included.
      Literal(node) {
        if (typeof node.value !== "string") return;
        if (claimed.has(node)) return;
        check(node, FOCUS_CHECKS);
      },
      TemplateLiteral(node) {
        if (claimed.has(node)) return;
        if (node.parent?.type === "TaggedTemplateExpression") return;
        check(node, FOCUS_CHECKS);
      },
    };
  },
};

export default {
  meta: { name: "eslint-plugin-ui" },
  rules: { "no-raw-class-tokens": rule },
};
