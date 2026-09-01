import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from groq import AsyncGroq

async def test():
    client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"), base_url=os.environ.get("GROQ_BASE_URL"))
    system_prompt = open("prompts/diagnosis_v1.txt").read()
    response = await client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Input:\nError: \"wrong_bank_details\"\nContext: \"None\""}
        ],
        max_tokens=256
    )
    print("Usage:", response.usage)
asyncio.run(test())
