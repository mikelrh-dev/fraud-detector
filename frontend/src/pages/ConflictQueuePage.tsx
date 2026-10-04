import { useSearchParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listTransactions } from "../api/transactions";
import type { Transaction } from "../api/transactions";
import { Sidebar } from "../components/Sidebar";
import { State, AlertLineArt } from "../components/State";
import { MotionList } from "../components/MotionList";
import { PageTransition } from "../components/PageTransition";
import { MAIN_LANDMARK_ID } from "../lib/focusable";
import { formatTimestamp } from "../lib/datetime";
import { formatMoney } from "../lib/money";
import { FOCUS_RING, NUMERIC_CELL, TABLE_HEADER_CELL, TABLE_HEADER_NUMERIC, cn } from "../lib/ui";
import {
  DEFAULT_PAGE,
  LIST_PARAMS,
  clampPage,
  fetchClampedPage,
  parsePage,
  writeListParams,
} from "../lib/list-query";

/**
 * The conflict queue — transactions whose two scoring layers disagreed.
 *
 * WHAT IS IN THE QUEUE, in the analyst's words, on the screen rather than only
 * in the backend's docstring: the deterministic rules cleared that
 * transaction's threshold and the model did not, or the reverse. Those are the
 * transactions the routed classification policy could not commit on, and they
 * are the ones worth a human's attention — not because either layer is right,
 * but because they disagree about something.
 *
 * WHY A SEPARATE PAGE AND NOT A TRANSACTIONS FILTER
 * =================================================
 * The disagreement is not a state a transaction is IN. It is a relationship
 * between two scores, and the transaction list has no column for a
 * relationship. Filing it as a tab there would have meant a screen labelled
 * "Transacciones" quietly answering a different question, and an analyst who
 * believed they were looking at everything.
 *
 * WHY THE NUMBERS, NOT TWO GAUGES
 * ===============================
 * `RiskMeter` is right for ONE score against the 0-100 scale: it encodes
 * magnitude as a bar and colour by classification. Two of them per row encode
 * four things to communicate one comparison — and a meter's colour is a VERDICT
 * about a layer, while a layer in a conflict has no verdict. It disagreed.
 * Painting the rules critical would claim they decided something; painting the
 * model clean would claim the model did. `NUMERIC_CELL` says exactly what is
 * true and lines the digits up so the gap is readable at a glance.
 *
 * WHY THE DIRECTION LABEL IS DERIVED, NOT DECIDED
 * ================================================
 * Eligibility is decided by the server's SQL (`services/conflict_queue.py`).
 * The label below only ranks the two numbers already on screen, and it is
 * labelled and tested as derived. If the client decided membership as well,
 * two definitions of "conflict" would exist — one in SQL and one in a
 * ternary — and they would eventually disagree, with the queue showing
 * ordinary transactions under a heading that says they disagreed.
 *
 * URL STATE
 * =========
 * The page number is the query string, for the same reason as on
 * `TransactionsPage` and `AlertsPage` and against the same contract: a
 * filtered list that cannot be linked cannot be reported. `lib/list-query.ts`
 * owns the parameter names, the clearing rule and what an unrecognised value
 * does. The conflict filter itself is NOT in the URL — this page IS the
 * filter, so `?conflict=true` would be a second address for one view.
 */

const CONFLICT_PAGE_SIZE = 20;

/** The em dash the rest of the product uses for "no value". */
const NO_VALUE = "—";

/**
 * A score for display, or an explicit dash.
 *
 * NOT `value ?? 0`: a fabricated zero reads as "the model ran and found
 * nothing", which is a different fact from "there is no score row", and the
 * backend distinguishes them deliberately.
 */
function scoreText(value: number | null | undefined): string {
  return value == null ? NO_VALUE : value.toFixed(1);
}

type ConflictDirection = "rules-loud" | "model-loud";

/**
 * Which layer scored higher — the one that disagreed with the other.
 *
 * `null` when either score is absent, because there is nothing to rank. It is
 * typed rather than defaulted so a row in that state cannot be given a
 * confident label by a future `?? "rules-loud"`.
 */
function directionOf(txn: Transaction): ConflictDirection | null {
  if (txn.rule_score == null || txn.ml_score == null) return null;
  return txn.rule_score > txn.ml_score ? "rules-loud" : "model-loud";
}

/** The two names an analyst needs, in the screen's own vocabulary. */
const DIRECTION_LABEL: Record<ConflictDirection, string> = {
  "rules-loud": "Reglas por encima",
  "model-loud": "Modelo por encima",
};

