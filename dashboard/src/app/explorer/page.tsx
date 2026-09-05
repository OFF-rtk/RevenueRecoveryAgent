"use client";

import { useState, useEffect } from "react";

// Drops falsy entries and narrows to string[] (plain .filter(Boolean) keeps
// the `false` branch of `cond && "text"` in the inferred type).
const compact = (arr: (string | false | undefined | null)[]): string[] => arr.filter((x): x is string => Boolean(x));

// One entry per real event_type emitted by the backend (see core/**/*.py and
// scripts/*.py for `event_type="..."`). Anything not listed falls back to a
// plain "System" style further down, so a new event type never renders blank.
const EVENT_CONFIG: Record<string, { badge: string; icon: string; colorClass: string; title: (p: any) => string; detail: (p: any) => string[] }> = {
  case_created: {
    badge: "Case", icon: "flag",
    colorClass: "bg-surface-container-high border-outline-variant text-on-surface",
    title: () => "Case Created",
    detail: (p) => compact([p.razorpay_event && `Event: ${p.razorpay_event}`, p.entity_id && `Entity: ${p.entity_id}`, p.source && `Source: ${p.source}`]),
  },
  diagnosis_completed: {
    badge: "Diagnosis", icon: "psychology",
    colorClass: "bg-tertiary-container border-tertiary text-on-tertiary-container",
    title: (p) => `Diagnosed: ${(p.causes || [])[0] || "unknown"}`,
    detail: (p) => compact([`Tier ${p.tier} model`, typeof p.confidence === "number" && `Confidence: ${p.confidence.toFixed(2)}`, p.reasoning]),
  },
  diagnosis_failed: {
    badge: "Diagnosis Failed", icon: "error",
    colorClass: "bg-error-container border-error text-on-error-container",
    title: () => "Diagnosis Failed",
    detail: (p) => compact([p.error]),
  },
  intervention_sent: {
    badge: "Agent", icon: "forum",
    colorClass: "bg-primary-fixed border-primary text-on-primary-fixed",
    title: () => "Intervention Sent",
    detail: (p) => compact([p.message, p.template_name && `Template: ${p.template_name}`]),
  },
  followup_sent: {
    badge: "Agent", icon: "forum",
    colorClass: "bg-primary-fixed border-primary text-on-primary-fixed",
    title: () => "Follow-up Sent",
    detail: (p) => compact([p.message]),
  },
  manual_followup_check_triggered: {
    badge: "Follow-up", icon: "notifications_active",
    colorClass: "bg-primary-fixed border-primary text-on-primary-fixed",
    title: () => "Automated Nudge Sent",
    detail: (p) => compact([p.message, `Attempt #${p.attempt_number}`, p.session_open === false && "Outside 24h WhatsApp session window"]),
  },
  customer_reply: {
    badge: "Customer", icon: "reply",
    colorClass: "bg-surface-container-high border-outline-variant text-on-surface",
    title: () => "Reply Received",
    detail: (p) => compact([p.message, p.classified_state && `Classified as: ${p.classified_state}`]),
  },
  whatsapp_webhook_received: {
    badge: "WhatsApp", icon: "chat_bubble",
    colorClass: "bg-surface-container-high border-outline-variant text-on-surface",
    title: () => "WhatsApp Webhook Received",
    detail: () => [],
  },
  state_transition: {
    badge: "State", icon: "swap_horiz",
    colorClass: "bg-secondary-container border-secondary text-on-secondary-container",
    title: (p) => `Transition: ${p.from_state || "?"} → ${p.to_state || p.new_status || "?"}`,
    detail: (p) => compact([p.reason]),
  },
  stopping_rule_triggered: {
    badge: "Stopped", icon: "block",
    colorClass: "bg-error-container border-error text-on-error-container",
    title: (p) => `Stopping Rule: ${p.rule || "triggered"}`,
    detail: (p) => Object.entries(p).filter(([k]) => k !== "rule").map(([k, v]) => `${k}: ${v}`),
  },
  case_escalated: {
    badge: "Escalated", icon: "support_agent",
    colorClass: "bg-error-container border-error text-on-error-container",
    title: () => "Escalated to Human",
    detail: (p) => compact([p.reason && `Reason: ${p.reason}`, p.rounds && `After ${p.rounds} rounds`]),
  },
  payment_captured_simulated: {
    badge: "Payment", icon: "payments",
    colorClass: "bg-tertiary-container border-tertiary text-on-tertiary-container",
    title: () => "Payment Captured",
    detail: (p) => compact([p.attribution && `Via: ${p.attribution}`]),
  },
  persona_simulation_started: {
    badge: "Simulation", icon: "smart_toy",
    colorClass: "bg-surface-container-high border-outline-variant text-on-surface",
    title: (p) => `Persona: ${(p.persona || "unknown").replace(/_/g, " ")}`,
    detail: (p) => compact([typeof p.temperature === "number" && `Temperature: ${p.temperature}`]),
  },
};

