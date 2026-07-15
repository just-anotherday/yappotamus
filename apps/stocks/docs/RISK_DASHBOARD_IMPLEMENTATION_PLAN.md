# Risk Dashboard & Market Regime System — Implementation Plan

## Overview

This document outlines the complete implementation of a new risk-based buy/sell signal system replacing the current static composite risk score. The system includes per-asset risk signals with configurable buy/sell thresholds and a market regime dashboard tracking SPY, QQQ, RUT, and DIA.

---

## Current State

### Existing Risk System (`backend/lib/risk_metrics.py`)
```python
Risk (0–10) = 10 × (0.25×βₙ + 0.25×ShortFloatₙ + 0.25×DebtEqₙ + 0.25×Volatilityₙ)
```
- Static snapshot computed at data fetch time
- Hard-coded normalization divisors with no empirical basis
- Volatility proxy: `(high52 - low52) / current_price` (not true volatility)
- No buy/sell signal boundaries
- No market regime context

### Data Storage
- No historical daily OHLCV price data stored
- Only point-in-time price snapshots from Finnhub/yFinance
- Database: SQLite via SQLAlchemy with Alembic migrations

---

## Target Architecture

### 1. Market Regime Dashboard (`/markets`)

#### Four Index Trackers
| Ticker | Coverage | What It Measures |
|--------|----------|------------------|
| **SPY** | S&P 500 (large cap) | Broad market direction, overall economy |
| **QQQ** | Nasdaq-100 (growth/tech) | Growth stock sentiment, interest rate sensitivity |
| **RUT** | Russell 2000 (small cap) | Domestic economy, small business health |
| **DIA** | Dow Jones (blue chip) | Established company stability |

#### Market Condition Logic
```python
def assess_market_regime(spy_trend, qqq_trend, rut_trend, dia_trend):
    # Scoring based on alignment of the 4 indicators
    green_count = sum(1 for t in [spy, qqq, rut, dia] if t == "UP")
    
    if green_count >= 3:
        return "BULLISH"      # Favorable conditions for buying
    elif green_count == 2:
        return "NEUTRAL"      # Mixed signals, selective buying
    else:
        return "BEARISH"      # Risk-off, reduce exposure
```

#### S&P 500 Sector Breakdown
Display current sector allocation percentages (Technology, Healthcare, Financials, etc.) with color-coded trend indicators.

---

### 2. Price History System

#### Database Model (`backend/models/price_history.py`)
```python
class DailyOHLCV(Base):
    __tablename__ = "daily_ohlcv"
    
    id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False, unique=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(BigInteger)
    adjusted_close = Column(Float)
```

#### Data Population
- Use yFinance `Ticker.history(period="2y")` to fetch historical data
- Populate via migration script on first deployment
- Daily refresh job to keep current

---

### 3. Enhanced Risk Signal Engine (`backend/lib/risk_engine.py`)

#### Factor-Based Scoring (0-10 scale per factor)

| Factor | Calculation | Buy Signal When... |
|--------|-------------|-------------------|
| **Volatility** | 30d realized vol / 1-yr avg vol × 10 | Score < 4 (lower than normal) |
| **Momentum** | -20d return % normalized to 0-10 | Score < 5 (not in sharp decline) |
| **Short Interest** | short% of float / 20% × 10 | Score < 5 (low pressure) |
| **Debt Risk** | debt-to-equity / 3.0 × 10 | Score < 6 (manageable leverage) |

#### Signal Output Structure
```python
{
    "score": 4.2,                    # Composite weighted score (0-10)
    "band": "MODERATE",              # BUY-ZONE / MODERATE / CAUTION / SELL-ZONE
    "buy_threshold": 3.5,           # User-configurable
    "sell_threshold": 7.0,          # User-configurable  
    "signal": "HOLD",               # BUY / HOLD / CAUTION / SELL
    "dominant_risk_factor": "momentum",
    "factors": {
        "volatility": {"score": 3.8, "label": "Normal"},
        "momentum": {"score": 5.2, "label": "Declining"},
        "short_interest": {"score": 4.1, "label": "Moderate"},
        "debt_risk": {"score": 3.0, "label": "Low"}
    },
    "market_regime_adjustment": -0.5 # Bullish market reduces effective risk score
}
```

---

### 4. Frontend Implementation

#### New Pages
| Route | Purpose |
|-------|---------|
| `/markets` | Main market regime dashboard with 4 ETF cards and S&P 500 sectors |
| `/markets/{ticker}` | Detailed view for SPY/QQQ/RUT/DIA with constituent tickers, news, price history charts |

