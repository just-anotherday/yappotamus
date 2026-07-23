"""Stable article identity and server-authoritative candidate fingerprints."""

from urllib.parse import urlsplit, urlunsplit

from backend.intelligence.hashing import canonical_hash
from backend.intelligence.schemas import ArticleIntelligenceOutput
from backend.maintenance.article_intelligence.contracts import StableArticleIdentity
from backend.models.news import NewsArticle


def normalized_article_url(value: str | None) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def stable_article_identity(article: NewsArticle) -> StableArticleIdentity:
    if article.finnhub_id:
        return StableArticleIdentity(kind="finnhub_id", value=article.finnhub_id.strip())
    normalized_url = normalized_article_url(article.article_url)
    if not normalized_url:
        raise ValueError("article has no stable external identity")
    return StableArticleIdentity(kind="article_url_hash", value=canonical_hash(normalized_url))


def candidate_fingerprint(
    *, stable_identity: StableArticleIdentity, source_content_hash: str,
    prompt_hash: str, input_hash: str, provider: str, model: str,
    output: ArticleIntelligenceOutput,
) -> str:
    return canonical_hash({
        "stable_article_identity": stable_identity.model_dump(mode="json"),
        "source_content_hash": source_content_hash,
        "prompt_hash": prompt_hash,
        "input_hash": input_hash,
        "provider": provider,
        "model": model,
        "output": output.model_dump(mode="json"),
    })