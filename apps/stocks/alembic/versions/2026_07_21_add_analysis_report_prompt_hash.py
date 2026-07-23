"""add nullable prompt hash to analysis reports

Revision ID: 2026_07_21_prompt_hash
Revises: 6158f15fad43
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2026_07_21_prompt_hash"
down_revision: Union[str, Sequence[str], None] = "6158f15fad43"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.analysis_reports') IS NOT NULL THEN
                ALTER TABLE analysis_reports
                    ADD COLUMN prompt_hash VARCHAR(64);
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE IF EXISTS analysis_reports
            DROP COLUMN IF EXISTS prompt_hash
    """)