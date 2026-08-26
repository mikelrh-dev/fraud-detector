import { TooltipProps } from "recharts";
import { THEME } from "../lib/chart-theme";

type RechartsTooltipProps = TooltipProps<number, string>;

export interface ChartTooltipProps extends RechartsTooltipProps {
  /** Optional value formatter (e.g. `(v) => v.toFixed(1)` for averages). */
  valueFormatter?: (value: number) => string;
}

/**
 * Shared chart tooltip surface for every recharts instance (DESIGN.md —
 * Charts). Rendered via recharts' `content={<ChartTooltip />}` pattern so
 * the library injects `active` / `payload` / `label`. Zero hardcoded hex —
 * all chrome comes from Tailwind slate utilities, dot colors from payload.
 */
export function ChartTooltip({
  active,
  payload,
  label,
  valueFormatter,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="rounded-xl border border-slate-700/80 bg-slate-900/95 backdrop-blur-sm px-3 py-2 shadow-xl shadow-slate-950/50">
      <p className="font-mono uppercase text-[11px] tracking-wider text-slate-400">
        {String(label ?? "")}
      </p>
      <div className="mt-1 space-y-0.5">
        {payload.map((entry, index) => {
          const raw = Number(entry.value);
          const dot =
            entry.color ??
            entry.stroke ??
            entry.payload?.color ??
            THEME.legendText;
          return (
            <div
              key={`${entry.name ?? "series"}-${index}`}
              className="flex items-center justify-between gap-4"
            >
              <span className="flex items-center gap-1.5 text-xs text-slate-300">
                <span
                  aria-hidden="true"
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: dot }}
                />
                {entry.name}
              </span>
              <span className="font-mono tabular-nums text-right text-xs text-slate-100">
                {Number.isFinite(raw)
                  ? valueFormatter
                    ? valueFormatter(raw)
                    : String(raw)
                  : String(entry.value)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ChartTooltip;
