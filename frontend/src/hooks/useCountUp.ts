import { useEffect, useRef, useState } from "react";

export interface UseCountUpOptions {
  /** Animation length in ms. Default 800. */
  duration?: number;
}

const DEFAULT_DURATION_MS = 800;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** easeOutCubic: fast start, gentle landing. */
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/**
 * Count a value up to `target` using requestAnimationFrame.
 *
 * A25: this used to restart from 0 on every `target` change. The dashboard
 * refetches every 30 s, so the KPIs re-bobbled from zero on a loop, forever.
 * On a fraud dashboard that is worse than static: a number sweeping up from
 * nothing reads as "activity spiking" when nothing happened.
 *
 * Now the first value animates from 0, and later changes interpolate from the
 * value currently on screen. A 30 s refetch that returns the same number is a
 * no-op, and one that returns a slightly different number moves gently instead
 * of rewinding.
 *
 * Respects prefers-reduced-motion by jumping straight to the target.
 */
export function useCountUp(
  target: number,
  options?: UseCountUpOptions,
): number {
  const duration = options?.duration ?? DEFAULT_DURATION_MS;
  const [value, setValue] = useState(() =>
    prefersReducedMotion() ? target : 0,
  );
  const frameRef = useRef<number | null>(null);
  // Where the current animation started from, so a mid-flight target change
  // continues from what is on screen rather than snapping to 0.
  const fromRef = useRef(0);
  const animatedOnceRef = useRef(false);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setValue(target);
      return undefined;
    }

    // First mount counts up from zero; after that, move from the current value.
    const from = animatedOnceRef.current ? value : 0;
    animatedOnceRef.current = true;
    fromRef.current = from;

    // Nothing to animate: the refetch returned the same number.
    if (from === target) {
      setValue(target);
      return undefined;
    }

    let startTime: number | null = null;
    const step = (now: number) => {
      // Anchor to the first rAF timestamp so progress is frame-clock based.
      if (startTime === null) startTime = now;
      const progress = Math.min((now - startTime) / duration, 1);
      setValue(from + (target - from) * easeOutCubic(progress));
      frameRef.current =
        progress < 1 ? requestAnimationFrame(step) : null;
    };

    frameRef.current = requestAnimationFrame(step);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
    // `value` is intentionally not a dependency: it is the animation's own
    // output, and depending on it would restart the animation on every frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, duration]);

  return value;
}
