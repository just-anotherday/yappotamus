"""
Markets Router — API endpoints for market regime dashboard, price history, and risk signals.

Endpoints:
  GET  /api/markets                  - List all market tracker statuses (SPY/QQQ/IWM/DIA)
  GET  /api/markets/{ticker}         - Detail for a single tracker with risk signal
  GET  /api/markets/{ticker}/prices  - OHLCV price history for charting
  GET  /api/markets/regime          - Overall market regime assessment
  GET  /api/markets/{ticker}/risk   - Full risk signal for any ticker (tracker or watchlist)
  POST /api/markets/refresh         - Trigger a data refresh for all trackers
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.database import get_async_session
from backend.lib.risk_engine import (
    compute_risk_signal,
    apply_market_regime_adjustment,
    trend_direction,
    historical_volatility,
    momentum_score,
    max_drawdown,
    value_at_var,
)
from backend.lib.risk_metrics import compute_risk_metrics
from backend.services.price_history_service import (
    MARKET_TRACKERS,
    get_close_prices,
    get_tracker_metadata,
    fetch_and_store_history,
    fetch_and_store_batch,
    seed_market_tracker_info,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["markets"])


def _flatten_risk_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten the nested compute_risk_signal() output to match frontend expectations.

    Frontend expects:
      - composite_score (we return 'score')
      - volatility_score, momentum_score, var_score, drawdown_score (nested in signal.factors.*.score)
      - buy_signal / sell_signal booleans (we return a string 'signal')
      - factor labels and detail strings for human-readable gauge descriptions
    """
    factors = signal.get("factors", {})

    raw_vol = factors.get("volatility", {}).get("score", 0.0) if isinstance(factors, dict) else 0.0
    raw_mom = factors.get("momentum", {}).get("score", 0.0) if isinstance(factors, dict) else 0.0
    raw_var = factors.get("var", {}).get("score", 0.0) if isinstance(factors, dict) else 0.0
    raw_dd = factors.get("drawdown", {}).get("score", 0.0) if isinstance(factors, dict) else 0.0

    # Extract human-readable labels and detail strings for each factor
    vol_label = factors.get("volatility", {}).get("label", "") if isinstance(factors, dict) else ""
    vol_detail = factors.get("volatility", {}).get("detail", "") if isinstance(factors, dict) else ""
    mom_label = factors.get("momentum", {}).get("label", "") if isinstance(factors, dict) else ""
    mom_detail = factors.get("momentum", {}).get("detail", "") if isinstance(factors, dict) else ""
    var_label = factors.get("var", {}).get("label", "") if isinstance(factors, dict) else ""
    var_detail = factors.get("var", {}).get("detail", "") if isinstance(factors, dict) else ""
    dd_label = factors.get("drawdown", {}).get("label", "") if isinstance(factors, dict) else ""
    dd_detail = factors.get("drawdown", {}).get("detail", "") if isinstance(factors, dict) else ""

    raw_signal = signal.get("signal", "HOLD")

    return {
        "composite_score": signal.get("score", 0.0),
        "buy_signal": raw_signal == "BUY",
        "sell_signal": raw_signal == "SELL",
        "volatility_score": raw_vol,
        "momentum_score": raw_mom,
        "var_score": raw_var,
        "drawdown_score": raw_dd,
        "volatility_label": vol_label,
        "volatility_detail": vol_detail,
        "momentum_label": mom_label,
        "momentum_detail": mom_detail,
        "var_label": var_label,
        "var_detail": var_detail,
        "drawdown_label": dd_label,
        "drawdown_detail": dd_detail,
        "regime_adjustment": signal.get("market_regime", ""),
        "dominant_risk_factor": signal.get("dominant_risk_factor", ""),
    }


def _assess_regime_from_trends(trends: Dict[str, str]) -> str:
    """
    Assess overall market regime based on individual tracker trend directions.
    
    Returns "BULLISH", "NEUTRAL", or "BEARISH".
    """
    bullish_count = sum(1 for t in trends.values() if t in ("UP", "STRONG_UP"))
    bearish_count = sum(1 for t in trends.values() if t in ("DOWN", "STRONG_DOWN"))
    
    if bullish_count >= 3:
        return "BULLISH"
    elif bearish_count >= 3:
        return "BEARISH"
    else:
        return "NEUTRAL"


