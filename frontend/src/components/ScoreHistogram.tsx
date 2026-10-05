import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { THEME, formatCompactTick } from "../lib/chart-theme";
import { ChartTooltip } from "./ChartTooltip";
import {
  classificationDotClass,
  classificationText,
  classificationTone,
  isKnownClassification,
  type ClassificationTone,
} from "../lib/classification";

/**
 * One row, as this chart needs it: the score, and the verdict the backend
 * actually recorded for it.
 *
 * The row is the input, not the bare score, and that is the whole fix. This
 * chart used to take `number[]` and colour the bars by POSITION — bucket 0-20
 * green, 40-60 amber, 80-100 red — under a legend that read
 * "Legítimo (0-40) / Revisión (41-80) / Fraude (81-100)".
 *
 * Nothing in this product classifies by score range. The threshold is TIERED BY
 * AMOUNT (`src/core/config.py:206-227`: 70 / 50 / 45 / 40 by amount band), and
 * the live verdict is routed on the LAYER scores by
 * `ScoringService._classify_routed` (`src/services/scoring_service.py:139`,
 * called at `:312`) rather than on any single number. So on a low-amount
 * transaction 76.46 is FRAUDE — and it was drawn inside the amber "Revisión"
 * bar, on the same screen whose table, directly below, called that row Fraude.
 *
 * (`EnsembleScorer.classify` in `src/services/ensemble.py` still compares a
 * score to a threshold, but only on the DEGRADED path — the one taken when the
 * model artifact failed to load. Citing it here would point a reader at the
 * path that does not run.)
 *
 * Re-deriving the verdict from the score here would have reproduced the same
 * lie with more code, and it is a scoring decision this component has no
 * business making: the amount is not in the score, and the row already carries
 * the answer. So the verdict is read, never recomputed.
 */
export interface ScoredRow {
  risk_score: number | null;
  classification: string | null;
}

/**
 * A bare score is a row whose verdict was not supplied — UNDETERMINED, which is
 * a state of its own and deliberately not `legitimate`. It stays accepted
 * because it is how this function was already called and because "scored but
 * unclassified" is a real row shape.
 */
export type ScoreSample = number | ScoredRow;

/** The slot an undetermined row stacks into, and how the legend names it. */
const UNDETERMINED = "undetermined";

/** Contiguous half-open intervals [min, max). The previous definition used
 *  inclusive bounds with a one-unit step (0-20, 21-40, ...), which silently
 *  dropped every score in a float gap: 20.5, 40.5, 60.5 and 80.5 matched no
 *  bucket, so the bars did not sum to the transaction count and nothing on the
 *  chart contradicted the discrepancy. */
const BUCKETS = [
  { min: 0, max: 20, label: "0-20" },
  { min: 20, max: 40, label: "20-40" },
  { min: 40, max: 60, label: "40-60" },
  { min: 60, max: 80, label: "60-80" },
  { min: 80, max: 101, label: "80-100" },
];

/**
 * Tone → chart fill, from the JS mirror of the CSS tokens.
 *
 * `neutral` is slate-700 (`THEME.axis.line`) and not `THEME.barTrack`: the track
 * behind each bucket is slate-800, so a neutral segment painted in the track
 * colour would be invisible — an "undetermined" row drawn as nothing, which is
 * the same claim as drawing it green.
 */
const TONE_FILL: Record<ClassificationTone, string> = {
  clean: THEME.risk.clean,
  warn: THEME.risk.warn,
  critical: THEME.risk.critical,
  neutral: THEME.axis.line,
};

/**
 * Stack order: severity, least to most.
 *
 * A stack's meaning is positional — "red sits on top" is something a reader
 * learns once. Deriving the order from which verdict happened to appear first
 * in the data would make the same rows stack differently for two analysts, and
 * would make slot 1 mean different things in different buckets.
 */
const TONE_RANK: Record<ClassificationTone, number> = {
  clean: 0,
  warn: 1,
  critical: 2,
  neutral: 3,
};

/** The three verdicts the backend emits, always present as stack slots. */
const BASE_SLOTS = ["legitimate", "review", "fraud"] as const;

/** One verdict's share of one bucket. */
export interface HistogramSegment {
  classification: string;
  label: string;
  tone: ClassificationTone;
  /** recharts fill — the JS mirror of the CSS token. */
  color: string;
  /** Legend-dot token class. */
  dotClass: string;
  count: number;
}

export interface HistogramBucket {
  range: string;
  /** Sum of the segments — the height of the bar. */
  count: number;
  /** One entry per stack slot, in stack order. Zero counts included, so every
   *  bucket stacks on the same slots and a colour cannot drift position. */
  segments: HistogramSegment[];
}

function slotFor(sample: ScoreSample): { slot: string; raw: number | null } {
  if (typeof sample === "number") return { slot: UNDETERMINED, raw: sample };
  const classification = sample.classification;
  return {
    // Every unrecognised verdict collapses into the one undetermined slot
    // rather than becoming a slot of its own: `classificationTone` already
    // treats them all alike, and two legend rows both reading "Pendiente"
    // would be a new way for the chart to mislead.
    //
    // The null check is written out rather than left to
    // `isKnownClassification`, which is a plain boolean and does not narrow —
    // and a slot typed `string | null` would put `null` into a Map key.
    slot:
      classification !== null && isKnownClassification(classification)
        ? classification
        : UNDETERMINED,
    raw: sample.risk_score,
  };
}

