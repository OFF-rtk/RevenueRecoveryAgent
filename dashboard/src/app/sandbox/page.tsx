"use client";

import { useState, useEffect, useRef } from "react";

// Short summaries of the actual persona prompts used server-side
// (see scripts/run_live_persona_harness.py PERSONAS) -- keeps the config
// panel honest about what each selection will actually do.
const PERSONA_DESCRIPTIONS: Record<string, string> = {
  considering_cancellation: "Genuinely on the fence about keeping the subscription -- may ask what they'd lose, or pause instead of paying. Outcome isn't scripted; it follows how the conversation actually goes.",
  needs_payment_help: "Wants to pay, but the card on file is broken -- needs the agent to actually offer a fix (e.g. a UPI link), not just repeat \"please pay.\"",
  accidental_failure: "Happy customer, payment failed by accident. Pays quickly once given a clear next step.",
  suspicious_payer: "Doesn't recognize the charge -- asks for proof (invoice, signup date) before paying. Escalates to a human if the agent can't provide it.",
  forgetful_promises_then_pays: "Willing to pay but busy -- promises to \"do it later\" on first contact, then may or may not follow through on a reminder.",
  ignores_completely: "Never replies, under any circumstances. Tests the stopping-rules / timeout path.",
};

// Inline simplified TimelineNode for Sandbox audit
function AuditNode({ evt }: { evt: any }) {
  const [expanded, setExpanded] = useState(false);
  let badge = "System";
  let title = evt.event;
  let displayDetail = evt.payload ? JSON.stringify(evt.payload, null, 2) : "";
  let colorClass = "bg-surface-container-low border-outline-variant text-on-surface-variant";
  let iconClass = "bg-surface border-outline-variant";

  if (evt.type === "state_transition") {
    badge = "State"; title = `Transition: ${evt.payload?.new_status || evt.payload?.to_state}`;
    colorClass = "bg-secondary-container border-secondary text-on-secondary-container";
    iconClass = "bg-secondary-container border-secondary";
  } else if (evt.type === "intervention_sent" || evt.type === "followup_sent") {
    badge = "Agent"; title = evt.type === "followup_sent" ? "Follow-up Sent" : "Intervention Sent";
    colorClass = "bg-primary-fixed border-primary text-on-primary-fixed";
    iconClass = "bg-primary-fixed border-primary";
  } else if (evt.type === "customer_reply") {
    badge = "Customer"; title = "Reply Received";
    colorClass = "bg-surface-container-high border-outline-variant text-on-surface";
  } else if (evt.type === "diagnosis_completed") {
    badge = "Diagnosis";
    const conf = evt.payload?.confidence;
    const confStr = typeof conf === 'number' ? conf.toFixed(2) : conf;
    title = `Diagnosed: ${evt.payload?.causes?.[0] || "unknown"} (tier ${evt.payload?.tier}, conf ${confStr})`;
    colorClass = "bg-tertiary-container border-tertiary text-on-tertiary-container";
    iconClass = "bg-tertiary-container border-tertiary";
  } else if (evt.type === "error") {
    badge = "Error"; title = "Simulation Error";
    colorClass = "bg-error-container border-error text-on-error-container";
    iconClass = "bg-error-container border-error";
  } else if (evt.type === "manual_followup_check_triggered") {
    badge = "Follow-up"; title = "Automated Nudge Sent";
    colorClass = "bg-primary-fixed border-primary text-on-primary-fixed";
    iconClass = "bg-primary-fixed border-primary";
  } else if (evt.type === "case_created") {
    badge = "Case"; title = "Case Created";
  }

  return (
    <div className="mb-4 relative pl-4 cursor-pointer" onClick={() => setExpanded(!expanded)}>
      <div className={`absolute w-2 h-2 border-2 rounded-full -left-[4.5px] top-1.5 ${iconClass}`}></div>
      <div className="flex items-center gap-2 mb-1">
        <span className="font-mono-timestamp text-[10px] text-on-surface-variant">
          {new Date(evt.timestamp * 1000).toLocaleTimeString()}
        </span>
        <span className={`px-1 py-0.5 border rounded text-[9px] ${colorClass}`}>{badge}</span>
      </div>
      <p className="text-sm font-medium text-on-surface">{title}</p>
      {expanded && displayDetail && (
        <pre className="mt-2 text-[10px] bg-surface-container-lowest border border-outline-variant p-2 rounded overflow-x-auto whitespace-pre-wrap text-on-surface-variant">
          {displayDetail}
        </pre>
      )}
    </div>
  );
}

