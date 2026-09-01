"""
core.models — public re-exports for the ORM layer.

Import all models here so SQLAlchemy's mapper registry is fully populated
before any query or migration runs. Any module that uses the DB should do:

    from core.models import Case, Diagnosis, ...
"""
from core.models.audit_events import AuditEvent
from core.models.base import Base
from core.models.cases import Case
from core.models.diagnoses import Diagnosis
from core.models.interventions import Intervention
from core.models.outcomes import Outcome
from core.models.replies import Reply
from core.models.state_transitions import StateTransition

__all__ = [
    "Base",
    "Case",
    "Diagnosis",
    "Intervention",
    "Reply",
    "StateTransition",
    "AuditEvent",
    "Outcome",
]
