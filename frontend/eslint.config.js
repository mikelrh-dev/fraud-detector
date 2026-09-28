import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";
import ui from "./eslint-rules/ui-class-tokens.js";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      ui,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],

      /**
       * Anti-rot. `src/lib/ui.ts` holds the shared class strings; without a
       * rule nothing stops the next component from re-typing them, because
       * copying is cheaper than importing and Tailwind v4 emits no error for
       * the result. See eslint-rules/ui-class-tokens.js for the two scopes and
       * why each check is a combination rather than a single token.
       *
       * The module that OWNS the patterns is exempt. Every other file is not:
       * the two focus-ring divergences that predate this rule each carry an
       * inline, rule-specific `eslint-disable` with the reason next to the
       * code, and `reportUnusedDisableDirectives` is on, so resolving either
       * divergence without deleting its suppression fails the lint run.
       */
      "ui/no-raw-class-tokens": "error",
    },
  },
  {
    files: ["src/lib/ui.ts"],
    rules: { "ui/no-raw-class-tokens": "off" },
  },
  {
    /**
     * Tests are exempt, and deliberately so.
     *
     * A test that pins a class name has to write it as a LITERAL. Comparing
     * against the imported constant would be a tautology — mutate the constant
     * and both sides of the assertion move, so the test still passes while the
     * design changes under it. `src/lib/ui.test.ts` and the page tests below are
     * the layer that holds the tokens honest, and the only way to write that
     * layer is to name the classes out loud. Linting them against the rule they
     * exist to police would force exactly the tautology this exemption avoids.
     */
    files: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "src/test-utils/**"],
    rules: { "ui/no-raw-class-tokens": "off" },
  },
  {
    files: ["**/*.{ts,tsx}"],
    linterOptions: {
      // A suppression that no longer suppresses anything is rot of the same
      // kind this rule exists to stop. Default in ESLint 9, set explicitly so
      // the intent survives a version bump.
      reportUnusedDisableDirectives: "warn",
    },
  },
);
