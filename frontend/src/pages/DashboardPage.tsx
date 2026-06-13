import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listTransactions } from "../api/transactions";
import type { Transaction } from "../api/transactions";
import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";
import ScoreHistogram from "../components/ScoreHistogram";
import ScoreTrendChart, { buildDailyAverages } from "../components/ScoreTrendChart";
import TransactionTable from "../components/TransactionTable";
import { Sidebar } from "../components/Sidebar";

interface DashboardMetrics {
  total_transactions: number;
  fraud_percentage: number;
  avg_score: number;
  active_alerts: number;
  model_status: string;
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
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ["dashboard-metrics"],
    queryFn: fetchDashboardMetrics,
    refetchInterval: 30_000,
  });

  // Recent transactions list (first page for histogram + trend)
  const { data: recentData } = useQuery({
    queryKey: ["transactions", { page: 1, page_size: 100 }],
    queryFn: () => listTransactions({ page: 1, page_size: 100 }),
  });

  // Filtered/sorted transactions
  const { data: filteredData, isLoading: filteredLoading } = useQuery({
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

  // Build score histogram and trend from recent data
  const allTransactions = recentData?.items || [];
  const scores = useMemo(
    () =>
      allTransactions
        .map((t) => t.risk_score)
        .filter((s): s is number => s !== null),
    [allTransactions],
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
    <div className="min-h-screen bg-slate-950 flex">
      <Sidebar activeItem="dashboard" />

      {/* Main content */}
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-7xl mx-auto space-y-6">
          {/* Metric cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              label="Transacciones"
              value={
                metricsLoading
                  ? "—"
                  : metrics?.total_transactions.toLocaleString("es-AR") || "0"
              }
              icon="💳"
            />
            <MetricCard
              label="Fraude"
              value={
                metricsLoading
                  ? "—"
                  : `${metrics?.fraud_percentage.toFixed(1) || "0.0"}%`
              }
              icon="🚨"
              highlight={
                (metrics?.fraud_percentage || 0) > 5 ? "text-red-400" : "text-green-400"
              }
            />
            <MetricCard
              label="Score Promedio"
              value={
                metricsLoading
                  ? "—"
                  : metrics?.avg_score.toFixed(1) || "0.0"
              }
              icon="📊"
            />
            <MetricCard
              label="Alertas Activas"
              value={
                metricsLoading
                  ? "—"
                  : String(metrics?.active_alerts || 0)
              }
              icon="🔔"
              highlight={
                (metrics?.active_alerts || 0) > 0 ? "text-yellow-400" : "text-green-400"
              }
            />
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ScoreHistogram scores={scores} />
            <ScoreTrendChart data={dailyAverages} />
          </div>

          {/* Transaction table */}
          <div>
            <h2 className="text-sm font-semibold text-slate-300 mb-3">
              Últimas Transacciones
            </h2>
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
      </main>
    </div>
  );
}

function MetricCard({
  label,
  value,
  icon,
  highlight,
}: {
  label: string;
  value: string;
  icon: string;
  highlight?: string;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-500 font-medium">{label}</span>
        <span className="text-lg">{icon}</span>
      </div>
      <p className={`text-2xl font-bold ${highlight || "text-slate-100"}`}>
        {value}
      </p>
    </div>
  );
}
