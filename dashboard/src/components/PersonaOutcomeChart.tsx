"use client";

import { useState } from "react";

type PersonaRow = {
  persona: string;
  attempted: number;
  recovered: number;
  retained_paused: number;
  human_escalated: number;
  stopped: number;
  timeout: number;
  error: number;
  success_rate: string;
};

// Outcome -> validated hex (light mode). Order matches a validated adjacent
// ordering (node scripts/validate_palette.js, dataviz skill): worst adjacent
// CVD ΔE 15.3 / normal-vision ΔE 20.8, both clear of the floors. Chosen so
// hue reads with the outcome's real-world valence (green=win, red=needs a
// human, ...) rather than an arbitrary categorical order.
const OUTCOME_CONFIG: { key: keyof PersonaRow; label: string; hex: string }[] = [
  { key: "recovered", label: "Recovered", hex: "#008300" },
  { key: "retained_paused", label: "Retained (paused)", hex: "#2a78d6" },
  { key: "timeout", label: "Timeout", hex: "#eda100" },
  { key: "human_escalated", label: "Escalated", hex: "#e34948" },
  { key: "stopped", label: "Stopped", hex: "#4a3aa7" },
  { key: "error", label: "Error", hex: "#eb6834" },
];

// Segments this thin need the count moved to the tooltip instead of an
// inline label -- otherwise the text clips or overflows a 4-6px sliver.
const MIN_INLINE_LABEL_PCT = 8;

type Hovered = { persona: string; label: string; count: number; pct: number; x: number; y: number } | null;

export default function PersonaOutcomeChart({ personas }: { personas: PersonaRow[] }) {
  const [hovered, setHovered] = useState<Hovered>(null);

  if (personas.length === 0) {
    return (
      <div className="py-8 text-center text-on-surface-variant font-body-sm text-body-sm">
        No persona data available. Run the harness first.
      </div>
    );
  }

  const maxAttempted = Math.max(...personas.map((p) => p.attempted), 1);

  const showTooltip = (e: React.MouseEvent | React.FocusEvent, persona: string, label: string, count: number, pct: number) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const containerRect = (e.currentTarget as HTMLElement).closest("[data-chart-root]")?.getBoundingClientRect();
    if (!containerRect) return;
    setHovered({
      persona, label, count, pct,
      x: rect.left - containerRect.left + rect.width / 2,
      y: rect.top - containerRect.top,
    });
  };

  return (
    <div data-chart-root className="relative">
      {/* Legend -- the dependable identity channel; color is never the only cue */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-6">
        {OUTCOME_CONFIG.map((o) => (
          <div key={o.key} className="flex items-center gap-1.5">
            <span className="inline-block w-2.5 h-2.5 rounded-[2px]" style={{ backgroundColor: o.hex }} />
            <span className="font-label-caps text-label-caps text-on-surface-variant">{o.label}</span>
          </div>
        ))}
      </div>

      {/* Rows */}
      <div className="space-y-4">
        {personas.map((p) => {
          const barWidthPct = (p.attempted / maxAttempted) * 100;
          const segments = OUTCOME_CONFIG.map((o) => ({
            ...o,
            count: (p[o.key] as number) || 0,
          })).filter((s) => s.count > 0);

          return (
            <div key={p.persona} className="flex items-center gap-3">
              <span className="w-32 shrink-0 font-body-sm text-body-sm text-on-surface capitalize leading-tight">
                {p.persona.replace(/_/g, " ")}
              </span>

              {/* Full-scale track so every row shares one comparable baseline */}
              <div className="relative flex-1 h-5 rounded-[4px] bg-surface-container-low overflow-hidden">
                <div className="flex h-full gap-[2px]" style={{ width: `${barWidthPct}%` }}>
                  {segments.map((s, i) => {
                    const segPct = (s.count / maxAttempted) * 100;
                    const isFirst = i === 0;
                    const isLast = i === segments.length - 1;
                    const showLabel = segPct >= MIN_INLINE_LABEL_PCT;
                    return (
                      <div
                        key={s.key}
                        role="img"
                        aria-label={`${s.label}: ${s.count} of ${p.attempted}`}
                        tabIndex={0}
                        className={`h-full flex items-center justify-center outline-none focus-visible:ring-2 focus-visible:ring-primary transition-[filter] hover:brightness-110 ${
                          isFirst ? "rounded-l-[4px]" : ""
                        } ${isLast ? "rounded-r-[4px]" : ""}`}
                        style={{ flexGrow: s.count, flexBasis: 0, backgroundColor: s.hex }}
                        onMouseEnter={(e) => showTooltip(e, p.persona, s.label, s.count, (s.count / p.attempted) * 100)}
                        onMouseLeave={() => setHovered(null)}
                        onFocus={(e) => showTooltip(e, p.persona, s.label, s.count, (s.count / p.attempted) * 100)}
                        onBlur={() => setHovered(null)}
                      >
                        {showLabel && (
                          <span className="font-data-tabular text-[10px] font-semibold text-white pointer-events-none">
                            {s.count}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Value at the tip -- always reachable without hovering */}
              <span className="w-20 shrink-0 text-right font-data-tabular text-data-tabular text-on-surface-variant">
                {p.attempted} {p.attempted === 1 ? "case" : "cases"}
              </span>
            </div>
          );
        })}
      </div>

      {/* Single floating tooltip, positioned per-hover -- value leads, label follows */}
      {hovered && (
        <div
          className="absolute z-20 -translate-x-1/2 -translate-y-[calc(100%+8px)] pointer-events-none"
          style={{ left: hovered.x, top: hovered.y }}
        >
          <div className="bg-surface-container-highest border border-outline-variant rounded shadow-lg px-2.5 py-1.5 whitespace-nowrap">
            <p className="font-data-tabular text-data-tabular text-on-surface font-semibold leading-tight">
              {hovered.count} <span className="font-body-sm text-on-surface-variant font-normal">({hovered.pct.toFixed(0)}%)</span>
            </p>
            <p className="font-label-caps text-label-caps text-on-surface-variant leading-tight mt-0.5">
              {hovered.label} · {hovered.persona.replace(/_/g, " ")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
