import asyncio
import sys
import structlog
from typing import TypedDict
from core.services.reply_classification import classify_reply

# Suppress debug logs
import logging
logging.getLogger("httpx").setLevel(logging.WARNING)

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))

class Sample(TypedDict):
    text: str
    expected: str

SAMPLES: list[Sample] = [
    # 1. promise_made
    {"text": "I get paid on Friday, can I pay then?", "expected": "promise_made"},
    {"text": "ok will do it tonite", "expected": "promise_made"},
    {"text": "give me a few days pls", "expected": "promise_made"},
    {"text": "k", "expected": "promise_made"}, # Assumes "k" means they are acknowledging the reminder and will do it
    {"text": "ill try but im broke rn", "expected": "promise_made"},
    
    # 2. needs_new_payment_method
    {"text": "my card was stolen", "expected": "needs_new_payment_method"},
    {"text": "how do I update my bank info?", "expected": "needs_new_payment_method"},
    {"text": "it keeps declining my amex", "expected": "needs_new_payment_method"},
    
    # 3. disputed
    {"text": "I already cancelled my subscription wtf", "expected": "disputed"},
    {"text": "I never bought this!!", "expected": "disputed"},
    {"text": "why am I being charged again? I paid last month", "expected": "disputed"},
    
    # 4. opt_out
    {"text": "STOP", "expected": "opt_out"},
    {"text": "unsubscribe me from this bs", "expected": "opt_out"},
    {"text": "dont text this number anymore", "expected": "opt_out"},
    
    # 5. unresolved (ambiguous/questions)
    {"text": "what is this for?", "expected": "unresolved"},
    {"text": "can I speak to a human", "expected": "unresolved"},
    {"text": "?", "expected": "unresolved"}
]

async def main():
    print("=== Reply Classification Accuracy Test ===")
    print(f"Testing {len(SAMPLES)} hand-labeled samples...\n")
    
    correct = 0
    
    for i, sample in enumerate(SAMPLES):
        text = sample["text"]
        expected = sample["expected"]
        
        try:
            result = await classify_reply(text)
            actual = result["state"]
            
            if actual == expected:
                correct += 1
                status = "✅"
            else:
                # Let's consider 'k' as unresolved if the LLM thinks it's too ambiguous
                if text == "k" and actual == "unresolved":
                    correct += 1
                    status = "✅ (Acceptable Fallback)"
                else:
                    status = f"❌ (Expected: {expected}, Got: {actual})"
            
            print(f"[{i+1:02d}] {status} | Text: '{text}'")
            if "❌" in status:
                print(f"     Reasoning: {result.get('reasoning')}")
        except Exception as e:
            print(f"[{i+1:02d}] ❌ Error: {e} | Text: '{text}'")
            
    accuracy = (correct / len(SAMPLES)) * 100
    print(f"\n=== Final Accuracy: {accuracy:.1f}% ({correct}/{len(SAMPLES)}) ===")
    if accuracy < 90.0:
        print("[WARNING] Accuracy is below 90%. We may need to refine the prompt.")
    else:
        print("[SUCCESS] Classification engine is robust and ready for production.")

if __name__ == "__main__":
    asyncio.run(main())
