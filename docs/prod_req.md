# Production Deployment & Live Test Requirements

## Objective
The final evaluation phase involves deploying the Revenue Recovery Agent to a live environment and connecting it to actual external services. We will simulate 100 live cases by firing real Razorpay webhooks and using an independent LLM script hooked to a real WhatsApp number to act as the "mock customer".

## Infrastructure Requirements
1. **Hosting Environment**: 
   - A live server (e.g., Render, AWS EC2, Fly.io, or Railway) to host the FastAPI application.
   - The server must expose a public HTTPS endpoint for webhooks (Razorpay and WhatsApp).
2. **Database**: 
   - A managed PostgreSQL instance (e.g., Supabase, Neon, RDS) accessible by the deployed application.
   - Run database migrations (`main.py` startup or alembic) to ensure the `cases`, `interventions`, and `audit_events` tables exist.

## External Integrations
1. **Meta WhatsApp Cloud API**:
   - Registered Meta Developer App with WhatsApp product enabled.
   - A verified test phone number or production business number.
   - `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_ACCESS_TOKEN` populated in production secrets.
   - Webhook URL configured in the Meta dashboard to point to `/webhooks/whatsapp` with a verified `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
   - Message templates (e.g. `payment_recovery_notice_v1`) approved in the WhatsApp Manager.
2. **Razorpay Webhooks**:
   - Razorpay Dashboard test mode configured to point to `/webhooks/razorpay`.
   - `RAZORPAY_WEBHOOK_SECRET` populated in production secrets for signature validation.

## The "Live Fire" 100-Case Test Run
Instead of using static JSON fixtures, we will run the final end-to-end test live:
1. **Webhook Injection**: 
   - A script will randomly select and inject 100 Razorpay webhooks (simulating `payment.failed`, `subscription.halted`, `invoice.expired`) directly into the production FastAPI endpoint over HTTPS.
2. **The LLM Customer Impersonator**:
   - The agent will send real WhatsApp messages to your configured mobile number.
   - We will run a separate independent script locally on your machine (the "impersonator"). This script will hook into your WhatsApp (via Twilio or a similar receiver, or just manual automation) and use an LLM (e.g. GPT-4o) to generate replies based on predefined personas (e.g., "angry customer", "confused user", "wants to pay but needs a link").
3. **Data Collection & Reporting**:
   - The production database will record the full audit trail.
   - At the end of the 100 cases, we will export the data and generate the final `batch_report.md` for pitch submission, proving the real-world recovery rate and diagnosis accuracy.
