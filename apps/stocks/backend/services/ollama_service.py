"""
Ollama Service (Compatibility Layer)

Maintains backward-compatible API for all existing consumers (routers, workers).
Internally routes through the provider abstraction in backend/services/ai/.

To switch providers, set AI_PROVIDER=openai in environment variables.
No changes required to calling code.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

import httpx
import requests
from pydantic import ValidationError

load_dotenv()

from backend.models.analysis import (
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
    KeyRisk,
    OllamaConfigResponse,
    OllamaModelInfo,
    OutlookResponse,
    TechnicalAnalysisResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (same env vars as before for backward compat)
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT_SMALL = float(os.getenv("OLLAMA_TIMEOUT_SMALL_S", "900"))
OLLAMA_TIMEOUT_LARGE = float(os.getenv("OLLAMA_TIMEOUT_LARGE_S", "1200"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))
MODEL_SIZE_THRESHOLD_GB = float(os.getenv("MODEL_SIZE_THRESHOLD_GB", "8"))

# ---------------------------------------------------------------------------
# System prompt (shared across all providers)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a financial analyst. Analyze the provided news and price data, then return a JSON report.

Rules: Use only provided data. No fabrication. Balanced analysis. Return valid JSON only (no markdown fences).

JSON Schema:
{
  "asset": "ticker",
  "overall_sentiment": "Very Bullish|Bullish|Neutral|Bearish|Very Bearish",
  "confidence_score": integer 0-100,
  "news_summary": ["key points"],
  "key_catalysts": ["positive drivers"],
  "key_risks": [{"risk": "description", "severity": "Low|Medium|High"}],
  "market_reaction_analysis": "price vs news analysis",
  "technical_analysis": {"trend": "string", "support_levels": [], "resistance_levels": [], "breakout_level": "level", "breakdown_level": "level"},
  "outlook": {"short_term": "1-7d", "medium_term": "1-3m", "long_term": "6-12m"},
  "articles_used": ["titles"],
  "actionable_insights": ["insights"],
  "executive_summary": "one paragraph"
}

IMPORTANT: overall_sentiment must be exactly one of the five values. Do NOT combine values (no "Neutral | Bearish"). Choose the single best match."""


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


async def list_available_models() -> List[OllamaModelInfo]:
    """Fetch available models (Ollama) or return configured model info."""
    provider = (os.getenv("AI_PROVIDER") or "ollama").lower()
    if provider == "openai":
        model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return [OllamaModelInfo(name=model_name, size=0, modified_at=None)]
    # Default: try Ollama tags endpoint
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
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
        logger.error(f"[AI] Failed to list models: {e}")
        return []


async def get_ollama_config() -> OllamaConfigResponse:
    """Get current AI provider configuration and status."""
    connected = await check_ollama_connection()
    models = []
    if connected:
        models = await list_available_models()

    provider = (os.getenv("AI_PROVIDER") or "ollama").lower()
    url = os.getenv("OPENAI_MODEL", "https://api.openai.com/v1/chat/completions") if provider == "openai" else OLLAMA_BASE_URL
    default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini") if provider == "openai" else OLLAMA_MODEL

    return OllamaConfigResponse(
        ollama_url=url,
        default_model=default_model,
        available_models=models,
        connected=connected,
    )


def _get_timeout_for_model(model_name: str) -> float:
    """Get timeout based on model size. Large models get 20 min, smaller get 15 min."""
    provider = (os.getenv("AI_PROVIDER") or "ollama").lower()
    if provider == "openai":
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
) -> FinancialAnalysisResponse:
    """Generate a financial analysis report using the configured AI provider.

    This is the primary entry point used by all consumers (routers, workers).
    Switching providers only requires changing AI_PROVIDER env var.
    """
    user_prompt = _build_user_prompt(request)
    last_error = None

    # Use the provider abstraction
    try:
        from backend.services.ai import get_ai_service
        ai = get_ai_service()
    except Exception as e:
        raise RuntimeError(f"Failed to initialize AI service: {e}") from e

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):
        try:
            start = time.perf_counter()
            raw_response = await ai.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=temperature,
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

        except ValidationError as e:
            last_error = e
            logger.warning(f"[AI] Response validation failed: {e} (attempt {attempt})")
        except Exception as e:
            last_error = e
            logger.error(f"[AI] Unexpected error on attempt {attempt}: {e}")

    raise RuntimeError(
        f"AI analysis failed after {OLLAMA_MAX_RETRIES} retries. "
        f"Last error: {last_error}"
    )
