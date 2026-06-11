import type { Transaction } from "../api/transactions";

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

const CLASSIFICATION_COLORS: Record<string, string> = {
  legitimate: "bg-fraud-legitimate-bg text-fraud-legitimate border border-fraud-legitimate/30",
  review: "bg-fraud-review-bg text-fraud-review border border-fraud-review/30",
  fraud: "bg-fraud-fraud-bg text-fraud-fraud border border-fraud-fraud/30",
  pending: "bg-slate-800 text-slate-400 border border-slate-600/30",
};

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
            className={`text-xs px-3 py-1 rounded-full transition-colors ${
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
            <tr className="border-b border-slate-800 text-slate-400 text-xs uppercase tracking-wider">
              <th className="text-left p-3 font-medium">ID</th>
              <th
                className="text-left p-3 font-medium cursor-pointer hover:text-slate-200"
                onClick={() => onSort("amount")}
              >
                Monto
                <SortIcon
                  field="amount"
                  currentField={sortField || ""}
                  direction={sortDirection}
                />
              </th>
              <th className="text-left p-3 font-medium">Comercio</th>
              <th
                className="text-left p-3 font-medium cursor-pointer hover:text-slate-200"
                onClick={() => onSort("risk_score")}
              >
                Score
                <SortIcon
                  field="risk_score"
                  currentField={sortField || ""}
                  direction={sortDirection}
                />
              </th>
              <th className="text-left p-3 font-medium">Clasificación</th>
              <th className="text-left p-3 font-medium">Estado</th>
              <th
                className="text-left p-3 font-medium cursor-pointer hover:text-slate-200"
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
                <td colSpan={7} className="p-8 text-center text-slate-500">
                  No se encontraron transacciones
                </td>
              </tr>
            ) : (
              transactions.map((tx) => {
                const classification = getClassification(tx.status);
                const colorClass =
                  CLASSIFICATION_COLORS[classification] ||
                  CLASSIFICATION_COLORS.pending;
                return (
                  <tr
                    key={tx.id}
                    onClick={() => onTransactionClick(tx.id)}
                    className="border-b border-slate-800/50 hover:bg-slate-800/50 cursor-pointer transition-colors"
                  >
                    <td className="p-3 text-slate-300 font-mono text-xs">
                      {tx.id.slice(0, 8)}...
                    </td>
                    <td className="p-3 text-slate-200 font-medium">
                      ${tx.amount.toLocaleString("es-AR")}
                    </td>
                    <td className="p-3 text-slate-300">{tx.merchant_name}</td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${tx.risk_score || 0}%`,
                              backgroundColor:
                                (tx.risk_score || 0) > 70
                                  ? "#ef4444"
                                  : (tx.risk_score || 0) > 40
                                    ? "#f59e0b"
                                    : "#22c55e",
                            }}
                          />
                        </div>
                        <span className="text-xs text-slate-400 w-6">
                          {tx.risk_score ?? "—"}
                        </span>
                      </div>
                    </td>
                    <td className="p-3">
                      <span
                        className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${colorClass}`}
                      >
                        {classification === "legitimate"
                          ? "Legítimo"
                          : classification === "review"
                            ? "Revisión"
                            : classification === "fraud"
                              ? "Fraude"
                              : classification}
                      </span>
                    </td>
                    <td className="p-3 text-slate-400 text-xs capitalize">
                      {tx.status}
                    </td>
                    <td className="p-3 text-slate-400 text-xs">
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
