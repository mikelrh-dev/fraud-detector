import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
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
import { formatTimestamp } from "../lib/datetime";
import { MAIN_LANDMARK_ID } from "../lib/focusable";
import {
  DEFAULT_PAGE,
  LIST_PARAMS,
  clampPage,
  fetchClampedPage,
  parseChoice,
  parseIsoDate,
  parsePage,
  writeListParams,
} from "../lib/list-query";
import {
  FOCUS_RING,
  NUMERIC_CELL,
  TABLE_HEADER_CELL,
  TABLE_HEADER_NUMERIC,
  BTN_BASE,
  BTN_SIZES,
  BTN_VARIANTS,
  cn,
} from "../lib/ui";

/**
 * The filter values a link may carry. `null` is "no filter" and has no
 * spelling, which is why the "Todas" pill's key is `null` rather than a
 * fourth string: an absent parameter and an unrecognised one both mean "every
 * transaction", and giving that state a value would give it a second spelling
 * in a shared link.
 */
const STATUS_FILTERS = ["legitimate", "review", "fraud"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

/**
 * The URL's word for a filter, translated into the one the transport takes.
 *
 * The link is written in the product's vocabulary because that is the
 * vocabulary of the screen it lands on — `?status=legitimate` is what the pill
 * says and what the classification column prints, so a person can read the
 * link, repeat it, and know what they will see. `approved` is the storage
 * detail behind it. `lib/list-query.ts` holds the rest of the contract,
 * including what an unrecognised value does.
 */
const STATUS_TO_API: Record<StatusFilter, string | undefined> = {
  legitimate: "approved",
  review: "flagged",
  fraud: "blocked",
};

const statusPills: { key: StatusFilter | null; label: string }[] = [
  { key: null, label: "Todas" },
  { key: "legitimate", label: "Legítimo" },
  { key: "review", label: "Revisión" },
  { key: "fraud", label: "Fraude" },
];

const PAGE_SIZE = 10;

export default function TransactionsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  /* ---------------------------------------------------------------- *
   * The filter, the date range and the page ARE the query string.
   *
   * They were `useState` until this commit, which meant a filtered view could
   * not be linked, bookmarked, reopened after a reload, or walked back to —
   * and a second copy of a filter in two places is two copies that can
   * disagree, with the rendered one decided by whichever wrote last. There is
   * no copy here. `parseChoice` and friends return the DEFAULT for a value
   * they do not recognise, so a hand-edited link degrades to the default
   * rather than rendering an empty table; see `lib/list-query.ts` for why the
   * rejected value is left in the address rather than silently stripped.
   * ---------------------------------------------------------------- */
  const statusFilter = parseChoice(
    searchParams.get(LIST_PARAMS.status),
    STATUS_FILTERS,
  );
  const dateFrom = parseIsoDate(searchParams.get(LIST_PARAMS.from)) ?? "";
  const dateTo = parseIsoDate(searchParams.get(LIST_PARAMS.to)) ?? "";
  const page = parsePage(searchParams.get(LIST_PARAMS.page));

  /**
   * Apply filters and return to the first page.
   *
   * The reset is not tidiness. A filter changes how many pages there are, so
   * carrying `page=4` across to a filter with one page of results lands the
   * user on a page that does not exist.
   */
  const applyFilters = (patch: Readonly<Record<string, string | null>>) => {
    setSearchParams(writeListParams(searchParams, patch, { resetPage: true }));
  };

  /** Move pages. Deliberately does NOT reset the page. */
  const goToPage = (next: number) => {
    setSearchParams(
      writeListParams(searchParams, {
        [LIST_PARAMS.page]: next === DEFAULT_PAGE ? null : String(next),
      }),
    );
  };

  const { data, isLoading, isError } = useQuery({
    queryKey: ["transactions", statusFilter, dateFrom, dateTo, page],
    // A shared link outlives the result set that produced it, so a page past
    // the end is re-requested as the last one. See `fetchClampedPage` for why
    // that is a second round trip rather than part of the query key.
    queryFn: () =>
      fetchClampedPage(page, (target) =>
        listTransactions({
          page: target,
          page_size: PAGE_SIZE,
          status: statusFilter ? STATUS_TO_API[statusFilter] : undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
        }),
      ),
    refetchOnMount: "always",
  });

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;
  /**
   * The page on screen, which is the requested one except when the link was
   * stale and the fetch was clamped. The URL keeps the requested number on
   * purpose: it is what the user asked for, and rewriting it would make the
   * back button mean "where I was" no longer.
   */
  const shownPage = clampPage(page, totalPages);

  return (
    <div className="min-h-screen bg-page-bg flex overflow-x-hidden">
      <Sidebar activeItem="transactions" />
      {/* The main landmark. The shell does not provide one — `<Sidebar>` is a
          sibling, and an element only gets the implicit `main` role when it is
          not inside sectioning content — so the page that owns the content has
          to own the landmark too. One per page: a second `<main>` is not a
          second landmark, it is invalid, and the skip link's target would
          become ambiguous. */}
      <main
        id={MAIN_LANDMARK_ID}
        tabIndex={-1}
        className="flex-1 p-6 overflow-y-auto"
        style={{ maxWidth: "var(--spacing-max-content)" }}
      >
        <PageTransition>
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-bold text-text-primary">Transacciones</h1>
          {/* A navigation control, so it stays a `<Link>` and composes the
              shared class constants rather than becoming a `Button`.
              `Button` renders a `<button>`, and making this one a button would
              cost middle-click, ctrl-click, "open in new tab" and the
              status-bar URL for no gain. DESIGN.md's Buttons section already
              prescribes exactly this composition, and it is what lets the link
              pick up the two things the hand-rolled string lacked: the shared
              keyboard-only focus ring, and an `enabled:`-gated hover.

              A real `ButtonLink` is the honest primitive for this shape; it is
              reported rather than invented in a migration commit. */}
          <Link
            to="/transactions/new"
            className={cn(
              BTN_BASE,
              BTN_VARIANTS.primary,
              BTN_SIZES.md,
            )}
          >
            <Plus size={16} aria-hidden="true" />
            Nueva Transacción
          </Link>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          {/* Status pills. NOT migrated, and this is a gap in the design system
              rather than a divergence from it.

              A segmented filter needs a SELECTED state, and `BTN_VARIANTS` has
              no pair for it: the selected treatment is `bg-slate-700
              text-slate-200` and the unselected is `bg-slate-800/50
              text-slate-400`, neither of which is `primary`, `secondary` or
              `ghost`. The SIZE is not the obstacle — these are `rounded-lg
              px-3 py-1.5 text-xs`, which is exactly `BTN_SIZES.sm` — so a
              selected/unselected pair is the only thing missing.

              Minting one is a DESIGN change, so it is reported rather than made.
              What it costs meanwhile, and what the test pins: these four
              controls have no focus ring at all, because the treatment they do
              carry was hand-rolled without `FOCUS_RING`. `AlertsPage` has the
              same pair in `rounded-full`, where a `Button` would additionally
              lose the radius — Tailwind emits `rounded`, `rounded-full` and
              `rounded-lg` in that stylesheet order, so the later `rounded-lg`
              from `BTN_SIZES` wins regardless of attribute order. */}
          <div className="flex gap-1.5">
            {statusPills.map((pill) => (
              <button
                key={pill.key}
                onClick={() => {
                  // `null` for the "Todas" pill: `writeListParams` deletes on
                  // a null, so choosing "every transaction" REMOVES the
                  // parameter instead of writing an empty one. The address
                  // returns to the bare path, which is the one worth sharing.
                  applyFilters({ [LIST_PARAMS.status]: pill.key });
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

          {/* Date range. The two inputs keep their own chrome and take only the
              shared FOCUS treatment, which is the half of the problem that is
              actually a defect.

              They cannot be `Input`: `INPUT_BASE` carries `w-full`, and these
              are intrinsic-width controls in a `flex ... ml-auto` row. Tailwind
              resolves two utilities of one property by stylesheet order, not
              attribute order, and it emits `w-auto` BEFORE `w-full` — so
              `className="w-auto"` loses and both fields would stretch to fill
              the row. The same holds for `px-3` over `px-2` and `py-2` over
              `py-1.5`: in both pairs the base sorts LATER, so the compact
              padding would be silently dropped and the control would grow.

              The focus ring IS fixed, and this is the landmine-3 change: a bare
              `focus:` ring paints on mouse click, which is wrong for a mouse
              user and the reason `FOCUS_RING` exists. It now paints on
              keyboard focus only, same hue (`--color-focus-ring`), same
              2px width. The only difference a user can observe is that clicking
              the field no longer flashes a ring. */}
          <div className="flex items-center gap-2 ml-auto">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                // An emptied date control reports "", which deletes the
                // parameter for the same reason the "Todas" pill does.
                applyFilters({ [LIST_PARAMS.from]: e.target.value });
              }}
              className={cn(
                "bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-300",
                FOCUS_RING,
              )}
            />
            <span className="text-xs text-slate-500">a</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => {
                applyFilters({ [LIST_PARAMS.to]: e.target.value });
              }}
              className={cn(
                "bg-slate-800 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-300",
                FOCUS_RING,
              )}
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
                  className="bg-slate-900 border border-slate-800 rounded-xl p-4 focus-within:border-slate-700"
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("a")) return;
                    navigate(`/transactions/${tx.id}`);
                  }}
                >
                  {/* Header row: merchant + amount */}
                  <div className="flex items-center justify-between mb-2">
                    <Link
                      to={`/transactions/${tx.id}`}
                      className={cn(
                        "text-sm font-medium text-slate-200 truncate rounded hover:text-slate-100 hover:underline underline-offset-2",
                        FOCUS_RING,
                      )}
                    >
                      {tx.merchant_name}
                    </Link>
                    <span className={`text-sm font-bold text-slate-100 ${NUMERIC_CELL}`}>
                  {formatMoney(tx.amount, tx.currency)}
                </span>
                  </div>
                  {/* Footer row: date + badge + score */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">
                      {formatTimestamp(tx.created_at)}
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
                          onClick={(e) => {
                            // The merchant cell is a real <Link>; see
                            // TransactionTable for why this guard exists.
                            if ((e.target as HTMLElement).closest("a")) return;
                            navigate(`/transactions/${tx.id}`);
                          }}
                          className="border-b border-slate-800/50 hover:bg-slate-800/40 focus-within:bg-slate-800/40 cursor-pointer transition-colors"
                        >
                          <td className="px-4 py-3 text-slate-200">
                            <Link
                              to={`/transactions/${tx.id}`}
                              className={cn(
                                "rounded hover:text-slate-100 hover:underline underline-offset-2",
                                FOCUS_RING,
                              )}
                            >
                              {tx.merchant_name}
                            </Link>
                          </td>
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
                            {formatTimestamp(tx.created_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Pagination. NOT migrated, and this is the design system's gap
                rather than a divergence from it.

                Both controls are a FILLED neutral (`bg-slate-800` resting,
                `bg-slate-700` hover) with `disabled:opacity-40`. `secondary` is
                the closest variant and is a different control: transparent with
                a border at rest, filling to `slate-800` on hover, dimmed to
                `disabled:opacity-50`. Adopting it would invert the resting and
                hovered states, which is the V-07 class of defect this
                refactor exists to remove.

                A filled-neutral variant is a DESIGN addition, so it is reported
                rather than made. Note that `TransactionTable` and `AlertsPage`
                carry the same two treatments, so the gap is product-wide, not
                local to this page. */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-xs text-slate-400">
                  Página {shownPage} de {totalPages} ({data?.total} transacciones)
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => goToPage(Math.max(DEFAULT_PAGE, shownPage - 1))}
                    disabled={shownPage <= DEFAULT_PAGE}
                    className="btn-motion active:scale-[0.98] px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Anterior
                  </button>
                  <button
                    onClick={() => goToPage(Math.min(totalPages, shownPage + 1))}
                    disabled={shownPage >= totalPages}
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
      </main>
    </div>
  );
}
