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
import { needsVisibleDots, type DailyAverage } from "../lib/trend";
import { ChartTooltip } from "./ChartTooltip";

/**
 * Re-exported so the existing importers of this module keep resolving.
 *
 * `DailyAverage` and the two predicates now live in `lib/trend.ts`, because they
 * are pure data logic with no JSX and `lib/` is where this repo keeps that
 * (`lib/score.ts`, `lib/classification.ts`, `lib/list-query.ts`). Keeping them
 * here as well would have meant this file exporting three values beside its
 * component, and every extra value export is a Fast-Refresh warning on a file
 * that already carries one.
 *
 * `buildDailyAverages` stays HERE, which is the inconsistency a reader will
 * notice: `tests/honest-data.test.ts` imports it from this path, and moving it
 * would mean editing an existing test to accommodate a refactor. Recorded rather
 * than done.
 */
export type { DailyAverage };

interface ScoreTrendChartProps {
  data: DailyAverage[];
}

export default function ScoreTrendChart({ data }: ScoreTrendChartProps) {
  // "No data" means no day in the window had a score, not "every score was 0".
  // Counting the nulls keeps a partially-populated window renderable while an
  // empty one reaches the designed message below.
  const hasData = data.some((d) => d.avgScore !== null);

  if (!hasData) {
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

  // A window with data in it but no two adjacent days has no stroke to draw, and
  // `dot={false}` left it as a blank 200px panel with axes and no explanation —
  // a live panel claiming nothing. The dots are the fallback that makes the one
  // measurement visible; they are NOT a claim that the trend is flat.
  const showDots = needsVisibleDots(data);

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
            // Dots only where the line cannot speak for itself. On a measured
            // window they are omitted, which is why the switch above is a
            // decision about the DATA rather than a styling constant.
            dot={
              showDots
                ? { r: 4, strokeWidth: 2, stroke: THEME.pageBg, fill: THEME.risk.warn }
                : false
            }
            // Break the line across days with no data instead of interpolating
            // through a fabricated point. A zero here would render as a real
            // "risk 0" measurement.
            connectNulls={false}
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

/**
 * Build daily average scores from a list of transactions.
 * Groups by day, computes average risk_score for each day.
 */export function buildDailyAverages(
  transactions: { risk_score: number | null; created_at: string }[],
  days = 7,
): DailyAverage[] {
  const groupMap = new Map<string, number[]>();

  const now = new Date();
  const cutoff = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);

  for (const tx of transactions) {
    // `risk_score` of 0 is a legitimate score, so test for null explicitly —
    // a falsy check dropped the safest transactions from the trend.
    if (tx.risk_score === null || tx.risk_score === undefined) continue;
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
      // A day without transactions is a gap, not a score of zero. Returning 0
      // made a failed query render as a flat "risk 0" line with no error shown.
      result.push({ date: key, avgScore: null });
    }
  }

  return result;
}
