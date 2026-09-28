import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./mocks/server";

/**
 * `ResizeObserver` stub, shared.
 *
 * jsdom has no `ResizeObserver`, and recharts measures its container before
 * drawing. Without this, rendering `/dashboard` throws into the route
 * ErrorBoundary AFTER the page's own assertions have already passed -- so the
 * test reported green while the route had actually failed. A test that tolerates
 * a render error is not a clean test.
 *
 * It lived in `DashboardPage.test.tsx`, where the only test that exercised the
 * dashboard also happened to define it. A second test file rendering the same
 * page got the throw and nothing to catch it, which is exactly how the hole
 * stayed invisible. Infrastructure belongs in the setup, not in whichever test
 * first needed it.
 */
class StubResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= StubResizeObserver as unknown as typeof ResizeObserver;

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
