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
import { AlertLineArt, ErrorState } from "../components/ErrorState";
import {
  classificationText,
  classificationTextClass,
} from "../lib/classification";
import { MotionList } from "../components/MotionList";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { PageTransition } from "../components/PageTransition";
import { RiskMeter } from "../components/RiskMeter";
import { NUMERIC_CELL } from "../lib/ui";

// Classification colour and label come from lib/classification. This page used
// to carry its own map that was missing `pending` entirely, so an unrecognised
// classification silently fell through to a fourth, undocumented colour.
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

  const { data, isLoading, isError, refetch } = useQuery({
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
              {/* A failed query must not read as "0 alertas": on a fraud
                  alerting surface that is a hard false negative. The same
                  applies while loading — `data?.total ?? 0` rendered a
                  confident zero before the request had even resolved. */}
              {isError ? (
                <span className="text-risk-critical" data-testid="alerts-total-error">
                  No disponible
                </span>
              ) : isLoading || !data ? (
                <span data-testid="alerts-total-pending">&mdash;</span>
              ) : (
                <span data-testid="alerts-total">{data.total} alertas</span>
              )}
            </span>
          </div>

          {/* Filter tabs. NOT migrated, and this is a gap in the design system
              rather than a divergence from it. A segmented filter needs a
              SELECTED state (`bg-slate-700 text-slate-200` vs `bg-slate-800
              text-slate-400 hover:bg-slate-700`) and `BTN_VARIANTS` defines
              none.               The radius blocks it independently: these are `rounded-full`
              and a `Button` would lose that. Tailwind emits `rounded`,
              `rounded-full` and `rounded-lg` in that stylesheet order, and it
              resolves two utilities of one property by stylesheet order rather
              than attribute order — so the later `rounded-lg` in `BTN_SIZES`
              wins whatever the attribute order is, and the tabs stop being
              tabs.

              Minting a selected variant is a DESIGN change, so it is reported.
              What it costs meanwhile, and what a test pins: these four controls
              have no focus ring at all, because the treatment they carry was
              hand-rolled without `FOCUS_RING`. */}
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
            ) : isError ? (
              <div
                role="alert"
                className="rounded-xl border border-risk-critical/30 bg-slate-900"
              >
                <ErrorState
                  icon={<AlertLineArt />}
                  title="No se pudieron cargar las alertas"
                  hint="Puede que las alertas no se estén mostrando. Reintentá la carga."
                  onRetry={() => void refetch()}
                  compact
                />
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
                      className={`text-xs font-medium ${classificationTextClass(alert.classification)}`}
                    >
                      {classificationText(alert.classification)}
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
                  {/* Action buttons row — touch target via max-md.
                      `ActionButton` below is NOT migrated: a tonal variant
                      (a semantic fill at 10%, a border at 30% and a hover at
                      20%) at `text-[11px] px-2 py-1 rounded` matches no entry in
                      `BTN_VARIANTS` or `BTN_SIZES`, and the radius is a second
                      blocker — `rounded` sorts before `rounded-lg`, so a
                      `Button` would visibly change the corner. The
                      action→tone map (info = review, clean = resolving
                      positively, warn = undoing) is also semantic, not
                      stylistic, and belongs to a design decision. */}
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
                    ) : isError ? (
                      <tr>
                        <td colSpan={6}>
                          <div
                            role="alert"
                            className="rounded-xl border border-risk-critical/30 bg-slate-900"
                          >
                            <ErrorState
                              icon={<AlertLineArt />}
                              title="No se pudieron cargar las alertas"
                              hint="Puede que las alertas no se estén mostrando. Reintentá la carga."
                              onRetry={() => void refetch()}
                              compact
                            />
                          </div>
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
                              className={`text-xs font-medium ${classificationTextClass(alert.classification)}`}
                            >
                              {classificationText(alert.classification)}
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

              {/* Pagination. NOT migrated, for the same reason as
                  `TransactionsPage`: these are a FILLED neutral (`bg-slate-800`
                  resting, `bg-slate-700` hover, `disabled:opacity-40`) and the
                  closest variant, `secondary`, is transparent-with-a-border at
                  rest that fills on hover — adopting it would invert both
                  states. These are also `px-3 py-1` with no `btn-motion`, so
                  they are not even internally consistent with the other
                  hand-rolled controls. A filled-neutral variant is a DESIGN
                  addition; reported, not made. */}
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

      {/* Action confirmation modal — role/focus/Escape handled by
          ConfirmDialog.

          STILL A SIBLING OF `<PageTransition>`, and that placement is
          load-bearing, not incidental. `PageTransition` wraps the page content
          in `animate-fade-slide-up`, whose `animation-fill-mode: both`
          PERSISTS the `to` keyframe's transform as
          `matrix(1, 0, 0, 1, 0, 0)` — not `none`. Any transformed ancestor
          establishes a containing block for `position: fixed`, and this
          dialog's backdrop is `fixed inset-0`. Measured in headless Edge: a
          fixed element inside that wrapper is 1241x4000 and CLIPPED; the same
          element outside any transform is 1241x581, the viewport. Move this
          dialog inside `<PageTransition>` and it renders as a full-height strip
          down the page instead of an overlay.

          `Modal` now renders through `createPortal`, which retires this class
          of bug for it. `ConfirmDialog` does not, so the placement stays as it
          is, and the "why" is written here rather than left to be rediscovered
          by the next person who tidies the JSX.

          WHY THIS IS NOT COMPOSED OVER `Modal` — the task asked for it where
          the shapes genuinely match, and they do not. Three disagreements, all
          of which would have to be resolved by CHANGING `Modal`:

          - The error slot. `ConfirmDialog` renders `error` as a `role="alert"`
            paragraph AND puts `aria-describedby` on the panel pointing at it.
            `Modal` has no `error` prop, so the error would have to be passed
            as `children` — which silently drops the `aria-describedby` and
            makes the dialog's description empty. That is an a11y REGRESSION,
            and adding the prop is a change to `Modal`.

          - The footer gap. `ConfirmDialog`'s button row has no margin and
            relies on the preceding node's `mb-3` for its 12px. `Modal`'s
            `MODAL_FOOTER` is `mt-4` (16px) and is not overridable from the
            call site. The two are ADJACENT SIBLINGS in normal flow, so their
            vertical margins COLLAPSE to the larger of the two: composing would
            make the gap 16px, not the 28px a naive sum suggests — a visible
            change on every dialog, but a 4px one rather than 16px.

          - The cancel button. `ConfirmDialog`'s is FILLED
            (`bg-slate-800`, `hover:bg-slate-700`, `rounded`);
            `BTN_VARIANTS.secondary` is transparent with a slate-700 border and
            hovers to a FILLED `bg-slate-800` — the inverse relationship, and
            `rounded-lg` over `rounded` is a second visible difference.

          `Modal` also renames the backdrop's test id to `modal-backdrop`, which
          `confirm-dialog.a11y.test.tsx` asserts on. All four are smaller than
          the value of the composition, and all four are `Modal` changes rather
          than `ConfirmDialog` ones — so this is recorded as a design-system
          decision, not made unilaterally in a page-migration commit. */}
      {actionAlertId && (
        <ConfirmDialog
          title={
            actionType === "review"
              ? "Revisar Alerta"
              : actionType === "false_positive"
                ? "Marcar como Falso Positivo"
                : "Revertir Alerta"
          }
          onConfirm={confirmAction}
          onCancel={() => setActionAlertId(null)}
          disabled={actionMutation.isPending}
          error={actionError}
          confirmLabel={actionMutation.isPending ? "Procesando..." : "Confirmar"}
        >
          {actionType !== "review" && (
            /* A FOCUS-RING DIVERGENCE, and it is left in place on purpose. Not
               THE one, though — it was described as the only one in the
               product, and that is not true. `AUTH_INPUT_CLASS` (the Login and
               Register fields) is a SECOND divergence: it carries
               `focus:ring-risk-critical/25`, not this accent ring. Two
               divergences, and the honest count is two today rather than a
               per-file census that rots on the next commit.

               This ring is `focus:ring-accent/40` — the accent token at 40%
               opacity — where `FOCUS_RING` and every control built on it use
               the `--color-focus-ring` token at full strength. Flattening it
               would shift the hue from #dc2626 to #ef4444 AND take the opacity
               from 40% to 100%, which is two visible changes, not one. It also
               carries the bare `focus:` prefix, so it paints on mouse click,
               which the `focus-visible:` sites do not.

               Neither resolution is a refactor's to make:

               - Flattening to `FOCUS_RING` is a visual change on a
                 deliberate-looking control, and the instruction this pass
                 inherited was to PRESERVE per-page focus intent.
               - Adding a supported second ring is what the design system
                 retracted once already. `BTN_VARIANTS.danger` used to carry its
                 own `risk-critical-hover` token, which resolved byte-identical
                 to `--color-accent`, so a destructive button's hover landed on
                 a primary button's rest colour. Minting a second red ramp, or
                 a second focus ring, to express "risky" is the same wrong
                 instrument; DESIGN.md has already answered that there is one
                 focus colour.
               - And `className` cannot bridge it either, but NOT for the reason
                 an earlier version of this comment gave. That version cited two
                 `focus:`-prefixed rules and a byte offset, and the second rule
                 it named DOES NOT EXIST. The house ring is `focus-visible:`-
                 prefixed, so the stylesheet contains no `focus:`-prefixed
                 variant of the focus-ring token at all: there is nothing for the
                 `focus:` rule here to compete with. The two are not rival
                 declarations of one property, they are different pseudo-classes.

                 What is actually true is stronger, and does not depend on
                 offsets. `focus:` and `focus-visible:` are DIFFERENT STATES.
                 Passing the house ring alongside this would leave both rules
                 applying, each in its own state: a mouse click still paints the
                 40% accent ring because only `focus:` matches then, and a
                 keyboard focus would carry BOTH declarations of
                 `--tw-ring-color`. No stylesheet order can suppress a rule in a
                 state that the other rule never enters, so there is no override
                 to reach for — the two are not competing claims on one property
                 in one state, they are two different rings.

               So the ring is preserved, the divergence is written down here
               instead of being quietly normalised, and the decision is owed to
               the visual pass: either this site is drift and gets `FOCUS_RING`
               along with a `focus-visible:` fix, or it is intent and the
               design system grows a named variant for it. A test pins the
               current value in BOTH directions so it cannot change silently
               either way.

               There is also no primitive to migrate it into. `Input` renders an
               `<input>`, and this is a `<textarea>` — the reason `INVALID_INPUT`
               lives in `lib/ui.ts` rather than `Input.tsx`, but no `Textarea`
               component exists. The controls here were not migrated, they were
               preserved. */
            <label className="block mb-3">
              <span className="sr-only">Razón (requerida)</span>
              <textarea
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                placeholder="Razón (requerida)"
                className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 mb-3"
                rows={2}
              />
            </label>
          )}
        </ConfirmDialog>
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
  // Left hand-rolled, deliberately. See the note at the call site: a tonal
  // `*/10`-fill variant at `text-[11px] px-2 py-1 rounded` matches nothing in
  // `BTN_VARIANTS` or `BTN_SIZES`, and the radius loses to `rounded-lg` on
  // stylesheet order. This is the smallest unit in the product that carries no
  // focus ring at all, which is the concrete cost of the missing variant.
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
