import hmac
import hashlib
import json
import requests
import time
import os

# --- Configuration ---
# Replace with your actual Render app URL
BASE_URL = "https://revenuerecoveryagent.onrender.com"
WEBHOOK_URL = f"{BASE_URL}/webhooks/razorpay"

# Must match the RAZORPAY_WEBHOOK_SECRET in your Render environment variables!
WEBHOOK_SECRET = "test_webhook_secret_phase1"

# IMPORTANT: Put your REAL mobile number here (with country code, no + or spaces)
# Example: "919876543210"
YOUR_PHONE_NUMBER = "919119022966"

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    """Generate Razorpay HMAC-SHA256 signature."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

def fire_webhook():
    print(f"Targeting: {WEBHOOK_URL}")
    print(f"Customer Ref (Phone): {YOUR_PHONE_NUMBER}")
    
    # We use a clean, unambiguous case: standard insufficient funds
    # This will easily resolve to Tier 1 diagnosis and send a payment_recovery_notice_v1
    payload_dict = {
        "entity": "event",
        "account_id": "acc_1234567890",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{int(time.time())}",
                    "amount": 99900,
                    "currency": "INR",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment failed due to insufficient funds in the account.",
                    "error_source": "bank",
                    "error_reason": "insufficient_funds",
                    "contact": YOUR_PHONE_NUMBER,
                    "notes": {
                        "customer_ref": YOUR_PHONE_NUMBER
                    }
                }
            }
        },
        "created_at": int(time.time())
    }

    # Convert to bytes exactly as it will be sent over the wire
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    
    # Sign it
    signature = generate_signature(payload_bytes, WEBHOOK_SECRET)
    
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature
    }
    
    print("Firing webhook...")
    try:
        response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook accepted successfully!")
        else:
            print("❌ Webhook failed. Check Render logs.")
    except Exception as e:
        print(f"❌ Connection error: {e}")

if __name__ == "__main__":
    if YOUR_PHONE_NUMBER == "REPLACE_ME_WITH_REAL_NUMBER":
        print("ERROR: Please edit the script and set YOUR_PHONE_NUMBER to your real mobile number!")
    else:
        fire_webhook()
