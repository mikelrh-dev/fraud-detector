import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import {
  ErrorBoundary,
  RouteErrorFallback,
} from "./components/ErrorBoundary";
import { RouteFallback } from "./components/RouteFallback";
import { SkipLink } from "./components/SkipLink";
import { logRenderError } from "./lib/logRenderError";
import type { ReactNode } from "react";

/**
 * Route-level code splitting.
 *
 * WHY LAZY: every page used to be imported statically, so all seven shipped in
 * the entry chunk and the first paint paid for seven pages the user may never
 * open. Each `import()` here becomes its own chunk, fetched when its route is
 * first entered and then cached for the session.
 *
 * The page modules are untouched. Only the *timing* of their arrival changed:
 * the paths, the `ProtectedRoute` guard, the `*` redirect and the element tree
 * below are byte-for-byte what they were. A lazy refactor that quietly altered
 * routing would be a different change wearing this one's commit message.
 */
const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const TransactionDetail = lazy(() => import("./pages/TransactionDetail"));
const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const TransactionsPage = lazy(() => import("./pages/TransactionsPage"));
const CreateTransactionPage = lazy(() => import("./pages/CreateTransactionPage"));
const ConflictQueuePage = lazy(() => import("./pages/ConflictQueuePage"));

function ProtectedRoute({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  const location = useLocation();

  return (
    // Route-level boundary: resetKeys clears the error as soon as the user
    // navigates, so one broken page does not poison the rest of the session.
    <ErrorBoundary
      resetKeys={[location.pathname]}
      fallback={(reset) => <RouteErrorFallback reset={reset} />}
      onError={logRenderError("route")}
    >
      {/*
        ONE boundary around the outlet, not one per route. Chosen deliberately:

        1. There is no state a per-route boundary could preserve. Every page is
           already torn down on navigation, because moving between two different
           routes swaps the component type regardless of where a boundary sits.
           (This sentence previously also credited `PageTransition`'s key, and
           that credit was wrong on two counts: the key lives on a div INSIDE the
           five pages that render it, so a descendant's key cannot remount its own
           ancestor, and `LoginPage` and `RegisterPage` do not render it at all.
           The conclusion holds without the key.) A per-route boundary would add
           seven remounts and buy back nothing.
        2. One live region, not seven. Each boundary renders its own
           `role="status"`, so a per-route layout hands assistive tech a
           different announcement node per route and creates seven places for
           the a11y contract to drift. One boundary is one place to change.

        KNOWN COST, accepted on purpose: this boundary sits ABOVE the page, and
        the page owns the `<Sidebar>`. So a pending chunk hides the shell for a
        moment and the sidebar reappears on arrival. Holding the shell steady
        needs a layout route with an `<Outlet/>` — that changes the element
        tree, which is exactly what this change promised not to do.

        The boundary sits INSIDE `ErrorBoundary` so the two occupy the same
        slot: a chunk still in flight shows the fallback, and the same slot
        becomes the route error UI if that chunk never lands.

        On that second case — a rejected `import()` (offline, a stale hashed
        filename after a deploy, a 404 from the CDN) — MEASURED, not assumed:
        React re-throws the rejection during the lazy component's render, so
        the nearest error boundary above `<Routes>` catches it, and that is the
        `ErrorBoundary` in this file, which already wrapped `<Routes>` before
        this change. Its position relative to `<Suspense>` makes no difference;
        swapping the two still passes. What WOULD break it is removing the
        boundary, which is what App.chunk-failure.test.tsx pins: it goes red
        and the throw escapes the tree.

        Worth stating plainly: chunk-load failure is a failure mode this change
        INTRODUCED. With every page in the entry bundle, no page could fail to
        load. The route boundary's `resetKeys={[location.pathname]}` is what
        makes the new failure recoverable — clicking any other link clears it
        without the user pressing "Reintentar".
      */}
      {/*
        The skip link goes ABOVE <Suspense> and is the first child of the
        boundary, so it is the first focusable element in the document on every
        route — including while a lazy chunk is in flight, which is exactly when
        a keyboard user is tabbing. See SkipLink.tsx for why the app does not
        wrap the pages in a layout route to host it.
      */}
      <SkipLink />

      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/transactions/new"
            element={
              <ProtectedRoute>
                <CreateTransactionPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/transactions"
            element={
              <ProtectedRoute>
                <TransactionsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/transactions/:id"
            element={
              <ProtectedRoute>
                <TransactionDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/alerts"
            element={
              <ProtectedRoute>
                <AlertsPage />
              </ProtectedRoute>
            }
          />
          {/* The conflict queue. Its own top-level path rather than a filter on
              `/transactions`, because the disagreement is a relationship
              between two scores and not a state a transaction is IN — see
              ConflictQueuePage for the full argument. */}
          <Route
            path="/conflicts"
            element={
              <ProtectedRoute>
                <ConflictQueuePage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
