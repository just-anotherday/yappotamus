"""
Ollama Service (Compatibility Layer)

Maintains backward-compatible API for all existing consumers (routers, workers).
Internally routes through the provider abstraction in backend/services/ai/.

To switch providers, set AI_PROVIDER=openai in environment variables.
No changes required to calling code.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
import requests
from pydantic import ValidationError

from backend.models.analysis import (
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
    KeyRisk,
    ModelInfo,
    OllamaConfigResponse,
    OllamaModelInfo,
    OutlookResponse,
    ProviderConfigResponse,
    ProviderInfo,
    TechnicalAnalysisResponse,
)

from backend.config.settings import settings
from backend.services.ai.exceptions import AIConnectionError, AIValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration: import from single source of truth (settings.py)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL      = settings.OLLAMA_BASE_URL
OLLAMA_MODEL         = settings.OLLAMA_MODEL
OLLAMA_TIMEOUT_SMALL = settings.OLLAMA_TIMEOUT_SMALL_S
OLLAMA_TIMEOUT_LARGE = settings.OLLAMA_TIMEOUT_LARGE_S
OLLAMA_MAX_RETRIES   = settings.OLLAMA_MAX_RETRIES
MODEL_SIZE_THRESHOLD_GB = settings.MODEL_SIZE_THRESHOLD_GB

# ---------------------------------------------------------------------------
# System prompt (shared across all providers)
# ---------------------------------------------------------------------------
CURRENT_PROMPT_VERSION = "2.0"

SYSTEM_PROMPT = """You are an institutional equity research analyst producing an evidence-based
research note for a portfolio manager. You are NOT giving financial advice or guaranteeing
future performance - you are synthesizing the news and price data provided into a structured,
well-reasoned view.

