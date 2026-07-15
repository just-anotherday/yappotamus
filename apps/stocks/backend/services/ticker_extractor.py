"""
Ticker Extraction Service — Lightweight NLP to extract tickers from article text.

Uses pattern matching (regex + company-to-ticker lookup) rather than expensive LLM calls.
This runs during ingestion so we can immediately link articles to companies before
queuing AI enrichment.

Architecture:
    Article collected → extract_tickers() → queue company report updates
"""

import re
from typing import Set, List


class TickerExtractor:
    """
    Extracts ticker symbols from article text using pattern matching.

    Strategy:
    1. Known company-to-ticker dictionary (~500 most-covered companies)
    2. Regex patterns for common formats: "$AAPL", "AAPL", "(AAPL)"
    3. Acronym detection against known ticker list
    """

    # Company name → primary ticker mapping (partial; extendable from Finnhub/DB)
    COMPANY_TICKER_MAP = {
        # Big Tech
        "apple": "AAPL",
        "microsoft": "MSFT",
        "google": "GOOGL",
        "alphabet": "GOOGL",
        "amazon": "AMZN",
        "meta": "META",
        "netflix": "NFLX",
        "tesla": "TSLA",
        "nvidia": "NVDA",
        "amd": "AMD",
        "ibm": "IBM",
        "oracle": "ORCL",
        "salesforce": "CRM",
        "adobe": "ADBE",
        "cisco": "CSCO",
        "qualcomm": "QCOM",
        "intel": "INTC",
        "tsmc": "TSM",

        # Finance
        "jpmorgan": "JPM",
        "j.p. morgan": "JPM",
        "bank of america": "BAC",
        "bofa": "BAC",
        "goldman sachs": "GS",
        "morgan stanley": "MS",
        "wells fargo": "WFC",
        "citigroup": "C",
        "citi": "C",
        "blackrock": "BLK",

        # Healthcare
        "johnson & johnson": "JNJ",
        "j&j": "JNJ",
        "pfizer": "PFE",
        "moderna": "MRNA",
        "unitedhealth": "UNH",
        "merck": "MRK",
        "abbvie": "ABBV",
        "gilead": "GILD",

        # Energy
        "exxonmobil": "XOM",
        "chevron": "CVX",
        "conocoPhillips": "COP",

        # Consumer / Retail
        "walmart": "WMT",
        "coca-cola": "KO",
        "pepsi": "PEP",
        "mcdonalds": "MCD",
        "starbucks": "SBUX",
        "nike": "NKE",
        "target": "TGT",

        # Defense / Aerospace
        "lockheed martin": "LMT",
        "boeing": "BA",
        "raytheon": "RTX",

        # Crypto (for reference)
        "bitcoin": "BTC-USD",
    }

    # Common ticker patterns in text
    TICKER_PATTERNS = [
        re.compile(r'\$([A-Z]{1,5})\b'),           # $AAPL
        re.compile(r'\(([A-Z]{1,5})\)\b'),          # (AAPL)
        re.compile(r'\b[A-Z][A-Z]{2,4}\s*(?:stock|shares|shrs|corp|inc\.?)\b'),  # AAPL Corp
    ]

    def __init__(self):
        self._ticker_cache = None

    async def load_tickers_from_db(self, db_session):
        """Load all active asset tickers from the database for matching."""
        try:
            from sqlalchemy import select
            from backend.models.asset import AssetTicker
            result = await db_session.execute(
                select(AssetTicker.ticker).where(
                    AssetTicker.active_to.is_(None)
                )
            )
            self._ticker_cache = set(row[0].upper() for row in result.all())
        except Exception:
            # Fallback to empty set if table doesn't exist yet (pre-migration)
            self._ticker_cache = set()

    def extract(self, text: str, title: str = "") -> Set[str]:
        """
        Extract ticker symbols from article text and title.
        Returns a set of uppercase ticker strings.
        """
        if not text:
            return set()

        found_tickers: Set[str] = set()

        # Combine title + text for matching (title often has the company name)
        combined = f"{title} {text}".lower()
        original_combined = f"{title} {text}"

        # Strategy 1: Company name → ticker lookup
        for company_name, ticker in self.COMPANY_TICKER_MAP.items():
            if company_name in combined:
                found_tickers.add(ticker)

        # Strategy 2: Pattern matching ($AAPL, (AAPL), AAPL Corp)
        for pattern in self.TICKER_PATTERNS:
            matches = pattern.findall(original_combined)
            for match in matches:
                candidate = match.upper()
                # Only include if it's a known ticker or matches common patterns
                if len(candidate) <= 5 and candidate.isalpha():
                    found_tickers.add(candidate)

        # Strategy 3: Cross-reference with known tickers (if loaded from DB)
        if self._ticker_cache:
            for ticker in self._ticker_cache:
                if ticker.lower() in combined:
                    found_tickers.add(ticker)

        return found_tickers


# Singleton instance
ticker_extractor = TickerExtractor()
