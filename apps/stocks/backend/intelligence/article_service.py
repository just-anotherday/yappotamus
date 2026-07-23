"""Append-only Article Intelligence orchestration and reuse."""

from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.intelligence.composition import build_providers, build_routing_policy
from backend.intelligence.contracts import IntelligenceStage, RoutingRequest, ValidationContext
from backend.intelligence.evaluation import DatabaseEvaluationRecorder
from backend.intelligence.generation import IntelligenceGenerator
from backend.intelligence.hashing import canonical_hash
from backend.intelligence.schemas import ArticleIntelligenceOutput
from backend.intelligence.validation import LayeredJSONValidator
from backend.models.intelligence import ArticleIntelligence
from backend.models.news import NewsArticle


ARTICLE_PROMPT_VERSION = "article-intelligence-v1"
ARTICLE_SYSTEM_PROMPT = "Return only JSON financial article intelligence matching the requested schema."
ARTICLE_PROMPT_HASH = canonical_hash({"version": ARTICLE_PROMPT_VERSION, "system": ARTICLE_SYSTEM_PROMPT})


def article_source_payload(article: NewsArticle) -> dict:
    return {"title": article.title or "", "summary": article.summary or "", "ticker": article.ticker or "", "url": article.article_url or "", "published_at": article.pub_date}


def article_source_content_hash(article: NewsArticle) -> str:
    return canonical_hash(article_source_payload(article))


async def generate_article_intelligence(session: AsyncSession, article_id: int, force: bool = False, provider: str | None = None, model: str | None = None) -> ArticleIntelligence:
    article = await session.get(NewsArticle, article_id)
    if article is None:
        raise ValueError("article not found")
    source_hash = article_source_content_hash(article)
    input_hash = canonical_hash({"source": source_hash, "prompt": ARTICLE_PROMPT_HASH})
    identity = canonical_hash([article_id, source_hash, ARTICLE_PROMPT_HASH, input_hash])
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:namespace), hashtext(:identity))"), {
        "namespace": "article_intelligence_generation", "identity": identity,
    })
    if not force:
        reused = (await session.execute(select(ArticleIntelligence).where(
            ArticleIntelligence.article_id == article_id,
            ArticleIntelligence.source_content_hash == source_hash,
            ArticleIntelligence.prompt_hash == ARTICLE_PROMPT_HASH,
            ArticleIntelligence.input_hash == input_hash,
            ArticleIntelligence.status == "completed",
        ).order_by(ArticleIntelligence.id.desc()).limit(1))).scalar_one_or_none()
        if reused:
            return reused

    latest_revision = (await session.execute(select(func.max(ArticleIntelligence.generation_revision)).where(
        ArticleIntelligence.article_id == article_id,
        ArticleIntelligence.source_content_hash == source_hash,
        ArticleIntelligence.prompt_hash == ARTICLE_PROMPT_HASH,
        ArticleIntelligence.input_hash == input_hash,
    ))).scalar_one_or_none() or 0
    generation_revision = latest_revision + 1
    generation_identity = canonical_hash([identity, generation_revision])
    row = ArticleIntelligence(article_id=article_id, ticker=article.ticker, status="processing", prompt_version=ARTICLE_PROMPT_VERSION, prompt_hash=ARTICLE_PROMPT_HASH, source_content_hash=source_hash, input_hash=input_hash, generation_revision=generation_revision)
    session.add(row)
    await session.flush()
    policy = build_routing_policy()
    decision = await policy.decide(RoutingRequest(IntelligenceStage.ARTICLE, max(1, len(str(article_source_payload(article))) // 4), deployment_profile=settings.INTELLIGENCE_ROUTING_PROFILE, provider_override=provider, model_override=model))
    validator = LayeredJSONValidator(ArticleIntelligenceOutput, ("summary", "market_impact", "short_term_outlook", "long_term_outlook"))
    generator = IntelligenceGenerator(build_providers(), validator, DatabaseEvaluationRecorder(session, ARTICLE_PROMPT_VERSION, ARTICLE_PROMPT_HASH))
    prompt = f"Analyze this immutable source article and return the complete JSON schema:\n{article_source_payload(article)}"
    try:
        output, metadata = await generator.generate(artifact_type="article", artifact_identity=generation_identity, artifact_id=row.id, decision=decision, system_prompt=ARTICLE_SYSTEM_PROMPT, user_prompt=prompt, context=ValidationContext(IntelligenceStage.ARTICLE, article.ticker))
        data = output.model_dump()
        row.status = "completed"; row.provider = metadata["provider"]; row.model = metadata["model"]
        row.summary = output.summary; row.summary_hash = canonical_hash(output.summary); row.sentiment = output.sentiment
        row.confidence = output.confidence; row.importance_score = output.importance_score; row.market_impact = output.market_impact
        row.short_term_outlook = output.short_term_outlook; row.long_term_outlook = output.long_term_outlook
        row.structured_data = {k: v for k, v in data.items() if k not in {"summary", "sentiment", "confidence", "importance_score", "market_impact", "short_term_outlook", "long_term_outlook"}}
        row.routing_metadata = asdict(decision)
        row.evaluation_metadata = {**row.evaluation_metadata, **metadata["metrics"]}
        row.generation_duration_ms = metadata["duration_ms"]; row.generated_at = datetime.now(timezone.utc)
    except Exception as exc:
        row.status = "failed"; row.error_code = type(exc).__name__; row.error_message = str(exc)[:2000]
        await session.commit()
        raise
    await session.commit()
    return row