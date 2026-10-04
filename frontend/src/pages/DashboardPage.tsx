import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listTransactions } from "../api/transactions";
import type { Transaction } from "../api/transactions";
import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";
import ScoreHistogram from "../components/ScoreHistogram";
import ScoreTrendChart, { buildDailyAverages } from "../components/ScoreTrendChart";
import TransactionTable from "../components/TransactionTable";
import { MotionList } from "../components/MotionList";
import { PageTransition } from "../components/PageTransition";
import { Sidebar } from "../components/Sidebar";
import { AlertLineArt, State } from "../components/State";
import { Button } from "../components/Button";
import { useCountUp } from "../hooks/useCountUp";
import { MAIN_LANDMARK_ID } from "../lib/focusable";
import type { Icon } from "@phosphor-icons/react";
import { Bell, ChartBar, CreditCard, ShieldWarning } from "@phosphor-icons/react";

/**
 * The backend's `ModelStatus` enum (src/schemas/monitoring.py), which has two
 * members and is derived from `MLModelService.is_available`.
 *
 * Typed as a closed union rather than `string` on purpose: this page does not
 * render the value today, and that is precisely why the spelling drifted three
 * ways without anyone noticing — "active" in the mock handler, "operational"
 * in the endpoint, "unknown" in the schema default. A `string` cannot fail a
 * build on any of them. The union makes a fourth spelling a compile error at
 * every site that reads this field.
 */
type ModelStatus = "ok" | "not_loaded";

interface DashboardMetrics {
  total_transactions: number;
  fraud_percentage: number;
  avg_score: number;
  active_alerts: number;
  model_status: ModelStatus;
}

async function fetchDashboardMetrics(): Promise<DashboardMetrics> {
  const response = await apiClient.get<DashboardMetrics>(
    "/monitoring/dashboard",
  );
  return response.data;
}

// Default recent page
const RECENT_PAGE_SIZE = 10;

