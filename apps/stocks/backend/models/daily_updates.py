"""Last acknowledged local configuration and worker heartbeat."""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from backend.config.database import Base


class DailyUpdateState(Base):
    __tablename__ = "daily_update_state"
    id = Column(Integer, primary_key=True)
    applied_revision = Column(String(64))
    applied_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    local_status = Column(JSONB, nullable=False, default=dict, server_default="{}")
