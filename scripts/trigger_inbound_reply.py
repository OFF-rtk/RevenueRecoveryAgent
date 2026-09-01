import httpx
import asyncio
import json
import uuid
import time
import argparse

async def trigger_inbound_reply(reply_text: str, phone: str = "919119022966"):
    url = "https://revenuerecoveryagent.onrender.com/webhooks/whatsapp"
    
    # Meta WhatsApp Cloud API exact payload structure for inbound texts
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1234567890", # Dummy WABA ID
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "1234567890"
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "Test User"
                                    },
                                    "wa_id": phone
                                }
                            ],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": f"wamid.{uuid.uuid4().hex}",
                                    "timestamp": str(int(time.time())),
                                    "text": {
                                        "body": reply_text
                                    },
                                    "type": "text"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }

    print(f"📡 Simulating inbound WhatsApp reply to {url}")
    print(f"📱 From: {phone}")
    print(f"💬 Message: '{reply_text}'")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"\nStatus Code: {response.status_code}")
        try:
            print(f"Response Body: {response.json()}")
        except:
            print(f"Response Body: {response.text}")
            
        if response.status_code == 200:
            print("✅ Simulated reply accepted! Check your phone for the AI's follow-up.")
        else:
            print("❌ Failed to trigger reply.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate an inbound WhatsApp reply from a customer.")
    parser.add_argument("--text", type=str, required=True, help="The text message the customer is replying with.")
    parser.add_argument("--phone", type=str, default="919119022966", help="The customer's phone number (default: 919119022966).")
    
    args = parser.parse_args()
    asyncio.run(trigger_inbound_reply(args.text, args.phone))