@router.get("/")
async def list_market_trackers(
    session: AsyncSession = Depends(get_async_session),
) -> List[Dict[str, Any]]:
    """List all market trackers with current status and metadata."""
    # Get metadata
    trackers_meta = await get_tracker_metadata(session)
    
    result = []
    for meta in trackers_meta:
        ticker = meta["ticker"]
        
        # Fetch recent prices for trend calculation
        prices = await get_close_prices(session, ticker, days=60)
        
        if not prices or len(prices) < 10:
            result.append({
                **meta,
                "status": "INSUFFICIENT_DATA",
                "current_price": None,
                "change_5d": 0,
                "change_20d": 0,
                "trend": "SIDEWAYS",
            })
            continue
        
        current_price = prices[-1]
        
        # Calculate momentum for different windows
        mom_5d = momentum_score(prices, 5) if len(prices) >= 6 else 0.0
        mom_20d = momentum_score(prices, 20) if len(prices) >= 21 else 0.0
        
        td = trend_direction(prices)
        
        result.append({
            **meta,
            "status": td,
            "current_price": round(current_price, 2),
            "change_5d": round(mom_5d, 2),
            "change_20d": round(mom_20d, 2),
            "trend": td,
        })
    
    return result


@router.get("/regime")
async def get_market_regime(
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Get the overall market regime assessment."""
    trends = {}
    
    for ticker in MARKET_TRACKERS:
        prices = await get_close_prices(session, ticker, days=60)
        if prices and len(prices) >= 25:
            trends[ticker] = trend_direction(prices)
        else:
            trends[ticker] = "SIDEWAYS"
    
    regime = _assess_regime_from_trends(trends)
    
    return {
        "regime": regime,
        "tracker_trends": trends,
        "bullish_count": sum(1 for t in trends.values() if t in ("UP", "STRONG_UP")),
        "bearish_count": sum(1 for t in trends.values() if t in ("DOWN", "STRONG_DOWN")),
    }


@router.get("/{ticker}")
async def get_tracker_detail(
    ticker: str,
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """
    Get detailed info for any ticker including risk signal.

    First tries the market_tracker_info table (SPY/QQQ/IWM/DIA).
    Falls back to yfinance for display_name/description so watchlist tickers
    like MSFT or AAPL still work on the detail page.
    """
    ticker = ticker.upper()

    # Try to get metadata from the tracker table
    meta_list = await get_tracker_metadata(session, ticker=ticker)
    if meta_list:
        meta = meta_list[0]
    else:
        # Fallback: pull basic info from yfinance so watchlist tickers work too
        try:
            quote = yf.Ticker(ticker)
            info = quote.fast_info
            display_name = getattr(info, 'shortName', ticker) or ticker
            current_price_val = getattr(info, 'currentPrice', None)
            if current_price_val is None:
                current_price_val = getattr(info, 'lastPrice', None)
        except Exception:
            display_name = ticker
            current_price_val = None

        meta = {
            "ticker": ticker,
            "display_name": display_name,
            "description": "",
            "category": "stock",
            "what_it_measures": "",
            "top_sectors": [],
            "key_constituents": [],
            "data_provider": "yfinance",
        }

    # Full price history for risk calculation
    prices = await get_close_prices(session, ticker, days=500)

    if not prices or len(prices) < 30:
        return {
            **meta,
            "current_price": current_price_val if meta.get("category") == "stock" else (prices[-1] if prices else None),
            "data_points": len(prices) if prices else 0,
            "signal": None,
            "error": "Insufficient price history for risk calculation",
        }

    # Compute risk signal
    signal = compute_risk_signal(prices)

    # Get some summary stats
    hv = historical_volatility(prices)
    mom_20d = momentum_score(prices, 20)
    md = max_drawdown(prices)
    var_95 = value_at_var(prices)

    flattened_signal = _flatten_risk_signal(signal)

    return {
        **meta,
        "current_price": round(prices[-1], 2),
        "data_points": len(prices),
        "summary_stats": {
            "historical_volatility_1y": hv,
            "momentum_20d_pct": round(mom_20d, 2),
            "max_drawdown_pct": md,
            "var_95_daily_pct": var_95,
        },
        "signal": flattened_signal,
    }


@router.get("/{ticker}/prices")
async def get_tracker_prices(
    ticker: str,
    days: int = Query(default=365, ge=30, le=1825),
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Get OHLCV price history for charting."""
    from backend.services.price_history_service import get_full_ohlcv_records
    
    records = await get_full_ohlcv_records(session, ticker.upper(), days=days * 2)
    
    if not records:
        return {
            "ticker": ticker,
            "prices": [],
            "dates": [],
            "message": "No price data available",
        }
    
    prices_data = []
    dates = []
    for rec in records:
        dates.append(str(rec.date))
        prices_data.append({
            "open": rec.open_price,
            "high": rec.high,
            "low": rec.low,
            "close": rec.close,
            "volume": rec.volume,
        })
    
    return {
        "ticker": ticker.upper(),
        "dates": dates,
        "prices": prices_data,
        "count": len(records),
    }


@router.get("/{ticker}/risk")
async def get_risk_signal(
    ticker: str,
    buy_threshold: float = Query(default=3.5, ge=0, le=10),
    sell_threshold: float = Query(default=7.0, ge=0, le=10),
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """
    Compute the full risk signal for any ticker (not just market trackers).

    Includes market regime adjustment and advanced statistical risk metrics:
      - Volatility (annualized)
      - Value at Risk (parametric + historical)
      - Expected Shortfall (CVaR)
      - Maximum Drawdown
      - Sharpe Ratio / Sortino Ratio
      - Beta vs SPY benchmark
    """
    ticker = ticker.upper()

    # Fetch price history
    prices = await get_close_prices(session, ticker, days=500)

    if not prices or len(prices) < 30:
        return {
            "ticker": ticker,
            "signal": None,
            "error": f"Insufficient price history for {ticker} (need ~30 trading days minimum)",
            "data_points": len(prices) if prices else 0,
        }

    # Compute base risk signal (existing heuristic engine)
    signal = compute_risk_signal(
        prices=prices,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
    )

    # Fetch current market regime and apply adjustment
    try:
        trends = {}
        for mt in MARKET_TRACKERS:
            mt_prices = await get_close_prices(session, mt, days=60)
            if mt_prices and len(mt_prices) >= 25:
                trends[mt] = trend_direction(mt_prices)
            else:
                trends[mt] = "SIDEWAYS"

        regime = _assess_regime_from_trends(trends)
        signal = apply_market_regime_adjustment(signal, regime)
    except Exception as e:
        logger.warning("[Markets] Failed to compute regime adjustment: %s", e)
        signal["market_regime"] = "UNKNOWN"
        signal["regime_adjustment"] = 0.0

    # Fetch SPY benchmark for beta calculation
    spy_prices: Optional[List[float]] = None
    try:
        spy_prices = await get_close_prices(session, "SPY", days=500)
    except Exception as e:
        logger.debug("[Markets] Failed to fetch SPY benchmark: %s", e)

    # Compute advanced statistical risk metrics
    try:
        advanced_metrics = compute_risk_metrics(
            prices=prices,
            benchmark_prices=spy_prices,
            confidence=0.95,
        )
    except Exception as e:
        logger.warning("[Markets] Failed to compute advanced metrics: %s", e)
        advanced_metrics = {"error": True, "message": str(e)}

    return {
        "ticker": ticker,
        "data_points": len(prices),
        "signal": signal,
        "advanced_metrics": advanced_metrics,
    }


@router.post("/refresh")
async def refresh_tracker_data() -> Dict[str, Any]:
    """
    Trigger a per-ticker price history refresh with isolated failure handling.
    
    Each tracker is refreshed independently so one failure doesn't block others.
    Returns aggregated status reporting with success/failure breakdown.
    """
    from backend.config.database import async_session_factory
    
    results: Dict[str, Any] = {}
    successes = 0
    failures = 0
    
    for ticker in MARKET_TRACKERS:
        try:
            async with async_session_factory() as session:
                count = await fetch_and_store_history(session, ticker, period="2y")
            results[ticker] = {"status": "ok", "records": count}
            successes += 1
        except Exception as e:
            logger.error("[Markets] Failed to refresh %s: %s", ticker, e)
            results[ticker] = {"status": "error", "message": str(e)}
            failures += 1
    
    total_records = sum(r.get("records", 0) for r in results.values() if isinstance(r, dict))
    
    return {
        "status": "success" if failures == 0 else "partial",
        "trackers_processed": len(MARKET_TRACKERS),
        "succeeded": successes,
        "failed": failures,
        "total_records": total_records,
        "results": results,
    }


@router.post("/seed")
async def seed_trackers(
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Seed or update the market tracker metadata table."""
    count = await seed_market_tracker_info(session)
    return {"status": "success", "trackers_seeded": count}
