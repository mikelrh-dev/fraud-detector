import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { THEME } from "../lib/chart-theme";

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
      <h3 className="text-sm font-semibold text-slate-300 mb-3">
        Tendencia de Score Promedio
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={THEME.grid} />
          <XAxis
            dataKey="date"
            tick={{ fill: THEME.axis.tick, fontSize: 11 }}
            axisLine={{ stroke: THEME.axis.line }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: THEME.axis.tick, fontSize: 11 }}
            axisLine={{ stroke: THEME.axis.line }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{ ...THEME.tooltip }}
            labelFormatter={(label: string) => `Fecha: ${label}`}
            formatter={(value: number) => [`${value.toFixed(1)}`, "Score Promedio"]}
          />
          <Line
            type="monotone"
            dataKey="avgScore"
            stroke={THEME.risk.warn}
            strokeWidth={2}
            dot={{ fill: THEME.risk.warn, r: 3 }}
            activeDot={{ r: 5, fill: THEME.risk.warn }}
            name="Score Promedio"
          />
        </LineChart>
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
