# Judge Dashboard & Sandbox — Specification

## Purpose

Give judges a way to *see* proof of the track's stated bar — measured money recovered, compliant escalation, stopping rules, and an audit trail — without needing to read raw JSON reports or trust our word for it. Two parts: a **Dashboard** (read-only, shows what already happened) and a **Sandbox** (interactive, lets a judge trigger and watch a new case happen live).

## Core architectural principle — non-negotiable

**Both parts read directly from our real Postgres tables** (`cases`, `diagnoses`, `interventions`, `replies`, `state_transitions`, `audit_events`, `outcomes`). No parallel data store, no mocked/precomputed display data. If the UI shows something, it's because it genuinely happened in the real system — same integrity standard as everywhere else in this build. The Sandbox triggers real webhook/diagnosis/messaging code paths, not a simulated re-implementation of them.

---

## Part A — Dashboard (read-only)

### A1. Batch Summary (landing view)
- Latest batch report headline numbers: total cases, recovery rate, total ₹ recovered vs at risk, diagnosis accuracy, tier-1/tier-2 escalation split, escalation recall (X/10 on hand-authored ambiguous cases)
- Per-persona recovery breakdown (from the live persona batch), with raw counts alongside percentages, not percentages alone
- Clear visual/textual distinction between the two evidence sources: the ground-truth-labeled local batch (diagnosis accuracy) vs. the live-deployed LLM-persona batch (recovery rate) — don't blend them into one undifferentiated number

### A2. Case Browser
- List of all cases, filterable by: outcome (`recovered` / `escalated` / `disputed` / `payment_method_required` / `stopped` / `pending`), case type (`failed_subscription` / `overdue_receivable`), diagnosis tier (1 or 2)
- Each row: case ID, amount, cause, final status, at a glance

### A3. Case Detail View — the audit trail, made visual
- Select any case → chronological timeline of every `audit_events` row for that case, e.g.:
  `[10:19:14] Webhook received (payment.failed) → [10:19:15] Diagnosed: insufficient_funds (tier 1, conf 0.91) → [10:19:16] Template sent: payment_recovery_notice_v1 → [10:20:02] Reply received → [10:20:03] Classified: promise_made → [Mon 09:00] Manual follow-up check → [Mon 09:01] Payment captured (Razorpay webhook) → Outcome: recovered, ₹999`
- Distinctly labeled event types for the three specific things judges are told to look for:
  - **Stopping rule triggers** (opt-out honored, max-retry cap hit) — visually flagged, not buried among regular events
  - **Escalation events**, explicitly sub-typed: retry-exhausted vs. `disputed_escalation` vs. `escalation_pending_human_data` (the "agent didn't have the data, escalated honestly instead of fabricating" case) — these are different findings and should read as different things
  - **Manual triggers** (e.g. `manual_followup_check_triggered`) clearly marked as manual, never presented as if they were an automatic cron fire

### A4. Templates Reference (small, optional)
- The 4 approved WhatsApp templates, shown as-approved (name, category, body), so a judge can see the actual compliant message shapes without digging into Meta's dashboard

---

## Part B — Sandbox (interactive)

### B1. Case Initiator
- A judge picks: case type (subscription/receivable), a cause (dropdown of canonical causes, including a couple of the deliberately ambiguous ones), and clicks **Trigger Case**
- This fires a real, signed synthetic Razorpay webhook at our live endpoint — same mechanism our own test scripts use, not a fake button
- Real diagnosis runs, real first-contact WhatsApp template sends (to our real test number, per Meta's constraints — the judge doesn't need their own WhatsApp)

### B2. Live Chat Window
- Renders the conversation as it actually happens, reading live from `interventions`/`replies` rows for this case — a chat-bubble UI mirroring the real WhatsApp thread, updating as new rows land (poll or websocket)
- This is the same underlying data our real phone receives; the UI is a second window onto the same real events, not a separate simulation

### B3. Reply Controls — the two-mode interaction
For each turn where a reply is expected, the judge chooses one of:
- **Type a reply themselves** — free-text box, submitted as a signed inbound webhook to our real endpoint, indistinguishable to our system from a real customer message
- **Let an LLM persona respond** — dropdown of our defined personas (`accidental_failure`, `suspicious_payer`, `needs_payment_help`, `considering_cancellation`, `ignores_completely`, `forgetful_promises_then_pays`), a **Run Persona** button generates and sends that persona's in-character reply through the same signed-webhook path

### B4. Time Advancement
- A **Check Follow-ups Now** button, reusing our existing manual follow-up trigger — lets a judge skip past a real-time wait to see a scheduled follow-up or retry-cap escalation fire on demand
- Clearly labeled in the UI as a manual stand-in for a production cron job, matching how it's labeled in the audit trail itself

### B5. Live Audit Trail Panel
- Runs alongside the chat window, updating in real time as the judge's sandbox case progresses — same timeline component as A3, just live instead of historical

### B6. Reset / New Case
- Simple control to end the current sandbox case and start a fresh one

---

## Explicit non-goals

- No parallel/mocked backend logic — every sandbox action calls our real endpoints
- No fabricated demo data anywhere in the dashboard — if a metric shows, it's computed from real rows
- No requirement for the judge to have WhatsApp themselves — the chat window is the interface, real WhatsApp delivery happens in parallel to our own number
- Not a general admin panel — scoped narrowly to what proves the track's bar, not a full internal ops tool

## Build note

Given the "full day or don't build it" rule already set for this feature: if remaining time gets tight, the Dashboard (Part A) alone — without the interactive Sandbox (Part B) — is a legitimate, still-valuable fallback scope, since it already demonstrates all three of the PS's named requirements (recovery numbers, escalation, stopping rules, audit trail) without needing the live-trigger complexity. Cut B before cutting A if time runs short.