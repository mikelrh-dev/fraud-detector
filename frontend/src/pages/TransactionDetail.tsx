import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "@phosphor-icons/react";
import { getTransaction } from "../api/transactions";
import type { ScoreResponse, Transaction } from "../api/transactions";
import apiClient from "../api/client";
import { parseReportLines, type ReportBlock } from "../lib/report-format";
import { formatMoney } from "../lib/money";
import { formatTimestamp } from "../lib/datetime";
import { MAIN_LANDMARK_ID } from "../lib/focusable";
import {
  classificationPillClass,
  classificationText,
} from "../lib/classification";
import { ScoreResultCard } from "./ScoreResultCard";
import { PageTransition } from "../components/PageTransition";
import { ShapAttributionCard } from "../components/ShapAttributionCard";

interface ReportResponse {
  transaction_id: string;
  report_text: string | null;
  model_name: string | null;
  status: string;
  generation_time_ms: number | null;
  created_at: string | null;
  error_detail: string | null;
}

function fetchTransaction(id: string) {
  return getTransaction(id);
}

/**
 * Outcome of asking for the LLM report.
 *
 * A31: this used to return `null` for every outcome that was not a 202 or a
 * 404, so a 500 from a dead worker rendered as "No hay reporte disponible para
 * esta transacción" — telling the analyst the report does not exist when in
 * fact the request failed. Those are different claims, and on a fraud
 * investigation the second one is the dangerous one: an analyst concludes
 * there is nothing to see when the system never looked.
 */
type ReportFetch =
  | { kind: "report"; report: ReportResponse }
  | { kind: "absent" }
  | { kind: "failed"; status?: number };

async function fetchReport(transactionId: string): Promise<ReportFetch> {
  try {
    const response = await apiClient.get<ReportResponse>(
      `/transactions/${transactionId}/report`,
    );
    return { kind: "report", report: response.data };
  } catch (err: unknown) {
    const status =
      err &&
      typeof err === "object" &&
      "response" in err &&
      (err as { response: { status: number } }).response.status;

    if (status === 202) {
      // Still being generated.
      return {
        kind: "report",
        report: {
          transaction_id: transactionId,
          report_text: null,
          model_name: null,
          status: "pending",
          generation_time_ms: null,
          created_at: null,
          error_detail: null,
        },
      };
    }

    if (status === 404) {
      // Genuinely absent: the worker has not produced one and is not trying.
      return { kind: "absent" };
    }

    // A 5xx, a network failure, an aborted request: we do not know. Say so
    // instead of asserting the report does not exist.
    return { kind: "failed", status: status as number | undefined };
  }
}

/**
 * Status → classification.
 *
 * Was duplicated byte-for-byte in api/transactions.ts; an unknown status now
 * falls through as itself so the classification helpers classify it as
 * neutral instead of silently guessing.
 */
function statusToClassification(status: string): string {
  return STATUS_TO_CLASSIFICATION[status] ?? status;
}

const STATUS_TO_CLASSIFICATION: Record<string, string> = {
  approved: "legitimate",
  flagged: "review",
  blocked: "fraud",
};

/**
 * Map a fetched transaction into the ScoreResponse shape consumed by
 * ScoreResultCard. fired_rules is a client-side adapter constant only —
 * it is never part of any GET API response (not persisted in fraud_scores).
 */
function buildScoreResponse(tx: Transaction): ScoreResponse {
  return {
    transaction_id: tx.id,
    rule_score: tx.scoring?.rule_score ?? 0,
    ml_score: tx.scoring?.ml_score ?? 0,
    ensemble_score: tx.scoring?.ensemble_score ?? tx.risk_score ?? 0,
    threshold: tx.scoring?.threshold ?? 0,
    classification:
      tx.scoring?.classification ?? statusToClassification(tx.status),
    fired_rules: [],
    created_at: tx.created_at,
  };
}

/**
 * Copy-to-clipboard button for the LLM report. Swaps Copy → Check for two
 * seconds on success; degrades silently when the clipboard API is missing.
 */
function CopyReportButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const handleCopy = async () => {
    try {
      if (!navigator.clipboard?.writeText) return;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable (permissions / insecure context): no-op.
    }
  };

  // Not on `Button`, and the reason is a gap in the design system rather than
  // a divergence from it. This is an ICON-ONLY control — `h-8 w-8`, no label,
  // no text — and `BTN_SIZES` is `sm`/`md`, both of which set horizontal
  // padding. At 32px wide with `px-3` (12px a side) the content box is 8px, so
  // the 16px glyph would overflow it and the box would stop being square.
  //
  // `secondary` is NOT the match, and the honest reason is only the geometry
  // above. An earlier version of this comment also claimed the resting text
  // colour was unoverridable, on the grounds that `.text-slate-300` sorts AFTER
  // `.text-slate-400` so the variant would win. That is BACKWARDS: Tailwind
  // emits `.text-slate-300` BEFORE `.text-slate-400`, so the later rule is the
  // one the page already carries — `className="text-slate-400
  // hover:text-slate-200"` would win on stylesheet order and apply cleanly.
  // The stated reason does not hold, and it is withdrawn rather than left to
  // justify anything.
  //
  // So what is actually left is the size: `BTN_SIZES` has no icon-only entry,
  // and both of the ones it has set horizontal padding. An `icon` size in
  // `BTN_SIZES` is what this control needs, and that is a DESIGN addition, so
  // it is reported rather than made. The concrete cost meanwhile is that this
  // control has no focus ring of its own and relies on whatever the user agent
  // draws.
  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? "Copiado" : "Copiar reporte"}
      className="btn-motion active:scale-[0.98] inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800 hover:text-slate-200 max-md:min-h-[40px]"
    >
      {copied ? (
        <Check size={16} weight="regular" className="text-risk-clean" />
      ) : (
        <Copy size={16} weight="regular" />
      )}
    </button>
  );
}

/** Light-markdown renderer for the completed report body. */
function ReportBody({ text }: { text: string }) {
  const blocks: ReportBlock[] = parseReportLines(text);
  return (
    <div
      data-testid="report-body"
      className="animate-report-in space-y-2 bg-slate-800 rounded-lg p-4"
    >
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          return block.level === 2 ? (
            <p
              key={index}
              className="text-base font-semibold text-slate-100 whitespace-pre-wrap"
            >
              {block.text}
            </p>
          ) : (
            <p
              key={index}
              className="text-sm font-semibold text-slate-200 whitespace-pre-wrap"
            >
              {block.text}
            </p>
          );
        }
        if (block.type === "list") {
          return (
            <ul key={index} className="list-disc space-y-1 pl-5">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} className="text-sm text-slate-300">
                  {item}
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p
            key={index}
            className="text-sm leading-relaxed whitespace-pre-wrap text-slate-300 font-sans"
          >
            {block.text}
          </p>
        );
      })}
    </div>
  );
}