#### Market Card Components (Replaces IntelligenceCard)
- **Header**: Ticker + full name + description
- **Status Bar**: Green/Yellow/Red indicator with score and signal band
- **Price Info**: Current price, daily change, 52-week context
- **Factor Breakdown**: Horizontal bars showing each risk factor's contribution
- **Market Context**: How this tracker's trend affects buy/sell decisions
- **Sector Ticker Grid**: 6-8 key tickers from sectors with their mini-status indicators

#### Enhanced Risk Display (Per-asset pages)
- Current score gauge visualization
- Signal badge (BUY/HOLD/CAUTION/SELL)
- Factor breakdown with explanations
- Market regime overlay effect on the signal

---

## Implementation Steps

### Phase 1: Backend Foundation
1. Create `price_history` database model and Alembic migration
2. Build price history population script using yFinance 
3. Create new `risk_engine.py` replacing `risk_metrics.py`
4. Add market regime assessment module with SPY/QQQ/RUT/DIA tracking
5. Update API endpoints to return enhanced risk signals
6. Add S&P 500 sector data endpoint

### Phase 2: Frontend Infrastructure  
1. Create TypeScript types for new data structures
2. Build `/markets` page layout
3. Implement MarketCard component with status indicators
4. Build `/markets/{ticker}` detail pages 
5. Add API calls for market data and sector information

### Phase 3: Integration & Polish
1. Wire market regime adjustment to individual asset risk signals
2. Create visual gauge components for risk scores
3. Add trend indicator animations and color coding
4. Update navigation in AppHeader to include Markets link
5. Test end-to-end flow from data fetching to signal display

---

## File Structure Changes

### New Backend Files
```
backend/models/price_history.py         # DailyOHLCV model
backend/lib/risk_engine.py             # Enhanced risk calculation engine  
backend/lib/market_regime.py           # Market condition assessment logic
backend/services/price_history_service.py  # Price data management service
backend/routers/markets.py            # Market data API endpoints
scripts/populate_price_history.py      # Initial historical data loader
alembic/versions/2026_07_01_add_price_history.py  # Migration
```

### New Frontend Files
```
frontend/app/markets/page.tsx          # Main market dashboard
frontend/app/markets/[ticker]/page.tsx # Individual tracker detail page  
frontend/components/market/MarketCard.tsx    # ETF status card component
frontend/components/market/RiskGauge.tsx     # Visual risk score gauge
frontend/components/market/SectorGrid.tsx    # S&P 500 sector breakdown display
frontend/types/market.ts               # Market data type definitions
```

### Modified Files
```
backend/models/stock.py                # Updated WatchlistItem with enhanced risk structure
backend/lib/risk_metrics.py           # Refactored into risk_engine.py 
frontend/components/AppHeader.tsx      # Add Markets navigation link
backend/routers/watchlist.py          # Integrate new risk signals
backend/services/finnhub_service.py   # Use new risk engine instead of old metrics  
```

---

## Buy/Sell Threshold System

### Configurable Boundaries
Users can adjust thresholds based on risk tolerance:

| Profile | Buy Zone | Sell Zone | Risk Tolerance |
|---------|----------|-----------|----------------|
| Conservative | 0-2.5 | 6.0-10 | Low volatility preference |
| Moderate | 0-3.5 | 7.0-10   | Balanced approach |  
| Aggressive | 0-4.5 | 8.0-10  | Higher risk tolerance |

### Market Regime Modifiers
The system adjusts effective scores based on market conditions:
- **Bullish regime**: -0.5 to all risk scores (more favorable)
- **Neutral regime**: No adjustment  
- **Bearish regime**: +1.0 to all risk scores (more cautious)

---

## Data Flow

```
yFinance Historical Prices → DailyOHLCV Table → Risk Engine
                                    ↓
Finnhub Real-time Quotes → Watchlist Service → Enhanced Signals
                                    ↓                            
Market Trackers (SPY/QQQ/RUT/DIA) → Regime Assessment → Score Adjustment
                                    ↓
                            Frontend Dashboard Display
```

---

## Validation Strategy

1. **Data Coverage**: Ensure all 4 market trackers have 2+ years of price history
2. **Signal Accuracy**: Verify risk signals make logical sense for known market conditions  
3. **Performance**: API response times < 500ms for market data endpoints
4. **UI Consistency**: Status colors match across all components (green=buy, red=sell)

---

## Migration Path

1. Keep existing `risk_metrics.py` as fallback during transition
2. Deploy new system alongside old endpoints initially
3. Update frontend to use new risk signals via feature flag  
4. Remove old implementation after validation period
