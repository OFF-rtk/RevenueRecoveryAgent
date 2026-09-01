import sys
import os
sys.path.insert(0, os.path.abspath("."))
import asyncio
import json
from sqlalchemy import select
from core.config import settings
from core.db import init_db, async_session_factory
from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.services.diagnosis import normalise_cause

async def main():
    await init_db(settings.database_url)
    factory = async_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Diagnosis, Case).join(Case, Case.id == Diagnosis.case_id)
        )
        for diag, case in result.all():
            ground_truth = (case.raw_payload or {}).get("ground_truth_cause", "unknown")
            expected = normalise_cause(ground_truth)
            if expected not in diag.causes:
                print(f"Type: {case.case_type} | Ground Truth: {ground_truth} (Expected: {expected})")
                print(f"Diagnosed: {diag.causes} | Tier: {diag.model_tier} | Conf: {diag.confidence}")
                try:
                    resp = json.loads(diag.raw_llm_response)
                    print(f"Reasoning: {resp.get('reasoning')}")
                except:
                    pass
                print("-" * 80)

if __name__ == "__main__":
    asyncio.run(main())
