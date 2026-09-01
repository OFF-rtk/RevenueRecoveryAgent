import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from core.models.cases import Case
from core.models.state_transitions import StateTransition
from core.models.replies import Reply

# Replace this with your Render External Database URL if you want to run this locally!
DB_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://recovery:recovery@localhost:5434/recovery_agent")

async def check_case(case_id_str: str):
    engine = create_async_engine(DB_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. Fetch Case
        case = await session.get(Case, case_id_str)
        if not case:
            print(f"❌ Case {case_id_str} not found!")
            return
            
        print(f"✅ Case found: {case.id}")
        print(f"Current Status: {case.status}")
        print(f"Amount: {case.currency} {case.amount}")
        print("-" * 40)
        
        # 2. Fetch Replies
        result = await session.execute(select(Reply).where(Reply.case_id == case.id))
        replies = result.scalars().all()
        print(f"📩 Replies ({len(replies)}):")
        for r in replies:
            print(f" - '{r.raw_reply}' => Classified as: {r.classified_state}")
        print("-" * 40)
        
        # 3. Fetch State Transitions
        result = await session.execute(select(StateTransition).where(StateTransition.case_id == case.id))
        transitions = result.scalars().all()
        print(f"🔄 State Transitions ({len(transitions)}):")
        for t in transitions:
            print(f" - {t.from_state} -> {t.to_state} (Reason: {t.reason})")

async def list_cases():
    engine = create_async_engine(DB_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        result = await session.execute(
            select(Case).order_by(Case.created_at.desc()).limit(10)
        )
        cases = result.scalars().all()
        print("Recent Cases:")
        for c in cases:
            print(f" - {c.id} | Status: {c.status} | Amount: {c.amount}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_case.py <case_id> OR python scripts/check_case.py --list")
        sys.exit(1)
        
    if sys.argv[1] == "--list":
        asyncio.run(list_cases())
    else:
        asyncio.run(check_case(sys.argv[1]))
