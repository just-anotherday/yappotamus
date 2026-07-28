"""add AI job worker leases and recovery audit fields

Revision ID: 2026_07_27_ai_job_leases
Revises: 2026_07_21_maintenance
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2026_07_27_ai_job_leases"
down_revision: Union[str, None] = "2026_07_21_maintenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_job_queue",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Preserve meaningful age for legacy rows. Recovery remains disabled by
    # default and cannot transition these jobs until explicitly enabled.
    op.execute(
        sa.text(
            "UPDATE ai_job_queue "
            "SET updated_at = COALESCE(completed_at, started_at, created_at, now())"
        )
    )
    op.add_column(
        "ai_job_queue",
        sa.Column("worker_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ai_job_queue",
        sa.Column("heartbeat_at", sa.TIMESTAMP(), nullable=True),
    )
    op.add_column(
        "ai_job_queue",
        sa.Column("lease_expires_at", sa.TIMESTAMP(), nullable=True),
    )
    op.add_column(
        "ai_job_queue",
        sa.Column(
            "recovery_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "ai_job_queue",
        sa.Column("last_recovery_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_ai_job_queue_status_lease",
        "ai_job_queue",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_ai_job_queue_status_lease", table_name="ai_job_queue")
    op.drop_column("ai_job_queue", "last_recovery_reason")
    op.drop_column("ai_job_queue", "recovery_count")
    op.drop_column("ai_job_queue", "lease_expires_at")
    op.drop_column("ai_job_queue", "heartbeat_at")
    op.drop_column("ai_job_queue", "worker_id")
    op.drop_column("ai_job_queue", "updated_at")
