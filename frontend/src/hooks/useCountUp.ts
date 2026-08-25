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
 * Count a value up from 0 to `target` using requestAnimationFrame.
 * Respects prefers-reduced-motion by jumping straight to the target.
 * The animation restarts whenever `target` changes and always lands on it.
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

  useEffect(() => {
    if (prefersReducedMotion()) {
      setValue(target);
      return undefined;
    }

    let startTime: number | null = null;
    const step = (now: number) => {
      // Anchor to the first rAF timestamp so progress is frame-clock based.
      if (startTime === null) startTime = now;
      const progress = Math.min((now - startTime) / duration, 1);
      setValue(target * easeOutCubic(progress));
      frameRef.current =
        progress < 1 ? requestAnimationFrame(step) : null;
    };

    frameRef.current = requestAnimationFrame(step);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [target, duration]);

  return value;
}
