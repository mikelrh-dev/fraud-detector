import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useCountUp } from "../hooks/useCountUp";

/**
 * Controllable requestAnimationFrame fake: frames only advance when the test
 * calls flushFrames, so easing output is deterministic.
 */
type FrameCb = (time: number) => void;
const scheduled = new Map<number, FrameCb>();
let nextId = 1;
let clock = 0;

function installFakeRaf() {
  vi.stubGlobal("requestAnimationFrame", (cb: FrameCb) => {
    const id = nextId++;
    scheduled.set(id, cb);
    return id;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => {
    scheduled.delete(id);
  });
}

/** Advance the fake frame clock inside act() so state updates flush. */
function flushFrames(stepMs: number) {
  act(() => {
    clock += stepMs;
    const pending = [...scheduled.values()];
    scheduled.clear();
    for (const cb of pending) cb(clock);
  });
}

function mockMatchMedia(matches: boolean) {
  vi.spyOn(window, "matchMedia").mockReturnValue({
    matches,
  } as MediaQueryList);
}

describe("useCountUp", () => {
  beforeEach(() => {
    scheduled.clear();
    nextId = 1;
    clock = 0;
    installFakeRaf();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("jumps straight to the target when prefers-reduced-motion is set", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useCountUp(42, { duration: 800 }));
    expect(result.current).toBe(42);
    // No animation frames were ever scheduled
    expect(scheduled.size).toBe(0);
  });

  it("animates from 0 toward the target across frames (eased, monotonic)", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useCountUp(100, { duration: 800 }));

    expect(result.current).toBe(0);

    // First fired frame anchors the animation start (progress 0 by design)
    flushFrames(0);
    let previous = result.current;
    for (let i = 0; i < 10; i++) {
      flushFrames(80);
      expect(result.current).toBeGreaterThanOrEqual(previous);
      previous = result.current;
    }

    // After >= duration of frames the value lands exactly on target
    expect(result.current).toBe(100);
    // Animation is done — nothing else scheduled
    expect(scheduled.size).toBe(0);
  });

  it("uses the default 800ms duration when no options are given", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useCountUp(100));

    // Halfway through an 800ms run (~400ms elapsed): eased cubic leaves us
    // well past the linear midpoint.
    flushFrames(0);
    flushFrames(200);
    flushFrames(200);
    const halfwayValue = result.current;
    expect(halfwayValue).toBeGreaterThan(50);
    expect(halfwayValue).toBeLessThan(100);

    flushFrames(400);
    expect(result.current).toBe(100);
  });

  it("cancels the pending frame on unmount", () => {
    mockMatchMedia(false);
    const { unmount } = renderHook(() => useCountUp(500));

    flushFrames(16); // first frame ran, second one is scheduled
    expect(scheduled.size).toBe(1);

    unmount();
    expect(scheduled.size).toBe(0);
  });
});
