"use client";

import { useState, useEffect, useRef } from "react";

function TimelineNode({ evt, idx }: { evt: any; idx: number }) {
  const [expanded, setExpanded] = useState(false);

  let badge = null;
  let title = "";
  let displayDetail = "";
  let isJson = false;
  let colorClass = "bg-surface-container-low border-outline-variant text-on-surface-variant";
  let iconClass = "bg-surface border-outline-variant";

  if (evt.type === "audit") {
    badge = "System";
    title = "Audit Event: " + evt.event.replace(/_/g, ' ');
    displayDetail = evt.payload ? JSON.stringify(evt.payload, null, 2) : "";
    isJson = true;
  } else if (evt.type === "state_transition") {
    badge = "State";
    title = `Transition: ${evt.payload?.to_state || "Unknown"}`;
    displayDetail = evt.payload?.reason || "";
    colorClass = "bg-secondary-container border-secondary text-on-secondary-container";
    iconClass = "bg-secondary-container border-secondary";
  } else if (evt.type === "agent_intervention" || evt.type === "intervention_sent") {
    badge = "Agent";
    title = "Intervention Sent";
    displayDetail = evt.payload?.message || JSON.stringify(evt.payload?.parameters);
    colorClass = "bg-primary-fixed border-primary text-on-primary-fixed";
    iconClass = "bg-primary-fixed border-primary";
  } else if (evt.type === "customer_reply") {
    badge = "Customer";
    title = "Reply Received";
    displayDetail = evt.payload?.message || "";
    colorClass = "bg-surface-container-high border-outline-variant text-on-surface";
  }

  // Pre-process any other JSON strings
  if (!isJson && displayDetail && typeof displayDetail === "string" && (displayDetail.startsWith("{") || displayDetail.startsWith("["))) {
    try {
      displayDetail = JSON.stringify(JSON.parse(displayDetail), null, 2);
      isJson = true;
    } catch (e) {}
  }

  return (
    <div className="mb-8 relative pl-6 cursor-pointer group" onClick={() => setExpanded(!expanded)}>
      <div className={`absolute w-3 h-3 border-2 rounded-full -left-[6.5px] top-1 ${iconClass} group-hover:scale-110 transition-transform`}></div>
      
      <div className="flex items-center gap-2 mb-1">
        <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant">
          {new Date(evt.timestamp).toLocaleTimeString()}
        </span>
        <span className={`px-1.5 py-0.5 border rounded font-label-caps text-[9px] ${colorClass}`}>
          {badge}
        </span>
        <span className="material-symbols-outlined text-on-surface-variant text-[14px] opacity-0 group-hover:opacity-100 transition-opacity ml-auto">
          {expanded ? "expand_less" : "expand_more"}
        </span>
      </div>
      
      <p className="font-data-tabular text-data-tabular text-on-surface font-medium capitalize">
        {title}
      </p>
      
      <div className={`overflow-hidden transition-all duration-300 ${expanded ? 'max-h-[1000px] opacity-100 mt-2' : 'max-h-0 opacity-0'}`}>
        {displayDetail && (
          <pre className="font-mono-timestamp text-[10px] bg-surface-container-lowest border border-outline-variant p-3 rounded-DEFAULT overflow-x-auto text-on-surface-variant whitespace-pre-wrap">
            {displayDetail}
          </pre>
        )}
      </div>
      
      {/* Show truncated preview when collapsed */}
      {!expanded && displayDetail && (
        <p className="font-body-sm text-body-sm text-on-surface-variant mt-1 overflow-hidden text-ellipsis whitespace-nowrap opacity-60">
           {isJson ? "{ ... }" : displayDetail.substring(0, 50) + "..."}
        </p>
      )}
    </div>
  );
}