/** Both values, in one cell — the comparison the whole page exists to show. */
function ScorePair({
  txn,
  className,
}: {
  txn: Transaction;
  className?: string;
}) {
  const direction = directionOf(txn);
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <span className={NUMERIC_CELL} data-testid={`rule-score-${txn.id}`}>
        <span className="sr-only">Puntuación de reglas: </span>
        {scoreText(txn.rule_score)}
      </span>
      <span
        className={NUMERIC_CELL}
        data-testid={`ml-score-${txn.id}`}
      >
        <span className="sr-only">Puntuación del modelo: </span>
        {scoreText(txn.ml_score)}
      </span>
      {/* Derived from the two numbers above, never authoritative — see the
          module note. Null when either is absent: no ranking, no claim. */}
      {direction && (
        <span
          className="text-[11px] text-slate-500"
          data-testid={`conflict-direction-${direction}`}
        >
          {DIRECTION_LABEL[direction]}
        </span>
      )}
    </div>
  );
}

/**
 * The row's way in to the transaction itself.
 *
 * A `<Link>`, not a `Button`, for the same reason `TransactionsPage` uses one:
 * a button would cost middle-click, ctrl-click and "copy link address" for no
 * gain, and a review queue whose whole purpose is opening an item for closer
 * reading needs those to work. The touch floor is the `max-md:` gate because
 * this control is intrinsic-width, not a row-filling target.
 */
function ConflictLink({ txn }: { txn: Transaction }) {
  return (
    <Link
      to={`/transactions/${txn.id}`}
      className={cn(
        "text-slate-200 hover:text-slate-100 underline underline-offset-2",
        FOCUS_RING,
        "max-md:inline-flex max-md:min-h-[40px] max-md:items-center",
      )}
    >
      {txn.merchant_name}
    </Link>
  );
}

