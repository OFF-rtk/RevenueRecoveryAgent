"""
0004 — add disputed status to outcomes

Updates the final_state check constraint in outcomes to include 'disputed'.
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision: str = "0004"
down_revision: str | None = "0003"
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
        CHECK (final_state IN ('recovered', 'pending', 'escalated', 'stopped', 'unresolved', 'disputed'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE outcomes 
        DROP CONSTRAINT IF EXISTS outcomes_final_state_check
    """)
    op.execute("""
        ALTER TABLE outcomes 
        ADD CONSTRAINT outcomes_final_state_check 
        CHECK (final_state IN ('recovered', 'pending', 'escalated', 'stopped', 'unresolved'))
    """)
