"""
0005 — add timeout to outcomes

Updates the final_state check constraint in outcomes to include 'timeout'.
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE outcomes 
        DROP CONSTRAINT IF EXISTS outcomes_final_state_check
    """)
    op.execute("""
        ALTER TABLE outcomes 
        ADD CONSTRAINT outcomes_final_state_check 
        CHECK (final_state IN ('recovered', 'pending', 'escalated', 'stopped', 'unresolved', 'disputed', 'timeout'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE outcomes 
        DROP CONSTRAINT IF EXISTS outcomes_final_state_check
    """)
    op.execute("""
        ALTER TABLE outcomes 
        ADD CONSTRAINT outcomes_final_state_check 
        CHECK (final_state IN ('recovered', 'pending', 'escalated', 'stopped', 'unresolved', 'disputed'))
    """)
