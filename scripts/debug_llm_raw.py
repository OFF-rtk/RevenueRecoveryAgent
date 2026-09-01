import asyncio
import json
import uuid
import structlog
import sys

from core.config import settings
from core.llm.client import call_llm

async def main():
    with open("fixtures/mini_fixtures.json") as f:
        data = json.load(f)
    case_data = data["cases"][2] 
    
    raw_payload_safe = {
        "synthetic": True,
        "batch_seed": 42,
        "batch_index": 2,
        "expect_escalation": case_data.get("expect_escalation", False),
        "additional_context": case_data.get("additional_context", "")
    }

    case_context = json.dumps({
        "case_type": case_data.get("type", case_data.get("case_type")),
        "amount": str(case_data["amount"]),
        "currency": case_data["currency"],
        "raw_failure_reason": case_data.get("razorpay_error_code", case_data.get("raw_failure_reason")),
        "raw_payload": raw_payload_safe,
    }, indent=2)

    llm_result = await call_llm(
        prompt_version="diagnosis_v1",
        model=settings.groq_tier1_model, # gpt-oss-20b
        user_messages=[{"role": "user", "content": case_context}]
    )
    print("--- RAW LLM OUTPUT ---")
    print(repr(llm_result.content))
    print("----------------------")

if __name__ == "__main__":
    asyncio.run(main())
