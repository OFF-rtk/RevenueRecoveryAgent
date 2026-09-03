import asyncio
import os
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from datetime import datetime, timezone
import json

from core.models.cases import Case
from core.models.interventions import Intervention
from core.models.audit_events import AuditEvent
from core.models.state_transitions import StateTransition
from core.models.replies import Reply

async def main():
    engine = create_async_engine(os.getenv("DATABASE_URL", "postgresql+asyncpg://revenue_recovery_db_jqur_user:D3s1iccskubcIe3txXWtvopU8fHukcqj@dpg-dab99b142hec73a9l4sg-a.singapore-postgres.render.com/revenue_recovery_db_jqur"))
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Case 1
        case1 = Case(
            case_type="failed_subscription",
            customer_ref="919000005901",
            amount=Decimal("999.00"),
            currency="INR",
            raw_failure_reason="BAD_REQUEST_ERROR",
            tenure=1,
            raw_payload={"persona": "considering_cancellation"},
            status="stopped"
        )
        session.add(case1)
        await session.flush()
        
        # Interventions and Replies for Case 1
        int1_1 = Intervention(case_id=case1.id, channel="whatsapp", message_sent="[payment_recovery_notice_v1] ['INR', '999.00', '919000005901', 'your card had insufficient funds']")
        rep1_1 = Reply(case_id=case1.id, raw_reply="Hmm, my card had insufficient funds. I'm not sure if I still want this. Can you tell me what I'd lose if I cancel or if I pause for a month? Maybe I can try again later.")
        session.add_all([int1_1, rep1_1])
        
        int1_2 = Intervention(case_id=case1.id, channel="whatsapp", message_sent="Cancelling will remove all premium features; pausing for a month stops billing but keeps access. You can update your card here: https://rzp.io/i/8e8a274f")
        session.add(int1_2)
        
        # Audit Events for Case 1
        ae1 = AuditEvent(case_id=case1.id, event_type="webhook_received", payload={"reason": "payment failed"})
        ae2 = AuditEvent(case_id=case1.id, event_type="diagnosis_completed", payload={"diagnosis": "insufficient funds"})
        ae3 = AuditEvent(case_id=case1.id, event_type="persona_simulation_started", payload={"persona": "considering_cancellation", "internal_reasoning": "I’m on the fence and want more info before deciding. I’m asking for clarification rather than committing to payment."})
        ae4 = AuditEvent(case_id=case1.id, event_type="state_transition", payload={"from_state": "open", "to_state": "in_progress", "reason": "agent engaged"})
        ae5 = AuditEvent(case_id=case1.id, event_type="agent_intervention", payload={"message": "Hi, this is a message from Razorpay. Your payment of INR 999.00 for your subscription (919000005901) failed because your card had insufficient funds. Please pay here to continue using the service."})
        ae6 = AuditEvent(case_id=case1.id, event_type="customer_reply", payload={"message": "Hmm, my card had insufficient funds. I'm not sure if I still want this. Can you tell me what I'd lose if I cancel or if I pause for a month? Maybe I can try again later.", "classified_state": "promise_made"})
        ae7 = AuditEvent(case_id=case1.id, event_type="state_transition", payload={"from_state": "in_progress", "to_state": "stopped", "reason": "customer decided to pause"})
        ae8 = AuditEvent(case_id=case1.id, event_type="agent_intervention", payload={"message": "Cancelling will remove all premium features; pausing for a month stops billing but keeps access. You can update your card here: https://rzp.io/i/8e8a274f"})
        session.add_all([ae1, ae2, ae3, ae4, ae5, ae6, ae7, ae8])

        # Case 2
        case2 = Case(
            case_type="failed_subscription",
            customer_ref="919000005902",
            amount=Decimal("999.00"),
            currency="INR",
            raw_failure_reason="BAD_REQUEST_ERROR",
            tenure=1,
            raw_payload={"persona": "considering_cancellation"},
            status="promise_pending"
        )
        session.add(case2)
        await session.flush()
        
        int2_1 = Intervention(case_id=case2.id, channel="whatsapp", message_sent="[payment_recovery_notice_v1] ['INR', '999.00', '919000005902', 'your card had insufficient funds']")
        rep2_1 = Reply(case_id=case2.id, raw_reply="Thanks for the notice. I'm not sure I really need the service right now. What would I lose if I cancel? Also, could I try again in a couple of days once I have enough funds?")
        
        int2_2 = Intervention(case_id=case2.id, channel="whatsapp", message_sent="If you cancel, you'll lose access to premium features and support. You can re‑subscribe anytime; when ready, pay here: https://rzp.io/i/7bd8d183")
        rep2_2 = Reply(case_id=case2.id, raw_reply="Thanks for the info. I need a bit more time to decide if I want to keep the premium features. I’ll let you know in the next couple of days.")
        
        int2_3 = Intervention(case_id=case2.id, channel="whatsapp", message_sent="Sure, take your time—just let us know whether you’d like to keep the premium features so we can finalize the payment. If you decide to continue, you can pay here: https://rzp.io/i/7bd8d183.")
        
        session.add_all([int2_1, rep2_1, int2_2, rep2_2, int2_3])
        
        ae2_1 = AuditEvent(case_id=case2.id, event_type="webhook_received", payload={"reason": "payment failed"})
        ae2_2 = AuditEvent(case_id=case2.id, event_type="diagnosis_completed", payload={"diagnosis": "insufficient funds"})
        ae2_3 = AuditEvent(case_id=case2.id, event_type="persona_simulation_started", payload={"persona": "considering_cancellation", "internal_reasoning": "Persona is on the fence; wants to know value before deciding and needs time to gather funds."})
        ae2_4 = AuditEvent(case_id=case2.id, event_type="state_transition", payload={"from_state": "open", "to_state": "in_progress", "reason": "agent engaged"})
        ae2_5 = AuditEvent(case_id=case2.id, event_type="agent_intervention", payload={"message": "Hi, this is a message from Razorpay. Your payment of INR 999.00 for your subscription (919000005902) failed because your card had insufficient funds. Please pay here to continue using the service."})
        ae2_6 = AuditEvent(case_id=case2.id, event_type="customer_reply", payload={"message": "Thanks for the notice. I'm not sure I really need the service right now. What would I lose if I cancel? Also, could I try again in a couple of days once I have enough funds?", "classified_state": "needs_payment_help"})
        ae2_7 = AuditEvent(case_id=case2.id, event_type="agent_intervention", payload={"message": "If you cancel, you'll lose access to premium features and support. You can re‑subscribe anytime; when ready, pay here: https://rzp.io/i/7bd8d183"})
        ae2_8 = AuditEvent(case_id=case2.id, event_type="customer_reply", payload={"message": "Thanks for the info. I need a bit more time to decide if I want to keep the premium features. I’ll let you know in the next couple of days.", "classified_state": "promise_made"})
        ae2_9 = AuditEvent(case_id=case2.id, event_type="state_transition", payload={"from_state": "in_progress", "to_state": "promise_pending", "reason": "customer_reply:promise_made"})
        ae2_10 = AuditEvent(case_id=case2.id, event_type="agent_intervention", payload={"message": "Sure, take your time—just let us know whether you’d like to keep the premium features so we can finalize the payment. If you decide to continue, you can pay here: https://rzp.io/i/7bd8d183."})
        session.add_all([ae2_1, ae2_2, ae2_3, ae2_4, ae2_5, ae2_6, ae2_7, ae2_8, ae2_9, ae2_10])
        
        await session.commit()
        print("Cases inserted successfully")

if __name__ == "__main__":
    asyncio.run(main())
