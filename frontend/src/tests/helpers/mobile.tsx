import { expect } from "vitest";

/**
 * Assert that an element's className contains all of the given class names.
 */
export function expectMobileClasses(el: HTMLElement, classes: string[]) {
  for (const cls of classes) {
    expect(el.className).toContain(cls);
  }
}

/**
 * Assert that an element has a specific class (exact match in space-split list).
 */
export function expectHasClass(el: HTMLElement, className: string) {
  expect(el.className.split(/\s+/)).toContain(className);
}
