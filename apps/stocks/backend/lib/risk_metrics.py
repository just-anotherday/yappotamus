"""
Risk Metrics Engine - Improved Risk Measurement for Stock Analysis

This module provides comprehensive risk metrics including:
- Data Validation (NaN, outliers)
- Volatility (Annualized, Realized, Historical)
- Value at Risk (VaR) - Parametric and Historical
- Expected Shortfall (CVaR)
- Maximum Drawdown
- Sharpe Ratio
- Sortino Ratio
- Beta vs market benchmarks
- Composite risk scoring (fundamental-based)
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ─── Constants ──────────────────────────────────────────────────────────────
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_DAILY = 0.04 / TRADING_DAYS_PER_YEAR  # ~4% annual risk-free rate


# ─── Legacy Helpers (used by finnhub_service and yfinance_fallback) ─────────

def _safe_pct(numerator: float, denominator: float) -> float:
    """Safely compute a percentage, returning 0.0 on division by zero."""
    if not denominator or denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _compute_composite_risk(
    beta: float,
    short_pct_of_float: float,
    debt_eq: float,
    high52: float,
    low52: float,
    current_price: float,
) -> float:
    """
    Compute a composite fundamental risk score (0-10 scale).

    Factors:
      - Beta: Market sensitivity (from Finnhub analyst estimates)
      - Short %: Short interest pressure on the stock
      - Debt/Equity: Leverage risk
      - 52-week position: How close current price is to 52w high/low range

    Returns a score from 0 (very safe) to 10 (very risky).
    """
    score = 0.0

    # Beta component (weight 30%): 1.0 -> 5, >2.0 -> 10, <0.5 -> 1
    beta_component = min(max((abs(beta) - 0.5) / 2.0 * 10, 0), 10)
    score += beta_component * 0.30

    # Short interest component (weight 25%): 0% -> 0, 20%+ -> 10
    si_component = min(short_pct_of_float / 20.0 * 10, 10)
    score += si_component * 0.25

    # Debt/Equity component (weight 25%): 0 -> 0, 300%+ -> 10
    de_component = min(debt_eq / 300.0 * 10, 10)
    score += de_component * 0.25

    # 52-week range component (weight 20%): near high -> 0, near low -> 10
    if high52 and low52 and high52 != low52:
        range_52 = high52 - low52
        dist_from_high = (high52 - current_price) / range_52 if range_52 > 0 else 0.5
        range_component = max(min(dist_from_high * 10, 10), 0)
    else:
        range_component = 5.0
    score += range_component * 0.20

    return round(min(max(score, 0), 10), 1)


# ─── Data Validation ───────────────────────────────────────────────────────

def validate_price_data(prices: List[float]) -> Tuple[List[float], List[str]]:
    """Validate and clean price data, returning cleaned prices and a list of warnings."""
    warnings: List[str] = []
    if not prices:
        return [], ["No price data provided"]
    
    # Remove NaN/None/Inf values
    clean = [p for p in prices if p is not None and isinstance(p, (int, float)) and math.isfinite(p)]
    removed = len(prices) - len(clean)
    if removed > 0:
        warnings.append(f"Removed {removed} invalid data points (NaN/Inf/None)")
    
    if len(clean) < 2:
        return clean, ["Insufficient data points (need at least 2 for calculations)"]
    
    # Detect outliers using IQR method and cap them
    q1 = np.percentile(clean, 25)
    q3 = np.percentile(clean, 75)
    iqr = q3 - q1
    lower_bound = q1 - 3 * iqr
    upper_bound = q3 + 3 * iqr
    
    outlier_count = sum(1 for p in clean if p < lower_bound or p > upper_bound)
    if outlier_count > 0:
        warnings.append(f"Detected {outlier_count} outliers (capped at IQR bounds)")
        clean = [max(lower_bound, min(upper_bound, p)) for p in clean]
    
    return clean, warnings


# ─── Return Calculations ──────────────────────────────────────────────────

def calculate_returns(prices: List[float]) -> List[float]:
    """Calculate log returns from a list of prices."""
    if len(prices) < 2:
        return []
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] != 0:
            r = math.log(prices[i] / prices[i - 1])
            returns.append(r)
    return returns


# ─── Volatility ───────────────────────────────────────────────────────────

def calculate_volatility(returns: List[float], annualize: bool = True) -> float:
    """Calculate volatility (standard deviation of returns)."""
    if len(returns) < 2:
        return 0.0
    vol = statistics.stdev(returns)
    if annualize:
        vol *= math.sqrt(TRADING_DAYS_PER_YEAR)
    return vol


# ─── Value at Risk (VaR) ──────────────────────────────────────────────────

def calculate_var_parametric(returns: List[float], confidence: float = 0.95) -> float:
    """
    Parametric VaR assuming normal distribution.
    Returns the max expected loss at the given confidence level.
    """
    if len(returns) < 2:
        return 0.0
    
    mean_ret = statistics.mean(returns)
    std_ret = statistics.stdev(returns)
    
    # Z-score for confidence levels
    z_scores = {0.90: 1.28, 0.95: 1.645, 0.99: 2.326}
    z = z_scores.get(confidence, 1.645)
    
    var = mean_ret - z * std_ret
    return abs(var)


def calculate_var_historical(returns: List[float], confidence: float = 0.95) -> float:
    """
    Historical VaR using actual distribution.
    Returns the max expected loss at the given confidence level.
    """
    if len(returns) < 2:
        return 0.0
    
    sorted_returns = sorted(returns)
    idx = int((1 - confidence) * len(sorted_returns))
    idx = max(0, min(idx, len(sorted_returns) - 1))
    return abs(sorted_returns[idx])


# ─── Expected Shortfall (CVaR) ───────────────────────────────────────────

def calculate_cvar(returns: List[float], confidence: float = 0.95) -> float:
    """
    Conditional VaR (Expected Shortfall).
    Average loss beyond the VaR threshold.
    """
    if len(returns) < 2:
        return 0.0
    
    sorted_returns = sorted(returns)
    idx = int((1 - confidence) * len(sorted_returns))
    idx = max(1, min(idx, len(sorted_returns)))
    
    tail = sorted_returns[:idx]
    return abs(statistics.mean(tail))


# ─── Maximum Drawdown ─────────────────────────────────────────────────────

def calculate_max_drawdown(prices: List[float]) -> float:
    """Calculate the maximum drawdown from peak to trough."""
    if len(prices) < 2:
        return 0.0
    
    peak = prices[0]
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    
    return max_dd


# ─── Sharpe Ratio ─────────────────────────────────────────────────────────

def calculate_sharpe_ratio(returns: List[float], risk_free_rate_annual: float = 0.04) -> Optional[float]:
    """Calculate the annualized Sharpe ratio."""
    if len(returns) < 2:
        return None
    
    mean_ret = statistics.mean(returns)
    std_ret = statistics.stdev(returns)
    
    if std_ret == 0:
        return None
    
    rf_daily = risk_free_rate_annual / TRADING_DAYS_PER_YEAR
    excess_return = mean_ret - rf_daily
    
    sharpe = (excess_return / std_ret) * math.sqrt(TRADING_DAYS_PER_YEAR)
    return round(sharpe, 4)


# ─── Sortino Ratio ────────────────────────────────────────────────────────

def calculate_sortino_ratio(returns: List[float], risk_free_rate_annual: float = 0.04) -> Optional[float]:
    """Calculate the annualized Sortino ratio (only penalizes downside volatility)."""
    if len(returns) < 2:
        return None
    
    mean_ret = statistics.mean(returns)
    rf_daily = risk_free_rate_annual / TRADING_DAYS_PER_YEAR
    excess_return = mean_ret - rf_daily
    
    # Downside deviation
    downside = [r for r in returns if r < 0]
    if not downside:
        return None
    
    downside_sq = [r ** 2 for r in downside]
    downside_dev = math.sqrt(sum(downside_sq) / len(returns))
    
    if downside_dev == 0:
        return None
    
    sortino = (excess_return / downside_dev) * math.sqrt(TRADING_DAYS_PER_YEAR)
    return round(sortino, 4)


# ─── Beta ─────────────────────────────────────────────────────────────────

def calculate_beta(asset_returns: List[float], benchmark_returns: List[float]) -> Optional[float]:
    """Calculate Beta of an asset against a benchmark."""
    min_len = min(len(asset_returns), len(benchmark_returns))
    if min_len < 2:
        return None
    
    asset = asset_returns[:min_len]
    bench = benchmark_returns[:min_len]
    
    mean_a = statistics.mean(asset)
    mean_b = statistics.mean(bench)
    
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(asset, bench)) / (min_len - 1)
    var_b = sum((b - mean_b) ** 2 for b in bench) / (min_len - 1)
    
    if var_b == 0:
        return None
    
    return round(cov / var_b, 4)


# ─── Main Risk Analysis Function ──────────────────────────────────────────

def compute_risk_metrics(
    prices: List[float],
    benchmark_prices: Optional[List[float]] = None,
    confidence: float = 0.95,
    rf_rate: float = 0.04,
) -> Dict[str, Any]:
    """
    Compute all risk metrics for a given price series.

    Returns:
        Dictionary with all computed risk metrics and data quality info.
    """
    # Validate
    clean_prices, data_warnings = validate_price_data(prices)
    
    if len(clean_prices) < 2:
        return {
            "error": True,
            "message": "Insufficient valid data for risk calculation",
            "warnings": data_warnings,
        }

    returns = calculate_returns(clean_prices)

    # Core metrics
    volatility = calculate_volatility(returns, annualize=True)
    max_dd = calculate_max_drawdown(clean_prices)
    var_parametric = calculate_var_parametric(returns, confidence)
    var_historical = calculate_var_historical(returns, confidence)
    cvar = calculate_cvar(returns, confidence)
    sharpe = calculate_sharpe_ratio(returns, rf_rate)
    sortino = calculate_sortino_ratio(returns, rf_rate)

    # Build result (keys aligned with frontend expectations)
    result: Dict[str, Any] = {
        "error": False,
        "warnings": data_warnings,
        "data_points": len(clean_prices),
        # Volatility
        "volatility_annualized": round(volatility * 100, 2),
        # Drawdown
        "max_drawdown_pct": round(max_dd * 100, 2),
        # VaR (use parametric as primary)
        "var_95": round(var_parametric * 100, 4),
        # CVaR / Expected Shortfall
        "cvar_95": round(cvar * 100, 4),
        # Risk-adjusted returns
        "sharpe_ratio": sharpe if sharpe is not None else 0.0,
        "sortino_ratio": sortino if sortino is not None else 0.0,
        # Benchmark (filled below)
        "beta": None,
        "alpha": None,
    }

    # Beta + Alpha (requires benchmark data)
    if benchmark_prices:
        bench_clean, _ = validate_price_data(benchmark_prices)
        bench_returns = calculate_returns(bench_clean)
        beta = calculate_beta(returns, bench_returns)
        result["beta"] = beta

        # Alpha = excess return of asset over what CAPM predicts
        if beta is not None and len(returns) > 0:
            asset_annual_return = statistics.mean(returns) * TRADING_DAYS_PER_YEAR
            bench_annual_return = statistics.mean(bench_returns) * TRADING_DAYS_PER_YEAR if bench_returns else 0.0
            expected_return = RISK_FREE_RATE_DAILY * TRADING_DAYS_PER_YEAR + beta * (bench_annual_return - RISK_FREE_RATE_DAILY * TRADING_DAYS_PER_YEAR)
            alpha = asset_annual_return - expected_return
            result["alpha"] = round(alpha * 100, 2)

    return result
