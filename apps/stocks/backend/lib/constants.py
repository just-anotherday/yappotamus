# lib/constants.py
"""
Shared constants used across multiple service modules.
"""


KNOWN_NON_STOCK_SYMBOLS: set[str] = {
    "SPY", "QQQ", "VOO", "IWM", "DIA",
    "VWO", "VEA", "VGT", "XLK", "XLF",
}

KNOWN_ETF_NAMES: dict[str, str] = {
    "SPY": "State Street SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "VOO": "Vanguard S&P 500 ETF",
    "IWM": "iShares Russell 2000 ETF",
    "DIA": "State Street SPDR Dow Jones Industrial Average ETF Trust",
    "VWO": "Vanguard FTSE Emerging Markets ETF",
    "VEA": "Vanguard FTSE Developed Markets ETF",
    "VGT": "Vanguard Information Technology ETF",
    "XLK": "Technology Select Sector SPDR Fund",
    "XLF": "Financial Select Sector SPDR Fund",
}


__all__ = [
    "KNOWN_NON_STOCK_SYMBOLS",
    "KNOWN_ETF_NAMES",
]
