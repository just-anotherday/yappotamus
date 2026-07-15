"""
Price History Service — Fetches daily OHLCV data from yFinance and persists to DB.

Handles:
  - Bulk historical fetch (2 years of daily data)
  - Incremental daily refresh
  - Market tracker metadata seeding (SPY, QQQ, IWM, DIA)
  - Price retrieval for risk engine consumption
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import yfinance as yf
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.price_history import DailyOHLCV, IntradayOHLCV, MarketTrackerInfo

logger = logging.getLogger(__name__)

# Default market trackers to monitor
MARKET_TRACKERS = ["SPY", "QQQ", "IWM", "DIA"]


# ---------------------------------------------------------------------------
# Market Tracker Metadata
# ---------------------------------------------------------------------------

TRACKER_DEFINITIONS = {
    "SPY": {
        "display_name": "S&P 500 ETF Trust",
        "description": "Tracks the S&P 500 index of 500 large-cap US companies. The gold standard for broad market performance and overall economic health.",
        "coverage_scope": "Large Cap (500 companies)",
        "what_it_measures": "When SPY trends up, conditions favor buying individual stocks across sectors. When declining broadly, exercise caution regardless of individual stock signals.",
        "top_sectors": "[{\"sector\":\"Technology\",\"weight\":32},{\"sector\":\"Finance\",\"weight\":13},{\"sector\":\"Healthcare\",\"weight\":9},{\"sector\":\"Consumer Cyclical\",\"weight\":8},{\"sector\":\"Industrials\",\"weight\":9},{\"sector\":\"Communication Services\",\"weight\":8}] ",
        "key_constituents": "[\"AAPL\",\"MSFT\",\"NVDA\",\"AMZN\",\"META\",\"GOOGL\",\"BRK.B\",\"LLY\",\"V\",\"JPM\"]",
    },
    "QQQ": {
        "display_name": "Invesco QQQ Trust (Nasdaq-100)",
        "description": "Tracks the Nasdaq-100 index of 100 largest non-financial companies on Nasdaq. Heavy in tech/growth stocks and highly sensitive to interest rate changes.",
        "coverage_scope": "Growth / Tech (100 companies)",
        "what_it_measures": "QQQ leading SPY signals growth/tech optimism. QQQ lagging or declining while SPY rises suggests rotation out of growth into value — time for selectivity.",
        "top_sectors": "[{\"sector\":\"Technology\",\"weight\":49},{\"sector\":\"Communication Services\",\"weight\":16},{\"sector\":\"Consumer Defensive\",\"weight\":6},{\"sector\":\"Industrials\",\"weight\":6},{\"sector\":\"Finance\",\"weight\":7}] ",
        "key_constituents": "[\"AAPL\",\"MSFT\",\"NVDA\",\"AMZN\",\"META\",\"GOOGL\",\"GOOG\",\"AVGO\",\"COST\",\"NFLX\"]",
    },
    "IWM": {
        "display_name": "iShares Russell 2000 ETF (Small Cap)",
        "description": "Tracks the Russell 2000 index of 2000 small-cap US companies. The most liquid and widely-traded small-cap ETF, a leading indicator of domestic economic health.",
        "coverage_scope": "Small Cap (2000 companies)",
        "what_it_measures": "IWM outperforming SPY = domestic economy strength and small business confidence. IWM under SPY = flight to quality/safety — risk-off environment for smaller positions.",
        "top_sectors": "[{\"sector\":\"Finance\",\"weight\":20},{\"sector\":\"Industrials\",\"weight\":16},{\"sector\":\"Healthcare\",\"weight\":14},{\"sector\":\"Real Estate\",\"weight\":8},{\"sector\":\"Consumer Cyclical\",\"weight\":10},{\"sector\":\"Technology\",\"weight\":9}] ",
        "key_constituents": "[\"SMCI\",\"SAFT\",\"GTS\",\"CRSP\",\"CELH\",\"APPF\",\"IONS\",\"PCTY\",\"KPTI\",\"ENVX\"]",
    },
    "DIA": {
        "display_name": "SPDR Dow Jones Industrial Average ETF",
        "description": "Tracks the Dow Jones Industrial Average of 30 large, blue-chip US companies. Represents established, dividend-paying corporations.",
        "coverage_scope": "Blue Chip / Dividend (30 companies)",
        "what_it_measures": "DIA stability signals mature company resilience. DIA weakness despite SPY strength = institutional investors hedging core holdings — reduce exposure signal.",
        "top_sectors": "[{\"sector\":\"Finance\",\"weight\":21},{\"sector\":\"Healthcare\",\"weight\":18},{\"sector\":\"Industrials\",\"weight\":16},{\"sector\":\"Consumer Defensive\",\"weight\":9},{\"sector\":\"Technology\",\"weight\":10},{\"sector\":\"Communication Services\",\"weight\":5}] ",
        "key_constituents": "[\"V\",\"MSFT\",\"UNH\",\"JPM\",\"HD\",\"GS\",\"CAT\",\"MCD\",\"AXP\",\"CRM\"]",
    },
}


async def seed_market_tracker_info(session: AsyncSession) -> int:
    """Seed or update the market tracker metadata table. Returns count of records written."""
    count = 0
    for ticker, data in TRACKER_DEFINITIONS.items():
        existing = await session.execute(
            select(MarketTrackerInfo).where(MarketTrackerInfo.ticker == ticker)
        )
        row = existing.scalar_one_or_none()

        if row:
            for key, val in data.items():
                setattr(row, key, val)
        else:
            new_row = MarketTrackerInfo(ticker=ticker, **data)
            session.add(new_row)
        count += 1

    await session.commit()
    logger.info("[PriceHistory] Seeded/updated %d market tracker records.", count)
    return count


# ---------------------------------------------------------------------------
# OHLCV Data Management
# ---------------------------------------------------------------------------

def _parse_ohlcv_dataframe(hist_df, ticker: str = "") -> List[Dict[str, any]]:
    """Parse yfinance history DataFrame into list of dicts.

    Handles varying column names across yfinance versions (e.g. "Adj Close" vs
    "adjclose" or missing entirely for some ETFs/indexes).

    Skips rows where Close is missing (critical field). Logs warnings for
    missing optional fields. Never silently masks bad data with zeros.
    """
    records = []
    if hist_df is None or hist_df.empty:
        return records

    # Find the adjusted close column (yfinance may use different names)
    adj_col = None
    for candidate in ["Adj Close", "adjclose", "adjClose"]:
        if candidate in hist_df.columns:
            adj_col = candidate
            break
    if not adj_col:
        logger.warning("[PriceHistory] No adjusted close column found for %s, using Close as fallback.", ticker)

    # Check that required columns exist
    required = ["Close", "Volume"]
    missing_required = [c for c in required if c not in hist_df.columns]
    if missing_required:
        logger.error(
            "[PriceHistory] Missing required columns for %s: %s. Available: %s",
            ticker, missing_required, list(hist_df.columns),
        )
        return records

    skipped = 0
    for dt_val, row in hist_df.iterrows():
        # Skip rows where Close is missing — it's a critical field
        if pd_isna(row.get("Close")):
            skipped += 1
            continue

        rec_date = dt_val.date() if hasattr(dt_val, "date") else datetime.strptime(str(dt_val), "%Y-%m-%d").date()

        records.append({
            "date": rec_date,
            "open_price": float(row["Open"]) if "Open" in hist_df.columns and not pd_isna(row.get("Open")) else None,
            "high": float(row["High"]) if "High" in hist_df.columns and not pd_isna(row.get("High")) else None,
            "low": float(row["Low"]) if "Low" in hist_df.columns and not pd_isna(row.get("Low")) else None,
            "close": float(row["Close"]),
            "adjusted_close": float(row[adj_col]) if adj_col and not pd_isna(row.get(adj_col)) else None,
            "volume": int(row["Volume"]) if not pd_isna(row.get("Volume")) else None,
        })

    if skipped:
        logger.warning("[PriceHistory] Skipped %d rows with missing Close for %s.", skipped, ticker)

    return records


def pd_isna(val) -> bool:
    """Check if a pandas value is NA/NaN."""
    try:
        import pandas as pd
        return pd.isna(val)
    except (ImportError, TypeError):
        import math
        return isinstance(val, float) and math.isnan(val)


async def fetch_and_store_history(
    session: AsyncSession,
    ticker: str,
    period: str = "2y",
) -> int:
    """
    Fetch historical OHLCV data for a ticker via yFinance and store in DB.
    
    Args:
        session: Async DB session.
        ticker: Stock/ETF symbol.
        period: Time period to fetch ("1y", "2y", "5y", "max").
    
    Returns:
        Number of records upserted.
    """
    ticker = ticker.upper()
    logger.info("[PriceHistory] Fetching %s history for %s...", period, ticker)

    try:
        yf_ticker = yf.Ticker(ticker)
        hist_df = yf_ticker.history(period=period)
    except Exception as e:
        logger.error("[PriceHistory] Failed to fetch data for %s: %s", ticker, e)
        return 0

    records = _parse_ohlcv_dataframe(hist_df, ticker=ticker)
    if not records:
        logger.warning("[PriceHistory] No OHLCV data returned for %s.", ticker)
        return 0

    upserted = 0
    for rec in records:
        # Check if record exists
        existing = await session.execute(
            select(DailyOHLCV).where(
                DailyOHLCV.ticker == ticker,
                DailyOHLCV.date == rec["date"],
            )
        )
        
        if existing.scalar_one_or_none():
            # Update existing record
            stmt = (
                DailyOHLCV.__table__.update()
                .where(
                    DailyOHLCV.ticker == ticker,
                    DailyOHLCV.date == rec["date"],
                )
                .values(
                    open_price=rec["open_price"],
                    high=rec["high"],
                    low=rec["low"],
                    close=rec["close"],
                    volume=rec["volume"],
                    adjusted_close=rec["adjusted_close"],
                )
            )
            await session.execute(stmt)
        else:
            # Insert new record
            ohlcv = DailyOHLCV(
                ticker=ticker,
                date=rec["date"],
                open_price=rec["open_price"],
                high=rec["high"],
                low=rec["low"],
                close=rec["close"],
                volume=rec["volume"],
                adjusted_close=rec["adjusted_close"],
            )
            session.add(ohlcv)
        
        upserted += 1

    await session.commit()
    logger.info("[PriceHistory] Upserted %d records for %s.", upserted, ticker)
    return upserted


async def fetch_and_store_batch(
    session: AsyncSession,
    tickers: List[str],
    period: str = "2y",
) -> Dict[str, int]:
    """Fetch and store history for multiple tickers. Returns {ticker: count} dict."""
    results = {}
    for ticker in tickers:
        count = await fetch_and_store_history(session, ticker, period=period)
        results[ticker] = count
    return results


async def get_close_prices(
    session: AsyncSession,
    ticker: str,
    days: Optional[int] = None,
) -> List[float]:
    """
    Retrieve close prices for a ticker, ordered oldest-first.
    
    Args:
        session: Async DB session.
        ticker: Symbol to fetch.
        days: Optional limit to last N trading days.
    
    Returns:
        List of close prices (oldest first).
    """
    ticker = ticker.upper()
    
    if days:
        cutoff = date.today() - timedelta(days=days * 1.5)  # extra buffer for weekends/holidays
        stmt = (
            select(DailyOHLCV.close)
            .where(
                DailyOHLCV.ticker == ticker,
                DailyOHLCV.date >= cutoff,
                DailyOHLCV.close.isnot(None),
            )
            .order_by(DailyOHLCV.date.asc())
        )
    else:
        stmt = (
            select(DailyOHLCV.close)
            .where(
                DailyOHLCV.ticker == ticker,
                DailyOHLCV.close.isnot(None),
            )
            .order_by(DailyOHLCV.date.asc())
        )
    
    result = await session.execute(stmt)
    prices = [row[0] for row in result.fetchall() if row[0] is not None]
    return prices


async def get_full_ohlcv_records(
    session: AsyncSession,
    ticker: str,
    days: Optional[int] = None,
) -> List[DailyOHLCV]:
    """Retrieve full OHLCV records for a ticker."""
    ticker = ticker.upper()
    
    if days:
        cutoff = date.today() - timedelta(days=days * 1.5)
        stmt = (
            select(DailyOHLCV)
            .where(
                DailyOHLCV.ticker == ticker,
                DailyOHLCV.date >= cutoff,
            )
            .order_by(DailyOHLCV.date.asc())
        )
    else:
        stmt = (
            select(DailyOHLCV)
            .where(DailyOHLCV.ticker == ticker)
            .order_by(DailyOHLCV.date.asc())
        )
    
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Intraday OHLCV helpers
# ---------------------------------------------------------------------------

def _parse_intraday_dataframe(hist_df, ticker: str = "") -> List[Dict[str, any]]:
    """Parse yfinance intraday DataFrame into list of dicts."""
    records = []
    if hist_df is None or hist_df.empty:
        return records
    for dt_val, row in hist_df.iterrows():
        rec_ts = dt_val if hasattr(dt_val, 'hour') else datetime.strptime(str(dt_val), "%Y-%m-%d %H:%M:%S")
        records.append({
            "timestamp": rec_ts,
            "open_price": float(row["Open"]) if not pd_isna(row.get("Open")) else None,
            "high": float(row["High"]) if not pd_isna(row.get("High")) else None,
            "low": float(row["Low"]) if not pd_isna(row.get("Low")) else None,
            "close": float(row["Close"]) if not pd_isna(row.get("Close")) else None,
            "volume": int(row["Volume"]) if not pd_isna(row.get("Volume")) else None,
        })
    return records


async def fetch_and_store_intraday(
    session: AsyncSession,
    ticker: str,
) -> int:
    """Fetch 5m intraday bars from yFinance for the last ~7 trading days and upsert."""
    ticker = ticker.upper()
    logger.info("[PriceHistory] Fetching intraday data for %s...", ticker)
    try:
        yf_ticker = yf.Ticker(ticker)
        # Fast interval: up to 7 days of 5m bars
        hist_df = yf_ticker.history(period="7d", interval="5m")
    except Exception as e:
        logger.error("[PriceHistory] Failed to fetch intraday for %s: %s", ticker, e)
        return 0

    records = _parse_intraday_dataframe(hist_df, ticker=ticker)
    if not records:
        logger.warning("[PriceHistory] No intraday data for %s.", ticker)
        return 0

    # Purge old intraday data (>7 days) for this ticker
    cutoff = datetime.now() - timedelta(days=14)
    await session.execute(
        delete(IntradayOHLCV).where(
            IntradayOHLCV.ticker == ticker,
            IntradayOHLCV.timestamp < cutoff,
        )
    )

    upserted = 0
    for rec in records:
        existing = await session.execute(
            select(IntradayOHLCV).where(
                IntradayOHLCV.ticker == ticker,
                IntradayOHLCV.timestamp == rec["timestamp"],
            )
        )
        if existing.scalar_one_or_none():
            stmt = (
                IntradayOHLCV.__table__.update()
                .where(
                    IntradayOHLCV.ticker == ticker,
                    IntradayOHLCV.timestamp == rec["timestamp"],
                )
                .values(**rec)
            )
            await session.execute(stmt)
        else:
            session.add(IntradayOHLCV(ticker=ticker, **rec))
        upserted += 1

    await session.commit()
    logger.info("[PriceHistory] Upserted %d intraday bars for %s.", upserted, ticker)
    return upserted


async def get_intraday_bars(
    session: AsyncSession,
    ticker: str,
    period: str = "1D",
    interval: str = "5m",
) -> List[Dict[str, any]]:
    """
    Retrieve intraday bars and aggregate to the requested interval.

    Supported periods: 1D, 5D
    Supported intervals: 5m, 15m, 60m
    """
    ticker = ticker.upper()

    # Determine cutoff based on period
    period_days = {"1D": 2, "5D": 7}
    days_back = period_days.get(period, 2)
    cutoff = datetime.now() - timedelta(days=days_back)

    stmt = (
        select(IntradayOHLCV)
        .where(
            IntradayOHLCV.ticker == ticker,
            IntradayOHLCV.timestamp >= cutoff,
        )
        .order_by(IntradayOHLCV.timestamp.asc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    if not rows:
        # Fallback: fetch fresh data from yFinance on-demand
        try:
            await fetch_and_store_intraday(session, ticker)
            rows = list((await session.execute(stmt)).scalars().all())
        except Exception:
            return []

    # Group 5m bars into the requested interval
    group_size = {"5m": 1, "15m": 3, "60m": 12}.get(interval, 1)
    groups: List[List[IntradayOHLCV]] = []
    current_group: List[IntradayOHLCV] = []

    for row in rows:
        current_group.append(row)
        if len(current_group) >= group_size:
            groups.append(current_group)
            current_group = []
    if current_group:
        groups.append(current_group)

    aggregated: List[Dict[str, any]] = []
    for g in groups:
        if not g:
            continue
        aggregated.append({
            "timestamp": g[0].timestamp.isoformat(),
            "open": g[0].open_price,
            "high": max(r.high or 0 for r in g),
            "low": min(r.low or float('inf') for r in g),
            "close": g[-1].close,
            "volume": sum(r.volume or 0 for r in g),
        })

    return aggregated


# ---------------------------------------------------------------------------
# Tracker Metadata Helper
# ---------------------------------------------------------------------------

async def get_tracker_metadata(session: AsyncSession, ticker: Optional[str] = None) -> List[Dict[str, any]]:
    """
    Retrieve market tracker metadata.
    
    Args:
        session: Async DB session.
        ticker: If provided, returns only that tracker. Otherwise all active trackers.
    
    Returns:
        List of dicts with tracker info.
    """
    stmt = select(MarketTrackerInfo).where(MarketTrackerInfo.active == 1)
    if ticker:
        stmt = stmt.where(MarketTrackerInfo.ticker == ticker.upper())
    
    result = await session.execute(stmt)
    rows = result.scalars().all()
    
    output = []
    for row in rows:
        # Parse JSON string columns to actual Python objects
        try:
            top_sectors = json.loads(row.top_sectors) if row.top_sectors else []
        except (json.JSONDecodeError, TypeError):
            top_sectors = []
        try:
            key_constituents = json.loads(row.key_constituents) if row.key_constituents else []
        except (json.JSONDecodeError, TypeError):
            key_constituents = []

        output.append({
            "ticker": row.ticker,
            "display_name": row.display_name,
            "description": row.description,
            "coverage_scope": row.coverage_scope,
            "what_it_measures": row.what_it_measures,
            "top_sectors": top_sectors,
            "key_constituents": key_constituents,
        })
    
    return output


__all__ = [
    "MARKET_TRACKERS",
    "seed_market_tracker_info",
    "fetch_and_store_history",
    "fetch_and_store_batch",
    "get_close_prices",
    "get_full_ohlcv_records",
    "get_tracker_metadata",
    "fetch_and_store_intraday",
    "get_intraday_bars",
]
