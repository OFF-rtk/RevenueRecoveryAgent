# Frontend Updates (Deferred)

The Dashboard's case-timeline UI needs to be updated to render the newly available audit event data. This will be implemented after the backend testing phase is complete.

## Required Changes
- Update `dashboard/src/app/explorer/page.tsx`'s `TimelineNode` component.
- The `type` returned by `get_case_timeline` is either `audit`, `state_transition`, `intervention_sent`, `customer_reply`, or `followup_sent`. The frontend currently checks for `transition`, `intervention`, and `reply`, which are mismatched and need correcting.
- Add specific rendering logic for `evt.event === "diagnosis_completed"`. 
- Render the diagnosis event as explicitly requested: **"Diagnosed: insufficient_funds (tier 1, conf 0.91)"** along with its reasoning payload.
- Map the backend `payload` fields accurately into the UI display format.