function segmentOf(slot: string, count: number): HistogramSegment {
  // `undetermined` has no classification string of its own, and passing it
  // through `classificationTone` would be the same thing by another name.
  const tone =
    slot === UNDETERMINED ? "neutral" : classificationTone(slot);
  return {
    classification: slot,
    label: slot === UNDETERMINED ? "Pendiente" : classificationText(slot),
    tone,
    color: TONE_FILL[tone],
    dotClass: slot === UNDETERMINED ? "bg-slate-400" : classificationDotClass(slot),
    count,
  };
}

function compareSlots(a: string, b: string): number {
  const rank = TONE_RANK[segmentOf(a, 0).tone] - TONE_RANK[segmentOf(b, 0).tone];
  // Alphabetical within a tone, so the order never depends on input order.
  return rank !== 0 ? rank : a.localeCompare(b);
}

export function buildBuckets(samples: ReadonlyArray<ScoreSample>): HistogramBucket[] {
  const tallies = BUCKETS.map(() => new Map<string, number>());
  const seen = new Set<string>();

  for (const sample of samples) {
    const { slot, raw } = slotFor(sample);
    if (raw === null || !Number.isFinite(raw)) continue;
    // Clamp into range so an out-of-contract value is still counted rather
    // than dropped, and never falls through every bucket.
    const score = Math.min(100, Math.max(0, raw));
    const index = BUCKETS.findIndex(({ min, max }) => score >= min && score < max);
    if (index === -1) continue;
    tallies[index].set(slot, (tallies[index].get(slot) ?? 0) + 1);
    seen.add(slot);
  }

  // The three backend verdicts are always slots, even at zero, so the stack
  // keeps its shape on a window where every row is legitimate — and an empty
  // window still draws its five bucket tracks instead of a bare axis.
  const slots = [...new Set([...BASE_SLOTS, ...seen])].sort(compareSlots);

  return BUCKETS.map((bucket, index) => {
    const segments = slots.map((slot) => segmentOf(slot, tallies[index].get(slot) ?? 0));
    return {
      range: bucket.label,
      count: segments.reduce((sum, s) => sum + s.count, 0),
      segments,
    };
  });
}

export interface ScoreHistogramProps {
  transactions: ReadonlyArray<ScoredRow>;
}

export default function ScoreHistogram({ transactions }: ScoreHistogramProps) {
  const buckets = buildBuckets(transactions);
  const slots = buckets[0]?.segments ?? [];
  const totalOf = (slot: string) =>
    buckets.reduce((sum, b) => sum + (b.segments.find((s) => s.classification === slot)?.count ?? 0), 0);

  // recharts stacks by giving every <Bar> the same `stackId` and one flat
  // numeric field per slot, so the buckets become rows keyed by slot name.
  const rows = buckets.map((bucket) => {
    const row: Record<string, number | string> = { range: bucket.range };
    for (const segment of bucket.segments) row[segment.classification] = segment.count;
    return row;
  });

  // Only verdicts with something in them. A legend entry for an empty verdict
  // is a claim that the chart cannot support, and it would also invite the
  // reader to hunt for a colour that is not on screen.
  const legend = slots
    .map((slot) => ({ ...slot, total: totalOf(slot.classification) }))
    .filter((slot) => slot.total > 0);

  return (
    <div className="bg-slate-900 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">
        Distribución de Scores
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows}>
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
          {slots.map((slot, index) => (
            <Bar
              key={slot.classification}
              dataKey={slot.classification}
              // The human verdict, so the shared tooltip names the segment the
              // reader is pointing at. It used to say "Transacciones", which
              // described the axis rather than the question being asked.
              name={slot.label}
              stackId="verdict"
              fill={slot.color}
              // Rounded only on the top of the stack: a radius on every segment
              // draws a rounded lip at each internal boundary.
              radius={
                index === slots.length - 1 ? ([6, 6, 0, 0] as [number, number, number, number]) : undefined
              }
              maxBarSize={48}
              // One track per category, on the bottom slot only. On every slot
              // they would overlap exactly and cost five times the nodes.
              background={
                index === 0
                  ? { fill: THEME.barTrack, rx: 6, ry: 6 }
                  : undefined
              }
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      {/*
        What this legend says, and what it deliberately does not.

        It counts the verdicts it drew. It does NOT map a score range to a
        verdict, because no such mapping exists here: the same score is a
        review at one amount and a fraud at another. The old legend asserted
        one anyway ("Fraude (81-100)"), which is how a 76.46 fraud came to be
        read as an amber "Revisión (41-80)" bar.

        The per-bucket half of the same question is answered by the tooltip,
        which lists each stack's count for the bucket under the cursor.
      */}
      <div
        data-testid="histogram-legend"
        className="flex flex-wrap gap-4 mt-2 text-xs text-slate-400"
      >
        {legend.map((entry) => (
          <span
            key={entry.classification}
            className="flex items-center gap-1.5"
          >
            <span
              aria-hidden="true"
              className={`h-2 w-2 rounded-full ${entry.dotClass}`}
            />
            {entry.label} ({entry.total})
          </span>
        ))}
      </div>
    </div>
  );
}
