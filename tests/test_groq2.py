import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from groq import AsyncGroq

async def test():
    client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"), base_url=os.environ.get("GROQ_BASE_URL"))
    system_prompt = open("prompts/diagnosis_v1.txt").read()
    
    # Simulating case 8
    response = await client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Input:\nError: \"cash_flow_issue\"\nContext: \"\""}
        ],
        max_tokens=1024,
        temperature=0
    )
    print("Content:", repr(response.choices[0].message.content))
    print("Finish Reason:", response.choices[0].finish_reason)
    if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'reasoning'):
        print("Reasoning:", repr(getattr(response.choices[0].message, 'reasoning', None)))

asyncio.run(test())