const DEFAULT_EVENT_CONFIG = {
  badge: "System", icon: "info",
  colorClass: "bg-surface-container-low border-outline-variant text-on-surface-variant",
  title: (_p: any, name: string) => name.replace(/_/g, " "),
  detail: (p: any) => Object.entries(p || {}).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`),
};

function TimelineNode({ evt }: { evt: any }) {
  const [expanded, setExpanded] = useState(false);

  const eventName: string = evt.event || evt.type || "unknown";
  const payload = evt.payload || {};
  const config = EVENT_CONFIG[eventName];
  const badge = config?.badge ?? DEFAULT_EVENT_CONFIG.badge;
  const icon = config?.icon ?? DEFAULT_EVENT_CONFIG.icon;
  const colorClass = config?.colorClass ?? DEFAULT_EVENT_CONFIG.colorClass;
  const title = config ? config.title(payload) : DEFAULT_EVENT_CONFIG.title(payload, eventName);
  const detailLines = config ? config.detail(payload) : DEFAULT_EVENT_CONFIG.detail(payload);
  const rawJson = JSON.stringify(payload, null, 2);

  return (
    <div className="mb-6 relative pl-8 group">
      <div className={`absolute w-6 h-6 border rounded-full -left-3 top-0 flex items-center justify-center ${colorClass}`}>
        <span className="material-symbols-outlined" style={{ fontSize: "13px" }}>{icon}</span>
      </div>

      <div
        className="cursor-pointer"
        onClick={() => detailLines.length > 0 && setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant">
            {new Date(evt.timestamp).toLocaleTimeString()}
          </span>
          <span className={`px-1.5 py-0.5 border rounded font-label-caps text-[9px] uppercase tracking-wide ${colorClass}`}>
            {badge}
          </span>
          {detailLines.length > 0 && (
            <span className="material-symbols-outlined text-on-surface-variant text-[14px] opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
              {expanded ? "expand_less" : "expand_more"}
            </span>
          )}
        </div>

        <p className="font-data-tabular text-data-tabular text-on-surface font-medium capitalize">
          {title}
        </p>

        {!expanded && detailLines.length > 0 && (
          <p className="font-body-sm text-body-sm text-on-surface-variant mt-1 overflow-hidden text-ellipsis whitespace-nowrap opacity-70">
            {detailLines[0]}
          </p>
        )}
      </div>

      {expanded && (
        <div className="mt-2 space-y-2">
          <ul className="text-[11px] text-on-surface-variant leading-relaxed bg-surface-container-lowest border border-outline-variant rounded-DEFAULT p-3 space-y-1">
            {detailLines.map((line, i) => (
              <li key={i} className="whitespace-pre-wrap break-words">{line}</li>
            ))}
          </ul>
          <details className="text-[10px]">
            <summary className="cursor-pointer text-on-surface-variant hover:text-primary select-none">Raw payload</summary>
            <pre className="font-mono-timestamp text-[10px] bg-surface-container-lowest border border-outline-variant p-3 rounded-DEFAULT overflow-x-auto text-on-surface-variant whitespace-pre-wrap mt-1">
              {rawJson}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default function Explorer() {
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [cases, setCases] = useState<any[]>([]);
  const [activeCase, setActiveCase] = useState<any>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchCases();
  }, [statusFilter]);

  const filteredCases = cases.filter((c) =>
    c.id.toLowerCase().includes(searchQuery.trim().toLowerCase())
  );

  const handleExport = () => {
    const headers = ["Case ID", "Customer", "Amount", "Status"];
    const rows = filteredCases.map((c) => [c.id, c.customer_ref, c.amount, c.outcome || c.status]);
    const csv = [headers, ...rows]
      .map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cases_export_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const fetchCases = async () => {
    setLoading(true);
    try {
      let url = `${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/cases`;
      if (statusFilter !== "All") {
        url += `?status=${statusFilter.toLowerCase()}`;
      }
      const res = await fetch(url);
      setCases(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const openDetail = async (c: any) => {
    setActiveCase(c);
    setIsDetailOpen(true);
    setTimeline([]); // clear old
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/cases/${c.id}/timeline`);
      setTimeline(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <>
      {/* Top Action Bar */}
      <header className="h-16 border-b border-outline-variant bg-surface-container-lowest flex items-center justify-between px-gutter shrink-0">
        <h2 className="font-headline-md text-headline-md text-on-surface">
          Case Explorer
        </h2>
        <div className="flex items-center gap-unit">
          {/* Search */}
          <div className="relative flex items-center">
            <span
              className="material-symbols-outlined absolute left-3 text-on-surface-variant"
              style={{ fontSize: "20px" }}
            >
              search
            </span>
            <input
              className="pl-10 pr-4 py-2 bg-surface border border-outline-variant rounded font-body-sm text-body-sm text-on-surface placeholder:text-on-surface-variant focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary w-64 transition-all"
              placeholder="Search case ID..."
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <button
            onClick={handleExport}
            disabled={filteredCases.length === 0}
            className="p-2 text-on-surface-variant border border-outline-variant bg-surface-container-lowest rounded hover:bg-surface-container-low transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span className="material-symbols-outlined">download</span>
            <span className="font-label-caps text-label-caps">Export</span>
          </button>
        </div>
      </header>

      {/* Filter Bar */}
      <div className="bg-surface border-b border-outline-variant p-4 flex gap-4 shrink-0 overflow-x-auto custom-scrollbar">
        <select 
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="bg-surface-container-lowest border border-outline-variant rounded px-3 py-1.5 font-body-sm text-body-sm text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
        >
          <option value="All">Outcome/Status: All</option>
          <option value="open">Open</option>
          <option value="promise_pending">Promise Pending</option>
          <option value="payment_method_required">Payment Method Required</option>
          <option value="disputed">Disputed</option>
          <option value="recovered">Recovered</option>
          <option value="retained_paused">Retained (Paused)</option>
          <option value="human_escalated">Human Escalated</option>
          <option value="stopped">Stopped</option>
          <option value="timeout">Timeout</option>
        </select>
        <div className="ml-auto flex items-center gap-2">
          <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant">
            Showing {filteredCases.length} Cases
          </span>
        </div>
      </div>

      {/* Main Layout Split */}
      <div className="flex flex-1 overflow-hidden">
        {/* Data Table (Left) */}
        <div className="flex-1 overflow-y-auto custom-scrollbar bg-surface-container-lowest p-gutter">
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 bg-surface-container-lowest z-10 border-b border-outline-variant">
              <tr>
                <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant">
                  Case ID
                </th>
                <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant">
                  Customer
                </th>
                <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant text-right">
                  Amount
                </th>
                <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="font-data-tabular text-data-tabular">
              {loading ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-on-surface-variant font-body-sm">
                    Loading cases...
                  </td>
                </tr>
              ) : filteredCases.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-on-surface-variant font-body-sm">
                    No cases found.
                  </td>
                </tr>
              ) : (
                filteredCases.map((c) => (
                  <tr
                    key={c.id}
                    className={`border-b border-outline-variant cursor-pointer transition-colors ${
                      activeCase?.id === c.id ? 'bg-surface-container-low' : 'hover:bg-surface'
                    }`}
                    onClick={() => openDetail(c)}
                  >
                    <td className={`py-3 px-4 font-mono-timestamp text-mono-timestamp ${
                      activeCase?.id === c.id ? 'text-primary font-medium' : 'text-on-surface-variant'
                    }`}>
                      #{c.id.substring(0,8)}
                    </td>
                    <td className="py-3 px-4 text-on-surface">
                      {c.customer_ref}
                    </td>
                    <td className="py-3 px-4 text-right text-on-surface">
                      ₹{c.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded font-label-caps text-label-caps font-bold capitalize ${
                        c.status === 'resolved' 
                          ? 'bg-surface-container-highest text-on-surface'
                          : c.status === 'escalated'
                            ? 'bg-error-container text-on-error-container'
                            : 'bg-secondary-container text-on-secondary-container'
                      }`}>
                        {c.outcome || c.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Detail Panel */}
        {isDetailOpen && activeCase && (
          <aside className="w-96 border-l border-outline-variant bg-surface flex flex-col h-full">
            {/* Panel Header */}
            <div className="p-4 border-b border-outline-variant bg-surface-container-lowest flex items-center justify-between sticky top-0 z-20 shrink-0">
              <div>
                <h3 className="font-headline-md text-headline-md text-on-surface font-semibold">
                  Case #{activeCase.id.substring(0,8)}
                </h3>
                <p className="font-label-caps text-label-caps text-on-surface-variant mt-1">
                  Timeline
                </p>
              </div>
              <button
                className="p-1.5 text-on-surface-variant hover:bg-surface-container-low rounded-full transition-colors"
                onClick={() => setIsDetailOpen(false)}
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            
            {/* Panel Content (Timeline) */}
            <div className="p-6 flex-1 overflow-y-auto custom-scrollbar">
              <div className="relative border-l border-outline-variant ml-3 pb-6">
                
                {timeline.length === 0 && (
                  <div className="text-on-surface-variant font-body-sm pl-4">Loading timeline...</div>
                )}

                {timeline.map((evt, idx) => (
                  <TimelineNode key={idx} evt={evt} />
                ))}
              </div>
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
