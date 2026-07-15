"""Watchlist configuration — single source of truth for watchlist defaults and limits."""


DEFAULT_TICKERS: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",
    "SPY", "QQQ", "IWM", "AMD", "NFLX", "JPM", "V", "DIS",
]

MAX_WATCHLIST_SIZE: int = 100

CONFIG_VERSION: int = 1
