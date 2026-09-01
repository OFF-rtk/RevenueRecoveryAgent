import asyncio
import sys
from decimal import Decimal
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from core.models.cases import Case
from core.models.base import Base
from core.services.diagnosis import diagnose_case
from core.services.intervention import draft_and_send_intervention
from core.services.state_machine import process_inbound_reply
from core.channels.mock import MockChannel
import structlog
from core.config import settings
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

async def main():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    print("=== Razorpay Recovery Agent - Automated Test ===")
    print("Simulating a 'wrong_details' / expired card failure...")
    
    async with factory() as session:
        case = Case(
            case_type="failed_subscription",
            customer_ref="CUST-8899",
            amount=Decimal("999.00"),
            currency="INR",
            raw_failure_reason="BAD_REQUEST_PAYMENT_CARD_EXPIRED",
            tenure=1,
            raw_payload={"additional_context": "Card ends in 4432, expired last month."}
        )
        session.add(case)
        await session.commit()
        
        print("\n[System] Diagnosing case...")
        diag = await diagnose_case(case.id, session)
        print(f"[System] Diagnosed Cause: {diag.causes[0] if diag.causes else 'unknown'}")
        
        print("\n[System] Sending first intervention...")
        channel = MockChannel()
        await draft_and_send_intervention(case.id, session, channel)
        
        await session.refresh(case)
        print(f"\n[System] Current Case Status: {case.status}")
        
        reply = "I get paid on Friday, can I pay then?"
        print(f"\n👤 Customer Reply: {reply}")
            
        print("\n[System] Processing reply...")
        await process_inbound_reply(case.customer_ref, reply, session, channel)
        
        await session.refresh(case)
        print(f"\n[System] Final Case Status: {case.status}")

if __name__ == "__main__":
    asyncio.run(main())
