"use client";

import { useState, useEffect } from "react";

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
  } else if (evt.type === "transition") {
    badge = "State";
    title = `Transition: ${evt.to}`;
    displayDetail = evt.reason || "";
    colorClass = "bg-secondary-container border-secondary text-on-secondary-container";
    iconClass = "bg-secondary-container border-secondary";
  } else if (evt.type === "intervention") {
    badge = "Agent";
    title = "Intervention Sent";
    displayDetail = evt.message;
    colorClass = "bg-primary-fixed border-primary text-on-primary-fixed";
    iconClass = "bg-primary-fixed border-primary";
  } else if (evt.type === "reply") {
    badge = "Customer";
    title = "Reply Received";
    displayDetail = evt.message;
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

export default function Explorer() {
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [cases, setCases] = useState<any[]>([]);
  const [activeCase, setActiveCase] = useState<any>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState("All");
  
  useEffect(() => {
    fetchCases();
  }, [statusFilter]);

  const fetchCases = async () => {
    setLoading(true);
    try {
      let url = "https://revenuerecoveryagent.onrender.com/api/cases";
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
      const res = await fetch(`https://revenuerecoveryagent.onrender.com/api/cases/${c.id}/timeline`);
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
            />
          </div>
          <button className="p-2 text-on-surface-variant border border-outline-variant bg-surface-container-lowest rounded hover:bg-surface-container-low transition-colors flex items-center gap-2">
            <span className="material-symbols-outlined">filter_list</span>
            <span className="font-label-caps text-label-caps">Filters</span>
          </button>
          <button className="p-2 text-on-surface-variant border border-outline-variant bg-surface-container-lowest rounded hover:bg-surface-container-low transition-colors flex items-center gap-2">
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
          <option value="resolved">Resolved</option>
          <option value="pending">Pending</option>
          <option value="escalated">Escalated</option>
        </select>
        <div className="ml-auto flex items-center gap-2">
          <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant">
            Showing {cases.length} Cases
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
              ) : cases.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-on-surface-variant font-body-sm">
                    No cases found.
                  </td>
                </tr>
              ) : (
                cases.map((c) => (
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
                      ${c.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
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
                  <TimelineNode key={idx} evt={evt} idx={idx} />
                ))}
              </div>
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
