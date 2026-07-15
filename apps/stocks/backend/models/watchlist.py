"""
Watchlist ORM Model — persistent watchlist stored in PostgreSQL.

Table:
    watchlist (
        id BIGSERIAL PRIMARY KEY,
        ticker VARCHAR(10) UNIQUE NOT NULL,
        position INTEGER DEFAULT 0,
        added_at TIMESTAMP DEFAULT NOW()
    )
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, func

from backend.config.database import Base


class WatchlistModel(Base):
    """Persistent watchlist row."""
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), unique=True, nullable=False)
    position = Column(Integer, default=0, nullable=False)
    added_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Watchlist ticker={self.ticker} position={self.position}>"
