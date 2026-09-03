import asyncio
import os
import json
from sqlalchemy import select, func
from core.db import init_db, async_session_factory
from core.models.cases import Case
from core.models.outcomes import Outcome
from core.models.interventions import Intervention
from core.models.audit_events import AuditEvent

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://revenue_recovery_db_jqur_user:D3s1iccskubcIe3txXWtvopU8fHukcqj@dpg-dab99b142hec73a9l4sg-a.singapore-postgres.render.com/revenue_recovery_db_jqur")

async def main():
    await init_db(DATABASE_URL)
    session_factory = async_session_factory()
    
    report = []
    
    async with session_factory() as session:
        # Get the latest 6 cases
        result = await session.execute(
            select(Case).order_by(Case.created_at.desc()).limit(6)
        )
        cases = result.scalars().all()
        
        for case in cases:
            case_data = {
                "id": str(case.id),
                "customer_ref": case.customer_ref,
                "status": case.status
            }
            
            # Outcome
            outcome_res = await session.execute(select(Outcome).where(Outcome.case_id == case.id))
            outcome = outcome_res.scalar_one_or_none()
            if outcome:
                case_data["outcome"] = outcome.final_state
                case_data["amount_recovered"] = float(outcome.amount_recovered)
            else:
                case_data["outcome"] = None
                
            # Interventions
            interv_res = await session.execute(select(Intervention).where(Intervention.case_id == case.id).order_by(Intervention.attempt_number))
            intervs = interv_res.scalars().all()
            case_data["interventions"] = []
            for inv in intervs:
                case_data["interventions"].append({
                    "id": str(inv.id),
                    "message_sent": inv.message_sent,
                    "attempt": inv.attempt_number
                })
                
            # Audit events
            audit_res = await session.execute(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at))
            audits = audit_res.scalars().all()
            case_data["audit_events"] = []
            for a in audits:
                case_data["audit_events"].append({
                    "event_type": a.event_type,
                    "payload": a.payload
                })
                
            report.append(case_data)
            
    with open("reports/db_dump.json", "w") as f:
        json.dump(report, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
