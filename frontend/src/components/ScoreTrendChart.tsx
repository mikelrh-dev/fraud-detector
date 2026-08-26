import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { THEME, formatCompactTick } from "../lib/chart-theme";
import { ChartTooltip } from "./ChartTooltip";

interface DailyAverage {
  date: string;
  avgScore: number;
}

interface ScoreTrendChartProps {
  data: DailyAverage[];
}

export default function ScoreTrendChart({ data }: ScoreTrendChartProps) {
  if (data.length === 0) {
    return (
      <div className="bg-slate-900 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">
          Tendencia de Score (7 días)
        </h3>
        <div className="flex items-center justify-center h-[200px] text-slate-500 text-sm">
          Sin datos suficientes
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-300">
          Tendencia de Score Promedio
        </h3>
        {/* Custom legend dot — replaces recharts' default legend chrome */}
        <span className="flex items-center gap-1.5 text-xs text-slate-400">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-risk-warn" />
          Score Promedio
        </span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={THEME.risk.warn} stopOpacity={0.18} />
              <stop offset="100%" stopColor={THEME.risk.warn} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            horizontal={true}
            vertical={false}
            strokeDasharray="3 3"
            stroke={THEME.gridSoft}
          />
          <XAxis
            dataKey="date"
            tick={{ fill: THEME.axis.tick, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: THEME.axis.tick, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatCompactTick}
          />
          <Tooltip
            cursor={{ stroke: THEME.gridSoft, strokeWidth: 1 }}
            content={<ChartTooltip valueFormatter={(v) => v.toFixed(1)} />}
          />
          <Area
            type="monotone"
            dataKey="avgScore"
            name="Score Promedio"
            stroke={THEME.risk.warn}
            strokeWidth={2.5}
            fill="url(#trend-fill)"
            dot={false}
            activeDot={{
              r: 4,
              strokeWidth: 2,
              stroke: THEME.pageBg,
              fill: THEME.risk.warn,
            }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export type { DailyAverage };

/**
 * Build daily average scores from a list of transactions.
 * Groups by day, computes average risk_score for each day.
 */
export function buildDailyAverages(
  transactions: { risk_score: number | null; created_at: string }[],
  days = 7,
): DailyAverage[] {
  const groupMap = new Map<string, number[]>();

  const now = new Date();
  const cutoff = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);

  for (const tx of transactions) {
    if (!tx.risk_score) continue;
    const d = new Date(tx.created_at);
    if (d < cutoff) continue;
    const key = d.toISOString().slice(0, 10);
    const arr = groupMap.get(key) || [];
    arr.push(tx.risk_score);
    groupMap.set(key, arr);
  }

  const result: DailyAverage[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    const key = d.toISOString().slice(0, 10);
    const scores = groupMap.get(key);
    if (scores && scores.length > 0) {
      const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
      result.push({ date: key, avgScore: Math.round(avg * 10) / 10 });
    } else {
      result.push({ date: key, avgScore: 0 });
    }
  }

  return result;
}
