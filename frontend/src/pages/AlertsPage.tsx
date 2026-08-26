import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listAlerts,
  reviewAlert,
  markFalsePositive,
  revertBlock,
} from "../api/alerts";
import { Sidebar } from "../components/Sidebar";
import { AlertStatusBadge } from "../components/AlertStatusBadge";
import { BellLineArt, EmptyState } from "../components/EmptyState";
import { MotionList } from "../components/MotionList";
import { PageTransition } from "../components/PageTransition";
import { RiskMeter } from "../components/RiskMeter";
import { NUMERIC_CELL } from "../lib/ui";

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

  const totalPages = Math.ceil((data?.total || 0) / 20);

  return (
    <div className="min-h-screen bg-slate-950 flex overflow-x-hidden">
      <Sidebar activeItem="alerts" />

      {/* Main — route entrance animates once per navigation */}
      <main className="flex-1 overflow-auto p-6">
        <PageTransition>
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
                className={`btn-motion active:scale-[0.98] text-xs px-3 py-1.5 rounded-full ${
                  statusFilter === f.value
                    ? "bg-slate-700 text-slate-200"
                    : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Mobile card list */}
          <div className="md:hidden space-y-3">
            {isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-24 bg-slate-800 animate-pulse rounded-lg" />
                ))}
              </div>
            ) : data?.items.length === 0 ? (
              <EmptyState
                icon={<BellLineArt />}
                title="No hay alertas"
                hint="Las alertas aparecen cuando una transacción supera los umbrales de riesgo."
                action={
                  <button
                    onClick={() => navigate("/transactions")}
                    className="max-md:inline-flex max-md:min-h-[40px] max-md:items-center max-md:px-3 text-sm text-status-info hover:underline"
                  >
                    Ver transacciones
                  </button>
                }
              />
            ) : (
              <MotionList className="space-y-3">
              {data?.items.map((alert) => (
                <div
                  key={alert.id}
                  data-testid={`alert-card-${alert.id}`}
                  className="bg-slate-900 border border-slate-800 rounded-xl p-4"
                >
                  {/* Status badge */}
                  <div className="mb-2">
                    <AlertStatusBadge status={alert.status} />
                  </div>
                  {/* Description: tx link + classification */}
                  <div className="flex items-center gap-2 mb-1">
                    <button
                      onClick={() =>
                        navigate(`/transactions/${alert.transaction_id}`)
                      }
                      className="font-mono text-xs text-slate-400 underline"
                    >
                      {alert.transaction_id.slice(0, 8)}...
                    </button>
                    <span
                      className={`text-xs font-medium ${
                        CLASSIFICATION_COLORS[alert.classification] ||
                        "text-slate-400"
                      }`}
                    >
                      {CLASSIFICATION_LABELS[alert.classification] ||
                        alert.classification}
                    </span>
                  </div>
                  {/* Timestamp */}
                  <p className="text-xs text-slate-500 mb-3">
                    {new Date(alert.created_at).toLocaleDateString("es-AR", {
                      day: "2-digit",
                      month: "2-digit",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                  {/* Action buttons row — touch target via max-md */}
                  <div className="flex gap-2">
                    {(alert.status === "open" ||
                      alert.status === "reviewed") && (
                      <>
                        {alert.status === "open" && (
                          <>
                            <ActionButton
                              label="Revisar"
                              onClick={() =>
                                openActionDialog(alert.id, "review")
                              }
                              tone="info"
                            />
                            <ActionButton
                              label="Falso Pos."
                              onClick={() =>
                                openActionDialog(
                                  alert.id,
                                  "false_positive",
                                )
                              }
                              tone="clean"
                            />
                          </>
                        )}
                        {alert.status === "reviewed" && (
                          <ActionButton
                            label="Revertir"
                            onClick={() =>
                              openActionDialog(alert.id, "revert")
                            }
                            tone="warn"
                          />
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
              </MotionList>
            )}
          </div>

          {/* Desktop table — never staggers (DESIGN.md non-goals) */}
          <div className="hidden md:block">
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
                        <td colSpan={6}>
                          <EmptyState
                            icon={<BellLineArt />}
                            title="No hay alertas"
                            hint="Las alertas aparecen cuando una transacción supera los umbrales de riesgo."
                            compact
                          />
                        </td>
                      </tr>
                    ) : (
                      data?.items.map((alert) => (
                        <tr
                          key={alert.id}
                          className="border-b border-slate-800/50 hover:bg-slate-800/40 transition-colors"
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
                              <RiskMeter value={alert.score} widthClass="w-12" />
                              <span className={`text-xs text-slate-400 w-5 ${NUMERIC_CELL}`}>
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
                            <AlertStatusBadge status={alert.status} />
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
                                      tone="info"
                                    />
                                    <ActionButton
                                      label="Falso Pos."
                                      onClick={() =>
                                        openActionDialog(
                                          alert.id,
                                          "false_positive",
                                        )
                                      }
                                      tone="clean"
                                    />
                                  </>
                                )}
                                {alert.status === "reviewed" && (
                                  <ActionButton
                                    label="Revertir"
                                    onClick={() =>
                                      openActionDialog(alert.id, "revert")
                                    }
                                    tone="warn"
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
        </div>
        </PageTransition>
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
                className="btn-motion active:scale-[0.98] px-3 py-1.5 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Cancelar
              </button>
              <button
                onClick={confirmAction}
                disabled={actionMutation.isPending}
                className="btn-motion active:scale-[0.98] px-3 py-1.5 text-xs rounded bg-accent text-white hover:bg-red-500 disabled:bg-red-800/50 disabled:cursor-not-allowed"
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

/**
 * Action semantics → semantic token tone (no raw palette colors):
 * info = neutral workflow step (review), clean = resolving positively
 * (false positive), warn = undoing with caution (revert).
 */
type ActionTone = "info" | "clean" | "warn";

function ActionButton({
  label,
  onClick,
  tone,
}: {
  label: string;
  onClick: () => void;
  tone: ActionTone;
}) {
  const tones: Record<ActionTone, string> = {
    info: "bg-status-info/10 text-status-info hover:bg-status-info/20 border-status-info/30",
    clean:
      "bg-risk-clean/10 text-risk-clean hover:bg-risk-clean/20 border-risk-clean/30",
    warn: "bg-risk-warn/10 text-risk-warn hover:bg-risk-warn/20 border-risk-warn/30",
  };

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`btn-motion active:scale-[0.98] max-md:min-h-[40px] max-md:px-3 max-md:text-xs text-[11px] px-2 py-1 rounded border ${tones[tone]}`}
    >
      {label}
    </button>
  );
}
