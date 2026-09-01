import asyncio
from core.config import settings
from core.db import init_db, async_session_factory
from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from sqlalchemy import select

async def find_failures():
    await init_db(settings.database_url)
    factory = async_session_factory()

    async with factory() as session:
        # Get all cases and their latest diagnosis
        cases = (await session.scalars(
            select(Case).where(Case.razorpay_event_id.is_(None))
        )).all()

        for case in cases:
            diagnosis = await session.scalar(
                select(Diagnosis)
                .where(Diagnosis.case_id == case.id)
                .order_by(Diagnosis.created_at.desc())
                .limit(1)
            )
            
            if not diagnosis:
                continue

            ground_truth = (case.raw_payload or {}).get("ground_truth_cause", "unknown")
            
            # Use the normalise logic used by run_batch if we need it, but let's just see raw vs diagnosed
            # Actually, we know that ground truth causes from fixtures are specific (e.g. price_increase_related_churn_risk)
            # The normalise_cause function maps it to the canonical one.
            from core.services.diagnosis import normalise_cause
            norm_gt = normalise_cause(ground_truth)
            
            if diagnosis.cause != norm_gt:
                print(f"CASE {case.id}")
                print(f"Raw Error: {case.raw_failure_reason}")
                print(f"Context: {(case.raw_payload or {}).get('additional_context')}")
                print(f"Ground Truth (Raw): {ground_truth}")
                print(f"Ground Truth (Norm): {norm_gt}")
                print(f"Diagnosed Cause: {diagnosis.cause}")
                print(f"Tier: {diagnosis.model_tier}, Confidence: {diagnosis.confidence}")
                print(f"LLM Reasoning: {diagnosis.raw_llm_response}")
                print("-" * 80)

if __name__ == "__main__":
    asyncio.run(find_failures())
