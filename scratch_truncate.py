import asyncio
import os
from sqlalchemy import text
from core.db import init_db, async_session_factory

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://revenue_recovery_db_jqur_user:D3s1iccskubcIe3txXWtvopU8fHukcqj@dpg-dab99b142hec73a9l4sg-a.singapore-postgres.render.com/revenue_recovery_db_jqur")

async def main():
    await init_db(DATABASE_URL)
    session_factory = async_session_factory()
    async with session_factory() as session:
        # Cascade truncate cases, which should wipe all related data (messages, audit_events, etc.)
        await session.execute(text("TRUNCATE TABLE cases CASCADE;"))
        await session.commit()
        print("Successfully truncated cases table and all related data.")
            
if __name__ == "__main__":
    asyncio.run(main())