DATA AVAILABLE TO YOU: recent news articles for this ticker and current/technical price data
(support/resistance, recent change %, 52-week range, volume). You do NOT have income statements,
balance sheets, cash flow statements, analyst ratings, or competitor financials for this request.
Never invent figures for data you were not given - reason only from the news and price data
provided, and be explicit when a conclusion is limited by that scope (e.g. "based on news flow
and price action; no fundamentals data available").

RULES:
1. Use only the provided articles and price data. No fabrication of facts, quotes, or numbers.
2. Separate fact (what the news/price data literally shows) from opinion (your interpretation).
3. Justify every rating or score with a specific reason drawn from the input data.
4. Do not rate bullish solely because price rose, or bearish solely because price fell - tie the
   rating to the underlying catalyst or news content.
5. Always include both a bull case and a bear case, even when your overall view leans one way.
6. Flag uncertainty explicitly rather than projecting false confidence.
7. Return valid JSON only - no markdown fences, no commentary outside the JSON object.

JSON Schema:
{
  "asset": "ticker",
  "overall_sentiment": "Very Bullish|Bullish|Neutral|Bearish|Very Bearish",
  "confidence_score": integer 0-100 (how well-supported this view is by the provided data),
  "investment_rating": "Strong Buy|Buy|Hold|Sell|Strong Sell",
  "news_summary": ["key factual points from the articles"],
  "key_catalysts": ["positive drivers grounded in the news/price data"],
  "key_risks": [{"risk": "description", "severity": "Low|Medium|High"}],
  "bull_case": ["specific evidence-based reasons the stock could outperform"],
  "bear_case": ["specific evidence-based reasons the stock could decline"],
  "market_reaction_analysis": "how the price has behaved relative to the news",
  "technical_analysis": {"trend": "string", "support_levels": [], "resistance_levels": [], "breakout_level": "level", "breakdown_level": "level"},
  "outlook": {"short_term": "1-7d", "medium_term": "1-3m", "long_term": "6-12m"},
  "actionable_insights": ["concrete things an investor should watch or do next"],
  "portfolio_fit": "which investor profiles this suits (growth/value/income/risk-tolerant/conservative) and what role it could play (core holding/growth position/speculative position/avoid)",
  "executive_summary": "one paragraph tying the thesis together"
}

IMPORTANT: overall_sentiment and investment_rating must each be exactly one of their listed
values. Do NOT combine values (no "Neutral | Bearish"). Choose the single best match for each."""


# ---------------------------------------------------------------------------
# Prompt builder (unchanged)
# ---------------------------------------------------------------------------
def _build_user_prompt(request: FinancialAnalysisRequest) -> str:
    """Construct the user prompt from news articles and price data."""
    parts = []
    asset_name = request.company_name or request.ticker
    parts.append(f"## Analyze: {request.ticker} ({asset_name})")
    if request.analysis_date:
        parts.append(f"Analysis Date: {request.analysis_date}")
    parts.append("")

    parts.append("## Market Price Data")
    p = request.price_data
    parts.append(f"- Current Price: ${p.current_price:.2f}")
    parts.append(f"- Daily Change: {p.daily_change_percent:+.2f}%")
    if p.weekly_change_percent is not None:
        parts.append(f"- Weekly Change: {p.weekly_change_percent:+.2f}%")
    if p.monthly_change_percent is not None:
        parts.append(f"- Monthly Change: {p.monthly_change_percent:+.2f}%")
    parts.append(f"- 52-Week Range: ${p.fifty_two_week_low:.2f} - ${p.fifty_two_week_high:.2f}")
    parts.append(f"- Trading Volume: {p.trading_volume:,}")
    if p.beta is not None:
        parts.append(f"- Beta: {p.beta}")
    if p.support_level is not None:
        parts.append(f"- Support Level: ${p.support_level:.2f}")
    if p.resistance_level is not None:
        parts.append(f"- Resistance Level: ${p.resistance_level:.2f}")
    if p.moving_average_50 is not None:
        parts.append(f"- 50-Day MA: ${p.moving_average_50:.2f}")
    if p.moving_average_200 is not None:
        parts.append(f"- 200-Day MA: ${p.moving_average_200:.2f}")
    if p.market_cap is not None:
        parts.append(f"- Market Cap: ${p.market_cap:,.0f}")
    parts.append("")

    parts.append("## News Articles")
    parts.append(f"Total Articles: {len(request.news_articles)}")
    parts.append("")

    for i, article in enumerate(request.news_articles, 1):
        parts.append(f"### Article {i}")
        parts.append(f"**Title:** {article.title}")
        if article.source:
            parts.append(f"**Source:** {article.source}")
        if article.published_at:
            parts.append(f"**Published:** {article.published_at}")
        if article.summary:
            parts.append(f"**Summary:** {article.summary}")
        if article.url:
            parts.append(f"**URL:** {article.url}")
        parts.append("")

    parts.append(
        "Based on the above news articles and market data, provide a comprehensive financial analysis report.\n"
        "Return ONLY valid JSON matching the schema in my system instructions. No markdown formatting around the JSON."
    )

    return "\n".join(parts)


def get_effective_prompt_hash(request: FinancialAnalysisRequest) -> str:
    """Return a deterministic SHA-256 hash of the exact effective prompt payload.

    The payload is the UTF-8 encoding of the system prompt, followed by a NUL
    separator, followed by the fully rendered user prompt sent to the provider.
    The separator prevents ambiguous concatenation while preserving exact text.
    """
    user_prompt = _build_user_prompt(request)
    payload = f"{SYSTEM_PROMPT}\0{user_prompt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Response parsing (unchanged)
# ---------------------------------------------------------------------------
def _clean_llm_response(raw: str) -> str:
    """Strip markdown code fences and whitespace from LLM output."""
    text = raw.strip()
    if text.startswith("```"):
        end_idx = text.rfind("```")
        if end_idx > 0:
            text = text[:end_idx].strip()
        for prefix in ["```json", "```JSON", "```"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
    return text


def _parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    """Parse LLM response into a dictionary, with fallback strategies."""
    cleaned = _clean_llm_response(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        json_str = cleaned[start:end]
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError):
        pass
    try:
        fixed = cleaned.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
        logger.error(f"[AI] All JSON parsing strategies failed for response of length {len(cleaned)}")
        return None


# ---------------------------------------------------------------------------
# Provider-aware connection check / config (unchanged public API)
# ---------------------------------------------------------------------------
async def check_ollama_connection() -> bool:
    """Check if the AI provider is reachable."""
    try:
        from backend.services.ai import get_ai_service
        ai = get_ai_service()
        return await ai.is_available()
    except Exception as e:
        logger.warning(f"[AI] Connection check failed: {e}")
        return False


async def _fetch_ollama_models() -> List[OllamaModelInfo]:
    """Try to fetch models from local Ollama instance."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code != 200:
                return []
            data = resp.json()
            models = []
            for m in data.get("models", []):
                models.append(OllamaModelInfo(
                    name=m.get("name", "unknown"),
                    size=m.get("size", 0),
                    modified_at=m.get("modified_at"),
                ))
            return models
    except Exception as e:
        logger.warning(f"[AI] Could not reach Ollama at {OLLAMA_BASE_URL}: {e}")
        return []


async def _fetch_openai_models() -> List[ModelInfo]:
    """Fetch allowed OpenAI models based on OPENAI_ALLOWED_MODELS whitelist.

    Only returns whitelisted models for cost control.
    Always shown in localhost mode so the UI displays options.
    The actual call will fail at runtime if no API key is configured.
    """
    allowed = settings.OPENAI_ALLOWED_MODELS
    return [
        ModelInfo(name=model, size=0, modified_at=None)
        for model in allowed
    ]


async def list_available_models() -> List[OllamaModelInfo]:
    """Fetch all available models from both Ollama and OpenAI (for the config endpoint)."""
    ollama_models = await _fetch_ollama_models()
    openai_models = await _fetch_openai_models()
    # Convert OpenAI ModelInfo to OllamaModelInfo for backward compat
    combined = list(ollama_models) + [OllamaModelInfo(name=m.name, size=m.size, modified_at=m.modified_at) for m in openai_models]
    return combined


async def get_provider_config() -> ProviderConfigResponse:
    """Get provider-aware configuration dynamically from ProviderRegistry.

    This is the single source of truth for provider availability and model discovery.
    Each provider class reports its own availability and models via is_available() / list_models().
    Unavailable providers are still listed so the frontend can show consistent UI.
    """
    from backend.services.ai import ProviderRegistry

    providers = []
    default_provider = "ollama"
    default_model = ""

    for provider_id in ProviderRegistry.all_ids():
        klass = ProviderRegistry.get(provider_id)
        if not klass:
            continue

        instance = klass()
        available = await instance.is_available()
        models = await instance.list_models()

        providers.append(ProviderInfo(
            id=provider_id,
            name=provider_id.capitalize(),
            available=available,
            models=models,
        ))

        # First available provider becomes the default
        if available and not default_model:
            default_provider = provider_id
            if models:
                first_model = models[0]
                default_model = first_model.get("name") if isinstance(first_model, dict) else getattr(first_model, "name", "")

    # Fallback defaults if nothing is available
    if not default_model:
        default_provider = "ollama"
        default_model = OLLAMA_MODEL

    return ProviderConfigResponse(
        providers=providers,
        default_provider=default_provider,
        default_model=default_model,
    )


async def get_ollama_config() -> OllamaConfigResponse:
    """Get current AI provider configuration and status (legacy endpoint)."""
    from backend.services.ai import ProviderRegistry

    provider = settings.AI_PROVIDER
    klass = ProviderRegistry.get(provider)
    if klass is None:
        raise AIValidationError(f"Unknown AI provider '{provider}'")
    instance = klass()
    connected = await instance.is_available()
    all_models = await instance.list_models()
    url = "openai" if provider == "openai" else OLLAMA_BASE_URL
    default_model = settings.default_model_for_provider(provider)

    return OllamaConfigResponse(
        ollama_url=url,
        default_model=default_model,
        available_models=all_models,
        connected=connected,
    )


def _get_timeout_for_model(model_name: str, provider: Optional[str] = None) -> float:
    """Get timeout based on model size. Large models get 20 min, smaller get 15 min."""
    active_provider = provider or settings.AI_PROVIDER
    if active_provider == "openai":
        return 120.0  # OpenAI has a fixed short timeout
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            for m in data.get("models", []):
                base_name = m.get("name", "").split(":")[0]
                query_name = model_name.split(":")[0]
                if model_name.startswith(base_name) or base_name.startswith(query_name):
                    size_bytes = m.get("size", 0)
                    size_gb = size_bytes / (1024 ** 3)
                    if size_gb > MODEL_SIZE_THRESHOLD_GB:
                        return OLLAMA_TIMEOUT_LARGE
                    else:
                        return OLLAMA_TIMEOUT_SMALL
    except Exception as e:
        logger.warning(f"[AI] Could not look up model size for timeout, using default large: {e}")
    return OLLAMA_TIMEOUT_LARGE


# ---------------------------------------------------------------------------
# Main analysis entry point (provider-aware)
# ---------------------------------------------------------------------------
async def generate_analysis(
    request: FinancialAnalysisRequest,
    model: Optional[str] = None,
    temperature: float = 0.3,
    provider: Optional[str] = None,
) -> FinancialAnalysisResponse:
    """Generate a financial analysis report using the configured AI provider.

    This is the primary entry point used by all consumers (routers, workers).
    If *provider* is given, it overrides the global AI_PROVIDER setting for this call.
    """
    user_prompt = _build_user_prompt(request)
    last_error = None

    from backend.services.ai.ai_service import validate_provider_model

    target_provider, active_model, ai = await validate_provider_model(provider, model)

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):
        try:
            start = time.perf_counter()
            raw_response = await ai.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
                model=active_model,
            )
            elapsed = time.perf_counter() - start
            logger.info(f"[AI] Response received in {elapsed:.1f}s (attempt {attempt})")

            parsed = _parse_llm_json(raw_response)

            if parsed is None:
                last_error = ValueError("Failed to parse LLM response as JSON")
                logger.warning(f"[AI] {last_error} (attempt {attempt})")
                continue

            # Populate articles_used with rich references
            parsed["articles_used"] = [
                {
                    "title": a.title,
                    "url": a.url,
                    "published_at": a.published_at,
                }
                for a in request.news_articles
                if a.title
            ]

            result = FinancialAnalysisResponse(**parsed)
            logger.info(
                f"[AI] Analysis complete for {request.ticker}: "
                f"sentiment={result.overall_sentiment}, confidence={result.confidence_score}"
            )
            return result

        except AIValidationError:
            # Never waste retries on an invalid provider/model/config - fail immediately.
            raise
        except AIConnectionError as e:
            last_error = e
            logger.warning(f"[AI] Connection error (attempt {attempt}): {e}")
        except ValidationError as e:
            last_error = e
            logger.warning(f"[AI] Response validation failed: {e} (attempt {attempt})")
        except Exception as e:
            last_error = e
            logger.error(f"[AI] Unexpected error on attempt {attempt}: {e}")

    if isinstance(last_error, AIConnectionError):
        raise last_error

    raise RuntimeError(
        f"AI analysis failed after {OLLAMA_MAX_RETRIES} retries. "
        f"Last error: {last_error}"
    )
