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
