import type { ErrorInfo } from "react";

/**
 * Logger for errors caught by `ErrorBoundary`.
 *
 * Lives in `lib/` rather than next to the component so the component module
 * only exports components, which keeps react-refresh working in dev.
 *
 * The message is logged, never rendered: on a fraud dashboard an internal
 * message can leak table names, queries or file paths, and it is not actionable
 * for the person reading the screen.
 */
export function logRenderError(scope: string) {
  return (error: Error, info: ErrorInfo): void => {
    console.error(`[${scope}] render error`, error, info.componentStack ?? "");
  };
}
