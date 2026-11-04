"""Account notes, article reading state, and durable report runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "2026_10_28_research_workspace"
down_revision = "2026_10_23_private_app_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("research_notes", sa.Column("owner_id", sa.String(100), primary_key=True), sa.Column("ticker", sa.String(20), primary_key=True), sa.Column("text", sa.Text(), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_table("article_reading_state", sa.Column("owner_id", sa.String(100), primary_key=True), sa.Column("article_id", sa.BigInteger(), primary_key=True), sa.Column("saved", sa.Boolean(), nullable=False), sa.Column("read", sa.Boolean(), nullable=False))
    op.create_table("report_runs", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("kind", sa.String(20), nullable=False), sa.Column("parent_id", sa.BigInteger()), sa.Column("status", sa.String(20), nullable=False), sa.Column("stage", sa.String(50), nullable=False), sa.Column("current_ticker", sa.String(20)), sa.Column("tickers", JSONB(), nullable=False), sa.Column("outcomes", JSONB(), nullable=False), sa.Column("news_counts", JSONB(), nullable=False), sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("finished_at", sa.DateTime()))
    op.execute("CREATE UNIQUE INDEX report_runs_one_active ON report_runs ((1)) WHERE status IN ('queued', 'running')")
    for table in ("research_notes", "article_reading_state", "report_runs"):
        op.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public.{table} FROM PUBLIC')
        op.execute(f"""DO $$ DECLARE r text; BEGIN FOR r IN SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated') LOOP EXECUTE format('REVOKE ALL ON TABLE public.{table} FROM %I', r); END LOOP; END $$;""")


def downgrade():
    op.drop_table("report_runs")
    op.drop_table("article_reading_state")
    op.drop_table("research_notes")
