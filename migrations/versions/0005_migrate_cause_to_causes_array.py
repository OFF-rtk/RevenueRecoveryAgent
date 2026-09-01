"""migrate cause to causes array

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-30 18:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add new JSONB column
    op.add_column('diagnoses', sa.Column('causes', postgresql.JSONB, nullable=True))
    
    # 2. Migrate existing data: wrap single string in a JSON array
    op.execute("""
        UPDATE diagnoses 
        SET causes = jsonb_build_array(cause)
    """)
    
    # 3. Make causes NOT NULL
    op.alter_column('diagnoses', 'causes', nullable=False)
    
    # 4. Drop old cause column
    op.drop_column('diagnoses', 'cause')


def downgrade():
    op.add_column('diagnoses', sa.Column('cause', sa.Text(), nullable=True))
    
    # Migrate data back (take the first element)
    op.execute("""
        UPDATE diagnoses 
        SET cause = causes->>0
    """)
    
    op.alter_column('diagnoses', 'cause', nullable=False)
    op.drop_column('diagnoses', 'causes')
