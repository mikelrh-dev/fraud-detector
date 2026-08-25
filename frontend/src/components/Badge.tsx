import type { ReactNode } from "react";

/**
 * Semantic tone → token class map. Zero hardcoded hex: every entry points at
 * a @theme token from index.css (risk-* triad + status-info) or slate
 * utilities (neutral). Badge pattern per DESIGN.md: /10 bg, /30 border,
 * full-color text. `neutral` is the unknown-state fallback and skips the
 * tinted pattern on purpose.
 */
export type BadgeTone = "clean" | "warn" | "critical" | "info" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  clean: "bg-risk-clean/10 border-risk-clean/30 text-risk-clean",
  warn: "bg-risk-warn/10 border-risk-warn/30 text-risk-warn",
  critical: "bg-risk-critical/10 border-risk-critical/30 text-risk-critical",
  info: "bg-status-info/10 border-status-info/30 text-status-info",
  neutral: "bg-slate-800 border-slate-700 text-slate-400",
};

const SIZE_CLASSES = {
  md: "px-3 py-1 text-sm",
  sm: "px-2 py-0.5 text-[11px]",
} as const;

export interface BadgeProps {
  tone: BadgeTone;
  children: ReactNode;
  /** Material Symbols glyph name rendered inside an icon slot. */
  icon?: string;
  /** sm = compact pills (alert status), md = standard badges (default). */
  size?: keyof typeof SIZE_CLASSES;
}

/**
 * Presentational pill badge. Single primitive for classification and alert
 * status badges — consumes semantic tokens only.
 */
export function Badge({ tone, children, icon, size = "md" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium border ${SIZE_CLASSES[size]} ${TONE_CLASSES[tone]}`}
    >
      {icon && <span className="material-symbols-outlined text-base mr-1">{icon}</span>}
      {children}
    </span>
  );
}