export default function DashboardPage() {
  const navigate = useNavigate();
  // Transaction table state
  const [page, setPage] = useState(1);
  const [sortField, setSortField] = useState<keyof Transaction>("created_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [classificationFilter, setClassificationFilter] = useState<
    string | undefined
  >(undefined);

  // Metrics
  const {
    data: metrics,
    isLoading: metricsLoading,
    isError: metricsError,
    refetch: refetchMetrics,
  } = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: fetchDashboardMetrics,
    refetchInterval: 30_000,
  });

  // Recent transactions list (first page for histogram + trend)
  const {
    data: recentData,
    isLoading: recentLoading,
    isError: recentError,
    refetch: refetchRecent,
  } = useQuery({
    queryKey: ["transactions", { page: 1, page_size: 100 }],
    queryFn: () => listTransactions({ page: 1, page_size: 100 }),
  });

  // Filtered/sorted transactions
  const {
    data: filteredData,
    isLoading: filteredLoading,
    isError: filteredError,
    refetch: refetchFiltered,
  } = useQuery({
    queryKey: [
      "transactions",
      { page, page_size: RECENT_PAGE_SIZE, status: classificationFilter },
    ],
    queryFn: () =>
      listTransactions({
        page,
        page_size: RECENT_PAGE_SIZE,
        status: classificationFilter
          ? { legitimate: "approved", review: "flagged", fraud: "blocked" }[
              classificationFilter
            ]
          : undefined,
      }),
  });

  // Build score histogram and trend from recent data.
  // Memoised because `recentData?.items || []` allocates a new array on every
  // render, which made both downstream useMemos recompute on every render.
  const allTransactions = useMemo(
    () => recentData?.items ?? [],
    [recentData],
  );
  const dailyAverages = useMemo(
    () => buildDailyAverages(allTransactions, 7),
    [allTransactions],
  );

  // Client-side sort
  const sortedTransactions = useMemo(() => {
    if (!filteredData?.items) return [];
    return [...filteredData.items].sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (aVal < bVal) return sortDirection === "asc" ? -1 : 1;
      if (aVal > bVal) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });
  }, [filteredData, sortField, sortDirection]);

  const handleSort = useCallback(
    (field: keyof Transaction) => {
      if (field === sortField) {
        setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDirection("desc");
      }
    },
    [sortField],
  );

  return (
    <div className="min-h-screen bg-slate-950 flex overflow-x-hidden">
      <Sidebar activeItem="dashboard" />

      {/* Main content — route entrance animates once per navigation */}
      <main id={MAIN_LANDMARK_ID} tabIndex={-1} className="flex-1 overflow-auto p-6">
            <PageTransition>
              <div className="max-w-7xl mx-auto space-y-6">
                {/* The dashboard had no h1 at all: its first heading was the
                    "Últimas Transacciones" h2, so a screen-reader user arriving
                    on the page got no page title and a heading hierarchy that
                    started at level 2. Every other page has an h1. Visually
                    hidden rather than added, because the KPI row is the visual
                    header and a second visible title would be redundant. */}
                <h1 className="sr-only">Dashboard de detección de fraude</h1>
                {/* Failure banner - a failed metrics query used to render as four
                    permanent em-dashes, indistinguishable from genuinely zero. */}
            {metricsError && (
              <div className="rounded-lg border border-risk-critical/30 bg-risk-critical/5">
                <State
                  tone="error"
                  icon={<AlertLineArt />}
                  title="No se pudieron cargar las métricas"
                  hint="Los valores mostrados pueden estar incompletos. Reintentá la carga."
                  onRetry={() => void refetchMetrics()}
                  compact
                />
              </div>
            )}

            {/* Metric cards */}
            <MotionList className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              label="Transacciones"
              value={metricsLoading ? null : metrics?.total_transactions ?? null}
              format={(n) => Math.round(n).toLocaleString("es-AR")}
              icon={CreditCard}
              tone="info"
            />
            <MetricCard
              label="Fraude"
              value={metricsLoading ? null : metrics?.fraud_percentage ?? null}
              format={(n) => `${n.toFixed(1)}%`}
              icon={ShieldWarning}
              tone="critical"
              highlight={
                (metrics?.fraud_percentage || 0) > 5 ? "critical" : "clean"
              }
            />
            <MetricCard
              label="Score Promedio"
              value={metricsLoading ? null : metrics?.avg_score ?? null}
              format={(n) => n.toFixed(1)}
              icon={ChartBar}
              tone="clean"
            />
            <MetricCard
              label="Alertas Activas"
              value={metricsLoading ? null : metrics?.active_alerts ?? null}
              format={(n) => String(Math.round(n))}
              icon={Bell}
              tone="warn"
              highlight={
                (metrics?.active_alerts || 0) > 0 ? "warn" : "clean"
              }
            />
            </MotionList>

            {/* Charts row — composed shimmer skeleton while data loads */}
            <MotionList className="grid grid-cols-1 lg:grid-cols-2 gap-4" aria-busy={recentLoading}>
            {recentLoading ? (
              <>
                <div
                  aria-hidden="true"
                  data-testid="chart-skeleton"
                  className="pointer-events-none h-[200px] rounded-xl border border-slate-800 bg-slate-900 animate-shimmer"
                />
                <div
                  aria-hidden="true"
                  data-testid="chart-skeleton"
                  className="pointer-events-none h-[200px] rounded-xl border border-slate-800 bg-slate-900 animate-shimmer"
                />
              </>
            ) : recentError ? (
              // Previously this fell through to the charts with an empty
              // dataset, which drew a flat line at zero: a failed request was
              // rendered as "fraud risk is currently zero".
              // No `role` on this wrapper: the `<State>` inside it already
              // renders `role="alert"`, and nesting two assertive live regions
              // announces the same failure twice and re-announces it whenever the
              // retry control inside changes. `State` owns the role; the wrapper
              // is a panel.
              <div
                data-testid="chart-error"
                className="lg:col-span-2 rounded-xl border border-risk-critical/30 bg-slate-900"
              >
                <State
                  tone="error"
                  icon={<AlertLineArt />}
                  title="No se pudieron cargar los gráficos"
                  hint="Sin estos datos no se puede evaluar la tendencia de riesgo."
                  onRetry={() => void refetchRecent()}
                  compact
                />
              </div>
            ) : (
              <>
                <ScoreHistogram transactions={allTransactions} />
                <ScoreTrendChart data={dailyAverages} />
              </>
            )}
          </MotionList>

          {/* Transaction table — desktop tables never stagger (DESIGN.md non-goals) */}
          <div>
            <h2 className="text-sm font-semibold text-slate-300 mb-3">
              Últimas Transacciones
            </h2>
            {filteredError && (
              <div
                role="alert"
                data-testid="table-error"
                className="mb-3 rounded-lg border border-risk-critical/30 bg-risk-critical/5 px-4 py-3"
              >
                <p className="text-sm text-slate-300">
                  No se pudieron cargar las transacciones.
                </p>
                {/* The page's only interactive control, and the only one the
                    primitives could take without being bent.

                    `secondary` + `sm` matches every token the hand-rolled
                    string re-typed: `border-slate-700`, `rounded-lg`,
                    `font-medium`, `px-3 py-1.5 text-xs`, and `btn-motion
                    active:scale-[0.98]`. `bg-transparent` is new but describes
                    what an unclassed button already rendered. `mt-2` is layout,
                    so it stays on `className`.

                    DELTA, one token, and it is not avoidable: the old string
                    said `text-slate-200` where `secondary` says
                    `text-slate-300`. On this `text-xs` button label that is
                    #e2e8f0 → #cbd5e1, which is ONE STEP DARKER, not lighter —
                    slate-300 sits at oklch lightness 0.869 against slate-200's
                    0.929. An earlier version of this comment gave the first
                    hex as #e2e8e0, which is not slate-200 at all (slate-300 is
                    the one that holds that near-miss, at #e2e8f0), and called
                    the direction "one step lighter", which is backwards.
                    Both are corrected here rather than left to describe a
                    change nobody actually made.

                    It cannot be pushed back through `className`, and the
                    reason matters — Tailwind decides between two `text-slate-*`
                    utilities by stylesheet order rather than attribute order,
                    and it emits `.text-slate-200` BEFORE `.text-slate-300`, so
                    the variant wins whatever the caller writes. Taking the
                    design system's value over the hand-rolled one is the
                    point of the migration; the alternative is to leave the
                    duplication in place and call it neutral.

                    Two wins alongside it: the hover is gated on `enabled:`, so
                    it no longer fires under the cursor on a disabled control,
                    and the control gains the shared keyboard-only focus ring. */}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void refetchFiltered()}
                  className="mt-2"
                >
                  Reintentar
                </Button>
              </div>
            )}
            <TransactionTable
              transactions={sortedTransactions}
              total={filteredData?.total || 0}
              page={page}
              pageSize={RECENT_PAGE_SIZE}
              sortField={sortField}
              sortDirection={sortDirection}
              classificationFilter={classificationFilter}
              onSort={handleSort}
              onPageChange={setPage}
              onFilterChange={(cls) => {
                setClassificationFilter(cls);
                setPage(1);
              }}
              onTransactionClick={(id) => navigate(`/transactions/${id}`)}
              loading={filteredLoading}
            />
          </div>
          </div>
        </PageTransition>
      </main>
    </div>
  );
}

