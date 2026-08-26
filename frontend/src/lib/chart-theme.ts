/**
 * Central color theme for recharts components.
 *
 * DUPLICATION CONSTRAINT: these hex values MUST stay identical to the CSS
 * tokens declared in `src/index.css` (@theme `--color-risk-*`, neutral
 * slates). Tailwind v4 does not expose @theme variables to JS yet; once it
 * does (@theme inline / var() interop), source these values from CSS instead.
 * The unit test `src/tests/chart-theme.test.ts` guards both sides.
 */
export interface ChartTooltipStyle {
  backgroundColor: string;
  border: string;
  borderRadius: string;
  color: string;
  fontSize: string;
}

export interface ChartTheme {
  axis: {
    tick: string;
    line: string;
  };
  grid: string;
  /** slate-800 — softer grid lines / bar tracks on slate-900 cards. */
  gridSoft: string;
  /** Track drawn behind each histogram bucket (Bar `background`). */
  barTrack: string;
  /** Page background (slate-950) — activeDot stroke so dots punch out. */
  pageBg: string;
  /** Bar-chart hover cursor fill (slate-800 at 40%). */
  tooltipCursor: string;
  tooltip: ChartTooltipStyle;
  legendText: string;
  risk: {
    clean: string; /* --color-risk-clean   (#22c55e / green-500) */
    warn: string; /*   --color-risk-warn    (#f59e0b / amber-500) */
    critical: string; /* --color-risk-critical (#ef4444 / red-500)  */
  };
}

export const THEME: ChartTheme = {
  axis: {
    tick: "#94a3b8", // slate-400  (--color-text-muted)
    line: "#334155", // slate-700  (--color-divider)
  },
  grid: "#334155", // slate-700 (--color-divider)
  gridSoft: "#1e293b", // slate-800 (--color-border-subtle)
  barTrack: "#1e293b", // slate-800 (--color-border-subtle)
  pageBg: "#020617", // slate-950 (--color-page-bg)
  tooltipCursor: "rgba(30, 41, 59, 0.4)", // slate-800/40
  tooltip: {
    backgroundColor: "#1e293b", // slate-800
    border: "1px solid #334155", // slate-700
    borderRadius: "8px",
    color: "#e2e8f0", // slate-200
    fontSize: "13px",
  },
  legendText: "#94a3b8", // slate-400
  risk: {
    clean: "#22c55e",
    warn: "#f59e0b",
    critical: "#ef4444",
  },
};

/**
 * Compact axis-tick formatter: values >= 1000 render as `N.Nk`
 * (e.g. 1500 -> "1.5k"), everything else renders as a plain integer.
 */
export function formatCompactTick(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : `${value}`;
}
