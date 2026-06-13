import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, Link } from "react-router-dom";
import { listTransactions } from "../api/transactions";
import { Sidebar } from "../components/Sidebar";
import type { Transaction } from "../api/transactions";

type StatusFilter = "all" | "legitimate" | "review" | "fraud";

const statusFilterMap: Record<StatusFilter, string | undefined> = {
  all: undefined,
  legitimate: "approved",
  review: "flagged",
  fraud: "blocked",
};

const statusPills: { key: StatusFilter; label: string }[] = [
  { key: "all", label: "Todas" },
  { key: "legitimate", label: "Legítimo" },
  { key: "review", label: "Revisión" },
  { key: "fraud", label: "Fraude" },
];

export default function TransactionsPage() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["transactions", statusFilter, dateFrom, dateTo, page],
    queryFn: () =>
      listTransactions({
        page,
        page_size: 10,
        status: statusFilterMap[statusFilter],
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    refetchOnMount: "always",
  });

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div className="min-h-screen bg-page-bg flex">
      <Sidebar activeItem="transactions" />
      <div className="flex-1 p-6 overflow-y-auto" style={{ maxWidth: "var(--spacing-max-content)" }}>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-bold text-text-primary">Transacciones</h1>
          <Link
            to="/transactions/new"
            className="inline-flex items-center gap-1.5 bg-primary-container hover:bg-action-hover text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <span className="material-symbols-outlined text-base">add</span>
            Nueva Transacción
          </Link>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          {/* Status pills */}
          <div className="flex gap-1.5">
            {statusPills.map((pill) => (
              <button
                key={pill.key}
                onClick={() => {
                  setStatusFilter(pill.key);
                  setPage(1);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  statusFilter === pill.key
                    ? "bg-slate-700 text-slate-200"
                    : "bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-slate-300"
                }`}
              >
                {pill.label}
              </button>
            ))}
          </div>

          {/* Date range */}
          <div className="flex items-center gap-2 ml-auto">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(1);
              }}
              className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-2 focus:ring-focus-ring"
            />
            <span className="text-xs text-slate-500">a</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(1);
              }}
              className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-2 focus:ring-focus-ring"
            />
          </div>
        </div>

        {/* Content */}
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-12 bg-slate-800 animate-pulse rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <div className="text-center py-12">
            <p className="text-sm text-red-400">Error al cargar transacciones</p>
          </div>
        ) : data && data.items.length === 0 ? (
          <div className="text-center py-12">
            <span className="material-symbols-outlined text-4xl text-slate-600 mb-3">receipt_long</span>
            <p className="text-sm text-slate-400">No hay transacciones</p>
            <Link
              to="/transactions/new"
              className="inline-block mt-3 text-sm text-status-info hover:underline"
            >
              Crear primera transacción
            </Link>
          </div>
        ) : (
          <>
            {/* Table */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="text-left px-4 py-3 text-xs text-slate-400 font-medium">Comercio</th>
                    <th className="text-left px-4 py-3 text-xs text-slate-400 font-medium">Monto</th>
                    <th className="text-left px-4 py-3 text-xs text-slate-400 font-medium">Moneda</th>
                    <th className="text-left px-4 py-3 text-xs text-slate-400 font-medium">Estado</th>
                    <th className="text-left px-4 py-3 text-xs text-slate-400 font-medium">Score</th>
                    <th className="text-left px-4 py-3 text-xs text-slate-400 font-medium">Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((tx: Transaction) => (
                    <tr
                      key={tx.id}
                      onClick={() => navigate(`/transactions/${tx.id}`)}
                      className="border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 text-slate-200">{tx.merchant_name}</td>
                      <td className="px-4 py-3 text-slate-200">${tx.amount.toFixed(2)}</td>
                      <td className="px-4 py-3 text-slate-400">{tx.currency}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            tx.status === "approved"
                              ? "bg-status-approved/10 text-status-approved"
                              : tx.status === "flagged"
                                ? "bg-status-flagged/10 text-status-flagged"
                                : tx.status === "blocked"
                                  ? "bg-status-blocked/10 text-status-blocked"
                                  : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {tx.status === "approved"
                            ? "Legítimo"
                            : tx.status === "flagged"
                              ? "Revisión"
                              : tx.status === "blocked"
                                ? "Fraude"
                                : tx.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-300">
                        {tx.risk_score !== null ? tx.risk_score.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {new Date(tx.created_at).toLocaleDateString("es-AR", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "numeric",
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-xs text-slate-400">
                  Página {page} de {totalPages} ({data?.total} transacciones)
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Anterior
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    Siguiente
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
