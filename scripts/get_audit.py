import asyncio
import json
from sqlalchemy import select
from core.db import init_db, async_session_factory
from core.config import settings
from core.models.cases import Case
from core.models.audit_events import AuditEvent

async def main():
    await init_db(settings.database_url)
    factory = async_session_factory()
    
    with open('fixtures/revenue_recovery_fixtures_v2.json') as f:
        data = json.load(f)
    cases = data.get("cases", data)
    
    no_reply_cases = [c for c in cases if c.get("outcome_path") == "resolved_no_reply"]
    customer_refs = [c["customer_ref"] for c in no_reply_cases[:5]]
    
    async with factory() as session:
        for ref in customer_refs:
            print(f"\n{'='*50}\nAudit Trail for customer_ref: {ref}\n{'='*50}")
            # Find the case
            result = await session.execute(select(Case).where(Case.customer_ref == ref))
            case = result.scalar_one_or_none()
            if not case:
                print("Case not found!")
                continue
                
            print(f"Case ID: {case.id}")
            result = await session.execute(
                select(AuditEvent)
                .where(AuditEvent.case_id == case.id)
                .order_by(AuditEvent.created_at)
            )
            events = result.scalars().all()
            for e in events:
                print(f"[{e.created_at.strftime('%H:%M:%S')}] {e.event_type}: {e.payload}")

if __name__ == "__main__":
    asyncio.run(main())
