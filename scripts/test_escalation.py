import asyncio
import json
from core.llm.client import call_llm
from core.config import settings

async def main():
    with open('fixtures/revenue_recovery_fixtures_v2.json') as f:
        data = json.load(f)
    cases = data.get("cases", data)

    escalation_cases = [c for c in cases if c.get("expect_escalation") is True]
    print(f"Found {len(escalation_cases)} cases expecting escalation")

    for i, c in enumerate(escalation_cases):
        context_str = f"Error: {c['razorpay_error_code']}"
        if c.get("additional_context"):
            context_str += f"\nContext: {c['additional_context']}"
        
        print(f"\n--- Case {i+1} ---")
        print(f"Prompt context:\n{context_str}")

        resp = await call_llm(
            prompt_version="diagnosis_v1",
            model="openai/gpt-oss-20b",
            user_messages=[{"role": "user", "content": context_str}],
            top_p=0.9,
            temperature=0.0,
            max_tokens=1000,
        )
        print("Raw response:")
        print(resp.content)
        try:
            parsed = json.loads(resp.content)
            conf = parsed.get("confidence", 1.0)
            print(f"Parsed Confidence: {conf}")
            print(f"Reasoning: {parsed.get('reasoning')}")
            if conf < 0.75:
                print("Result: ESCALATED")
            else:
                print("Result: NOT ESCALATED (FAIL)")
        except Exception as e:
            print(f"Parse error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
