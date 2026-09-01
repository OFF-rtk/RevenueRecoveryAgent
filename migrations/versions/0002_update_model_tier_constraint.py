"""
0002 — update model tier constraint

Updates the model_tier check constraint in diagnoses to allow 'tier1' and 'tier2'.
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Drop the old constraint and add the new one
    op.execute("""
        ALTER TABLE diagnoses 
        DROP CONSTRAINT IF EXISTS diagnoses_model_tier_check
    """)
    op.execute("""
        ALTER TABLE diagnoses 
        ADD CONSTRAINT diagnoses_model_tier_check 
        CHECK (model_tier IN ('tier1', 'tier2', '8b', '70b'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE diagnoses 
        DROP CONSTRAINT IF EXISTS diagnoses_model_tier_check
    """)
    # Re-add the original constraint, but truncate the table first to avoid violations
    op.execute("TRUNCATE TABLE diagnoses CASCADE")
    op.execute("""
        ALTER TABLE diagnoses 
        ADD CONSTRAINT diagnoses_model_tier_check 
        CHECK (model_tier IN ('8b', '70b'))
    """)
