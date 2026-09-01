import structlog
import uuid
from core.db import async_session_factory
from core.config import settings
from core.services.diagnosis import diagnose_case, DiagnosisFailedError
from core.services.intervention import draft_and_send_intervention
from core.channels.whatsapp import WhatsAppChannel
from core.channels.mock import MockChannel

log = structlog.get_logger(__name__)

async def process_new_webhook_case(case_id: uuid.UUID) -> None:
    """
    Background task to process a newly created case from a Razorpay webhook.
    1. Diagnoses the case using the LLM.
    2. Drafts and sends the initial intervention via WhatsApp.
    """
    log.info("background_pipeline_started", case_id=str(case_id))
    
    if settings.use_mock_channel:
        channel = MockChannel()
    else:
        channel = WhatsAppChannel(
            phone_number_id=settings.phone_number_id,
            api_token=settings.whatsapp_token
        )

    # Use a new session context for the background task
    async with async_session_factory() as session:
        try:
            # 1. Diagnose
            await diagnose_case(case_id, session)
            
            # 2. Intervene
            await draft_and_send_intervention(case_id, session, channel=channel)
            
        except DiagnosisFailedError as e:
            log.error("background_pipeline_diagnosis_failed", case_id=str(case_id), error=str(e))
        except Exception as e:
            log.exception("background_pipeline_failed", case_id=str(case_id), error=str(e))
