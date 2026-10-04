import { cloneElement, isValidElement } from "react";
import type { ReactElement } from "react";

/**
 * recharts mock: give `ResponsiveContainer` a size, because jsdom cannot.
 *
 * WHY IT IS NEEDED
 * `ResponsiveContainer` measures its own box before drawing. jsdom reports no
 * layout, so it renders an EMPTY div — zero `<svg>` in the document — and every
 * assertion about a drawn bar or a visible dot fails as "unable to find", which
 * reads like a missing element and is actually a missing browser API. Measured
 * before this helper existed: an unmocked `ScoreTrendChart` render produced
 * `svg` count 0.
 *
 * WHY IT LIVES HERE AND NOT IN setup.ts
 * Same reasoning as the `ResizeObserver` stub that `tests/setup.ts` holds: shared
 * infrastructure belongs in one place rather than in whichever suite needed it
 * first. It is not global because only the chart suites need it, and a global
 * mock would silently make every suite believe it exercises chart code paths.
 *
 * WHAT IT DOES NOT DO
 * It does not change production. The component still renders
 * `ResponsiveContainer` and still gets its dimensions from the container at
 * runtime; only the measurement is substituted, and only under test. It also
 * does not disable the entry animation — recharts grows bars and areas in from
 * zero height, and `Rectangle` renders nothing at all while the height is 0, so
 * a geometry assertion must wait for the animation to settle. Assertions here use
 * `waitFor` on an exact expected count rather than `> 0`, because a
 * half-finished animation satisfies the weaker condition.
 */
export function sizedResponsiveContainer(
  children: ReactElement,
): ReactElement {
  return isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        width: 800,
        height: 200,
      })
    : children;
}
