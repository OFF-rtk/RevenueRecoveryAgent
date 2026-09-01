"""
Shared pytest fixtures for the Revenue Recovery Agent.
"""
import pytest
import pytest_asyncio
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def webhook_secret() -> str:
    return "test_webhook_secret_phase1"


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """
    Apply migrations once before the session, tear them down after.
    Uses subprocess to exercise the full `alembic` CLI path.

    We run downgrade→upgrade at the START of every session so that even
    if a previous session left the DB in a partially torn-down state
    (e.g. alembic_version says 'head' but tables are gone), we still get
    a clean slate.
    """
    # Downgrade first — guarantees a clean slate regardless of prior state
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    # Upgrade to head
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}"
    )

    yield  # tests run here


@pytest_asyncio.fixture()
async def db_session():
    """Yield an AsyncSession connected to the real test database."""
    from core.config import settings
    from core.db import init_db

    await init_db(settings.database_url)

    from core.db import async_session_factory
    factory = async_session_factory()
    async with factory() as session:
        yield session
        await session.rollback()  # clean up after each test


@pytest.fixture()
def fastapi_client(webhook_secret, monkeypatch):
    """
    TestClient wired to the FastAPI app with the test webhook secret.
    Overrides the razorpay_webhook_secret setting to match test fixtures.
    """
    from core import config as cfg_module

    # Patch the singleton settings object in place
    monkeypatch.setattr(cfg_module.settings, "razorpay_webhook_secret", webhook_secret)

    from core.main import app
    from starlette.testclient import TestClient

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture
async def sample_case_and_diagnosis(db_session):
    import uuid
    from decimal import Decimal
    from core.models.cases import Case
    from core.models.diagnoses import Diagnosis

    event_id = f"payment.failed:pay_01_{uuid.uuid4()}"
    case = Case(
        case_type="failed_subscription",
        customer_ref="919999999999",
        amount=Decimal("100.00"),
        raw_failure_reason="CARD_EXPIRED",
        razorpay_event_id=event_id
    )
    db_session.add(case)
    await db_session.flush()
    
    diagnosis = Diagnosis(
        case_id=case.id,
        model_tier="tier1",
        prompt_version="diagnosis_v1",
        prompt_hash="hash",
        causes=["expired_card"],
        confidence=Decimal("0.95"),
        recommended_action="Ask customer to update card",
        raw_llm_response="{}"
    )
    db_session.add(diagnosis)
    await db_session.commit()
    
    return case, diagnosis
