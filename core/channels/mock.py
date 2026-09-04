"""
core/channels/mock.py
────────────────────
Mock channel for local development. Logs output without sending real messages.
"""
import structlog
from .base import BaseChannel

log = structlog.get_logger(__name__)

TEMPLATES = {
    "payment_recovery_notice_v1": "Hi, \n\nwe noticed an issue processing your recent payment of {0} {1} for customer ref {2}. \n\nThe payment failed due to: \n{3}.\n\nPlease tap the link below to update your payment details and avoid any service interruption.",
    
    "payment_reminder_followup_v1": "Hi, \nwe haven't heard back from you regarding your pending payment of {0} {1} for customer ref {2}.\n\nThe issue: {3}\n\nReply to the message if you need any assistance.",
    
    "payment_confirmed_v1": "Hello, \nwe have successfully received your payment of {0} {1} for customer ref {2}.\n \nYour account is now in good standing. \nThank you!",
    
    "invoice_reminder_notice_v1": "Hi, \nthis is a reminder regarding your overdue invoice of {0} {1} for customer ref {2}. \n\nThe payment failed due to: \n{3}.\n\nPlease update your payment details or reply to this message if you need assistance."
}

class MockChannel(BaseChannel):
    name = "mock"

    async def send(self, to: str, message: str) -> dict:
        import sys
        print(f"\n💬 [Agent -> {to}] (Free-form)\n{message}\n", file=sys.stderr)
        log.info("mock_channel_send", to=to, message=message)
        return {"status": "success", "channel": "mock", "provider_id": "mock_123"}

    async def send_template(self, to: str, template_name: str, parameters: list[str], button_parameters: list[str] = None) -> dict:
        template = TEMPLATES.get(template_name, "[Unknown Template]")
        formatted_message = template.format(*parameters)
        import sys
        print(f"\n📝 [Agent -> {to}] (Template: {template_name})\n{formatted_message}\n", file=sys.stderr)
        log.info("mock_channel_send_template", to=to, template_name=template_name, parameters=parameters, button_parameters=button_parameters)
        import uuid
        return {"status": "success", "channel": self.name, "provider_id": str(uuid.uuid4())}
