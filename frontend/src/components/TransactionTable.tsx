import type { Transaction } from "../api/transactions";
import { Link } from "react-router-dom";
import { EmptyState, ReceiptLineArt } from "./EmptyState";
import { classificationPillClass, classificationText } from "../lib/classification";
import { formatMoney } from "../lib/money";
import { RiskMeter } from "./RiskMeter";
import {
  NUMERIC_CELL,
  TABLE_HEADER_CELL,
  TABLE_HEADER_NUMERIC,
} from "../lib/ui";

interface TransactionTableProps {
  transactions: Transaction[];
  total: number;
  page: number;
  pageSize: number;
  sortField?: keyof Transaction;
  sortDirection?: "asc" | "desc";
  classificationFilter?: string;
  onSort: (field: keyof Transaction) => void;
  onPageChange: (page: number) => void;
  onFilterChange: (classification: string | undefined) => void;
  onTransactionClick: (id: string) => void;
  loading?: boolean;
}

/** Status → classification. Unknown statuses fall through as-is so the
 *  classification helpers classify them as neutral rather than guessing. */
const CLASSIFICATION_LABELS: Record<string, string> = {
  approved: "legitimate",
  flagged: "review",
  blocked: "fraud",
};

function getClassification(status: string): string {
  return CLASSIFICATION_LABELS[status] || status || "pending";
}

function SortIcon({
  field,
  currentField,
  direction,
}: {
  field: string;
  currentField: string;
  direction: "asc" | "desc";
}) {
  if (field !== currentField) {
    return <span className="text-slate-600 ml-1">↕</span>;
  }
  return (
    <span className="text-fraud-review ml-1">
      {direction === "asc" ? "↑" : "↓"}
    </span>
  );
}

export default function TransactionTable({
  transactions,
  total,
  page,
  pageSize,
  sortField,
  sortDirection = "desc",
  classificationFilter,
  onSort,
  onPageChange,
  onFilterChange,
  onTransactionClick,
  loading = false,
}: TransactionTableProps) {
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="bg-slate-900 rounded-lg overflow-hidden">
      {/* Filter bar */}
      <div className="flex items-center gap-3 p-3 border-b border-slate-800">
        <span className="text-xs text-slate-400 font-medium">
          Filtro:
        </span>
        {["all", "legitimate", "review", "fraud"].map((cls) => (
          <button
            key={cls}
            onClick={() => onFilterChange(cls === "all" ? undefined : cls)}
            className={`btn-motion active:scale-[0.98] text-xs px-3 py-1 rounded-full ${
              (cls === "all" && !classificationFilter) ||
              classificationFilter === cls
                ? "bg-slate-700 text-slate-200"
                : "bg-slate-800 text-slate-400 hover:bg-slate-700"
            }`}
          >
            {cls === "all"
              ? "Todos"
              : cls === "legitimate"
                ? "Legítimo"
                : cls === "review"
                  ? "Revisión"
                  : "Fraude"}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              <th className={TABLE_HEADER_CELL}>ID</th>
              <th
                className={`${TABLE_HEADER_NUMERIC} cursor-pointer hover:text-slate-200`}
                onClick={() => onSort("amount")}
              >
                Monto
                <SortIcon
                  field="amount"
                  currentField={sortField || ""}
                  direction={sortDirection}
                />
              </th>
              <th className={TABLE_HEADER_CELL}>Comercio</th>
              <th
                className={`${TABLE_HEADER_NUMERIC} cursor-pointer hover:text-slate-200`}
                onClick={() => onSort("risk_score")}
              >
                Score
                <SortIcon
                  field="risk_score"
                  currentField={sortField || ""}
                  direction={sortDirection}
                />
              </th>
              <th className={TABLE_HEADER_CELL}>Clasificación</th>
              <th className={TABLE_HEADER_CELL}>Estado</th>
              <th
                className={`${TABLE_HEADER_CELL} cursor-pointer hover:text-slate-200`}
                onClick={() => onSort("created_at")}
              >
                Fecha
                <SortIcon
                  field="created_at"
                  currentField={sortField || ""}
                  direction={sortDirection}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-slate-500">
                  Cargando...
                </td>
              </tr>
            ) : transactions.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <EmptyState
                    icon={<ReceiptLineArt />}
                    title="No se encontraron transacciones"
                    hint="Ajusta los filtros activos o crea una nueva transacción."
                    compact
                  />
                </td>
              </tr>
            ) : (
              transactions.map((tx) => {
                const classification =
                  tx.classification ?? getClassification(tx.status);
                return (
                  <tr
                    key={tx.id}
                    onClick={(e) => {
                      // The merchant cell is a real <Link>, so it handles its
                      // own activation — including middle-click, cmd-click and
                      // "copy link address". Without this guard the row's
                      // handler would also fire and push a second history
                      // entry for the same route.
                      if ((e.target as HTMLElement).closest("a")) return;
                      onTransactionClick(tx.id);
                    }}
                    className="border-b border-slate-800/50 hover:bg-slate-800/40 focus-within:bg-slate-800/40 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                      {tx.id.slice(0, 8)}...
                    </td>
                    <td className={`px-4 py-3 text-slate-200 font-medium ${NUMERIC_CELL}`}>
                      {formatMoney(tx.amount, tx.currency)}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {/* The row's primary action is reachable by keyboard and
                          exposes a real href; the row onClick is mouse-only
                          convenience for the rest of the cells. */}
                      <Link
                        to={`/transactions/${tx.id}`}
                        className="rounded hover:text-slate-100 hover:underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                      >
                        {tx.merchant_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <RiskMeter value={tx.risk_score} />
                        <span className={`text-xs text-slate-400 w-6 ${NUMERIC_CELL}`}>
                          {tx.risk_score ?? "—"}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${classificationPillClass(classification)}`}
                      >
                        {classificationText(classification)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-xs capitalize">
                      {tx.status}
                    </td>
                    <td className="px-4 py-3 text-slate-400 text-xs">
                      {new Date(tx.created_at).toLocaleDateString("es-AR", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                      })}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between p-3 border-t border-slate-800">
          <span className="text-xs text-slate-500">
            Pág. {page} de {totalPages} ({total} resultados)
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="px-3 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Anterior
            </button>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="px-3 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
