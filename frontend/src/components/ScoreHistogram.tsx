import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";

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
  // legitimate (green) for low scores, review (amber) for mid, fraud (red) for high
  if (label === "0-20" || label === "21-40") return "#22c55e";
  if (label === "41-60" || label === "61-80") return "#f59e0b";
  return "#ef4444";
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
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 12 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "8px",
              color: "#e2e8f0",
              fontSize: "13px",
            }}
            formatter={(value: number) => [value, "Transacciones"]}
          />
          <Legend
            wrapperStyle={{ fontSize: "12px", color: "#94a3b8" }}
            formatter={(value: string) => <span style={{ color: "#94a3b8" }}>{value}</span>}
          />
          <Bar dataKey="count" name="Transacciones" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-[#22c55e]" />
          Legítimo (0-40)
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-[#f59e0b]" />
          Revisión (41-80)
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded bg-[#ef4444]" />
          Fraude (81-100)
        </span>
      </div>
    </div>
  );
}
