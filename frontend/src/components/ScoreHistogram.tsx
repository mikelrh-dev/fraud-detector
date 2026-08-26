import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { THEME, formatCompactTick } from "../lib/chart-theme";
import { ChartTooltip } from "./ChartTooltip";

interface HistogramBucket {
  range: string;
  count: number;
  color: string;
}

interface ScoreHistogramProps {
  scores: number[];
}

const BUCKETS = [
  { min: 0, max: 20, label: "0-20" },
  { min: 21, max: 40, label: "21-40" },
  { min: 41, max: 60, label: "41-60" },
  { min: 61, max: 80, label: "61-80" },
  { min: 81, max: 100, label: "81-100" },
];

function getBucketColor(label: string): string {
  // legitimate (clean) for low scores, review (warn) for mid, fraud (critical) for high
  if (label === "0-20" || label === "21-40") return THEME.risk.clean;
  if (label === "41-60" || label === "61-80") return THEME.risk.warn;
  return THEME.risk.critical;
}

function buildBuckets(scores: number[]): HistogramBucket[] {
  const counts = new Array(BUCKETS.length).fill(0);

  for (const score of scores) {
    for (let i = 0; i < BUCKETS.length; i++) {
      const { min, max } = BUCKETS[i];
      if (score >= min && score <= max) {
        counts[i]++;
        break;
      }
    }
  }

  return BUCKETS.map((bucket, i) => ({
    range: bucket.label,
    count: counts[i],
    color: getBucketColor(bucket.label),
  }));
}

export default function ScoreHistogram({ scores }: ScoreHistogramProps) {
  const data = buildBuckets(scores);

  return (
    <div className="bg-slate-900 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">
        Distribución de Scores
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data}>
          <XAxis
            dataKey="range"
            tick={{ fill: THEME.axis.tick, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: THEME.axis.tick, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
            tickFormatter={formatCompactTick}
          />
          <Tooltip
            cursor={{ fill: THEME.tooltipCursor, radius: 4 }}
            content={<ChartTooltip />}
          />
          <Bar
            dataKey="count"
            name="Transacciones"
            radius={[6, 6, 0, 0]}
            maxBarSize={48}
            background={{ fill: THEME.barTrack, rx: 6, ry: 6 }}
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {/* Custom legend dots — replaces recharts' default legend chrome */}
      <div className="flex gap-4 mt-2 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-risk-clean" />
          Legítimo (0-40)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-risk-warn" />
          Revisión (41-80)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-risk-critical" />
          Fraude (81-100)
        </span>
      </div>
    </div>
  );
}
