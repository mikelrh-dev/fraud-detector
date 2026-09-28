import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "@phosphor-icons/react";
import { getTransaction } from "../api/transactions";
import type { ScoreResponse, Transaction } from "../api/transactions";
import apiClient from "../api/client";
import { parseReportLines, type ReportBlock } from "../lib/report-format";
import { formatMoney } from "../lib/money";
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
  // `secondary` is also not the match: it says `text-slate-300` where this
  // says `text-slate-400` and hovers to `text-slate-200` as well as filling,
  // and that hover-on-text half has no variant at all. It cannot be pushed
  // back through `className` — the built CSS has `.text-slate-300` (315) after
  // `.text-slate-400` (316), so the variant wins — which means adopting
  // `secondary` here would change the resting colour AND silently drop a
  // hover state.
  //
  // So: an `icon` size in `BTN_SIZES`, and possibly an `icon` variant, is what
  // this control needs. Both are DESIGN additions, so this is reported rather
  // than made. The concrete cost meanwhile is that this control has no focus
  // ring of its own and relies on whatever the user agent draws.
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
        <div className="text-center">
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
              size, and no variant whose resting/hover text matches
              `slate-400` → `slate-200`. `ghost` says `text-slate-400` hovering
              to `text-slate-100` and adds `px-3 py-1.5`, which on a 20px box
              leaves no content box at all.

              REPORTED, NOT FIXED, because it is out of scope for a tokenisation
              pass and needs a product decision on the copy: this control has
              NO ACCESSIBLE NAME. A screen reader announces "button" and
              nothing else, and there are two such controls on this page's
              failure path. The obvious label is already on screen elsewhere on
              the page ("Volver al Dashboard"), so it is a one-line fix — but
              it is a change to the accessibility tree, and it belongs in a
              commit that says it is doing that. */}
          <button
            onClick={() => navigate("/dashboard")}
            className="text-slate-400 hover:text-slate-200 transition-colors"
          >
            <svg
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

      <main className="max-w-5xl mx-auto p-6 space-y-6">
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
              value={new Date(tx.created_at).toLocaleString("es-AR")}
            />
            <DetailField
              label="Actualizado"
              value={new Date(tx.updated_at).toLocaleString("es-AR")}
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
            <div>
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
