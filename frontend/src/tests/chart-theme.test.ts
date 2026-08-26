import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { THEME, formatCompactTick } from "../lib/chart-theme";

/**
 * Palette constants — MUST stay identical to the @theme values in src/index.css
 * (--color-risk-clean/warn/critical and neutral slates).
 */
const PALETTE = {
  clean: "#22c55e",
  warn: "#f59e0b",
  critical: "#ef4444",
  slate400: "#94a3b8",
  slate700: "#334155",
  slate800: "#1e293b",
  slate200: "#e2e8f0",
} as const;

describe("chart-theme", () => {
  it("exports a THEME object with axis/grid/tooltip/risk sections", () => {
    expect(THEME).toBeTruthy();
    expect(THEME.axis).toBeTruthy();
    expect(THEME.grid).toBeTruthy();
    expect(THEME.tooltip).toBeTruthy();
    expect(THEME.risk).toBeTruthy();
  });

  it("risk colors match the CSS token palette", () => {
    expect(THEME.risk.clean).toBe(PALETTE.clean);
    expect(THEME.risk.warn).toBe(PALETTE.warn);
    expect(THEME.risk.critical).toBe(PALETTE.critical);
  });

  it("neutral axis/tooltip colors match the slate palette", () => {
    expect(THEME.axis.tick).toBe(PALETTE.slate400);
    expect(THEME.axis.line).toBe(PALETTE.slate700);
    expect(THEME.grid).toBe(PALETTE.slate700);
    expect(THEME.tooltip.backgroundColor).toBe(PALETTE.slate800);
    expect(THEME.tooltip.border).toBe(`1px solid ${PALETTE.slate700}`);
    expect(THEME.tooltip.color).toBe(PALETTE.slate200);
    expect(THEME.legendText).toBe(PALETTE.slate400);
  });

  it.each(["ScoreHistogram.tsx", "ScoreTrendChart.tsx", "ChartTooltip.tsx"])(
    "%s contains zero literal hex colors",
    (file) => {
      const src = readFileSync(
        join(process.cwd(), "src", "components", file),
        "utf-8",
      );
      const hexMatches = src.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
      expect(hexMatches).toEqual([]);
    },
  );

  it("exposes chart-level neutral extensions matching the slate palette", () => {
    // slate-800 grid/track + slate-950 page bg (mirrors --color-page-bg)
    expect(THEME.gridSoft).toBe(PALETTE.slate800);
    expect(THEME.barTrack).toBe(PALETTE.slate800);
    expect(THEME.pageBg).toBe("#020617");
    // Bar tooltip cursor: slate-800 at 40% opacity
    expect(THEME.tooltipCursor).toBe("rgba(30, 41, 59, 0.4)");
  });

  describe("formatCompactTick", () => {
    it("compacts values >= 1000 to a 1-decimal k suffix", () => {
      expect(formatCompactTick(1000)).toBe("1.0k");
      expect(formatCompactTick(1500)).toBe("1.5k");
      expect(formatCompactTick(12345)).toBe("12.3k");
    });

    it("leaves values below 1000 untouched (integer string)", () => {
      expect(formatCompactTick(0)).toBe("0");
      expect(formatCompactTick(42)).toBe("42");
      expect(formatCompactTick(999)).toBe("999");
    });
  });
});
