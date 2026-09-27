import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, Link } from "react-router-dom";
import { Plus } from "@phosphor-icons/react";
import { listTransactions } from "../api/transactions";
import { ClassificationBadge } from "../components/ClassificationBadge";
import { EmptyState, ReceiptLineArt } from "../components/EmptyState";
import { MotionList } from "../components/MotionList";
import { PageTransition } from "../components/PageTransition";
import { Sidebar } from "../components/Sidebar";
import type { Transaction } from "../api/transactions";
import { formatScore } from "../lib/score";
import { formatMoney } from "../lib/money";
import {
  NUMERIC_CELL,
  TABLE_HEADER_CELL,
  TABLE_HEADER_NUMERIC,
} from "../lib/ui";

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
    <div className="min-h-screen bg-page-bg flex overflow-x-hidden">
      <Sidebar activeItem="transactions" />
      <div className="flex-1 p-6 overflow-y-auto" style={{ maxWidth: "var(--spacing-max-content)" }}>
        <PageTransition>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-bold text-text-primary">Transacciones</h1>
          <Link
            to="/transactions/new"
            className="btn-motion active:scale-[0.98] inline-flex items-center gap-1.5 bg-accent hover:bg-red-500 text-white text-sm font-medium px-4 py-2 rounded-lg"
          >
            <Plus size={16} aria-hidden="true" />
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
                className={`btn-motion active:scale-[0.98] px-3 py-1.5 rounded-lg text-xs font-medium ${
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
          <EmptyState
            icon={<ReceiptLineArt />}
            title="No hay transacciones"
            hint="Registra una transacción para comenzar a monitorear su riesgo."
            action={
              <Link
                to="/transactions/new"
                className="max-md:inline-flex max-md:min-h-[40px] max-md:items-center max-md:px-3 text-sm text-status-info hover:underline"
              >
                Crear primera transacción
              </Link>
            }
          />
        ) : (
          <>
            {/* Mobile card list — staggered reveal (md+ table never staggers) */}
            <MotionList className="md:hidden space-y-3">
              {data?.items.map((tx: Transaction) => (
                <div
                  key={tx.id}
                  data-testid={`tx-card-${tx.id}`}
                  className="bg-slate-900 border border-slate-800 rounded-xl p-4"
                  onClick={() => navigate(`/transactions/${tx.id}`)}
                >
                  {/* Header row: merchant + amount */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-slate-200 truncate">{tx.merchant_name}</span>
                    <span className={`text-sm font-bold text-slate-100 ${NUMERIC_CELL}`}>
                  {formatMoney(tx.amount, tx.currency)}
                </span>
                  </div>
                  {/* Footer row: date + badge + score */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">
                      {new Date(tx.created_at).toLocaleDateString("es-AR", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                      })}
                    </span>
                    <div className="flex items-center gap-2">
                      {tx.classification ? (
                        <ClassificationBadge classification={tx.classification} />
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                      <span className={`text-xs text-slate-300 ${NUMERIC_CELL}`}>
                        {formatScore(tx.risk_score)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </MotionList>

            {/* Desktop table */}
            <div className="hidden md:block">
              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-800">
                        <th className={TABLE_HEADER_CELL}>Comercio</th>
                        <th className={TABLE_HEADER_NUMERIC}>Monto</th>
                        <th className={TABLE_HEADER_CELL}>Moneda</th>
                        <th className={TABLE_HEADER_CELL}>Estado</th>
                        <th className={TABLE_HEADER_NUMERIC}>Score</th>
                        <th className={TABLE_HEADER_CELL}>Clasificación</th>
                        <th className={TABLE_HEADER_CELL}>Fecha</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data?.items.map((tx: Transaction) => (
                        <tr
                          key={tx.id}
                          onClick={() => navigate(`/transactions/${tx.id}`)}
                          className="border-b border-slate-800/50 hover:bg-slate-800/40 cursor-pointer transition-colors"
                        >
                          <td className="px-4 py-3 text-slate-200">{tx.merchant_name}</td>
                          <td className={`px-4 py-3 text-slate-200 ${NUMERIC_CELL}`}>
                  {formatMoney(tx.amount, tx.currency)}
                </td>
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
                          <td className={`px-4 py-3 text-slate-300 ${NUMERIC_CELL}`}>
                            {formatScore(tx.risk_score)}
                          </td>
                          <td className="px-4 py-3">
                            {tx.classification ? (
                              <ClassificationBadge classification={tx.classification} />
                            ) : (
                              <span className="text-slate-500">—</span>
                            )}
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
              </div>
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
                    className="btn-motion active:scale-[0.98] px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Anterior
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="btn-motion active:scale-[0.98] px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Siguiente
                  </button>
                </div>
              </div>
            )}
          </>
        )}
        </PageTransition>
      </div>
    </div>
  );
}
