# Phase 4: Intervention Layer

## Objective
Translate the root cause diagnosed in Phase 3 into a tailored, tone-correct recovery message, and dispatch it via a channel abstraction.

## Key Outcomes

1. **Prompt Engineering (`prompts/message_draft_v1.txt`)**
   - Created a prompt specifically designed for copywriting a polite and empathetic recovery message.
   - Instructs the LLM to write in Hinglish (a mix of Hindi and English) to appeal to the target demographic.
   - Embeds a clear "Call to Action" based directly on the diagnosed failure `cause` (e.g., asking to update a card for `expired_card`).

2. **Channel Abstractions (`core/channels/`)**
   - Created `BaseChannel` as a standard interface.
   - Implemented `MockChannel` which simulates message delivery by logging it to the console/DB, preventing accidental spam during development.
   - Stubbed out `WhatsAppChannel` which will be used in the future to plug into the real Meta WhatsApp Cloud API.

3. **Intervention Service (`core/services/intervention.py`)**
   - Implemented `draft_and_send_intervention` to orchestrate the LLM call (`openai/gpt-oss-20b`) and channel delivery.
   - Successfully tied the new `Intervention` record to the originating `Case`.
   - Hardened observability by logging the drafted message, channel, and LLM metadata directly to the `audit_events` table as an `intervention_sent` event.

4. **Testing and Verification (`tests/test_phase4.py`)**
   - Wrote a test to verify the end-to-end intervention flow using the mock channel.
   - Validated that both the `Intervention` record and the `AuditEvent` are saved correctly to the database.
   - All tests pass locally against the Postgres instance.

## Next Steps
Proceed to Phase 5: Reply Interpretation + Promise-to-Pay State Machine. This will allow the agent to understand inbound messages from customers who reply to these interventions.
