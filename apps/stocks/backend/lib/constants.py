# lib/constants.py
"""
Shared constants used across multiple service modules.
"""


KNOWN_NON_STOCK_SYMBOLS: set[str] = {
    "SPY", "QQQ", "VOO", "IWM", "DIA",
    "VWO", "VEA", "VGT", "XLK", "XLF", "SPCX",
}


__all__ = [
    "KNOWN_NON_STOCK_SYMBOLS",
]
