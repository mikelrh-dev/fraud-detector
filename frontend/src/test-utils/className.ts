import { expect } from "vitest";

/**
 * Assert that an element carries every class in a fragment.
 *
 * WHY TOKEN-WISE AND NOT A SUBSTRING CHECK: the contract these primitives have
 * is that every class in a fragment is present. A `className` containing the
 * fragment as a substring would pass a substring check while a class was
 * missing, and would fail on a class that `className` legitimately interleaves
 * with others. Token comparison is the only check that matches the contract.
 *
 * Lives in `src/test-utils/` rather than `src/tests/helpers/` on purpose:
 * `tsconfig.json` excludes `src/tests`, so a helper placed there would never be
 * type-checked. This file is inside the include set, so a signature mistake in
 * it fails the build.
 */
export function expectCarries(el: Element, fragment: string) {
  for (const cls of fragment.split(" ").filter(Boolean)) {
    expect(el.classList.contains(cls), `missing class ${cls}`).toBe(true);
  }
}
