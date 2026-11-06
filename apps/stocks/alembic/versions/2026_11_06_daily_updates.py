"""Shared daily-update preferences and local-worker acknowledgement."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "2026_11_06_daily_updates"
down_revision = "2026_10_30_report_publishing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("watchlist", sa.Column("news_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("watchlist", sa.Column("reports_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("watchlist", sa.Column("news_pending", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("watchlist", "news_pending", server_default=sa.true())
    op.add_column("watchlist", sa.Column("news_status", sa.String(40), nullable=False, server_default="not_requested"))
    op.alter_column("watchlist", "news_status", server_default="pending")
    op.add_column("watchlist", sa.Column("news_checked_at", sa.DateTime()))
    op.create_table("daily_update_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("applied_revision", sa.String(64)),
        sa.Column("applied_at", sa.DateTime()),
        sa.Column("last_seen_at", sa.DateTime()),
        sa.Column("local_status", JSONB(), nullable=False, server_default="{}"),
    )
    op.execute('ALTER TABLE public.daily_update_state ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON TABLE public.daily_update_state FROM PUBLIC')
    op.execute("""DO $$ DECLARE r text; BEGIN FOR r IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated') LOOP EXECUTE format('REVOKE ALL ON TABLE public.daily_update_state FROM %I', r); END LOOP; END $$;""")


def downgrade():
    op.drop_table("daily_update_state")
    for name in ("news_checked_at", "news_status", "news_pending", "reports_enabled", "news_enabled"):
        op.drop_column("watchlist", name)