export default function Sandbox() {
  const [accessKey, setAccessKey] = useState("");
  const [isAllowed, setIsAllowed] = useState(false);
  const [keyError, setKeyError] = useState("");

  const [persona, setPersona] = useState("considering_cancellation");
  const [caseType, setCaseType] = useState("failed_subscription");
  const [rootCause, setRootCause] = useState("insufficient_funds");

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [running, setRunning] = useState(false);
  const [pollingError, setPollingError] = useState("");
  const [showAudit, setShowAudit] = useState(false);
  
  const pollInterval = useRef<any>(null);

  useEffect(() => {
    return () => {
      if (pollInterval.current) clearInterval(pollInterval.current);
    };
  }, []);

  const startSimulation = async () => {
    setEvents([]);
    setPollingError("");
    setSessionId(null);
    setRunning(true);
    
    if (pollInterval.current) clearInterval(pollInterval.current);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/sandbox/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${accessKey}`
        },
        body: JSON.stringify({ persona, case_type: caseType, root_cause: rootCause })
      });

      if (res.status === 401) {
        setKeyError("Invalid access key");
        setIsAllowed(false);
        setRunning(false);
        return;
      }
      
      if (res.status === 429) {
        setPollingError("Rate limit exceeded. Please try again later.");
        setRunning(false);
        return;
      }

      if (!res.ok) throw new Error("Failed to start simulation");

      const data = await res.json();
      setSessionId(data.session_id);

      // Start polling
      pollInterval.current = setInterval(() => pollStatus(data.session_id), 1500);

    } catch (e: any) {
      setPollingError(e.message);
      setRunning(false);
    }
  };

  const pollStatus = async (sid: string) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/sandbox/run/${sid}/status`, {
        headers: { "Authorization": `Bearer ${accessKey}` }
      });
      
      if (res.status === 401) {
        setKeyError("Access key revoked or invalid");
        setIsAllowed(false);
        clearInterval(pollInterval.current);
        return;
      }

      const data = await res.json();
      setEvents(data.events);

      if (data.done || data.error) {
        clearInterval(pollInterval.current);
        setRunning(false);
      }
    } catch (e: any) {
      setPollingError(e.message);
      clearInterval(pollInterval.current);
      setRunning(false);
    }
  };

  const handleKeySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (accessKey.trim()) {
      setIsAllowed(true);
      setKeyError("");
    }
  };

  if (!isAllowed) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-surface p-4">
        <div className="bg-surface-container p-8 rounded-lg border border-outline-variant max-w-md w-full shadow-lg">
          <h2 className="text-xl font-bold mb-4 text-on-surface">Sandbox Access</h2>
          <p className="text-on-surface-variant mb-6 text-sm">
            Please enter your judge access key to enter the live simulation environment.
          </p>
          <form onSubmit={handleKeySubmit}>
            <input
              type="password"
              value={accessKey}
              onChange={e => setAccessKey(e.target.value)}
              placeholder="Enter access key..."
              className="w-full px-4 py-2 border border-outline-variant bg-surface rounded mb-4 focus:ring-2 focus:ring-primary outline-none"
            />
            {keyError && <p className="text-error text-sm mb-4">{keyError}</p>}
            <button type="submit" className="w-full bg-primary text-on-primary py-2 rounded font-medium hover:opacity-90">
              Verify
            </button>
          </form>
          <div className="mt-6 text-center">
            <p className="text-on-surface-variant text-sm">
              Don't have the access key? Ask the team.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Filter messages for chat view
  const chatMessages = events.filter(e => e.type === "intervention_sent" || e.type === "followup_sent" || e.type === "customer_reply" || e.type === "manual_followup_check_triggered");

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      {/* Sidebar Configuration */}
      <div className="w-80 border-r border-outline-variant bg-surface-container-lowest p-6 flex flex-col shrink-0">
        <h2 className="text-lg font-bold mb-6 text-on-surface">Configuration</h2>
        
        <div className="mb-4">
          <label className="block text-xs font-bold text-on-surface-variant mb-2 uppercase tracking-wide">Case Type</label>
          <select value={caseType} onChange={e => setCaseType(e.target.value)} className="w-full p-2 border border-outline-variant rounded bg-surface">
            <option value="failed_subscription">Failed Subscription</option>
            <option value="overdue_invoice">Overdue Invoice</option>
          </select>
          <p className="text-[10px] text-on-surface-variant mt-2 leading-tight">
            {caseType === "overdue_invoice"
              ? "Fires an invoice.expired event -- the agent uses its overdue-invoice template, not the subscription one."
              : "Fires a payment.failed event -- the agent uses its subscription recovery template."}
          </p>
        </div>

        <div className="mb-4">
          <label className="block text-xs font-bold text-on-surface-variant mb-2 uppercase tracking-wide">Root Cause</label>
          <select value={rootCause} onChange={e => setRootCause(e.target.value)} className="w-full p-2 border border-outline-variant rounded bg-surface">
            <option value="insufficient_funds">Insufficient Funds</option>
            <option value="bank_declined">Bank Declined</option>
            <option value="expired_card">Expired Card</option>
            <option value="technical_error">Technical Error</option>
          </select>
        </div>

        <div className="mb-6">
          <label className="block text-xs font-bold text-on-surface-variant mb-2 uppercase tracking-wide">Customer Persona</label>
          <select value={persona} onChange={e => setPersona(e.target.value)} className="w-full p-2 border border-outline-variant rounded bg-surface">
            <option value="considering_cancellation">Considering Cancellation</option>
            <option value="needs_payment_help">Needs Payment Help</option>
            <option value="accidental_failure">Accidental Failure</option>
            <option value="suspicious_payer">Suspicious Payer</option>
            <option value="forgetful_promises_then_pays">Forgetful (Promises, Then Pays)</option>
            <option value="ignores_completely">Ignores Completely</option>
          </select>
          <p className="text-[10px] text-on-surface-variant mt-2 leading-tight">
            {PERSONA_DESCRIPTIONS[persona]}
          </p>
        </div>

        <button 
          onClick={startSimulation} 
          disabled={running}
          className="w-full bg-primary text-on-primary py-3 rounded font-bold hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {running ? "Simulation Running..." : "Run Simulation"}
        </button>

        <div className="mt-auto pt-6 border-t border-outline-variant">
          <p className="text-[10px] text-on-surface-variant leading-tight">
            <strong>Disclaimer:</strong> Live simulation using our real diagnosis and conversation engine. No WhatsApp messages sent, no production data written.
          </p>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col relative bg-[#EFEAE2]">
        {/* Header */}
        <div className="bg-surface border-b border-outline-variant p-4 flex justify-between items-center shadow-sm z-10">
          <div>
            <h1 className="font-bold text-on-surface">Recovery Agent</h1>
            <p className="text-xs text-on-surface-variant">Isolated Sandbox Environment</p>
          </div>
          <button 
            onClick={() => setShowAudit(!showAudit)}
            className="px-4 py-2 border border-outline-variant rounded text-sm font-medium bg-surface-container hover:bg-surface-container-high transition-colors"
          >
            {showAudit ? "Hide Audit Events" : "View Audit Events"}
          </button>
        </div>

        {/* Chat window */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {events.length === 0 && !running && (
            <div className="h-full flex items-center justify-center text-on-surface-variant">
              Configure parameters and click "Run Simulation" to start.
            </div>
          )}
          
          {chatMessages.map((msg, i) => {
            const isAgent = msg.type === "intervention_sent" || msg.type === "followup_sent" || msg.type === "manual_followup_check_triggered";
            return (
              <div key={i} className={`flex ${isAgent ? 'justify-start' : 'justify-end'}`}>
                <div className={`max-w-[70%] p-3 rounded-lg shadow-sm ${isAgent ? 'bg-white rounded-tl-none' : 'bg-[#d9fdd3] rounded-tr-none'}`}>
                  <p className="text-sm text-gray-800 whitespace-pre-wrap">{msg.payload?.message}</p>
                  <span className="text-[10px] text-gray-500 mt-1 block text-right">
                    {new Date(msg.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
            );
          })}
          
          {running && (
            <div className="flex justify-start">
              <div className="bg-white p-3 rounded-lg shadow-sm rounded-tl-none text-sm text-gray-500 italic flex items-center gap-2">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.2s'}}></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{animationDelay: '0.4s'}}></span>
              </div>
            </div>
          )}

          {pollingError && (
            <div className="mx-auto bg-error-container text-on-error-container p-3 rounded text-sm text-center max-w-md">
              {pollingError}
            </div>
          )}
          
          {events.find(e => e.type === "error") && (
            <div className="mx-auto bg-error-container text-on-error-container p-3 rounded text-sm text-center max-w-md">
              {events.find(e => e.type === "error")?.payload?.message}
            </div>
          )}
        </div>
      </div>

      {/* Audit Panel Side Sheet */}
      {showAudit && (
        <div className="w-[400px] border-l border-outline-variant bg-surface-container-lowest p-6 overflow-y-auto shrink-0 shadow-[-4px_0_15px_rgba(0,0,0,0.05)]">
          <h2 className="text-lg font-bold mb-6 text-on-surface">Audit Timeline</h2>
          {events.length === 0 ? (
            <p className="text-sm text-on-surface-variant">No events yet.</p>
          ) : (
            <div className="border-l border-outline-variant ml-2">
              {events.map((evt, i) => (
                <AuditNode key={i} evt={evt} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
