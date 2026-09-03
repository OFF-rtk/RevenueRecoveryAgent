import asyncio
import os
from sqlalchemy import select, delete, func
from core.db import init_db, async_session_factory
from core.models.cases import Case

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://revenue_recovery_db_jqur_user:D3s1iccskubcIe3txXWtvopU8fHukcqj@dpg-dab99b142hec73a9l4sg-a.singapore-postgres.render.com/revenue_recovery_db_jqur")

async def main():
    await init_db(DATABASE_URL)
    session_factory = async_session_factory()
    async with session_factory() as session:
        # Check what kinds of cases we have
        total = await session.scalar(select(func.count(Case.id)))
        print("Total cases:", total)
        
        # Are there cases with specific raw_payload structure that indicates they are static?
        result = await session.execute(select(Case.id, Case.raw_payload).limit(10))
        for row in result:
            print(f"ID: {row[0]}, Payload: {row[1]}")
            
if __name__ == "__main__":
    asyncio.run(main())
