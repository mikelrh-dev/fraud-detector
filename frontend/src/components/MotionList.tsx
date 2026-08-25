import {
  Children,
  cloneElement,
  isValidElement,
} from "react";
import type {
  CSSProperties,
  ComponentPropsWithoutRef,
  ReactElement,
  ReactNode,
} from "react";

/**
 * Maximum stagger index. With a 60ms per-step delay this caps the accumulated
 * animation-delay at ~480ms no matter how many children the list renders —
 * long lists must never feel like a slow curtain.
 */
export const MOTION_STAGGER_MAX_INDEX = 8;

export const MOTION_STAGGER_STEP_MS = 60;

/** Clamp a child index into the stagger window (0..MOTION_STAGGER_MAX_INDEX). */
export function clampStaggerIndex(index: number): number {
  return Math.min(Math.max(index, 0), MOTION_STAGGER_MAX_INDEX);
}

type StaggerStyle = CSSProperties & { "--i"?: number };

interface MotionListProps extends ComponentPropsWithoutRef<"div"> {
  children: ReactNode;
}

/**
 * Container for the `.motion-stagger` reveal pattern (DESIGN.md — Motion).
 *
 * Renders its children inside a `motion-stagger` div and stamps each element
 * child with an inline `--i` custom property (clamped via
 * {@link clampStaggerIndex}) that drives the CSS
 * `animation-delay: calc(var(--i) * 60ms)`. Non-element children (strings,
 * numbers, null) pass through untouched since they cannot carry inline styles.
 *
 * Intended for card lists and chip groups on first contentful render — NOT
 * for desktop data tables (re-animating rows on pagination is churn; see
 * DESIGN.md non-goals).
 */
export function MotionList({ children, className, ...rest }: MotionListProps) {
  const items = Children.toArray(children);

  return (
    <div className={className ? `motion-stagger ${className}` : "motion-stagger"} {...rest}>
      {items.map((child, index) => {
        if (!isValidElement(child)) return child;
        const childProps = child.props as { style?: CSSProperties };
        return cloneElement(child as ReactElement<{ style?: CSSProperties }>, {
          style: {
            ...childProps.style,
            "--i": clampStaggerIndex(index),
          } as StaggerStyle,
        });
      })}
    </div>
  );
}
