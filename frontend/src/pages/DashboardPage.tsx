import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { listTransactions } from "../api/transactions";
import type { Transaction } from "../api/transactions";
import { useQuery } from "@tanstack/react-query";
import apiClient from "../api/client";
import ScoreHistogram from "../components/ScoreHistogram";
import ScoreTrendChart, { buildDailyAverages } from "../components/ScoreTrendChart";
import TransactionTable from "../components/TransactionTable";

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
  const { user, logout } = useAuthStore();

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

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const sidebarItems = [
    { label: "Dashboard", active: true, icon: "📊" },
    { label: "Transacciones", active: false, icon: "💳" },
    { label: "Alertas", active: false, icon: "🔔" },
  ];

  return (
    <div className="min-h-screen bg-slate-950 flex">
      {/* Sidebar */}
      <aside className="w-56 bg-slate-900 border-r border-slate-800 flex flex-col flex-shrink-0">
        <div className="p-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-red-900/30 border border-red-800/40 flex items-center justify-center">
              <svg
                className="w-4 h-4 text-red-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
                />
              </svg>
            </div>
            <span className="text-sm font-bold text-slate-100">
              Fraud Detector
            </span>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {sidebarItems.map((item) => (
            <button
              key={item.label}
              onClick={() => {
                if (item.label === "Transacciones")
                  navigate("/transactions");
                else if (item.label === "Alertas") navigate("/alerts");
              }}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                item.active
                  ? "bg-slate-800 text-slate-200"
                  : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-300"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        {/* User info */}
        <div className="p-3 border-t border-slate-800">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs text-slate-300 font-medium">
              {user?.id?.slice(0, 2).toUpperCase() || "?"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-slate-300 truncate">
                {user?.role || "Analista"}
              </p>
              <p className="text-[10px] text-slate-500">ID: {user?.id?.slice(0, 8) || "—"}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full text-xs text-slate-500 hover:text-red-400 transition-colors py-1"
          >
            Cerrar sesión
          </button>
        </div>
      </aside>

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
