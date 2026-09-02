"""
core/services/reply_classification.py
───────────────────────────────
LLM-driven classification of inbound customer replies.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from core.config import settings
from core.llm.client import call_llm

log = structlog.get_logger(__name__)


async def analyze_reply(case: Any, raw_text: str, session: Any) -> dict[str, Any]:
    """
    Classify a customer's free-text reply and draft a response using gpt-oss-20b.
    Returns a dict with: state, confidence, follow_up_hours, reasoning, and message.
    """
    from sqlalchemy import select, func
    from core.models.replies import Reply

    # Count previous customer replies
    reply_count_query = await session.execute(
        select(func.count(Reply.id)).where(Reply.case_id == case.id)
    )
    reply_count = reply_count_query.scalar() or 0
    
    if reply_count >= 2:
        model = settings.groq_tier2_model
    else:
        model = settings.groq_tier1_model
        
    prompt_version = "analyze_and_respond_v1"
    
    payment_entity = case.raw_payload.get("payload", {}).get("payment", {}).get("entity", {}) if case.raw_payload else {}
    product_description = payment_entity.get("description", "your outstanding balance")
    failure_reason = payment_entity.get("error_description", "your payment failed")
    payment_method = payment_entity.get("method", "card")

    context = json.dumps({
        "case_type": case.case_type,
        "amount": str(case.amount),
        "currency": case.currency,
        "customer_reply": raw_text,
        "payment_link": f"https://rzp.io/i/{case.id.hex[:8]}",
        "product_description": product_description,
        "failure_reason": failure_reason,
        "payment_method": payment_method
    }, indent=2)
    
    for attempt in range(2):
        try:
            llm_result = await call_llm(
                prompt_version=prompt_version,
                model=model,
                user_messages=[{"role": "user", "content": context}],
                response_format={"type": "json_object"},
            )
            parsed = json.loads(llm_result.content)
            
            # Validate required fields
            if "state" not in parsed or "confidence" not in parsed or "message" not in parsed:
                raise ValueError("Missing 'state', 'confidence', or 'message' in JSON output")
                
            log.info(
                "reply_analyzed",
                state=parsed["state"],
                confidence=parsed["confidence"],
                follow_up_hours=parsed.get("follow_up_hours"),
            )
            
            # include LLM metadata to pass up
            parsed["_meta"] = {
                "prompt_version": llm_result.prompt_version,
                "prompt_hash": llm_result.prompt_hash,
            }
            return parsed

        except (json.JSONDecodeError, ValueError) as exc:
            log.warning(
                "reply_classification_json_error",
                attempt=attempt + 1,
                error=str(exc)
            )
            if attempt == 1:
                # Fallback on unresolved
                return {
                    "state": "unresolved",
                    "confidence": 0.0,
                    "follow_up_hours": None,
                    "reasoning": f"Failed to parse LLM response: {exc}",
                    "message": "Thank you for your response. We will update your case.",
                    "_meta": {}
                }
    
    return {
        "state": "unresolved",
        "confidence": 0.0,
        "follow_up_hours": None,
        "reasoning": "Unexpected classification failure",
        "message": "Thank you for your response. We will update your case.",
        "_meta": {}
    }