/** Metric tone → token colour class (no hex; see DESIGN.md tokens). */
type MetricTone = "info" | "warn" | "critical" | "clean";

/**
 * ONE table for both the icon and the value.
 *
 * It used to be `ICON_TONE_CLASSES`, used by the icon only, and the VALUE took
 * a ready-made class string through a `highlight?: string` prop. That prop is
 * how three raw palette steps — a red, a green and a yellow, none of them a
 * token — reached this component: raw values standing in for risk semantics
 * that this file already had tokens for, one line above, in the same card. The
 * icon said "critical" in `--color-risk-critical` while the number next to it
 * said it in a lighter, unnamed red, and neither followed a theme change.
 *
 * (Described in words rather than spelled out: Tailwind's scanner reads
 * comments, so writing the utilities here emits rules for them. Same trap as
 * the note in `lib/ui.ts`.)
 *
 * `highlight` is now a TONE, not a class, so the value cannot name a colour
 * that the design system has not defined. The tone is still data-driven — the
 * fraud card's icon is always `critical` while its value is `clean` when the
 * rate is low — which is why this is a lookup and not a reuse of `tone`.
 */
const TONE_TEXT_CLASSES: Record<MetricTone, string> = {
  info: "text-status-info",
  warn: "text-risk-warn",
  critical: "text-risk-critical",
  clean: "text-risk-clean",
};

function MetricCard({
  label,
  value,
  format,
  icon: Icon,
  tone,
  highlight,
}: {
  label: string;
  /** null renders the em-dash placeholder (loading / no data). */
  value: number | null;
  format: (n: number) => string;
  icon: Icon;
  tone: MetricTone;
  /** Tone of the VALUE, when it is data-driven. Omitted = neutral ink. */
  highlight?: MetricTone;
}) {
  return (
    // Hover = lift + border tint only. NO shadow animation (DESIGN.md non-goals):
    // transform and color are cheap; box-shadow transitions are not.
    <div className="transition-[border-color,transform] duration-150 ease-out-expo-like motion-reduce:transition-none motion-reduce:hover:translate-y-0 hover:-translate-y-[1px] hover:border-slate-700 bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-500 font-medium">{label}</span>
        <span
          className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${TONE_TEXT_CLASSES[tone]}`}
        >
          <Icon size={18} weight="regular" />
        </span>
      </div>
      <p
        className={`text-2xl font-bold ${
          highlight ? TONE_TEXT_CLASSES[highlight] : "text-slate-100"
        }`}
      >
        {value === null ? (
          "—"
        ) : (
          <AnimatedMetricValue value={value} format={format} />
        )}
      </p>
    </div>
  );
}

/**
 * Isolated so useCountUp only mounts once a real value exists — while data
 * is loading (null) there is zero requestAnimationFrame churn animating
 * toward a fabricated 0.
 */
function AnimatedMetricValue({
  value,
  format,
}: {
  value: number;
  format: (n: number) => string;
}) {
  const animated = useCountUp(value);
  return <>{format(animated)}</>;
}
