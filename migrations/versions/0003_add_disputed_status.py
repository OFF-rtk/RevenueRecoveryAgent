"""
0003 — add disputed status

Updates the status check constraint in cases to include 'disputed'.
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE cases 
        DROP CONSTRAINT IF EXISTS cases_status_check
    """)
    op.execute("""
        ALTER TABLE cases 
        ADD CONSTRAINT cases_status_check 
        CHECK (status IN ('open', 'in_progress', 'promise_pending', 'payment_method_required', 'recovered', 'escalated', 'stopped', 'unresolved', 'disputed'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE cases 
        DROP CONSTRAINT IF EXISTS cases_status_check
    """)
    op.execute("""
        ALTER TABLE cases 
        ADD CONSTRAINT cases_status_check 
        CHECK (status IN ('open', 'in_progress', 'promise_pending', 'payment_method_required', 'recovered', 'escalated', 'stopped', 'unresolved'))
    """)
