import type { ReactNode } from "react";

export interface EmptyStateProps {
  /** Icon slot — caller supplies inline SVG line-art (~64px). */
  icon?: ReactNode;
  /** Primary message, text-slate-300 per DESIGN.md. */
  title: string;
  /** One-line supporting hint, text-slate-500. */
  hint?: string;
  /** Optional CTA (link or button) rendered below the hint. */
  action?: ReactNode;
  /** Compact padding for embedding inside table cells. */
  compact?: boolean;
}

/**
 * Composed empty state shared by mobile and desktop views (single component
 * renders in both). Icon slot keeps this presentational and reusable:
 * pages pass their own line-art glyph, title, one-line hint and CTA.
 */
export function EmptyState({
  icon,
  title,
  hint,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center px-6 text-center ${
        compact ? "py-6" : "py-12"
      }`}
    >
      {icon && (
        <div aria-hidden="true" className="mb-4 text-slate-600">
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-slate-300">{title}</p>
      {hint && <p className="mt-1 max-w-xs text-xs text-slate-500">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** Minimal receipt line-art for transaction empty states. */
export function ReceiptLineArt() {
  return (
    <svg
      width={64}
      height={64}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 3h14v18l-2.33-1.75L14.33 21 12 19.25 9.67 21l-2.34-1.75L5 21V3Z" />
      <path d="M9 8h6" />
      <path d="M9 12h6" />
      <path d="M9 16h3" />
    </svg>
  );
}

/** Minimal alert-bell line-art for alert empty states. */
export function BellLineArt() {
  return (
    <svg
      width={64}
      height={64}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z" />
      <path d="M10.3 20a1.9 1.9 0 0 0 3.4 0" />
    </svg>
  );
}
