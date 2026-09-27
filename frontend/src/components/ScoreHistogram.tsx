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

// Contiguous half-open intervals [min, max). The previous definition used
// inclusive bounds with a one-unit step (0-20, 21-40, ...), which silently
// dropped every score in a float gap: 20.5, 40.5, 60.5 and 80.5 matched no
// bucket, so the bars did not sum to the transaction count and nothing on the
// chart contradicted the discrepancy.
const BUCKETS = [
  { min: 0, max: 20, label: "0-20" },
  { min: 20, max: 40, label: "20-40" },
  { min: 40, max: 60, label: "40-60" },
  { min: 60, max: 80, label: "60-80" },
  { min: 80, max: 101, label: "80-100" },
];

/** Buckets are coloured by position so the palette cannot drift from the ranges. */
const BUCKET_TONES: readonly string[] = [
  THEME.risk.clean,
  THEME.risk.clean,
  THEME.risk.warn,
  THEME.risk.warn,
  THEME.risk.critical,
];

function getBucketColor(index: number): string {
  return BUCKET_TONES[index] ?? THEME.risk.clean;
}

export function buildBuckets(scores: number[]): HistogramBucket[] {
  const counts = new Array(BUCKETS.length).fill(0);

  for (const raw of scores) {
    if (!Number.isFinite(raw)) continue;
    // Clamp into range so an out-of-contract value is still counted rather
    // than dropped, and never falls through every bucket.
    const score = Math.min(100, Math.max(0, raw));
    for (let i = 0; i < BUCKETS.length; i++) {
      const { min, max } = BUCKETS[i];
      if (score >= min && score < max) {
        counts[i]++;
        break;
      }
    }
  }

  return BUCKETS.map((bucket, i) => ({
    range: bucket.label,
    count: counts[i],
    color: getBucketColor(i),
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
