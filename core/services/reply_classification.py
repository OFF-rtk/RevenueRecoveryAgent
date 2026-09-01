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


async def classify_reply(raw_text: str) -> dict[str, Any]:
    """
    Classify a customer's free-text reply using gpt-oss-20b.
    Returns a dict with: state, confidence, follow_up_hours, reasoning.
    """
    prompt_version = "reply_classification_v1"
    model = settings.groq_tier1_model  # Always use the cheap tier for reply interpretation
    
    context = f"Customer Reply: {raw_text}"
    
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
            if "state" not in parsed or "confidence" not in parsed:
                raise ValueError("Missing 'state' or 'confidence' in JSON output")
                
            log.info(
                "reply_classified",
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
                    "_meta": {}
                }
    
    return {
        "state": "unresolved",
        "confidence": 0.0,
        "follow_up_hours": None,
        "reasoning": "Unexpected classification failure",
        "_meta": {}
    }
