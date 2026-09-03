import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

async def main():
    engine = create_async_engine(os.getenv("DATABASE_URL", "postgresql+asyncpg://revenue_recovery_db_jqur_user:D3s1iccskubcIe3txXWtvopU8fHukcqj@dpg-dab99b142hec73a9l4sg-a.singapore-postgres.render.com/revenue_recovery_db_jqur"))
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        await session.execute(text("TRUNCATE TABLE cases CASCADE;"))
        await session.commit()
        print("Database truncated successfully.")

if __name__ == "__main__":
    asyncio.run(main())