export default function ConflictQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const page = parsePage(searchParams.get(LIST_PARAMS.page));

  /** Move pages. Deliberately does NOT reset the page. */
  const goToPage = (next: number) => {
    setSearchParams(
      writeListParams(searchParams, {
        [LIST_PARAMS.page]: next === DEFAULT_PAGE ? null : String(next),
      }),
    );
  };

  const { data, isLoading, isError, refetch } = useQuery({
    // `conflict: true` is part of the key as well as the request. It cannot
    // change on this page, but the key is what makes a future reuse of this
    // component elsewhere correct, and a cache entry keyed only by the page
    // number would happily serve the ordinary list under this heading.
    queryKey: ["conflicts", { page }],
    queryFn: () =>
      fetchClampedPage(page, (target) =>
        listTransactions({
          page: target,
          page_size: CONFLICT_PAGE_SIZE,
          conflict: true,
        }),
      ),
  });

  const totalPages = data ? Math.ceil(data.total / CONFLICT_PAGE_SIZE) : 0;
  // The page on screen rather than the one in the address, which differ only
  // for a stale link — see `fetchClampedPage`.
  const shownPage = clampPage(page, totalPages);
  const items = data?.items ?? [];

  return (
    <div className="min-h-screen bg-slate-950 flex overflow-x-hidden">
      <Sidebar activeItem="conflicts" />

      {/* Main — the page that owns the content owns the landmark; the shell
          does not provide one. */}
      <main id={MAIN_LANDMARK_ID} tabIndex={-1} className="flex-1 overflow-auto p-6">
        <PageTransition>
          <div className="max-w-7xl mx-auto space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-lg font-bold text-slate-100">
                  Cola de Conflictos
                </h1>
                {/* The definition, on the screen.
                    A queue whose membership rule lives only in a backend
                    docstring is a queue nobody can trust: an analyst who finds
                    a transaction missing has no way to tell whether it was
                    never a conflict or the rule moved. One line, in the words
                    the page uses. */}
                <p className="text-xs text-slate-500 mt-1">
                  Transacciones donde las reglas y el modelo superaron el
                  umbral y el otro no.
                </p>
              </div>
              <span className="text-xs text-slate-500">
                {/* A failed query must not read as "0 conflictos": on this
                    surface a zero is the claim "the layers never disagreed",
                    which is the one statement the page must never fabricate.
                    The same applies while loading. */}
                {isError ? (
                  <span className="text-risk-critical" data-testid="conflicts-total-error">
                    No disponible
                  </span>
                ) : isLoading || !data ? (
                  <span data-testid="conflicts-total-pending">{NO_VALUE}</span>
                ) : (
                  <span data-testid="conflicts-total">
                    {data.total} conflicto{data.total === 1 ? "" : "s"}
                  </span>
                )}
              </span>
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
                // No live-region role on the wrapper: `State`'s error tone owns
                // the assertive region, and a second one here would nest two
                // and announce the same failure twice.
                <div className="rounded-xl border border-risk-critical/30 bg-slate-900">
                  <State
                    tone="error"
                    icon={<AlertLineArt />}
                    title="No se pudieron cargar los conflictos"
                    hint="Puede que la cola de conflictos no se esté mostrando. Reintentá la carga."
                    onRetry={() => void refetch()}
                    compact
                  />
                </div>
              ) : items.length === 0 ? (
                <State
                  tone="empty"
                  icon={<AlertLineArt />}
                  title="No hay conflictos"
                  hint="Las reglas y el modelo coinciden en todas las transacciones."
                  compact
                />
              ) : (
                <MotionList className="space-y-3">
                  {items.map((txn) => (
                    <div
                      key={txn.id}
                      data-testid={`conflict-card-${txn.id}`}
                      className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm truncate">
                          <ConflictLink txn={txn} />
                        </span>
                        <span
                          className={cn(NUMERIC_CELL, "text-slate-300 text-sm")}
                        >
                          {formatMoney(txn.amount, txn.currency)}
                        </span>
                      </div>
                      <ScorePair txn={txn} />
                      <p className="text-xs text-slate-500">
                        {formatTimestamp(txn.created_at)}
                      </p>
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
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className={TABLE_HEADER_CELL}>Comercio</th>
                        <th className={TABLE_HEADER_NUMERIC}>Importe</th>
                        <th className={TABLE_HEADER_CELL}>
                          Reglas / Modelo
                        </th>
                        <th className={TABLE_HEADER_NUMERIC}>Ensemble</th>
                        <th className={TABLE_HEADER_CELL}>Fecha</th>
                      </tr>
                    </thead>
                    <tbody>
                      {isLoading ? (
                        <tr>
                          <td colSpan={5} className="p-8 text-center text-slate-500">
                            Cargando...
                          </td>
                        </tr>
                      ) : isError ? (
                        <tr>
                          <td colSpan={5}>
                            {/* No `role` here, for the same reason as the
                                mobile card above. */}
                            <div className="rounded-xl border border-risk-critical/30 bg-slate-900">
                              <State
                                tone="error"
                                icon={<AlertLineArt />}
                                title="No se pudieron cargar los conflictos"
                                hint="Puede que la cola de conflictos no se esté mostrando. Reintentá la carga."
                                onRetry={() => void refetch()}
                                compact
                              />
                            </div>
                          </td>
                        </tr>
                      ) : items.length === 0 ? (
                        <tr>
                          <td colSpan={5}>
                            <State
                              tone="empty"
                              icon={<AlertLineArt />}
                              title="No hay conflictos"
                              hint="Las reglas y el modelo coinciden en todas las transacciones."
                              compact
                            />
                          </td>
                        </tr>
                      ) : (
                        items.map((txn) => (
                          <tr
                            key={txn.id}
                            className="border-b border-slate-800/50 hover:bg-slate-800/40 transition-colors"
                          >
                            <td className="px-4 py-3">
                              <ConflictLink txn={txn} />
                            </td>
                            <td className={cn("px-4 py-3", NUMERIC_CELL)}>
                              {formatMoney(txn.amount, txn.currency)}
                            </td>
                            <td className="px-4 py-3">
                              <ScorePair txn={txn} />
                            </td>
                            <td className={cn("px-4 py-3", NUMERIC_CELL)}>
                              {txn.risk_score == null
                                ? NO_VALUE
                                : txn.risk_score.toFixed(1)}
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-400">
                              {formatTimestamp(txn.created_at)}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Pagination. NOT migrated to `Button`, for the same reason as
                    on `TransactionsPage` and `AlertsPage`: these are a FILLED
                    neutral (`bg-slate-800` resting, `bg-slate-700` hover,
                    `disabled:opacity-40`) and the closest variant, `secondary`,
                    is transparent-with-a-border at rest that fills on hover —
                    adopting it would invert both states. A filled-neutral
                    variant is a DESIGN addition; reported, not made.

                    The two treatments that are NOT a variant question are
                    composed over the hand-rolled string, exactly as on the
                    sibling pages: `FOCUS_RING`, and the house
                    `max-md:min-h-[40px]` — `px-3 py-1` on a `text-xs` line box
                    is 24px, well under the floor. Neither changes a resting or
                    hovered colour. */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between p-3 border-t border-slate-800">
                    <span className="text-xs text-slate-500">
                      Pág. {shownPage} de {totalPages}
                    </span>
                    <div className="flex gap-1">
                      <button
                        onClick={() => goToPage(Math.max(DEFAULT_PAGE, shownPage - 1))}
                        disabled={shownPage <= DEFAULT_PAGE}
                        className={cn(
                          "px-3 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed",
                          FOCUS_RING,
                          "max-md:min-h-[40px]",
                        )}
                      >
                        Anterior
                      </button>
                      <button
                        onClick={() => goToPage(Math.min(totalPages, shownPage + 1))}
                        disabled={shownPage >= totalPages}
                        className={cn(
                          "px-3 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed",
                          FOCUS_RING,
                          "max-md:min-h-[40px]",
                        )}
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
    </div>
  );
}