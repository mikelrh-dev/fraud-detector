import { vi } from "vitest";
import type { AuthState } from "../store/authStore";

/**
 * The one fake `AuthState` the suite builds.
 *
 * WHY IT IS EXHAUSTIVE ON PURPOSE. `setTokens` was added to `AuthState` in
 * ca3c2bf and twenty hand-written fakes across eighteen test files were never
 * updated. The omission went unnoticed because `tsconfig.json` excluded
 * `src/tests` from type-checking, so no test had ever been checked against the
 * real interface — and ca3c2bf's "tsc clean" was true only because of that
 * exclude. Removing the exclude (86bfd33) is what surfaced all twenty at once
 * and proved they were twenty copies of one thing.
 *
 * The fragility was never those twenty. It was that the next field added to
 * `AuthState` would have to be found and edited by hand in twenty places, and
 * that a helper written against a hand-maintained subset of the fields would
 * repeat the same omission one level down: still compiling, still green, still
 * quietly wrong. So the return type is the real `AuthState` and every field is
 * written out. Add a field to the interface and the compiler reports one
 * error, in this file, instead of fanning out across the suite.
 *
 * Overriding a single field is a spread at the call site, e.g.
 * `{ ...makeAuthState(), isAuthenticated: false }`. There is deliberately no
 * merged-defaults parameter: a helper that fills in what the caller left out
 * lets a test which means to leave a value alone receive a set one instead,
 * which neuters the test without ever failing it.
 *
 * No test asserts anything about what this returns. It is arrangement, not
 * subject — a test that checks a fixture is checking its own setup.
 *
 * Lives in `src/test-utils/` beside `className.ts`, which is the established
 * home for helpers shared across both test conventions, and is already
 * imported from co-located tests (`Button.test.tsx`) and from `src/tests`
 * (`CreateTransactionPage.test.tsx`) alike. Nothing outside a test imports this
 * directory, so the bundler cannot reach it, and there is no barrel that
 * re-exports it.
 */
export function makeAuthState(): AuthState {
  return {
    token: "mock-token",
    refreshToken: null,
    user: { id: "test-user-id", role: "analista" },
    isAuthenticated: true,
    login: vi.fn(),
    setTokens: vi.fn(),
    logout: vi.fn(),
  };
}
