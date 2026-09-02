import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.models.cases import Case
from core.models.replies import Reply
from core.models.interventions import Intervention
from core.config import settings

async def run():
    engine = create_async_engine("postgresql+asyncpg://revenue_recovery_db_jqur_user:D3s1iccskubcIe3txXWtvopU8fHukcqj@dpg-dab99b142hec73a9l4sg-a.singapore-postgres.render.com/revenue_recovery_db_jqur")
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Get all 28 cases from the recent batch run
        result = await session.execute(
            select(Case).order_by(Case.created_at.desc()).limit(28)
        )
        cases = result.scalars().all()
        
        for case in cases:
            # Get interventions
            int_res = await session.execute(
                select(Intervention).where(Intervention.case_id == case.id).order_by(Intervention.sent_at.asc())
            )
            interventions = int_res.scalars().all()
            
            # Get replies
            rep_res = await session.execute(
                select(Reply).where(Reply.case_id == case.id).order_by(Reply.received_at.asc())
            )
            replies = rep_res.scalars().all()
            
            # Combine and sort by time
            events = []
            for i in interventions:
                events.append({"type": "Agent", "time": i.sent_at, "text": i.message_sent})
            for r in replies:
                events.append({"type": "Customer", "time": r.received_at, "text": r.raw_reply})
            
            events.sort(key=lambda x: x["time"])
            
            # Print if there is any customer reply
            if len(replies) > 0:
                print(f"\n--- Case {case.customer_ref} (Status: {case.status}) ---")
                for e in events:
                    print(f"{e['type']}: {e['text']}")

asyncio.run(run())
