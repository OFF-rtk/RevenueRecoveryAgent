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

# Suppress debug logs for cleaner interactive output
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

from core.config import settings

async def main():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    print("=== Razorpay Recovery Agent - Interactive Test ===")
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
        
        while True:
            await session.refresh(case)
            print(f"\n[System] Current Case Status: {case.status}")
            if case.status in ["recovered", "stopped", "escalated"]:
                print("[System] Terminal state reached. Agent will no longer respond.")
                break
                
            reply = input("\n👤 You (Customer Reply, or 'q' to quit): ").strip()
            if reply.lower() == 'q' or not reply:
                break
                
            print("\n[System] Processing your reply...")
            await process_inbound_reply(case.customer_ref, reply, session, channel)

if __name__ == "__main__":
    asyncio.run(main())
