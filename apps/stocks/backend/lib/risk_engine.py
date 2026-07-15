"""
Enhanced Risk Engine — replaces the static composite risk score with proper 
time-series metrics (volatility, VaR, drawdown, momentum) derived from 
historical OHLCV data.

Provides per-factor scores (0-10 scale), composite signals with configurable 
buy/sell thresholds, and market regime adjustments.
"""

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    """Clamp a value to [lo, hi] (default 0-10 scale for all risk factor scores)."""
    return max(lo, min(hi, value))


def _log_returns(prices: List[float]) -> List[float]:
    """Compute daily log returns from a list of close prices."""
    returns = []
    for i in range(1, len(prices)):
        if prices[i] > 0 and prices[i - 1] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))
        else:
            returns.append(0.0)
    return returns


def _std_dev(values: List[float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


# ---------------------------------------------------------------------------
# Volatility Metrics
# ---------------------------------------------------------------------------

def historical_volatility(prices: List[float], window: Optional[int] = None, annualize: bool = True) -> float:
    """
    Calculate annualized historical volatility from close prices.
    
    Args:
        prices: List of daily close prices (oldest first).
        window: Optional lookback window in trading days. Uses all data if None.
        annualize: If True, multiply by sqrt(252) for annualized vol.
    
    Returns:
        Annualized volatility as a percentage (e.g., 20.0 means 20%).
    """
    if len(prices) < 2:
        return 0.0
    
    if window and window < len(prices):
        prices = prices[-window:]
    
    returns = _log_returns(prices)
    daily_vol = _std_dev(returns)
    
    if annualize:
        return round(daily_vol * math.sqrt(252) * 100, 2)
    return round(daily_vol * 100, 4)


def realized_volatility_ratio(prices: List[float], short_window: int = 30, long_window: int = 252) -> float:
    """
    Compare recent (30d) volatility to long-term (252d) average volatility.
    
    Returns ratio: 1.0 = normal, <1.0 = calmer than usual, >1.0 = more volatile.
    """
    if len(prices) < short_window + 5:
        return 1.0  # not enough data, assume normal
    
    short_vol = historical_volatility(prices, window=short_window)
    long_vol = historical_volatility(prices, window=long_window)
    
    if long_vol == 0:
        return 1.0
    
    return round(short_vol / long_vol, 4)


# ---------------------------------------------------------------------------
# Downside Risk Metrics
# ---------------------------------------------------------------------------

def value_at_var(prices: List[float], confidence: float = 0.95, horizon: int = 1) -> float:
    """
    Parametric Value at Risk — expected max loss over `horizon` days 
    at given confidence level.
    
    Returns VaR as a percentage of current price (e.g., 2.5 means 2.5% loss).
    """
    if len(prices) < 10:
        return 0.0
    
    returns = _log_returns(prices)
    mean_ret = sum(returns) / len(returns)
    std_ret = _std_dev(returns)
    
    # Z-scores for common confidence levels
    z_scores = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
    z = z_scores.get(confidence, 1.645)
    
    var = (mean_ret - z * std_ret) * math.sqrt(horizon)
    return round(abs(var) * 100, 2)


def expected_shortfall(prices: List[float], confidence: float = 0.95) -> float:
    """
    Conditional VaR (Expected Shortfall) — average loss given we are 
    in the worst (1-confidence)% of outcomes. More tail-robust than VaR.
    """
    if len(prices) < 10:
        return 0.0
    
    returns = _log_returns(prices)
    sorted_ret = sorted(returns)
    tail_count = max(1, int(len(sorted_ret) * (1 - confidence)))
    tail_losses = sorted_ret[:tail_count]
    
    avg_tail_loss = sum(tail_losses) / len(tail_losses)
    return round(abs(avg_tail_loss) * 100, 2)


def max_drawdown(prices: List[float]) -> float:
    """
    Maximum drawdown — worst peak-to-trough decline observed.
    Returns as a percentage (e.g., 15.0 means 15% peak-to-trough loss).
    """
    if not prices:
        return 0.0
    
    peak = prices[0]
    max_dd = 0.0
    
    for price in prices:
        if price > peak:
            peak = price
        dd = (peak - price) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    return round(max_dd, 2)


# ---------------------------------------------------------------------------
# Momentum Metrics
# ---------------------------------------------------------------------------

def momentum_score(prices: List[float], lookback_days: int = 20) -> float:
    """
    Rate of change over lookback period as a percentage.
    Positive = uptrend, Negative = downtrend.
    """
    if len(prices) < lookback_days + 1:
        return 0.0
    
    old_price = prices[-lookback_days - 1]
    new_price = prices[-1]
    
    if old_price == 0:
        return 0.0
    
    return round((new_price - old_price) / old_price * 100, 2)


def trend_direction(prices: List[float], short_days: int = 5, long_days: int = 20) -> str:
    """
    Determine trend direction based on short and long term momentum.
    Returns: "STRONG_UP", "UP", "SIDEWAYS", "DOWN", "STRONG_DOWN"
    """
    short_mom = momentum_score(prices, short_days)
    long_mom = momentum_score(prices, long_days)
    
    if short_mom > 3 and long_mom > 5:
        return "STRONG_UP"
    elif short_mom > 0 and long_mom > 0:
        return "UP"
    elif abs(short_mom) <= 2 and abs(long_mom) <= 3:
        return "SIDEWAYS"
    elif short_mom < -3 or long_mom < -5:
        return "STRONG_DOWN"
    else:
        return "DOWN"


# ---------------------------------------------------------------------------
# Additional Modern Risk Metrics
# ---------------------------------------------------------------------------

def value_at_risk_historical(prices: List[float], confidence: float = 0.95) -> float:
    """
    Historical (non-parametric) Value at Risk using actual return distribution.
    Does not assume normal distribution, more accurate for fat-tailed assets.
    Returns VaR as a percentage (e.g., 2.5 means 2.5% loss).
    """
    if len(prices) < 10:
        return 0.0

    returns = _log_returns(prices)
    sorted_ret = sorted(returns)
    idx = max(0, int((1 - confidence) * len(sorted_ret)))
    return round(abs(sorted_ret[idx]) * 100, 2)


def sharpe_ratio(prices: List[float], risk_free_rate_annual: float = 0.04) -> Optional[float]:
    """
    Annualized Sharpe ratio: (mean excess return) / volatility.
    Higher = better risk-adjusted performance.
    """
    if len(prices) < 10:
        return None

    returns = _log_returns(prices)
    mean_ret = sum(returns) / len(returns)
    std_ret = _std_dev(returns)

    if std_ret == 0:
        return None

    rf_daily = risk_free_rate_annual / 252.0
    excess = mean_ret - rf_daily
    sharpe = (excess / std_ret) * math.sqrt(252)
    return round(sharpe, 4)


def sortino_ratio(prices: List[float], risk_free_rate_annual: float = 0.04) -> Optional[float]:
    """
    Annualized Sortino ratio: penalizes only downside volatility.
    Higher = better risk-adjusted performance (downside-focused).
    """
    if len(prices) < 10:
        return None

    returns = _log_returns(prices)
    mean_ret = sum(returns) / len(returns)
    rf_daily = risk_free_rate_annual / 252.0
    excess = mean_ret - rf_daily

    downside = [r for r in returns if r < 0]
    if not downside:
        return None

    downside_sq = [r ** 2 for r in downside]
    downside_dev = math.sqrt(sum(downside_sq) / len(returns))

    if downside_dev == 0:
        return None

    sortino = (excess / downside_dev) * math.sqrt(252)
    return round(sortino, 4)


def beta_coefficient(asset_prices: List[float], benchmark_prices: List[float]) -> Optional[float]:
    """
    Beta of an asset vs a benchmark (e.g., SPY).
    >1 = more volatile than market, <1 = less volatile.
    """
    min_len = min(len(asset_prices), len(benchmark_prices))
    if min_len < 10:
        return None

    asset_ret = _log_returns(asset_prices)[:min_len - 1]
    bench_ret = _log_returns(benchmark_prices)[:min_len - 1]

    actual = min(len(asset_ret), len(bench_ret))
    if actual < 2:
        return None

    asset_ret = asset_ret[:actual]
    bench_ret = bench_ret[:actual]

    mean_a = sum(asset_ret) / actual
    mean_b = sum(bench_ret) / actual

    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(asset_ret, bench_ret)) / (actual - 1)
    var_b = sum((b - mean_b) ** 2 for b in bench_ret) / (actual - 1)

    if var_b == 0:
        return None

    return round(cov / var_b, 4)


# ---------------------------------------------------------------------------
# Factor Scoring (0-10 scale per factor)
# ---------------------------------------------------------------------------

def _score_volatility(prices: List[float]) -> Dict[str, Any]:
    """Volatility factor score. Lower = more stable = better for buying.
    
    Calibrated for broad market ETFs (SPY/QQQ/IWM/DIA) where realized volatility
    ratios typically range from 0.7 to 1.8."""
    ratio = realized_volatility_ratio(prices)
    
    # Tightened range: 0.7 (very calm) → score 0; 1.8 (turbulent) → score 10
    score = _clamp((ratio - 0.7) / 1.1 * 10)
    
    if score <= 2:
        label = "Low — Calmer than usual"
    elif score <= 4:
        label = "Moderate-Low — Near normal levels"
    elif score <= 6:
        label = "Moderate — Normal volatility"
    elif score <= 8:
        label = "Elevated — More volatile than usual"
    else:
        label = "High — Unusually unstable"
    
    return {
        "score": round(score, 1),
        "label": label,
        "detail": f"30d vol is {ratio:.2f}× the yearly average",
        "raw_ratio": round(ratio, 4),
    }


def _score_momentum(prices: List[float]) -> Dict[str, Any]:
    """Momentum factor score. Lower = not falling sharply = better for buying.
    
    Calibrated for broad market ETFs where 20d momentum typically ranges -10% to +10%."""
    mom_20d = momentum_score(prices, 20)
    mom_5d = momentum_score(prices, 5)
    
    # Negative momentum (falling price) → higher risk score
    combined_mom = (mom_20d * 0.7 + mom_5d * 0.3)
    
    # Tightened range: -10% → score 10; +10% → score 0
    score = _clamp((-combined_mom + 10) / 20 * 10)
    
    if score <= 2:
        label = "Strong Uptrend — Price rising steadily"
    elif score <= 4:
        label = "Mild Uptrend — Moderate gains"
    elif score <= 6:
        label = "Flat / Mixed — No clear direction"
    elif score <= 8:
        label = "Declining — Price dropping"
    else:
        label = "Sharp Decline — High risk"
    
    return {
        "score": round(score, 1),
        "label": label,
        "detail": f"5d: {mom_5d:+.2f}% | 20d: {mom_20d:+.2f}%",
        "momentum_5d": round(mom_5d, 2),
        "momentum_20d": round(mom_20d, 2),
    }


def _score_var(prices: List[float]) -> Dict[str, Any]:
    """Value-at-Risk factor score. Lower VaR = lower risk = better for buying.
    
    Calibrated for broad market ETFs where 95% daily VaR typically ranges 0.2%-3%."""
    var_95 = value_at_var(prices, confidence=0.95)
    
    # Tightened range: 0.2% → score 1; 3% → score 10
    score = _clamp((var_95 - 0.2) / 2.8 * 10)
    
    if score <= 2:
        label = "Low — Minimal downside risk"
    elif score <= 4:
        label = "Moderate-Low — Manageable VaR"
    elif score <= 6:
        label = "Moderate — Normal tail risk"
    else:
        label = "High — Significant potential daily loss"
    
    return {
        "score": round(score, 1),
        "label": label,
        "detail": f"95% VaR: {var_95:.2f}% daily max loss expected",
        "raw_var": round(var_95, 2),
    }


def _score_drawdown(prices: List[float]) -> Dict[str, Any]:
    """Max drawdown factor score. Lower = recovered well from dips.
    
    Calibrated for broad market ETFs where 500-day max drawdown typically ranges 0%-25%."""
    md = max_drawdown(prices)
    
    # Tightened range: 0% → score 0; 25% → score 10
    score = _clamp(md / 25.0 * 10)
    
    if score <= 2:
        label = "Tight — Minimal drawdowns"
    elif score <= 4:
        label = "Low-Moderate — Small corrections"
    elif score <= 6:
        label = "Moderate — Typical market corrections"
    else:
        label = "Deep — Significant peak-to-trough losses"
    
    return {
        "score": round(score, 1),
        "label": label,
        "detail": f"Worst drawdown: {md:.2f}% peak-to-trough",
        "raw_drawdown": round(md, 2),
    }


# ---------------------------------------------------------------------------
# Composite Risk Signal
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "volatility": 0.25,
    "momentum": 0.30,   # momentum is the biggest buy/sell timing signal
    "var": 0.20,
    "drawdown": 0.25,
}


