import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useCountUp } from "../hooks/useCountUp";

/**
 * A25: `useCountUp` restarted from 0 on every `target` change. The dashboard
 * refetches every 30 s, so the KPIs re-bobbled from zero on a loop, forever.
 * On a fraud dashboard a number sweeping up from nothing reads as "activity
 * spiking" when nothing happened.
 */

function mockMatchMedia(reduced: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: reduced && query.includes("reduce"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

/** Drives requestAnimationFrame with a controllable clock. */
function installRaf() {
  let now = 0;
  let frames: Array<(t: number) => void> = [];
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
    frames.push(cb as (t: number) => void);
    return frames.length;
  });
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});

  /** Delivers one frame at the current clock. */
  function step(ms = 16) {
    now += ms;
    const due = frames;
    frames = [];
    for (const cb of due) cb(now);
  }

  return {
    /** Advances by `ms` in frame-sized increments, as a real clock would. */
    advance(ms: number) {
      let remaining = ms;
      while (remaining > 0) {
        const chunk = Math.min(16, remaining);
        step(chunk);
        remaining -= chunk;
      }
    },
    /** Runs frames until the animation schedules no more. */
    runToEnd(maxFrames = 200) {
      let n = 0;
      while (frames.length > 0 && n < maxFrames) {
        step(16);
        n += 1;
      }
    },
    pending: () => frames.length,
  };
}

describe("useCountUp — A25 no re-bobble on refetch", () => {
  beforeEach(() => {
    mockMatchMedia(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("counts up from zero on the first mount", async () => {
    const raf = installRaf();
    const { result } = renderHook(() => useCountUp(100, { duration: 100 }));

    expect(result.current).toBe(0);
    act(() => raf.advance(50));
    expect(result.current).toBeGreaterThan(0);
    expect(result.current).toBeLessThan(100);

    act(() => raf.runToEnd());
    await waitFor(() => expect(result.current).toBe(100));
  });

  it("does not rewind to zero when the refetch returns the same number", async () => {
    const raf = installRaf();
    const { result, rerender } = renderHook(() => useCountUp(100, { duration: 100 }));

    act(() => raf.runToEnd());
    await waitFor(() => expect(result.current).toBe(100));

    // A 30 s refetch returning the same value must be a no-op.
    rerender();
    act(() => raf.advance(50));

    expect(result.current).toBe(100);
    expect(raf.pending()).toBe(0);
  });

  it("moves from the current value when the number changes slightly", async () => {
    const raf = installRaf();
    let target = 100;
    const { result, rerender } = renderHook(() => useCountUp(target, { duration: 100 }));

    act(() => raf.runToEnd());
    await waitFor(() => expect(result.current).toBe(100));

    // The next refetch reports 103.
    target = 103;
    rerender();

    // Critically: it must not drop to 0 or below the previous value.
    act(() => raf.advance(10));
    expect(result.current).toBeGreaterThanOrEqual(100);

    act(() => raf.runToEnd());
    await waitFor(() => expect(result.current).toBe(103));
  });

  it("interpolates within bounds across a whole refresh cycle, up or down", async () => {
    const raf = installRaf();
    // A real dashboard reading rises and falls. The property to protect is not
    // monotonicity — a genuinely lower number must render lower — it is that the
    // display never rewinds to zero, which is what re-bobbling looked like.
    const targets = [100, 104, 103, 107, 105, 105, 110];
    let index = 0;
    const { result, rerender } = renderHook(() =>
      useCountUp(targets[index], { duration: 80 }),
    );

    act(() => raf.runToEnd());
    await waitFor(() => expect(result.current).toBe(100));

    for (index = 1; index < targets.length; index += 1) {
      const from = targets[index - 1];
      const to = targets[index];
      const low = Math.min(from, to);

      rerender();

      // Mid-flight: between the two endpoints, never at or near zero.
      act(() => raf.advance(40));
      expect(result.current).toBeGreaterThanOrEqual(low);
      expect(result.current).toBeLessThanOrEqual(Math.max(from, to));

      act(() => raf.runToEnd());
      await waitFor(() => expect(result.current).toBe(to));
    }
  });

  it("drops straight to a lower target instead of animating up through zero", async () => {
    const raf = installRaf();
    let target = 500;
    const { result, rerender } = renderHook(() => useCountUp(target, { duration: 100 }));

    act(() => raf.runToEnd());
    await waitFor(() => expect(result.current).toBe(500));

    target = 480;
    rerender();

    act(() => raf.advance(50));
    // The old behaviour animated `target * ease(progress)` from 0, so this is
    // where the re-bobble was visible: a crash from 500 down towards 0.
    expect(result.current).toBeGreaterThan(480);

    act(() => raf.runToEnd());
    await waitFor(() => expect(result.current).toBe(480));
  });

  it("jumps straight to the target with reduced motion", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useCountUp(42, { duration: 100 }));
    expect(result.current).toBe(42);
  });
});
