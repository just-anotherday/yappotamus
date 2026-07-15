"""Shared ticker normalization utilities."""

import re


def normalize_ticker(ticker: str) -> str:
    """Normalize a ticker symbol to uppercase, stripped of whitespace.

    Raises:
        ValueError: If the ticker contains invalid characters.
    """
    if not isinstance(ticker, str):
        raise ValueError("Ticker must be a string")

    cleaned = ticker.strip().upper()

    # Validate: only alphanumeric characters, length 1-10
    if not cleaned or len(cleaned) > 10:
        raise ValueError(f"Invalid ticker length: '{cleaned}' (must be 1-10 characters)")

    if not re.match(r'^[A-Z0-9]+$', cleaned):
        raise ValueError(f"Invalid ticker format: '{cleaned}' (only uppercase letters and digits allowed)")

    return cleaned


def validate_ticker(ticker: str) -> bool:
    """Check whether a string is a valid ticker symbol without normalizing."""
    try:
        normalize_ticker(ticker)
        return True
    except ValueError:
        return False


def deduplicate_tickers(tickers: list[str]) -> list[str]:
    """Remove duplicate tickers while preserving original order.

    Compares uppercase versions for deduplication but returns the original
    casing of the first occurrence.
    """
    seen: set[str] = set()
    unique: list[str] = []
    for t in tickers:
        key = t.upper()
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


__all__ = [
    "normalize_ticker",
    "validate_ticker",
    "deduplicate_tickers",
]
