# Phase 6: Intervention Strategy & Actioning

## Overview
Phase 6 handles the actions taken based on the diagnosis from Phase 5. It enforces stopping rules, determines the appropriate intervention (e.g., sending a specific WhatsApp template), and executes the action through mocked channels.

## Interview-Ready Bullet Points

- **Rule-Based Stopping Engine**: Implemented hard safety gates (`core/services/stopping_rules.py`) that evaluate case state before any intervention is allowed.
  - **No Blind Retries**: Prevents repeated messages for hard failures (e.g., `invalid_card`, `wrong_details`).
  - **Max Interventions**: Caps the total number of communications sent to a single customer to prevent spam.
- **Dynamic Intervention Mapping**: Maps the resolved canonical cause to one of several pre-approved intervention templates (e.g., `payment_reminder_followup_v1`, `invoice_reminder_notice_v1`).
- **Template Rendering**: Parameterizes external communications. Supports templates with variable slots (e.g., `{{currency}}`, `{{amount}}`, `{{cause}}`) to inject contextual data into the WhatsApp payload.
- **Mock Channel Integration**: Designed a pluggable `MockChannel` architecture for testing the end-to-end communication flow. The system simulates sending the WhatsApp message, updating case states, and writing to the audit log asynchronously.
- **Strict Determinism & Observability**: Every intervention attempt, whether successful or blocked by a stopping rule, is durably written to the `audit_events` database table with its associated `case_id`.

## Accomplishments
- Ensured compliance with customer communication limits by preventing spam and unwanted messages.
- Decoupled the diagnosis logic from the intervention logic, allowing them to scale and be tested independently.
- Finalized message payload delivery logic, bringing the agent closer to real-world webhook integration.
