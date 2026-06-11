import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listAlerts,
  reviewAlert,
  markFalsePositive,
  revertBlock,
} from "../api/alerts";
import { useAuthStore } from "../store/authStore";

const STATUS_COLORS: Record<string, string> = {
  open: "bg-yellow-900/30 text-yellow-400 border-yellow-600/30",
  reviewed: "bg-blue-900/30 text-blue-400 border-blue-600/30",
  resolved: "bg-green-900/30 text-green-400 border-green-600/30",
};

const STATUS_LABELS: Record<string, string> = {
  open: "Abierta",
  reviewed: "Revisada",
  resolved: "Resuelta",
};

const CLASSIFICATION_COLORS: Record<string, string> = {
  legitimate: "text-fraud-legitimate",
  review: "text-fraud-review",
  fraud: "text-fraud-fraud",
};

const CLASSIFICATION_LABELS: Record<string, string> = {
  legitimate: "Legítimo",
  review: "Revisión",
  fraud: "Fraude",
};

type AlertAction = "review" | "false_positive" | "revert";

export default function AlertsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, logout } = useAuthStore();

  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(
    undefined,
  );
  const [actionAlertId, setActionAlertId] = useState<string | null>(null);
  const [actionType, setActionType] = useState<AlertAction>("review");
  const [actionReason, setActionReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["alerts", { page, status: statusFilter }],
    queryFn: () =>
      listAlerts({
        page,
        page_size: 20,
        status: statusFilter,
      }),
  });

  const actionMutation = useMutation({
    mutationFn: async ({
      alertId,
      action,
      reason,
    }: {
      alertId: string;
      action: AlertAction;
      reason?: string;
    }) => {
      switch (action) {
        case "review":
          return reviewAlert(alertId, reason);
        case "false_positive":
          return markFalsePositive(alertId, reason);
        case "revert":
          return revertBlock(alertId, reason);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      setActionAlertId(null);
      setActionReason("");
      setActionError(null);
    },
    onError: () => {
      setActionError("Error al ejecutar la acción. Intente nuevamente.");
    },
  });

  const openActionDialog = useCallback(
    (alertId: string, action: AlertAction) => {
      setActionAlertId(alertId);
      setActionType(action);
      setActionReason("");
      setActionError(null);
    },
    [],
  );

  const confirmAction = useCallback(() => {
    if (!actionAlertId) return;
    actionMutation.mutate({
      alertId: actionAlertId,
      action: actionType,
      reason: actionReason || undefined,
    });
  }, [actionAlertId, actionType, actionReason, actionMutation]);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const totalPages = Math.ceil((data?.total || 0) / 20);

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
          <button
            onClick={() => navigate("/dashboard")}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 transition-colors"
          >
            <span>📊</span> Dashboard
          </button>
          <button
            onClick={() => navigate("/dashboard")}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-400 hover:bg-slate-800/50 hover:text-slate-300 transition-colors"
          >
            <span>💳</span> Transacciones
          </button>
          <button className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm bg-slate-800 text-slate-200 transition-colors">
            <span>🔔</span> Alertas
          </button>
        </nav>

        <div className="p-3 border-t border-slate-800">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs text-slate-300 font-medium">
              {user?.id?.slice(0, 2).toUpperCase() || "?"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-slate-300 truncate">
                {user?.role || "Analista"}
              </p>
              <p className="text-[10px] text-slate-500">
                ID: {user?.id?.slice(0, 8) || "—"}
              </p>
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

      {/* Main */}
      <main className="flex-1 overflow-auto p-6">
        <div className="max-w-7xl mx-auto space-y-4">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-bold text-slate-100">Alertas</h1>
            <span className="text-xs text-slate-500">
              {data?.total || 0} alertas
            </span>
          </div>

          {/* Filter tabs */}
          <div className="flex gap-2">
            {[
              { label: "Todas", value: undefined },
              { label: "Abiertas", value: "open" },
              { label: "Revisadas", value: "reviewed" },
              { label: "Resueltas", value: "resolved" },
            ].map((f) => (
              <button
                key={f.label}
                onClick={() => {
                  setStatusFilter(f.value);
                  setPage(1);
                }}
                className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
                  statusFilter === f.value
                    ? "bg-slate-700 text-slate-200"
                    : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Table */}
          <div className="bg-slate-900 rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-xs uppercase tracking-wider">
                    <th className="text-left p-3 font-medium">Transacción</th>
                    <th className="text-left p-3 font-medium">Score</th>
                    <th className="text-left p-3 font-medium">
                      Clasificación
                    </th>
                    <th className="text-left p-3 font-medium">Estado</th>
                    <th className="text-left p-3 font-medium">Fecha</th>
                    <th className="text-right p-3 font-medium">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-500">
                        Cargando...
                      </td>
                    </tr>
                  ) : data?.items.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-500">
                        No hay alertas
                      </td>
                    </tr>
                  ) : (
                    data?.items.map((alert) => (
                      <tr
                        key={alert.id}
                        className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors"
                      >
                        <td className="p-3">
                          <button
                            onClick={() =>
                              navigate(`/transactions/${alert.transaction_id}`)
                            }
                            className="font-mono text-xs text-slate-400 hover:text-slate-200 underline underline-offset-2"
                          >
                            {alert.transaction_id.slice(0, 8)}...
                          </button>
                        </td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <div className="w-12 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${Math.min(alert.score, 100)}%`,
                                  backgroundColor:
                                    alert.score > 70
                                      ? "#ef4444"
                                      : alert.score > 40
                                        ? "#f59e0b"
                                        : "#22c55e",
                                }}
                              />
                            </div>
                            <span className="text-xs text-slate-400 w-5">
                              {alert.score.toFixed(0)}
                            </span>
                          </div>
                        </td>
                        <td className="p-3">
                          <span
                            className={`text-xs font-medium ${
                              CLASSIFICATION_COLORS[
                                alert.classification
                              ] || "text-slate-400"
                            }`}
                          >
                            {CLASSIFICATION_LABELS[alert.classification] ||
                              alert.classification}
                          </span>
                        </td>
                        <td className="p-3">
                          <span
                            className={`text-[11px] px-2 py-0.5 rounded-full font-medium border ${
                              STATUS_COLORS[alert.status] ||
                              "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {STATUS_LABELS[alert.status] || alert.status}
                          </span>
                        </td>
                        <td className="p-3 text-xs text-slate-400">
                          {new Date(alert.created_at).toLocaleDateString(
                            "es-AR",
                            {
                              day: "2-digit",
                              month: "2-digit",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            },
                          )}
                        </td>
                        <td className="p-3 text-right">
                          {(alert.status === "open" ||
                            alert.status === "reviewed") && (
                            <div className="flex gap-1 justify-end">
                              {alert.status === "open" && (
                                <>
                                  <ActionButton
                                    label="Revisar"
                                    onClick={() =>
                                      openActionDialog(alert.id, "review")
                                    }
                                    color="blue"
                                  />
                                  <ActionButton
                                    label="Falso Pos."
                                    onClick={() =>
                                      openActionDialog(
                                        alert.id,
                                        "false_positive",
                                      )
                                    }
                                    color="green"
                                  />
                                </>
                              )}
                              {alert.status === "reviewed" && (
                                <ActionButton
                                  label="Revertir"
                                  onClick={() =>
                                    openActionDialog(alert.id, "revert")
                                  }
                                  color="yellow"
                                />
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between p-3 border-t border-slate-800">
                <span className="text-xs text-slate-500">
                  Pág. {page} de {totalPages}
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="px-3 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Anterior
                  </button>
                  <button
                    onClick={() => setPage((p) => p + 1)}
                    disabled={page >= totalPages}
                    className="px-3 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Siguiente
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Action confirmation modal */}
      {actionAlertId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 rounded-xl border border-slate-800 p-5 w-full max-w-sm">
            <h3 className="text-sm font-semibold text-slate-200 mb-3">
              {actionType === "review"
                ? "Revisar Alerta"
                : actionType === "false_positive"
                  ? "Marcar como Falso Positivo"
                  : "Revertir Alerta"}
            </h3>

            {actionType !== "review" && (
              <textarea
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                placeholder="Razón (requerida)"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40 mb-3"
                rows={2}
              />
            )}

            {actionError && (
              <p className="text-xs text-red-400 mb-3">{actionError}</p>
            )}

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setActionAlertId(null)}
                className="px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={confirmAction}
                disabled={actionMutation.isPending}
                className="px-3 py-1.5 text-xs rounded bg-red-600 text-white hover:bg-red-500 disabled:bg-red-800/50 disabled:cursor-not-allowed transition-colors"
              >
                {actionMutation.isPending ? "Procesando..." : "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  color,
}: {
  label: string;
  onClick: () => void;
  color: "blue" | "green" | "yellow";
}) {
  const colors = {
    blue: "bg-blue-900/30 text-blue-400 hover:bg-blue-800/40 border-blue-700/30",
    green:
      "bg-green-900/30 text-green-400 hover:bg-green-800/40 border-green-700/30",
    yellow:
      "bg-yellow-900/30 text-yellow-400 hover:bg-yellow-800/40 border-yellow-700/30",
  };

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`text-[11px] px-2 py-1 rounded border ${colors[color]} transition-colors`}
    >
      {label}
    </button>
  );
}