def compute_risk_signal(
    prices: List[float],
    weights: Optional[Dict[str, float]] = None,
    buy_threshold: float = 3.5,
    sell_threshold: float = 7.0,
    short_interest_pct: Optional[float] = None,
    debt_to_equity: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute the full risk signal for an asset based on price history.
    
    Args:
        prices: List of daily close prices (oldest first).
        weights: Factor weights dict. Uses DEFAULT_WEIGHTS if None.
        buy_threshold: Composite score below this → BUY signal.
        sell_threshold: Composite score above this → SELL signal.
        short_interest_pct: Optional short % of float for additional scoring.
        debt_to_equity: Optional debt-to-equity ratio for additional scoring.
    
    Returns:
        Full signal dict with composite score, band, factors, etc.
    """
    w = weights or DEFAULT_WEIGHTS
    
    # Compute factor scores
    vol = _score_volatility(prices)
    mom = _score_momentum(prices)
    var_s = _score_var(prices)
    dd = _score_drawdown(prices)
    
    factors = {
        "volatility": vol,
        "momentum": mom,
        "var": var_s,
        "drawdown": dd,
    }
    
    # Additional fundamental factors if available
    if short_interest_pct is not None:
        # Normalize: 0% → score 1; 20%+ → score 10
        si_score = _clamp(short_interest_pct / 0.20 * 10)
        factors["short_interest"] = {
            "score": round(si_score, 1),
            "label": "Low pressure" if si_score < 4 else "High short interest",
            "detail": f"{short_interest_pct:.2f}% of float held short",
        }
        # Adjust weights to include this factor
        total_w = sum(w.values()) + 0.15
        w = {k: v / total_w for k, v in w.items()}
        w["short_interest"] = 0.15 / total_w
    
    if debt_to_equity is not None:
        de_score = _clamp(debt_to_equity / 300.0 * 10)
        factors["debt_risk"] = {
            "score": round(de_score, 1),
            "label": "Manageable" if de_score < 5 else "High leverage",
            "detail": f"Debt/Equity: {debt_to_equity:.1f}%",
        }
        total_w = sum(w.values()) + 0.15
        w = {k: v / total_w for k, v in w.items()}
        w["debt_risk"] = 0.15 / total_w
    
    # Weighted composite score
    composite = sum(f["score"] * w.get(k, 0) for k, f in factors.items())
    composite = round(min(composite, 10.0), 1)
    
    # Determine signal band
    if composite <= buy_threshold:
        band = "BUY-ZONE"
        signal = "BUY"
    elif composite <= (buy_threshold + sell_threshold) / 2:
        band = "MODERATE"
        signal = "HOLD"
    elif composite <= sell_threshold:
        band = "CAUTION"
        signal = "CAUTION"
    else:
        band = "SELL-ZONE"
        signal = "SELL"
    
    # Identify dominant risk factor (highest score among core 4)
    core_factors = {k: v for k, v in factors.items() if k in DEFAULT_WEIGHTS}
    dominant = max(core_factors, key=lambda k: core_factors[k]["score"])
    
    # Compute trend direction
    td = trend_direction(prices) if len(prices) >= 25 else "SIDEWAYS"
    
    return {
        "score": composite,
        "band": band,
        "signal": signal,
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "dominant_risk_factor": dominant,
        "trend_direction": td,
        "factors": factors,
        "weights": {k: round(v, 4) for k, v in w.items()},
    }


def apply_market_regime_adjustment(signal: Dict[str, Any], regime: str) -> Dict[str, Any]:
    """
    Adjust risk signal based on current market regime.
    
    Args:
        signal: Output from compute_risk_signal().
        regime: "BULLISH", "NEUTRAL", or "BEARISH".
    
    Returns:
        Modified signal dict with adjusted score.
    """
    adjustments = {
        "BULLISH": -0.5,   # Bullish market reduces effective risk
        "NEUTRAL": 0.0,
        "BEARISH": +1.0,   # Bearish market increases effective risk
    }
    
    adj = adjustments.get(regime, 0.0)
    original_score = signal["score"]
    adjusted_score = round(max(0, min(10, original_score + adj)), 1)
    
    signal["original_score"] = original_score
    signal["market_regime"] = regime
    signal["regime_adjustment"] = adj
    signal["score"] = adjusted_score
    
    # Re-determine band based on adjusted score
    bt = signal["buy_threshold"]
    st = signal["sell_threshold"]
    
    if adjusted_score <= bt:
        signal["band"] = "BUY-ZONE"
        signal["signal"] = "BUY"
    elif adjusted_score <= (bt + st) / 2:
        signal["band"] = "MODERATE"
        signal["signal"] = "HOLD"
    elif adjusted_score <= st:
        signal["band"] = "CAUTION"
        signal["signal"] = "CAUTION"
    else:
        signal["band"] = "SELL-ZONE"
        signal["signal"] = "SELL"
    
    return signal


__all__ = [
    "historical_volatility",
    "realized_volatility_ratio",
    "value_at_var",
    "expected_shortfall",
    "max_drawdown",
    "momentum_score",
    "trend_direction",
    "compute_risk_signal",
    "apply_market_regime_adjustment",
]
