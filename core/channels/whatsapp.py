"""
core/channels/whatsapp.py
────────────────────────
Real WhatsApp Cloud API integration.
"""
import httpx
import structlog
from .base import BaseChannel

log = structlog.get_logger(__name__)


class WhatsAppChannel(BaseChannel):
    """
    Sends messages via the Meta Graph API /messages endpoint.
    """
    def __init__(self, api_token: str, phone_number_id: str):
        self.api_token = api_token
        self.phone_number_id = phone_number_id
        # Hardcoding API version v20.0 for stability
        self.base_url = f"https://graph.facebook.com/v20.0/{self.phone_number_id}/messages"

    async def send(self, to: str, message: str) -> dict:
        log.info("whatsapp_channel_send_attempt", to=to)
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=10.0
            )
            
            try:
                response.raise_for_status()
                response_data = response.json()
                
                # Meta returns messages array with IDs if successful
                message_id = response_data.get("messages", [{}])[0].get("id", "unknown_id")
                
                log.info("whatsapp_channel_send_success", to=to, message_id=message_id)
                return {
                    "status": "success", 
                    "channel": "whatsapp", 
                    "provider_id": message_id,
                    "raw_response": response_data
                }
            except httpx.HTTPStatusError as e:
                log.error(
                    "whatsapp_channel_send_failed", 
                    to=to, 
                    status_code=e.response.status_code,
                    response_body=e.response.text
                )
                return {
                    "status": "failed",
                    "channel": "whatsapp",
                    "error": str(e),
                    "response_body": e.response.text
                }
            except Exception as e:
                log.exception("whatsapp_channel_send_exception", to=to, error=str(e))
                return {
                    "status": "error",
                    "channel": "whatsapp",
                    "error": str(e)
                }

    async def send_template(self, to: str, template_name: str, parameters: list[str], button_parameters: list[str] = None) -> dict:
        log.info("whatsapp_channel_send_template_attempt", to=to, template_name=template_name)
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        components = []
        if parameters:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(p)} for p in parameters
                ]
            })
            
        if button_parameters:
            for i, p in enumerate(button_parameters):
                components.append({
                    "type": "button",
                    "sub_type": "url",
                    "index": str(i),
                    "parameters": [
                        {"type": "text", "text": str(p)}
                    ]
                })

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": "en"
                },
                "components": components
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=10.0
            )
            
            try:
                response.raise_for_status()
                response_data = response.json()
                
                # Meta returns messages array with IDs if successful
                message_id = response_data.get("messages", [{}])[0].get("id", "unknown_id")
                
                log.info("whatsapp_channel_send_template_success", to=to, message_id=message_id, template_name=template_name)
                return {
                    "status": "success", 
                    "channel": "whatsapp", 
                    "provider_id": message_id,
                    "raw_response": response_data
                }
            except httpx.HTTPStatusError as e:
                log.error(
                    "whatsapp_channel_send_template_failed", 
                    to=to, 
                    template_name=template_name,
                    status_code=e.response.status_code,
                    response_body=e.response.text
                )
                return {
                    "status": "failed",
                    "channel": "whatsapp",
                    "error": str(e),
                    "response_body": e.response.text
                }
            except Exception as e:
                log.exception("whatsapp_channel_send_template_exception", to=to, template_name=template_name, error=str(e))
                return {
                    "status": "error",
                    "channel": "whatsapp",
                    "error": str(e)
                }
