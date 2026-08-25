import { useLocation } from "react-router-dom";
import type { ReactNode } from "react";

/**
 * Route-level entrance: wraps authenticated page content in a div keyed by
 * `location.pathname`. Changing routes swaps the key, remounts the wrapper
 * and replays the one-shot `animate-fade-slide-up` entrance exactly once per
 * navigation. In-page state changes never re-trigger it because the key only
 * moves on pathname.
 *
 * Reduced-motion users get the final state immediately via the global guard
 * in index.css (`animation: none` under prefers-reduced-motion).
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const location = useLocation();

  return (
    <div
      key={location.pathname}
      data-testid="page-transition"
      className="animate-fade-slide-up"
    >
      {children}
    </div>
  );
}
