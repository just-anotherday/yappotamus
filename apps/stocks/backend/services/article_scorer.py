"""
Article Relevance Scorer

Ranks news articles by relevance to a specific ticker so the AI worker
can feed the LLM the most important articles instead of just the newest ones.

Scoring factors:
  1. Ticker in title (high signal)
  2. Ticker in summary/body
  3. Article has meaningful summary text
  4. Recency (exponential decay)
  5. Source quality weight
"""

import math
import re
from datetime import datetime, timedelta
from typing import List, Optional

from backend.models.news import NewsArticle


# Higher-weight sources are more editorially curated or directly from the company.
_SOURCE_WEIGHTS = {
    "reuters": 1.3,
    "bloomberg": 1.3,
    "cnbc": 1.2,
    "marketwatch": 1.2,
    "wall street journal": 1.3,
    "financial times": 1.3,
    "barrons": 1.2,
    "benzinga": 1.1,
    "yahoo finance": 1.0,
    "business insider": 1.0,
    "the verge": 0.9,
    "techcrunch": 1.0,
}


def _source_multiplier(provider_name: Optional[str]) -> float:
    """Return a quality multiplier based on the article's source."""
    if not provider_name:
        return 0.8
    lower = provider_name.lower()
    for keyword, weight in _SOURCE_WEIGHTS.items():
        if keyword in lower:
            return weight
    return 1.0  # unknown sources get neutral weight


def score_article(article: NewsArticle, ticker: str, now: datetime) -> float:
    """Score a single article for relevance to the given ticker.

    Returns a float (higher = more relevant).
    """
    score = 0.0

    # --- Recency (exponential decay) ---
    if article.pub_date:
        age_hours = (now - article.pub_date).total_seconds() / 3600
        # Half-life of ~48 hours: an article is worth half as much after 2 days
        recency_score = 20.0 * math.exp(-math.log(2) * age_hours / 48)
    else:
        recency_score = 5.0  # unknown age gets a low baseline

    score += recency_score

    # --- Ticker in title (strong signal) ---
    title = article.title or ""
    if re.search(r'\b' + re.escape(ticker) + r'\b', title, re.IGNORECASE):
        score += 25.0

    # --- Ticker in summary ---
    summary = article.summary or ""
    ticker_count = len(re.findall(r'\b' + re.escape(ticker) + r'\b', summary, re.IGNORECASE))
    if ticker_count > 0:
        # Diminishing returns after the first few mentions
        score += min(15.0, ticker_count * 5.0)

    # --- Has meaningful summary ---
    if summary and len(summary.strip()) > 50:
        score += 8.0
    elif summary and len(summary.strip()) > 0:
        score += 3.0

    # --- Source quality multiplier applied to total ---
    multiplier = _source_multiplier(article.provider_name)

    return round(score * multiplier, 2)


def rank_articles(articles: List[NewsArticle], ticker: str, now: Optional[datetime] = None) -> List[NewsArticle]:
    """Sort articles by relevance score (descending). Returns a new list."""
    if not now:
        now = datetime.utcnow()

    scored = [(score_article(a, ticker, now), a) for a in articles]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored]
