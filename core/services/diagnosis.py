"""
core/services/diagnosis.py
─────────────────────────
Implements the LLM-driven diagnosis layer (Phase 3).
Analyzes cases using tiered LLM routing (Tier 1 -> Tier 2 on low confidence)
and saves the result to the diagnoses table.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.llm.client import call_llm
from core.models.cases import Case
from core.models.diagnoses import Diagnosis

log = structlog.get_logger(__name__)

# Canonical cause labels — must match seed_synthetic.py ground_truth_cause values exactly.
CANONICAL_CAUSES = {
    "insufficient_funds",
    "expired_card",
    "wrong_details",
    "bank_declined",
    "mandate_revoked",
    "technical_error",
    "payment_forgotten",
    "dispute_raised",
    "wrong_invoice_details",
    "cash_flow_issue",
    "unknown",
}

# Normalisation map — catches label drift from prompt non-compliance.
_CAUSE_NORMALISE: dict[str, str] = {
    # bank variants
    "bank_decline": "bank_declined",
    "bank_reject": "bank_declined",
    "bank_rejection": "bank_declined",
    # technical variants
    "system_error": "technical_error",
    "gateway_error": "technical_error",
    "processing_error": "technical_error",
    "technical_failure": "technical_error",
    # dispute / fraud variants
    "fraud_suspected": "dispute_raised",
    "fraud": "dispute_raised",
    "chargeback": "dispute_raised",
    # mandate variants
    "customer_canceled": "mandate_revoked",
    "customer_cancelled": "mandate_revoked",
    "mandate_cancelled": "mandate_revoked",
    "subscription_cancelled": "mandate_revoked",
    # invoice variants
    "wrong_invoice": "wrong_invoice_details",
    "incorrect_invoice": "wrong_invoice_details",
    # payment forgotten variants
    "overdue": "payment_forgotten",
    "unpaid": "payment_forgotten",
    "invoice_unpaid": "payment_forgotten",
    # cash flow variants
    "cash_flow": "cash_flow_issue",
    "financial_difficulty": "cash_flow_issue",
    # fixture v2 complex variants
    "accidental_mandate_revocation_during_card_switch": "mandate_revoked",
    "atypical_persistent_technical_error": "technical_error",
    "early_tenure_churn_risk": "dispute_raised",
    "invoice_dispute_pending": "wrong_invoice_details",
    "likely_transient_bank_flag": "bank_declined",
    "new_relationship_first_friction_needs_care": "unknown",
    "possible_mislabeled_dispute_status": "dispute_raised",
    "possible_undisclosed_billing_dispute": "dispute_raised",
    "price_increase_related_churn_risk": "dispute_raised",
    "secondary_unresolved_issue_after_details_correction": "technical_error",
    "selective_lapse_ambiguous_intent": "payment_forgotten",
    "wrong_bank_details": "wrong_details",
    "wrong_cvv": "wrong_details",
}


def normalise_cause(raw_cause: str) -> str:
    """Map any LLM-output cause label to the nearest canonical value."""
    cleaned = raw_cause.strip().lower().replace(" ", "_")
    if cleaned in CANONICAL_CAUSES:
        return cleaned
    normalised = _CAUSE_NORMALISE.get(cleaned)
    if normalised:
        log.warning(
            "cause_label_normalised",
            raw=raw_cause,
            canonical=normalised,
        )
        return normalised
    # Unknown label — log loudly and fall back to 'unknown'
    log.error(
        "cause_label_unrecognised",
        raw=raw_cause,
        action="falling_back_to_unknown",
    )
    return "unknown"


class DiagnosisFailedError(Exception):
    """Raised when the LLM diagnosis fails completely after retries."""
    pass


async def _run_llm_diagnosis(
    prompt_version: str,
    model: str,
    case_context: str,
) -> tuple[dict[str, Any], Any]:
    """
    Runs the LLM call and parses the JSON response.
    Retries once internally on JSON parsing errors.
    Returns (parsed_dict, raw_llm_response_obj)
    """
    for attempt in range(2):
        try:
            llm_result = await call_llm(
                prompt_version=prompt_version,
                model=model,
                user_messages=[{"role": "user", "content": case_context}],
                top_p=0.9,
                max_tokens=2048
            )
            raw_text = llm_result.content.strip()
            start_idx = raw_text.find("{")
            end_idx = raw_text.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                raw_text = raw_text[start_idx:end_idx + 1]
            
            parsed = json.loads(raw_text)
            
            # Validate required fields
            if not isinstance(parsed, dict):
                raise ValueError("LLM did not return a JSON object")
            if "causes" not in parsed or "confidence" not in parsed or "recommended_action" not in parsed:
                raise ValueError("Missing required fields in JSON output (need: causes, confidence, recommended_action)")
            if not isinstance(parsed["causes"], list):
                raise ValueError("'causes' must be a list of strings")
                
            return parsed, llm_result

        except (json.JSONDecodeError, ValueError) as exc:
            log.warning(
                "diagnosis_json_parse_error",
                model=model,
                attempt=attempt + 1,
                error=str(exc),
                raw_text_repr=repr(raw_text)
            )
            if attempt == 1:
                raise DiagnosisFailedError(f"Failed to parse LLM JSON after 2 attempts: {exc}") from exc

    raise DiagnosisFailedError("Unexpected diagnosis failure")


async def diagnose_case(
    case_id: uuid.UUID,
    session: AsyncSession,
    escalation_threshold: float = 0.75
) -> Diagnosis:
    """
    Diagnose a case using Tier 1 model, escalating to Tier 2 if confidence is low.
    Writes the resulting diagnosis to the DB.
    """
    case = await session.scalar(select(Case).where(Case.id == case_id))
    if not case:
        raise ValueError(f"Case {case_id} not found")

    # Strip ground_truth_cause from raw_payload to prevent LLM from cheating
    raw_payload_safe = dict(case.raw_payload) if case.raw_payload else {}
    raw_payload_safe.pop("ground_truth_cause", None)
    
    additional_context = raw_payload_safe.get('additional_context', 'None')
    case_context = f"Input:\nError: \"{case.raw_failure_reason}\"\nContext: \"{additional_context}\"\nOutput:\n"

    prompt_version = "diagnosis_v1"
    
    # 1. Try Tier 1 model
    log.info("diagnosis_started", case_id=str(case_id), tier=1, model=settings.groq_tier1_model)
    parsed, llm_result = await _run_llm_diagnosis(
        prompt_version=prompt_version,
        model=settings.groq_tier1_model,
        case_context=case_context
    )
    
    confidence = float(parsed["confidence"])
    tier = 1
    
    # 2. Escalate to Tier 2 if confidence is below threshold
    if confidence < escalation_threshold:
        log.info(
            "diagnosis_escalated",
            case_id=str(case_id),
            reason="low_confidence",
            confidence=confidence,
            threshold=escalation_threshold,
            tier=2,
            model=settings.groq_tier2_model
        )
        tier = 2
        parsed, llm_result = await _run_llm_diagnosis(
            prompt_version="diagnosis_v1_tier2",
            model=settings.groq_tier2_model,
            case_context=case_context
        )
        confidence = float(parsed["confidence"])

    log.info(
        "diagnosis_completed",
        case_id=str(case_id),
        tier=tier,
        causes=parsed["causes"],
        confidence=confidence
    )

    # 3. Normalise cause labels to canonical vocabulary
    canonical_causes = [normalise_cause(c) for c in parsed["causes"]]

    # 4. Save diagnosis to database
    diagnosis = Diagnosis(
        case_id=case.id,
        model_tier=f"tier{tier}",
        prompt_version=llm_result.prompt_version,
        prompt_hash=llm_result.prompt_hash,
        causes=canonical_causes,
        confidence=confidence,
        recommended_action=parsed["recommended_action"],
        raw_llm_response=llm_result.content
    )
    session.add(diagnosis)
    
    # Optionally, the caller should save an AuditEvent, but for completeness, we flush
    await session.flush()
    
    return diagnosis