export default function TransactionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: tx,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["transaction", id],
    queryFn: () => fetchTransaction(id!),
    enabled: !!id,
  });

  // Poll report if pending
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [reportLoading, setReportLoading] = useState(true);
  // A31: tracked separately from `report === null`, which now means "the
  // worker has not produced one", so a failed request is not reported as an
  // absent report.
  const [reportError, setReportError] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    function apply(result: ReportFetch) {
      if (result.kind === "report") {
        setReport(result.report);
        setReportError(null);
      } else if (result.kind === "absent") {
        setReport(null);
        setReportError(null);
      } else {
        setReport(null);
        setReportError(result.status ?? null);
      }
    }

    async function loadReport() {
      const result = await fetchReport(id!);
      if (cancelled) return;
      apply(result);
      setReportLoading(false);

      // If pending, poll every 5s
      if (result.kind === "report" && result.report.status === "pending") {
        pollInterval = setInterval(async () => {
          const updated = await fetchReport(id!);
          if (cancelled) return;
          apply(updated);
          if (updated.kind !== "report" || updated.report.status !== "pending") {
            if (pollInterval) clearInterval(pollInterval);
          }
        }, 5000);
      }
    }

    loadReport();

    return () => {
      cancelled = true;
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [id]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-slate-500">Cargando...</div>
      </div>
    );
  }

  if (error || !tx) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        {/* `role="alert"`: the transaction could not be fetched, or does not
            exist. A link deep to a transaction that an analyst cannot open is
            the exact case where silence is worst -- the user has no other way to
            learn the request failed rather than the record being absent.

            This is the block the fix for the list's failure UI was justified by,
            and it had no live region at all. The `reportError` block further
            down the same file has had one all along, so the two failure UIs in
            one page were inconsistent with each other. */}
        <div role="alert" className="text-center" data-testid="detail-error">
          <p className="text-red-400 mb-4">
            {error ? "Error al cargar la transacción" : "Transacción no encontrada"}
          </p>
          {/* Unmigrated: a text link, not a button. `ghost` would drop the
              underline and the `text-sm`, and `secondary` would add a border
              and a background. Neither is this control. */}
          <button
            onClick={() => navigate("/dashboard")}
            className="text-sm text-slate-400 hover:text-slate-200 underline"
          >
            Volver al Dashboard
          </button>
        </div>
      </div>
    );
  }

  const classification = statusToClassification(tx.status);
  const colorKey = classificationPillClass(classification);
  const classificationLabel = classificationText(classification);

  return (
    <div className="min-h-screen bg-slate-950 overflow-x-hidden">
      {/* Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-6 py-3">
        <div className="max-w-5xl mx-auto flex items-center gap-3 flex-wrap min-w-0">
          {/* Unmigrated, same reason as the copy control above: no icon-only
              size. `ghost` adds `px-3 py-1.5`, which on a 20px box leaves no
              content box at all.

              The accessible name this control was reported as MISSING is no
              longer missing — see the `aria-label` below. That defect was fixed
              in its own commit (1bdf0e7), which is exactly what this comment
              used to ask for, and it left the "REPORTED, NOT FIXED" note in
              place above the very attribute that answers it. The note is
              removed rather than left contradicting the line under it. The
              "two such controls" figure was wrong too: this page has no
              unnamed icon button now, and had one at most, not two.

              THE HIT AREA IS NOW THE FLOOR, and this is the half of the gap that
              was not a design question. The box was 20px — the `w-5 h-5` glyph
              and nothing else — while every other icon-only control in the
              product carries `max-md:min-h-[40px]`. Applying the same
              `max-md:` treatment to BOTH axes reaches 40x40 on a touch
              viewport: `min-h` alone would have left a 40x20 target, which is
              under the floor on the axis that matters less and so does not clear
              it. The glyph stays at `w-5 h-5` — the hit area grew, the icon did
              not — and the desktop box is untouched, because the 40px floor is
              a touch-viewport concern and the copy control above it takes the
              same view. An icon-only `BTN_SIZES` entry is still the real fix and
              is still reported, not made. */}
          <button
            type="button"
            // The icon carries no text, so without this the control is announced
            // as a bare "button" — on the one control that gets you off a
            // not-found page. `aria-hidden` on the svg stops the graphic being
            // read as content; the name comes from here.
            aria-label="Volver al dashboard"
            onClick={() => navigate("/dashboard")}
            className="text-slate-400 hover:text-slate-200 transition-colors max-md:min-h-[40px] max-md:min-w-[40px] max-md:inline-flex max-md:items-center max-md:justify-center"
          >
            <svg
              aria-hidden="true"
              focusable="false"
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 19l-7-7m0 0l7-7m-7 7h18"
              />
            </svg>
          </button>
          <h1 className="text-sm font-semibold text-slate-200">
            Detalle de Transacción
          </h1>
          <span className="text-xs font-mono text-slate-500 truncate min-w-0">{tx.id}</span>
          <span
            className={`ml-auto text-xs px-2 py-0.5 rounded-full font-medium border ${colorKey}`}
          >
            {classificationLabel}
          </span>
        </div>
      </header>

      <main id={MAIN_LANDMARK_ID} tabIndex={-1} className="max-w-5xl mx-auto p-6 space-y-6">
        <PageTransition>
        {/* Transaction details */}
        <section className="bg-slate-900 rounded-lg border border-slate-800 p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">
            Información General
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <DetailField label="Monto" value={formatMoney(tx.amount, tx.currency)} />
            <DetailField label="Moneda" value={tx.currency} />
            <DetailField label="Comercio" value={tx.merchant_name} />
            <DetailField label="Categoría" value={tx.merchant_category || "—"} />
            <DetailField label="Tarjeta" value={`****${tx.card_last4}`} />
            <DetailField label="Estado" value={tx.status} />
            <DetailField
              label="Creado"
              value={formatTimestamp(tx.created_at)}
            />
            <DetailField
              label="Actualizado"
              value={formatTimestamp(tx.updated_at)}
            />
          </div>
        </section>

        {/* Scoring breakdown */}
        {tx.scoring ? (
          <ScoreResultCard result={buildScoreResponse(tx)} />
        ) : (
          <section className="bg-slate-900 rounded-lg border border-slate-800 p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-4">
              Score de Riesgo
            </h2>
            <p className="text-sm text-slate-500">
              Score no disponible para esta transacción.
            </p>
          </section>
        )}

        {/* SHAP attribution (FRD-SHP-002) — renders null when absent */}
        <ShapAttributionCard
          contributions={tx.scoring?.shap_contributions}
        />

        {/* LLM Report */}
        <section className="bg-slate-900 rounded-lg border border-slate-800 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-300">
              Reporte LLM
            </h2>
            {report !== null &&
              report.status === "completed" &&
              report.report_text && (
                <CopyReportButton text={report.report_text} />
              )}
          </div>

          {reportLoading ? (
            <div className="text-sm text-slate-500">Cargando reporte...</div>
          ) : reportError !== null ? (
            // A31: a failed request must not read as an absent report. "We
            // could not ask" and "there is nothing there" are different claims,
            // and an analyst investigating fraud needs to know which one they
            // are looking at.
            <div
              role="alert"
              className="flex flex-col items-center px-6 py-8 text-center"
              data-testid="report-error"
            >
              <p className="text-sm font-medium text-slate-300">
                No se pudo consultar el reporte
              </p>
              <p className="mt-1 max-w-xs text-xs text-slate-500">
                {reportError
                  ? `El servicio respondió con un error (${reportError}). El reporte puede existir; no se pudo verificar.`
                  : "No se pudo contactar al servicio. El reporte puede existir; no se pudo verificar."}
              </p>
            </div>
          ) : report === null ? (
            <div className="text-sm text-slate-500">
              No hay reporte disponible para esta transacción.
            </div>
          ) : report.status === "pending" ? (
            <div className="flex items-center gap-3 text-sm text-yellow-400">
              <svg
                className="w-4 h-4 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Generando reporte...
            </div>
          ) : report.status === "failed" ? (
            /* `role="alert"`, matching the `reportError` block above it: a
               report that came back failed is a failure the user asked about and
               is waiting on, and this file already had one announced failure
               next to an unannounced one. */
            <div role="alert" data-testid="report-status-failed">
              <p className="text-sm text-red-400 mb-2">
                {report.error_detail || "El reporte no pudo generarse."}
              </p>
              {report.report_text && (
                <pre className="text-sm text-slate-400 whitespace-pre-wrap font-sans bg-slate-800 rounded-lg p-3">
                  {report.report_text}
                </pre>
              )}
            </div>
          ) : (
              <div>
                {report.model_name && (
                  <p className="text-xs text-slate-500 mb-2">
                    Modelo: {report.model_name}
                    {report.generation_time_ms != null &&
                      ` · ${report.generation_time_ms}ms`}
                  </p>
                )}
                {report.report_text ? (
                  <ReportBody text={report.report_text} />
                ) : (
                  <div className="bg-slate-800 rounded-lg p-4">
                    <p className="text-sm text-slate-300 font-sans">
                      Sin contenido
                    </p>
                  </div>
                )}
              </div>
          )}
        </section>
        </PageTransition>
      </main>
    </div>
  );
}

function DetailField({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>
      <p className="text-xs text-slate-500 mb-0.5">{label}</p>
      <p className="text-sm text-slate-200">{value}</p>
    </div>
  );
}
