import type { ReactNode } from "react";

export interface ErrorStateProps {
  /** Primary message, text-slate-300. */
  title?: string;
  /** One-line supporting hint, text-slate-500. */
  hint?: string;
  /** Icon slot — caller supplies inline SVG line-art (~64px). */
  icon?: ReactNode;
  /** Retry callback; when omitted the action button is not rendered. */
  onRetry?: () => void;
  retryLabel?: string;
  /** Compact padding for embedding inside a card or table cell. */
  compact?: boolean;
}

/**
 * Shared failure state.
 *
 * Exists because a failed query used to be indistinguishable from an empty
 * one: `data?.total || 0` rendered "0 alertas" and the dashboard drew a flat
 * line at zero. On a fraud dashboard that is the most dangerous possible
 * misread — "no risk detected" when the truth is "we could not ask".
 *
 * Marked `role="alert"` so the failure is announced, not just coloured.
 */
export function ErrorState({
  title = "No se pudieron cargar los datos",
  hint = "Revisá tu conexión o intentá de nuevo en unos segundos.",
  icon,
  onRetry,
  retryLabel = "Reintentar",
  compact = false,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      data-testid="error-state"
      className={`flex flex-col items-center justify-center px-6 text-center ${
        compact ? "py-6" : "py-12"
      }`}
    >
      {icon && (
        <div aria-hidden="true" className="mb-4 text-risk-critical">
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-slate-300">{title}</p>
      <p className="mt-1 max-w-xs text-xs text-slate-500">{hint}</p>
      {onRetry && (
        <div className="mt-4">
          <button
            type="button"
            onClick={onRetry}
            className="btn-motion active:scale-[0.98] rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            {retryLabel}
          </button>
        </div>
      )}
    </div>
  );
}

/** Minimal warning line-art for failure states. */
export function AlertLineArt() {
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
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}
