"""
Daily OHLCV price history model for risk calculations and market tracking.

Stores historical daily open/high/low/close/volume data fetched from yFinance,
used for volatility computation, VaR, drawdown, momentum analysis, and
chart rendering on the frontend.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.config.database import Base


class DailyOHLCV(Base):
    __tablename__ = "daily_ohlcv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False)
    open_price = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(BigInteger, nullable=True)
    adjusted_close = Column(Float, nullable=True)

    # Unique constraint: only one record per ticker per date
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_ticker_date"),
    )

    def __repr__(self) -> str:
        return f"<DailyOHLCV(ticker={self.ticker}, date={self.date}, close={self.close})>"


class MarketTrackerInfo(Base):
    """
    Static metadata for market index trackers (SPY, QQQ, IWM, DIA).

    Provides human-readable descriptions, coverage scope, and the constituent
    tickers that each tracker represents.
    """

    __tablename__ = "market_tracker_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    coverage_scope = Column(String(200), nullable=True)
    what_it_measures = Column(String(500), nullable=True)  # Buy/sell implication text
    top_sectors = Column(String(1000), nullable=True)  # JSON string of sector list
    key_constituents = Column(String(2000), nullable=True)  # JSON string of ticker list
    active = Column(Integer, default=1)  # soft-delete flag

    def __repr__(self) -> str:
        return f"<MarketTrackerInfo(ticker={self.ticker}, name={self.display_name})>"


class IntradayOHLCV(Base):
    """
    Intraday OHLCV bars at 5-minute resolution.

    Raw data from yFinance is stored at 5m granularity. Higher intervals (15m, 1h)
    are derived by aggregating these base bars on query or during backfill.
    Auto-purged based on age: <2 days for 1D view, <7 days for 5D, <45 days cached.
    """

    __tablename__ = "intraday_ohlcv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    open_price = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_intraday_ticker_timestamp", "ticker", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<IntradayOHLCV(ticker={self.ticker}, ts={self.timestamp}, close={self.close})>"
