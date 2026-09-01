#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure the project root is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from core.models.cases import Case
from core.models.replies import Reply
from core.models.interventions import Intervention
from core.models.audit_events import AuditEvent
from core.channels.mock import MockChannel
from core.channels.whatsapp import WhatsAppChannel
from core.config import settings
from core.services.state_machine import draft_and_send_followup


async def check_followup(case_id_str: str, force: bool):
    try:
        case_id = uuid.UUID(case_id_str)
    except ValueError:
        print(f"❌ Invalid UUID: {case_id_str}")
        return

    db_url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        case = await session.get(Case, case_id)
        if not case:
            print(f"❌ Case {case_id_str} not found.")
            return

        print(f"🔍 Checking follow-up for Case {case_id}")
        print(f"Current Status: {case.status}")

        if case.status not in ("promise_pending", "payment_method_required", "open"):
            if not force:
                print(f"⏭️ Case is in terminal state '{case.status}'. Skipping (use --force to override).")
                return
            else:
                print(f"⚠️ Forcing follow-up on terminal case ({case.status}).")

        # Fetch latest reply to check 24-hour window
        result = await session.execute(
            select(Reply).where(Reply.case_id == case.id).order_by(Reply.received_at.desc()).limit(1)
        )
        latest_reply = result.scalars().first()

        is_session_open = False
        if latest_reply and latest_reply.received_at:
            time_since_reply = datetime.now(timezone.utc) - latest_reply.received_at
            if time_since_reply < timedelta(hours=24):
                is_session_open = True
                
        # Determine channel
        if settings.use_mock_channel:
            channel = MockChannel()
            print("🔧 Using MockChannel for testing.")
        else:
            channel = WhatsAppChannel(
                phone_number_id=settings.phone_number_id,
                api_token=settings.whatsapp_token
            )

        print(f"📱 WhatsApp Session Open: {is_session_open}")

        if is_session_open:
            print(f"🧠 Generating contextual follow-up via LLM...")
            # We reuse the exact batch runner / state machine logic for free-text follow ups
            await draft_and_send_followup(
                case=case, 
                customer_reply=latest_reply.raw_reply if latest_reply else "", 
                classified_state=latest_reply.classified_state if latest_reply else "unknown", 
                channel=channel,
                session=session
            )
            print(f"✅ Follow-up sent and logged successfully to audit_events (via draft_and_send_followup)!")
            
        else:
            print(f"📜 Sending fallback template outside 24h window...")
            template_used = "payment_reminder_followup_v1"
            parameters = [str(case.currency), str(case.amount), str(case.customer_ref)]
            
            channel_response = await channel.send_template(
                to=case.customer_ref,
                template_name=template_used,
                parameters=parameters
            )
            sent_representation = f"[{template_used}] {parameters}"

            # Get the next attempt number
            result = await session.execute(
                select(func.max(Intervention.attempt_number)).where(Intervention.case_id == case.id)
            )
            last_attempt = result.scalar() or 0
            next_attempt = last_attempt + 1

            # Save Intervention record
            intervention = Intervention(
                case_id=case.id,
                channel=channel.name,
                message_sent=sent_representation,
                attempt_number=next_attempt
            )
            session.add(intervention)
            
            # Save Audit Event
            audit_event = AuditEvent(
                case_id=case.id,
                event_type="manual_followup_check_triggered",
                payload={
                    "channel": channel.name,
                    "session_open": is_session_open,
                    "attempt_number": next_attempt,
                    "template_used": template_used,
                }
            )
            session.add(audit_event)
            
            await session.commit()
            print(f"✅ Follow-up template sent (Attempt #{next_attempt}) and logged successfully to audit_events!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manually trigger a follow-up for a case.")
    parser.add_argument("--case-id", type=str, required=True, help="The UUID of the case")
    parser.add_argument("--force", action="store_true", help="Force follow-up even if case is in a terminal state")
    
    args = parser.parse_args()
    asyncio.run(check_followup(args.case_id, args.force))
