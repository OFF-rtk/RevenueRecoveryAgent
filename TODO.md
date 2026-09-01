# Phase 2 TODOs

- [ ] **Enhance `followup_draft_v1` Prompt (Context & Formatting)**: 
  - **Context**: Extract `product_name` / `invoice_description` from the Razorpay Webhook payload, save it to the `Case` database model (e.g., in `raw_payload`), and include this information in the `followup_draft_v1` prompt context. This will allow the LLM to directly answer the customer's questions about what the invoice is for (e.g., "Razorpay Premium Plan") instead of just vaguely pointing to the payment link, which currently makes skeptical personas (like `disputes_easily`) refuse to pay.
  - **Formatting**: Ensure the prompt instructs the LLM to output the message in valid JSON format with a single `message` key, and add a fallback message in the Python code to prevent crashes if the LLM returns malformed JSON.
