"use client";

import { useState, useEffect } from "react";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("all");
  const [summary, setSummary] = useState<any>(null);
  const [personas, setPersonas] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [summaryRes, personasRes] = await Promise.all([
          fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/dashboard/summary`),
          fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001"}/api/dashboard/persona-breakdown`)
        ]);
        const summaryData = await summaryRes.json();
        const personasData = await personasRes.json();
        
        setSummary(summaryData);
        setPersonas(personasData);
      } catch (err) {
        console.error("Failed to fetch dashboard data", err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-surface-container-lowest">
        <div className="flex flex-col items-center gap-4">
          <span className="material-symbols-outlined animate-spin text-primary" style={{ fontSize: "32px" }}>sync</span>
          <span className="font-label-caps text-label-caps text-on-surface-variant">Loading Dashboard Data...</span>
        </div>
      </div>
    );
  }

  return (
    <>
      <header className="sticky top-0 z-40 flex items-center justify-between w-full h-16 px-gutter bg-surface border-b border-outline-variant shrink-0">
        <div className="flex items-center gap-4">
          <h2 className="font-headline-md text-headline-md text-on-surface">
            Batch Summary
          </h2>
          <span className="px-2 py-1 bg-surface-variant text-on-surface rounded font-mono-timestamp text-mono-timestamp">
            Batch ID: BT-24X9A
          </span>
        </div>
        <div className="flex items-center gap-4 text-on-surface-variant">
          <span className="material-symbols-outlined hover:text-primary cursor-pointer transition-colors">
            download
          </span>
          <span className="material-symbols-outlined hover:text-primary cursor-pointer transition-colors">
            filter_list
          </span>
        </div>
      </header>
      
      <div className="p-margin max-w-container-max mx-auto w-full space-y-margin pb-20 overflow-y-auto custom-scrollbar">
        {/* Headline Numbers */}
        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-gutter">
          {/* Total Cases */}
          <div className="bg-surface-container-lowest border border-outline-variant rounded p-density-comfortable flex flex-col justify-between">
            <p className="font-label-caps text-label-caps text-on-surface-variant mb-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-[14px]">
                library_books
              </span>
              Total Cases Processed
            </p>
            <div className="flex items-end justify-between">
              <span className="font-display text-display text-on-surface">
                {summary?.total_cases || 0}
              </span>
              <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant flex items-center">
                <span className="material-symbols-outlined text-[12px] text-green-600">
                  arrow_upward
                </span>
                +12%
              </span>
            </div>
          </div>
          {/* Recovery Rate */}
          <div className="bg-surface-container-lowest border border-outline-variant rounded p-density-comfortable flex flex-col justify-between">
            <p className="font-label-caps text-label-caps text-on-surface-variant mb-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-[14px]">
                check_circle
              </span>
              Overall Recovery Rate
            </p>
            <div className="flex items-end justify-between">
              <span className="font-display text-display text-on-surface">
                {summary?.overall_recovery_rate || 0}%
              </span>
              <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant flex items-center">
                <span className="material-symbols-outlined text-[12px] text-red-600">
                  arrow_downward
                </span>
                -2.1%
              </span>
            </div>
          </div>
          {/* Financials */}
          <div className="bg-surface-container-lowest border border-outline-variant rounded p-density-comfortable flex flex-col justify-between lg:col-span-2">
            <p className="font-label-caps text-label-caps text-on-surface-variant mb-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-[14px]">
                account_balance
              </span>
              Total Recovered vs At Risk
            </p>
            <div className="flex items-end justify-between w-full">
              <div>
                <span className="font-display text-display text-on-surface">
                  ${(summary?.total_recovered || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant block mt-1">
                  Recovered
                </span>
              </div>
              <div className="h-8 w-[1px] bg-outline-variant mx-4"></div>
              <div className="text-right">
                <span className="font-display text-display text-on-surface-variant">
                  ${(summary?.total_at_risk || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span className="font-mono-timestamp text-mono-timestamp text-on-surface-variant block mt-1">
                  At Risk (Pending)
                </span>
              </div>
            </div>
            {/* Progress Bar */}
            <div className="w-full h-1.5 bg-surface-variant mt-3 rounded-full overflow-hidden">
              <div className="h-full bg-primary" style={{ width: `${summary?.overall_recovery_rate || 0}%` }}></div>
            </div>
          </div>
        </section>
        
        {/* Evidence Sources Breakdown */}
        <section>
          <h3 className="font-headline-md text-headline-md text-on-surface mb-gutter">
            Evidence Sources Breakdown
          </h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-gutter">
            {/* Ground Truth Local Batch */}
            <div className="bg-surface-container-lowest border border-outline-variant rounded flex flex-col overflow-hidden relative">
              <div className="absolute inset-0 bg-gradient-to-br from-surface-container-low to-transparent opacity-50 pointer-events-none"></div>
              <div className="p-density-comfortable border-b border-outline-variant bg-surface-container-low relative z-10">
                <div className="flex items-center justify-between">
                  <h4 className="font-body-lg text-body-lg font-semibold text-on-surface flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px]">
                      database
                    </span>
                    Ground Truth Local Batch
                  </h4>
                  <span className="px-2 py-0.5 bg-surface-variant text-on-surface rounded text-[10px] font-bold uppercase tracking-widest border border-outline-variant">
                    Verified
                  </span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
                  Static historical datasets used for primary baseline accuracy
                  validation.
                </p>
              </div>
              <div className="p-density-comfortable flex-1 flex flex-col gap-4 relative z-10">
                <div className="flex justify-between items-center pb-3 border-b border-outline-variant border-dashed">
                  <span className="font-data-tabular text-data-tabular text-on-surface-variant">
                    Diagnosis Accuracy
                  </span>
                  <span className="font-data-tabular text-data-tabular text-on-surface font-semibold">
                    {summary?.diagnosis_accuracy || 0}%
                  </span>
                </div>
                <div className="flex justify-between items-center pb-3 border-b border-outline-variant border-dashed">
                  <span className="font-data-tabular text-data-tabular text-on-surface-variant">
                    False Positive Rate
                  </span>
                  <span className="font-data-tabular text-data-tabular text-on-surface font-semibold">
                    {summary?.false_positive_rate || 0}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-data-tabular text-data-tabular text-on-surface-variant">
                    Total Volume Processed
                  </span>
                  <span className="font-data-tabular text-data-tabular text-on-surface font-semibold">
                    {summary?.total_cases || 0} Cases
                  </span>
                </div>
              </div>
            </div>
            
            {/* Live LLM-Persona Batch */}
            <div className="bg-surface-container-lowest border border-outline-variant rounded flex flex-col overflow-hidden relative">
              {/* Simulated 'Blueprint' grid background pattern */}
              <div
                className="absolute inset-0 opacity-[0.03] pointer-events-none"
                style={{
                  backgroundImage: "radial-gradient(#000 1px, transparent 1px)",
                  backgroundSize: "16px 16px",
                }}
              ></div>
              <div className="p-density-comfortable border-b border-outline-variant bg-surface-variant relative z-10">
                <div className="flex items-center justify-between">
                  <h4 className="font-body-lg text-body-lg font-semibold text-on-surface flex items-center gap-2">
                    <span className="material-symbols-outlined text-[18px]">
                      psychology
                    </span>
                    Live LLM-Persona Batch
                  </h4>
                  <span className="px-2 py-0.5 bg-surface text-on-surface rounded text-[10px] font-bold uppercase tracking-widest border border-outline-variant border-dashed">
                    Interactive
                  </span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-1">
                  Dynamic simulated interactions testing dynamic negotiation paths.
                </p>
              </div>
              <div className="p-density-comfortable flex-1 flex flex-col gap-4 relative z-10">
                <div className="flex justify-between items-center pb-3 border-b border-outline-variant border-dashed">
                  <span className="font-data-tabular text-data-tabular text-on-surface-variant">
                    Simulated Recovery Rate
                  </span>
                  <span className="font-data-tabular text-data-tabular text-on-surface font-semibold">
                    {summary?.overall_recovery_rate || 0}%
                  </span>
                </div>
                <div className="flex justify-between items-center pb-3 border-b border-outline-variant border-dashed">
                  <span className="font-data-tabular text-data-tabular text-on-surface-variant">
                    Avg. Interaction Turns
                  </span>
                  <span className="font-data-tabular text-data-tabular text-on-surface font-semibold">
                    {summary?.avg_interaction_turns || 0}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-data-tabular text-data-tabular text-on-surface-variant">
                    Total Volume Processed
                  </span>
                  <span className="font-data-tabular text-data-tabular text-on-surface font-semibold">
                    {summary?.total_cases || 0} Cases
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
        
        {/* Per-Persona Recovery Table */}
        <section>
          <h3 className="font-headline-md text-headline-md text-on-surface mb-gutter">
            Per-Persona Recovery Breakdown
          </h3>
          <div className="bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead className="bg-surface-container-low border-b border-outline-variant">
                <tr>
                  <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant w-1/3">
                    Persona Profile
                  </th>
                  <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant text-right">
                    Attempted
                  </th>
                  <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant text-right">
                    Recovered
                  </th>
                  <th className="py-3 px-4 font-label-caps text-label-caps text-on-surface-variant text-right">
                    Success Rate
                  </th>
                </tr>
              </thead>
              <tbody className="font-data-tabular text-data-tabular divide-y divide-outline-variant">
                {personas.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-4 px-4 text-center text-on-surface-variant font-body-sm text-body-sm">
                      No persona data available. Run the harness first.
                    </td>
                  </tr>
                ) : (
                  personas.map((p, idx) => (
                    <tr key={idx} className="hover:bg-surface-variant transition-colors group">
                      <td className="py-3 px-4 text-on-surface flex items-center gap-2 capitalize">
                        <span className={`w-2 h-2 rounded-full ${
                          p.success_rate >= 80 ? 'bg-emerald-600' : p.success_rate >= 50 ? 'bg-amber-500' : 'bg-red-500'
                        }`}></span>
                        {p.persona.replace(/_/g, ' ')}
                      </td>
                      <td className="py-3 px-4 text-right text-on-surface-variant">
                        {p.attempted}
                      </td>
                      <td className="py-3 px-4 text-right text-on-surface">{p.recovered}</td>
                      <td className="py-3 px-4 text-right">
                        <span className={`px-2 py-1 rounded font-mono-timestamp text-mono-timestamp ${
                          p.success_rate >= 80 ? 'bg-emerald-100 text-emerald-800' : p.success_rate >= 50 ? 'bg-surface-container text-on-surface' : 'bg-red-100 text-red-800'
                        }`}>
                          {p.success_rate}%
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}