export default function Sandbox() {
  const [messages, setMessages] = useState<any[]>([]);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [isTriggering, setIsTriggering] = useState(false);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [phone, setPhone] = useState("+15550000000");
  const [isAuditOpen, setIsAuditOpen] = useState(false);

  useEffect(() => {
    setPhone("+1555" + Math.floor(1000000 + Math.random() * 9000000));
  }, []);
  
  // Form State
  const [caseType, setCaseType] = useState("Subscription Delinquency");
  const [rootCause, setRootCause] = useState("insufficient_funds");
  const [customerPersona, setCustomerPersona] = useState("considering_cancellation");
  const [isTyping, setIsTyping] = useState(false);
  
  // Reply State
  const [manualText, setManualText] = useState("");
  const [replyType, setReplyType] = useState("manual"); // manual, persona, delay

  // Polling ref
  const intervalRef = useRef<any>(null);

  const pollCaseData = async (caseId: string) => {
    try {
      const [chatRes, auditRes] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/cases/${caseId}/chat`),
        fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/cases/${caseId}/timeline`)
      ]);
      if (chatRes.ok) {
          const newMessages = await chatRes.json();
          if (newMessages.length > messages.length) {
              setMessages(newMessages);
              setIsTyping(false);
          }
      }
      if (auditRes.ok) setAuditEvents(await auditRes.json());
    } catch (e) {
      console.error("Polling error", e);
    }
  };

  const startPolling = (caseId: string) => {
    setActiveCaseId(caseId);
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => pollCaseData(caseId), 2000);
  };

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const triggerCase = async () => {
    setIsTriggering(true);
    setMessages([]);
    setAuditEvents([]);
    setActiveCaseId(null);
    try {
      setIsTyping(true);
      await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/sandbox/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, amount: 999.00, persona: customerPersona, root_cause: rootCause })
      });
      
      // We need the case ID. Let's poll the cases endpoint to find it.
      let caseId = null;
      for (let i = 0; i < 10; i++) {
        await new Promise(r => setTimeout(r, 1000));
        const casesRes = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/cases`);
        const cases = await casesRes.json();
        // Just grab the most recent one for now
        if (cases.length > 0) {
          caseId = cases[0].id;
          break;
        }
      }
      
      if (caseId) {
        startPolling(caseId);
      }
    } catch (err) {
      console.error("Trigger failed", err);
    } finally {
      setIsTriggering(false);
    }
  };

  const handleSend = async () => {
    if (!activeCaseId) return;
    
    if (replyType === "manual" && manualText) {
      setIsTyping(true);
      await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/sandbox/reply/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, text: manualText })
      });
      setManualText("");
    } else if (replyType.startsWith("persona:")) {
      setIsTyping(true);
      const persona = replyType.split(":")[1];
      await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/sandbox/reply/persona`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: activeCaseId, phone, persona })
      });
    }
  };

  const forceFollowup = async () => {
    if (!activeCaseId) return;
    await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/sandbox/force-cron`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: activeCaseId })
    });
  };

  return (
    <>
      {/* Top Action Bar */}
      <header className="h-16 border-b border-outline-variant bg-surface-container-lowest flex items-center justify-between px-gutter shrink-0 relative z-20">
        <h2 className="font-headline-md text-headline-md text-on-surface">
          Live Interaction Sandbox
        </h2>
        
        {/* Sandbox Indicator (Centered absolutely so it does not affect flex layout) */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-surface-container border border-outline-variant rounded-full px-4 py-1 flex items-center gap-2 z-10 shadow-sm opacity-80 pointer-events-none">
          <span className="material-symbols-outlined text-outline" style={{ fontSize: "16px" }}>
            experiment
          </span>
          <span className="font-label-caps text-label-caps text-on-surface-variant">
            SANDBOX MODE
          </span>
        </div>

        <button
          onClick={() => setIsAuditOpen(!isAuditOpen)}
          className="ml-auto flex items-center gap-2 bg-surface border border-outline-variant rounded-full px-4 py-1.5 hover:bg-surface-container transition-colors z-20 relative cursor-pointer"
        >
          <span className="material-symbols-outlined text-[16px]">history</span>
          <span className="font-label-caps text-label-caps">Audit Trail</span>
        </button>
      </header>

      <div className="flex-1 p-gutter flex gap-gutter overflow-hidden">
        {/* Left Panel: Case Initiator */}
        <div className="w-80 flex flex-col gap-margin border border-outline-variant rounded-lg bg-surface-container-lowest p-6 overflow-y-auto custom-scrollbar shrink-0">
          <div className="pb-4 border-b border-outline-variant">
            <h2 className="font-body-lg text-body-lg font-semibold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px]">
                rocket_launch
              </span>
              Case Initiator
            </h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
              Configure simulation parameters.
            </p>
          </div>
          <div className="flex flex-col gap-4">
            <div>
              <label className="block font-label-caps text-label-caps text-on-surface-variant mb-2">
                CASE TYPE
              </label>
              <select 
                value={caseType}
                onChange={e => setCaseType(e.target.value)}
                className="w-full bg-surface border-outline-variant focus:border-primary focus:ring-0 rounded-DEFAULT font-body-sm text-body-sm py-2"
              >
                <option>Subscription Delinquency</option>
                <option>Receivable Default</option>
                <option>Chargeback Dispute</option>
              </select>
            </div>
            <div>
              <label className="block font-label-caps text-label-caps text-on-surface-variant mb-2">
                ROOT CAUSE (SIMULATED)
              </label>
              <select 
                value={rootCause}
                onChange={e => setRootCause(e.target.value)}
                className="w-full bg-surface border-outline-variant focus:border-primary focus:ring-0 rounded-DEFAULT font-body-sm text-body-sm py-2"
              >
                <option value="expired_card">Card Expired</option>
                <option value="insufficient_funds">Insufficient Funds</option>
                <option value="intentional_evasion">Intentional Evasion</option>
                <option value="technical_error">Technical Error</option>
              </select>
            </div>
            <div>
              <label className="block font-label-caps text-label-caps text-on-surface-variant mb-2">
                CUSTOMER PERSONA
              </label>
              <select 
                value={customerPersona}
                onChange={e => setCustomerPersona(e.target.value)}
                className="w-full bg-surface border-outline-variant focus:border-primary focus:ring-0 rounded-DEFAULT font-body-sm text-body-sm py-2"
              >
                <option value="considering_cancellation">Considering Cancellation</option>
                <option value="angry_customer">Aggressive / Defensive</option>
                <option value="confused_customer">Cooperative but Confused</option>
                <option value="accidental_failure">Accidental Failure</option>
                <option value="suspicious_payer">Suspicious Payer</option>
                <option value="needs_payment_help">Needs Payment Help</option>
                <option value="ignores_completely">Ignores Completely</option>
                <option value="forgetful_promises_then_pays">Forgetful, Promises then Pays</option>
              </select>
            </div>
          </div>
          <div className="mt-auto pt-6">
            <button 
              onClick={triggerCase}
              disabled={isTriggering}
              className="w-full bg-primary text-on-primary py-3 rounded-DEFAULT font-data-tabular text-data-tabular flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>
                {isTriggering ? 'hourglass_empty' : 'play_arrow'}
              </span>
              {isTriggering ? 'Triggering...' : 'Trigger Case'}
            </button>
          </div>
        </div>

        {/* Center Panel: Live Chat Window */}
        <div className="flex-1 flex flex-col border border-outline-variant rounded-lg bg-surface-container-lowest overflow-hidden">
          {/* Chat Header */}
          <div className="h-16 border-b border-outline-variant bg-surface flex items-center justify-between px-6 shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-surface-container border border-outline-variant flex items-center justify-center">
                <span className="material-symbols-outlined text-on-surface-variant">person</span>
              </div>
              <div>
                <h3 className="font-data-tabular text-data-tabular text-on-surface">
                  Simulated Customer ({phone})
                </h3>
                <div className="flex items-center gap-1 text-emerald-600">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  <span className="font-label-caps text-label-caps">ONLINE</span>
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button className="p-2 text-on-surface-variant hover:bg-surface-container rounded-DEFAULT transition-colors">
                <span className="material-symbols-outlined">more_vert</span>
              </button>
            </div>
          </div>

          {/* Chat Canvas */}
          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-4 bg-surface-container-lowest custom-scrollbar">
            {activeCaseId && (
              <div className="flex justify-center my-2">
                <span className="bg-surface-variant text-on-surface-variant px-3 py-1 rounded-full font-mono-timestamp text-mono-timestamp text-[10px]">
                  Simulation Started
                </span>
              </div>
            )}
            
            {messages.length === 0 && activeCaseId && (
              <div className="text-center text-on-surface-variant font-body-sm py-4">Waiting for agent...</div>
            )}

            {messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === "agent" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[70%] flex flex-col ${msg.role === "agent" ? "items-end" : "items-start"}`}>
                  <div className={msg.role === "agent"
                        ? "bg-primary-container text-on-primary-container p-3 rounded-xl rounded-tr-sm border border-outline-variant/20 shadow-sm"
                        : "bg-surface text-on-surface p-3 rounded-xl rounded-tl-sm border border-outline-variant shadow-sm"
                    }
                  >
                    <p className="font-body-sm text-body-sm whitespace-pre-wrap">{msg.message}</p>
                  </div>
                  <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant mt-1 text-[10px]">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))}
            
            {/* Animated Typing Indicator */}
            {isTyping && activeCaseId && (
              <div className="flex justify-start">
                <div className="max-w-[70%] flex flex-col items-start">
                  <div className="bg-surface text-on-surface p-3 rounded-xl rounded-tl-sm border border-outline-variant shadow-sm flex items-center gap-1">
                    <span className="w-1.5 h-1.5 bg-on-surface-variant rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                    <span className="w-1.5 h-1.5 bg-on-surface-variant rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                    <span className="w-1.5 h-1.5 bg-on-surface-variant rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Reply Controls */}
          <div className="p-4 border-t border-outline-variant bg-surface shrink-0 flex flex-col gap-3">
            <div className="flex gap-2 items-center">
              <span className="font-label-caps text-label-caps text-on-surface-variant px-2">JUDGE OVERRIDE</span>
              <div className="h-px flex-1 bg-outline-variant/50"></div>
            </div>
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <textarea
                  className="w-full bg-surface-container-lowest border-outline-variant focus:border-primary focus:ring-0 rounded-DEFAULT font-body-sm text-body-sm py-2 px-3 resize-none disabled:opacity-50"
                  placeholder="Type manual response to test system routing..."
                  rows={2}
                  value={manualText}
                  onChange={e => setManualText(e.target.value)}
                  disabled={!activeCaseId || replyType !== "manual"}
                ></textarea>
              </div>
              <div className="w-48 flex flex-col gap-2">
                <select 
                  value={replyType}
                  onChange={e => setReplyType(e.target.value)}
                  className="w-full bg-surface-container-lowest border-outline-variant focus:border-primary focus:ring-0 rounded-DEFAULT font-label-caps text-label-caps py-1.5 h-8 disabled:opacity-50"
                  disabled={!activeCaseId}
                >
                  <option value="manual">Manual Text</option>
                  <option value="persona:angry_customer">Run Persona: Angry</option>
                  <option value="persona:confused_customer">Run Persona: Confused</option>
                </select>
                <button 
                  onClick={handleSend}
                  disabled={!activeCaseId}
                  className="w-full bg-surface-container-lowest border border-outline-variant text-on-surface hover:bg-surface-container py-1.5 rounded-DEFAULT font-data-tabular text-data-tabular flex items-center justify-center gap-1 h-8 disabled:opacity-50 transition-colors"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>send</span>
                  Send
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Side Sheet: Live Audit Trail */}
      {isAuditOpen && (
        <>
          {/* Blurred Backdrop */}
          <div 
            className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
            onClick={() => setIsAuditOpen(false)}
          />
          {/* Side Sheet Panel */}
          <div className="fixed right-0 top-0 h-full w-[400px] bg-surface-container-lowest z-50 shadow-2xl flex flex-col p-6 animate-in slide-in-from-right-full duration-300">
            <div className="pb-4 border-b border-outline-variant flex justify-between items-end shrink-0">
              <div className="flex items-center gap-3">
                <button 
                  onClick={() => setIsAuditOpen(false)}
                  className="p-1 hover:bg-surface-container rounded-full transition-colors text-on-surface-variant flex items-center justify-center"
                >
                  <span className="material-symbols-outlined">close</span>
                </button>
                <h2 className="font-body-lg text-body-lg font-semibold text-on-surface flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px]">history</span>
                  Audit Trail
                </h2>
              </div>
              <div className="flex items-center gap-1 bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-DEFAULT">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="font-label-caps text-label-caps">LIVE</span>
              </div>
            </div>

            {/* Timeline */}
            <div className="flex-1 overflow-y-auto pr-2 relative custom-scrollbar mt-4">
              <div className="relative border-l border-outline-variant ml-3 pb-6">
                
                {auditEvents.length === 0 && (
                  <div className="text-on-surface-variant font-body-sm pl-4">No events yet...</div>
                )}

                {auditEvents.map((evt, idx) => (
                  <TimelineNode key={idx} evt={evt} idx={idx} />
                ))}
                
              </div>
            </div>

            <div className="pt-4 border-t border-outline-variant shrink-0 mt-auto">
              <button 
                onClick={forceFollowup}
                disabled={!activeCaseId}
                className="w-full bg-surface-container-lowest border border-outline-variant text-on-surface py-2 rounded-DEFAULT font-data-tabular text-data-tabular flex items-center justify-center gap-2 hover:bg-surface transition-colors disabled:opacity-50"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>update</span>
                Check Follow-ups Now
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
