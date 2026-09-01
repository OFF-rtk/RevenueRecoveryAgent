"""
Test script for WhatsApp integration.
Run this directly from the root of the project to test the send path.
Usage:
  python scripts/test_whatsapp_send.py +919999999999
"""
import sys
import asyncio
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

from core.config import settings
from core.channels.whatsapp import WhatsAppChannel

async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_whatsapp_send.py <phone_number>")
        print("Example: python scripts/test_whatsapp_send.py 919876543210")
        sys.exit(1)
        
    phone_number = sys.argv[1]
    
    # Strip any common non-numeric characters for safety (e.g. +)
    phone_number = "".join(filter(str.isdigit, phone_number))
    
    if not settings.whatsapp_token or not settings.phone_number_id:
        print("Error: WHATSAPP_TOKEN and PHONE_NUMBER_ID must be set in .env")
        sys.exit(1)
        
    channel = WhatsAppChannel(
        api_token=settings.whatsapp_token,
        phone_number_id=settings.phone_number_id
    )
    
    template_name = "payment_recovery_notice_v1"
    parameters = ["INR", "999.00", "cust_12345", "insufficient_funds"]
    
    print(f"Sending test template '{template_name}' to {phone_number}...")
    
    response = await channel.send_template(
        to=phone_number, 
        template_name=template_name,
        parameters=parameters
    )
    
    print("\n--- Response ---")
    print(f"Status: {response.get('status')}")
    if response.get("status") == "success":
        print(f"Message ID: {response.get('provider_id')}")
        print("Raw Data:", response.get('raw_response'))
    else:
        print(f"Error: {response.get('error')}")
        if "response_body" in response:
            print("Raw Error Body:", response.get("response_body"))

if __name__ == "__main__":
    asyncio.run(main())
