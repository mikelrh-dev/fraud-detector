import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTransaction } from "../api/transactions";
import apiClient from "../api/client";

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

async function fetchReport(
  transactionId: string,
): Promise<ReportResponse | null> {
  try {
    const response = await apiClient.get<ReportResponse>(
      `/transactions/${transactionId}/report`,
    );
    return response.data;
  } catch (err: unknown) {
    if (
      err &&
      typeof err === "object" &&
      "response" in err &&
      (err as { response: { status: number } }).response.status === 202
    ) {
      // Pending — return a pending state
      return {
        transaction_id: transactionId,
        report_text: null,
        model_name: null,
        status: "pending",
        generation_time_ms: null,
        created_at: null,
        error_detail: null,
      };
    }
    if (
      err &&
      typeof err === "object" &&
      "response" in err &&
      (err as { response: { status: number } }).response.status === 404
    ) {
      return null;
    }
    return null;
  }
}

function statusToClassification(status: string): string {
  switch (status) {
    case "approved":
      return "legitimate";
    case "flagged":
      return "review";
    case "blocked":
      return "fraud";
    default:
      return "pending";
  }
}

const CLASSIFICATION_COLORS: Record<string, string> = {
  legitimate: "text-fraud-legitimate bg-fraud-legitimate-bg border-fraud-legitimate/30",
  review: "text-fraud-review bg-fraud-review-bg border-fraud-review/30",
  fraud: "text-fraud-fraud bg-fraud-fraud-bg border-fraud-fraud/30",
  pending: "text-slate-400 bg-slate-800 border-slate-600/30",
};

const CLASSIFICATION_LABELS: Record<string, string> = {
  legitimate: "Legítimo",
  review: "Revisión",
  fraud: "Fraude",
  pending: "Pendiente",
};

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

  useEffect(() => {
    if (!id) return;

    let cancelled = false;
    let pollInterval: ReturnType<typeof setInterval> | null = null;

    async function loadReport() {
      const result = await fetchReport(id!);
      if (cancelled) return;
      setReport(result);
      setReportLoading(false);

      // If pending, poll every 5s
      if (result?.status === "pending") {
        pollInterval = setInterval(async () => {
          const updated = await fetchReport(id!);
          if (cancelled) return;
          setReport(updated);
          if (updated?.status !== "pending") {
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
  const colorKey =
    CLASSIFICATION_COLORS[classification] || CLASSIFICATION_COLORS.pending;
  const classificationLabel =
    CLASSIFICATION_LABELS[classification] || classification;

  return (
    <div className="min-h-screen bg-slate-950">
      {/* Header */}
      <header className="bg-slate-900 border-b border-slate-800 px-6 py-3">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
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
          <span className="text-xs font-mono text-slate-500">{tx.id}</span>
          <span
            className={`ml-auto text-xs px-2 py-0.5 rounded-full font-medium border ${colorKey}`}
          >
            {classificationLabel}
          </span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6 space-y-6">
        {/* Transaction details */}
        <section className="bg-slate-900 rounded-lg border border-slate-800 p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">
            Información General
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <DetailField label="Monto" value={`$${tx.amount.toLocaleString("es-AR")}`} />
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
        <section className="bg-slate-900 rounded-lg border border-slate-800 p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">
            Score de Riesgo
          </h2>
          {tx.risk_score != null ? (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-slate-400">
                    Score General
                  </span>
                  <span className="text-sm font-bold text-slate-200">
                    {tx.risk_score.toFixed(1)} / 100
                  </span>
                </div>
                <div className="h-3 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${tx.risk_score}%`,
                      backgroundColor:
                        tx.risk_score > 70
                          ? "#ef4444"
                          : tx.risk_score > 40
                            ? "#f59e0b"
                            : "#22c55e",
                    }}
                  />
                </div>
              </div>

              {/* Score bar representation */}
              <div className="flex gap-1 h-2">
                {[0, 1, 2, 3, 4].map((bucket) => {
                const bucketMin = bucket * 20;
                  const filled = tx.risk_score! > bucketMin;
                  const color =
                    bucket >= 4
                      ? "#ef4444"
                      : bucket >= 3
                        ? "#f59e0b"
                        : "#22c55e";
                  return (
                    <div
                      key={bucket}
                      className="flex-1 rounded"
                      style={{
                        backgroundColor: filled ? color : "#1e293b",
                        opacity: filled ? 1 : 0.3,
                      }}
                    />
                  );
                })}
              </div>

              <div className="flex justify-between text-[10px] text-slate-500">
                <span>0</span>
                <span>20</span>
                <span>40</span>
                <span>60</span>
                <span>80</span>
                <span>100</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              Score no disponible para esta transacción.
            </p>
          )}
        </section>

        {/* LLM Report */}
        <section className="bg-slate-900 rounded-lg border border-slate-800 p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">
            Reporte LLM
          </h2>

          {reportLoading ? (
            <div className="text-sm text-slate-500">Cargando reporte...</div>
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
              <div className="bg-slate-800 rounded-lg p-4">
                <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans leading-relaxed">
                  {report.report_text || "Sin contenido"}
                </pre>
              </div>
            </div>
          )}
        </section>
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
