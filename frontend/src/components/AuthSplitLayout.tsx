import type { CSSProperties, ReactNode } from "react";
import { ShieldCheck, Scales, Sparkle } from "@phosphor-icons/react";
import { BrandShield } from "./BrandShield";
import { MAIN_LANDMARK_ID } from "../lib/focusable";

type StaggerStyle = CSSProperties & { "--i"?: number };

/**
 * A RECORDED FOCUS-RING DIVERGENCE, held in its own constant so the reason
 * sits next to the one string it is about.
 *
 * It is the bare `focus:` prefix at 25% of the risk tone where `FOCUS_RING` is
 * the accent token at full strength on `focus-visible:` — and it is inherited,
 * not invented here: the Login and Register fields carried it before the split
 * screen existed, and the note at their call sites explains why flattening it
 * is a visual change owed to the visual pass rather than something a refactor
 * should decide.
 *
 * NO LINT SUPPRESSION, and the reason is a scope decision rather than an
 * oversight. `ui/no-raw-class-tokens` reads class POSITIONS — a `className`
 * value, or an argument of `cn(...)` — and this string reaches the DOM only by
 * being referenced (`AUTH_INPUT_CLASS` below, spliced into the auth fields'
 * classNames). The rule does not follow references: doing that is a type
 * checker, and the heuristics that approximate one produce false positives on
 * prose, which is a worse failure than a stated limit. See the "WHERE IT LOOKS"
 * section of `eslint-rules/ui-class-tokens.js`.
 *
 * What pins this string instead is a TEST, in both directions, which is this
 * codebase's mechanism for a divergence that is deliberately kept:
 * `LoginPage.test.tsx` and `RegisterPage.test.tsx` each assert the ring is
 * present, so silently flattening it to `FOCUS_RING` fails, and assert the
 * house ring is absent, so silently deleting it fails. Two files, because the
 * fields are two different pages that could diverge from each other next.
 */
const AUTH_INPUT_RING =
  "focus:border-risk-critical focus:outline-none focus:ring-2 focus:ring-risk-critical/25";

/** Shared input treatment for the auth forms (DESIGN.md — Forms). */
export const AUTH_INPUT_CLASS =
  `h-11 w-full rounded-lg bg-slate-900 border border-slate-800 px-3 text-sm ` +
  `text-slate-200 placeholder:text-slate-600 transition-colors ` +
  AUTH_INPUT_RING;

const FEATURES = [
  {
    icon: <Scales size={18} weight="regular" aria-hidden="true" />,
    title: "Motor de reglas determinista",
    copy: "Cada score se calcula con reglas auditables, sin cajas negras.",
  },
  {
    icon: <ShieldCheck size={18} weight="regular" aria-hidden="true" />,
    title: "Explicabilidad SHAP por transacción",
    copy: "Mira exactamente qué empujó cada score hacia el fraude.",
  },
  {
    icon: <Sparkle size={18} weight="regular" aria-hidden="true" />,
    title: "Reportes explicativos con LLM local",
    copy: "Narrativas generadas on-device vía Ollama, sin exponer datos.",
  },
];

function BrandPanel() {
  return (
    <section
      className="hidden md:flex flex-col justify-center px-12 lg:px-20 relative overflow-hidden bg-slate-950"
      style={{ "--i": 0 } as StaggerStyle}
    >
      {/* Radial glows — sanctioned inline-gradient location (DESIGN.md — Don'ts) */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 20% 15%, rgba(239,68,68,0.07), transparent 55%), radial-gradient(circle at 85% 90%, rgba(34,197,94,0.05), transparent 55%)",
        }}
      />

      <div className="relative">
        <div className="w-fit rounded-2xl border border-slate-800 bg-slate-900 p-3">
          <BrandShield className="h-16 w-16 text-accent" />
        </div>

        <h1 className="mt-8 text-4xl lg:text-5xl font-semibold tracking-tighter leading-[1.05] text-slate-100">
          Detecta <span className="text-risk-critical">fraude</span> antes de
          que ocurra
        </h1>
        <p className="mt-4 max-w-[42ch] text-slate-400">
          La consola donde cada transacción recibe un score explicable en
          segundos, no en horas.
        </p>

        <ul className="mt-10 space-y-4">
          {FEATURES.map((feature) => (
            <li key={feature.title} className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-slate-800 bg-slate-900 text-slate-300">
                {feature.icon}
              </span>
              <div>
                <p className="text-sm font-medium text-slate-200">
                  {feature.title}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">{feature.copy}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

interface AuthSplitLayoutProps {
  children: ReactNode;
}

/**
 * Split-screen auth shell (desktop): brand panel left, form panel right.
 * Below md it collapses to a single column with a compact brand header.
 * Panels ride the shared `.motion-stagger` entrance (--i 0/1), which the
 * global reduced-motion guard disables (see DESIGN.md — Motion).
 */
export function AuthSplitLayout({ children }: AuthSplitLayoutProps) {
  return (
    <div className="min-h-dvh bg-slate-950 md:grid md:grid-cols-[1.15fr_1fr] motion-stagger">
      {/* Mobile compact brand header */}
      <header
        className="md:hidden flex h-14 items-center gap-2 border-b border-slate-800/60 px-4"
        style={{ "--i": 0 } as StaggerStyle}
      >
        <BrandShield className="h-7 w-7 text-accent" />
        <span className="text-sm font-semibold text-slate-100">
          Fraud Detector
        </span>
      </header>

      <BrandPanel />

      {/* Form panel */}
      <main
        id={MAIN_LANDMARK_ID}
        tabIndex={-1}
        className="flex items-center justify-center px-6 py-10 md:p-8"
        style={{ "--i": 1 } as StaggerStyle}
      >
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
