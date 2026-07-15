"""
Ollama Service

Manages communication with a local Ollama instance for financial analysis.
Supports multiple models via environment variable configuration.
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

# Configuration via environment variables
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT_SMALL = float(os.getenv("OLLAMA_TIMEOUT_SMALL_S", "900"))   # 15 min for smaller models
OLLAMA_TIMEOUT_LARGE = float(os.getenv("OLLAMA_TIMEOUT_LARGE_S", "1200"))   # 20 min for larger models
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))
MODEL_SIZE_THRESHOLD_GB = float(os.getenv("MODEL_SIZE_THRESHOLD_GB", "8"))  # GB threshold between small/large


def _get_timeout_for_model(model_name: str) -> float:
    """Get timeout based on model size. Large models (>8GB) get 20 min, smaller get 15 min."""
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
                        logger.info(f"[Ollama] Model {model_name} is {size_gb:.1f}GB (>={MODEL_SIZE_THRESHOLD_GB}GB) -> timeout={OLLAMA_TIMEOUT_LARGE}s")
                        return OLLAMA_TIMEOUT_LARGE
                    else:
                        logger.info(f"[Ollama] Model {model_name} is {size_gb:.1f}GB (<{MODEL_SIZE_THRESHOLD_GB}GB) -> timeout={OLLAMA_TIMEOUT_SMALL}s")
                        return OLLAMA_TIMEOUT_SMALL
    except Exception as e:
        logger.warning(f"[Ollama] Could not look up model size for timeout, using default large: {e}")
    # Fallback to larger timeout for safety
    return OLLAMA_TIMEOUT_LARGE


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


def _build_user_prompt(request: FinancialAnalysisRequest) -> str:
    """Construct the user prompt from news articles and price data."""

    parts = []

    # Asset header
    asset_name = request.company_name or request.ticker
    parts.append(f"## Analyze: {request.ticker} ({asset_name})")
    if request.analysis_date:
        parts.append(f"Analysis Date: {request.analysis_date}")
    parts.append("")

    # Price data section
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

    # News articles section
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

    # Final instruction
    parts.append(
        "Based on the above news articles and market data, provide a comprehensive financial analysis report.\n"
        "Return ONLY valid JSON matching the schema in my system instructions. No markdown formatting around the JSON."
    )

    return "\n".join(parts)


async def check_ollama_connection() -> bool:
    """Check if Ollama server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"[Ollama] Connection check failed: {e}")
        return False


async def list_available_models() -> List[OllamaModelInfo]:
    """Fetch the list of installed models from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code != 200:
                logger.warning(f"[Ollama] Model list returned status {resp.status_code}")
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
        logger.error(f"[Ollama] Failed to list models: {e}")
        return []


async def get_ollama_config() -> OllamaConfigResponse:
    """Get current Ollama configuration and status."""
    connected = await check_ollama_connection()
    models = []
    if connected:
        models = await list_available_models()

    return OllamaConfigResponse(
        ollama_url=OLLAMA_BASE_URL,
        default_model=OLLAMA_MODEL,
        available_models=models,
        connected=connected,
    )


def _clean_llm_response(raw: str) -> str:
    """Strip markdown code fences and whitespace from LLM output."""
    text = raw.strip()

    # Remove markdown JSON code fences if present
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

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object in the text by finding matching braces
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        json_str = cleaned[start:end]
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError):
        pass

    # Last resort: try to fix common issues
    try:
        fixed = cleaned.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
        logger.error(f"[Ollama] All JSON parsing strategies failed for response of length {len(cleaned)}")
        return None


async def generate_analysis(
    request: FinancialAnalysisRequest,
    model: Optional[str] = None,
    temperature: float = 0.3,
) -> FinancialAnalysisResponse:
    """Generate a financial analysis report using Ollama.

    Args:
        request: The analysis request with news + price data.
        model: Override the default model name.
        temperature: LLM temperature (lower = more deterministic).

    Returns:
        A validated FinancialAnalysisResponse.

    Raises:
        RuntimeError: If Ollama is unreachable or all retries fail.
    """
    model_name = model or OLLAMA_MODEL
    user_prompt = _build_user_prompt(request)
    timeout = _get_timeout_for_model(model_name)
    last_error = None

    for attempt in range(1, OLLAMA_MAX_RETRIES + 1):
        try:
            start = time.perf_counter()

            async with httpx.AsyncClient(timeout=timeout) as client:
                payload = {
                    "model": model_name,
                    "prompt": user_prompt,
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_ctx": 16384,
                    },
                }

                resp = await client.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json=payload,
                )

            elapsed = time.perf_counter() - start
            logger.info(f"[Ollama] Response received in {elapsed:.1f}s (attempt {attempt})")

            if resp.status_code != 200:
                last_error = ValueError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")
                logger.warning(f"[Ollama] {last_error}")
                continue

            raw_response = resp.json().get("response", "")
            parsed = _parse_llm_json(raw_response)

            if parsed is None:
                last_error = ValueError("Failed to parse LLM response as JSON")
                logger.warning(f"[Ollama] {last_error} (attempt {attempt})")
                continue

            # Populate articles_used with rich references from the request
            parsed["articles_used"] = [
                {
                    "title": a.title,
                    "url": a.url,
                    "published_at": a.published_at,
                }
                for a in request.news_articles
                if a.title
            ]

            # Validate against Pydantic model
            result = FinancialAnalysisResponse(**parsed)
            logger.info(
                f"[Ollama] Analysis complete for {request.ticker}: "
                f"sentiment={result.overall_sentiment}, confidence={result.confidence_score}"
            )
            return result

        except httpx.TimeoutException:
            last_error = TimeoutError(f"Ollama request timed out after {timeout}s")
            logger.warning(f"[Ollama] {last_error} (attempt {attempt})")
        except ValidationError as e:
            last_error = e
            logger.warning(f"[Ollama] Response validation failed: {e} (attempt {attempt})")
        except Exception as e:
            last_error = e
            logger.error(f"[Ollama] Unexpected error on attempt {attempt}: {e}")

    raise RuntimeError(
        f"Ollama analysis failed after {OLLAMA_MAX_RETRIES} retries. "
        f"Last error: {last_error}"
    )
