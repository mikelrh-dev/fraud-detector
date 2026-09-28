import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { AlertLineArt, State } from "./State";
import { FOCUS_RING, cn } from "../lib/ui";

export interface ErrorBoundaryProps {
  children: ReactNode;
  /**
   * Renders the recovery UI. Receives a `reset` callback that clears the error
   * and remounts the subtree.
   */
  fallback?: (reset: () => void) => ReactNode;
  /** Side-effect hook for logging. Never render the error to the user. */
  onError?: (error: Error, info: ErrorInfo) => void;
  /**
   * When any of these change, the error is cleared automatically. Pass the
   * router pathname so navigating away from a broken page recovers without the
   * user having to press anything.
   */
  resetKeys?: unknown[];
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Catches render and lifecycle errors below it.
 *
 * WHY THIS EXISTS
 * There was no error boundary anywhere in `src/`. React's default behaviour is
 * to unmount the entire tree on a render error, so a single throw in any page
 * left a blank white screen with no way back: no navigation, no retry, no
 * message. For a fraud dashboard that is the worst failure mode, because the
 * user cannot tell a broken app from "nothing to review".
 *
 * It must be a class component: `useErrorBoundary` does not exist and hooks
 * cannot catch errors thrown during render.
 *
 * Two layers are used (see `App.tsx` and `main.tsx`): one per route that resets
 * on navigation, and one global as the last resort if a provider itself throws.
 *
 * The error message is deliberately NOT shown to the user. On a security tool
 * an internal message can leak table names, queries or file paths, and it is
 * not actionable for the person reading it. It goes to `onError` for logging
 * instead, and the user gets a retry.
 */
export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    const { resetKeys } = this.props;
    if (!this.state.error || !resetKeys) return;

    const prev = prevProps.resetKeys ?? [];
    const changed =
      prev.length !== resetKeys.length ||
      resetKeys.some((key, i) => !Object.is(key, prev[i]));

    if (changed) this.reset();
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) return this.props.fallback(this.reset);

    return <State tone="error" icon={<AlertLineArt />} onRetry={this.reset} />;
  }
}

/**
 * Route-level recovery UI. Needs router access to offer a way out, and a class
 * component cannot use `useNavigate`, so this receives `reset` from the
 * boundary and wires the router itself.
 *
 * Retry uses `reset()` (remount the subtree), never `window.location.reload()`:
 * a full reload throws away every cache entry and is the same "the whole SPA
 * restarts" problem A28 describes.
 */
export function RouteErrorFallback({ reset }: { reset: () => void }) {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <State
        tone="error"
        icon={<AlertLineArt />}
        title="Esta página no se pudo mostrar"
        hint="Es un error de la aplicación, no de tus datos. Podés reintentar o volver al dashboard."
        onRetry={reset}
        retryLabel="Reintentar"
      />
      <div className="flex justify-center pb-12">
        <button
          type="button"
          onClick={() => {
            reset();
            navigate("/dashboard", { replace: true });
          }}
          className={cn(
            "btn-motion active:scale-[0.98] rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800",
            FOCUS_RING,
          )}
        >
          Volver al dashboard
        </button>
      </div>
    </div>
  );
}
