"""Durable one-way report publishing and deduplication receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "2026_10_30_report_publishing"
down_revision = "2026_10_28_research_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("report_publications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", sa.BigInteger(), sa.ForeignKey("analysis_reports.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("remote_report_id", sa.BigInteger()),
        sa.Column("last_error", sa.String(100)),
    )
    op.create_index("ix_report_publications_next_attempt_at", "report_publications", ["next_attempt_at"])
    op.create_table("report_publication_receipts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("report_id", sa.BigInteger(), sa.ForeignKey("analysis_reports.id", ondelete="SET NULL")),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for table in ("report_publications", "report_publication_receipts"):
        op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public.{table} FROM PUBLIC')
        op.execute(f"""DO $$ DECLARE r text; BEGIN FOR r IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated') LOOP EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I', r); END LOOP; END $$;""")


def downgrade():
    op.drop_table("report_publication_receipts")
    op.drop_table("report_publications")
