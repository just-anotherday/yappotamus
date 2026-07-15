"""
AI Worker Service — Background processor for the AI Job Queue.

Polls `ai_job_queue` for pending jobs, executes the appropriate AI enrichment task,
and updates the job status with results or error messages.

Runs as an asyncio background task inside FastAPI's lifespan.

Job Types:
- company_report: Generate AI intelligence report for a single asset (calls Ollama)
- sector_report: Aggregate company reports into sector intelligence
- market_report: Daily market-wide intelligence summary
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable

from sqlalchemy import select, update, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.analysis import (
    FinancialAnalysisRequest,
    NewsArticleRequest,
    PriceDataRequest,
)
from backend.models.ai_reports import AICompanyReport
from backend.models.asset import Asset, AssetTicker
from backend.models.news import NewsArticle
from backend.services.finnhub_service import get_finnhub_client
from backend.services.article_scorer import rank_articles
from backend.services.ollama_service import OLLAMA_MODEL

logger = logging.getLogger(__name__)


class AIWorker:
    """Background worker that processes AI enrichment jobs from the queue."""

    def __init__(self, get_session_factory: Callable[..., Awaitable], poll_interval: float = 10.0, max_concurrent: int = 2):
        self.get_session_factory = get_session_factory
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent
        self._running = False
        self._semaphore = asyncio.Semaphore(max_concurrent)
        # Registry of job_type -> handler method
        self._handlers = {
            "company_report": self._handle_company_report,
            "sector_report": self._handle_sector_report,
            "market_report": self._handle_market_report,
        }

    async def start(self):
        """Start the background polling loop."""
        self._running = True
        logger.info("[AIWorker] Started, polling every %.1fs (max_concurrent=%d)", self.poll_interval, self.max_concurrent)

        while self._running:
            try:
                await self._poll_cycle()
            except Exception:
                logger.exception("[AIWorker] Unexpected error in poll loop")
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self._running = False
        logger.info("[AIWorker] Stop requested")

    # ------------------------------------------------------------------
    # Polling cycle
    # ------------------------------------------------------------------
    async def _poll_cycle(self):
        """Claim pending jobs and dispatch them."""
        async with self.get_session_factory() as session:
            try:
                jobs = await self._claim_pending_jobs(session)
            except Exception:
                logger.exception("[AIWorker] Error claiming jobs")
                return

            for job in jobs:
                await self._semaphore.acquire()
                asyncio.create_task(self._process_job(job))

    async def _claim_pending_jobs(self, session: AsyncSession) -> list:
        """Atomically claim up to max_concurrent pending jobs."""
        from backend.models.ai_job_queue import AIJobQueue

        stmt = (
            select(AIJobQueue)
            .where(
                and_(
                    AIJobQueue.status == "pending",
                    AIJobQueue.scheduled_for <= datetime.utcnow(),
                    AIJobQueue.retry_count < AIJobQueue.max_retries,
                )
            )
            .order_by(AIJobQueue.priority.asc(), AIJobQueue.scheduled_for.asc())
            .limit(self.max_concurrent)
        )

        result = await session.execute(stmt)
        jobs = list(result.unique().scalars().all())

        for job in jobs:
            job.status = "processing"
            job.started_at = datetime.utcnow()

        if jobs:
            await session.commit()
        return jobs

    async def _process_job(self, job):
        """Dispatch a single job to its handler with a per-job timeout."""
        # Per-job timeout (minutes) by type
        TIMEOUT_MINUTES = {
            "company_report": 30,
            "sector_report": 5,
            "market_report": 10,
        }
        timeout_seconds = TIMEOUT_MINUTES.get(job.job_type, 10) * 60

        try:
            handler = self._handlers.get(job.job_type)
            if not handler:
                logger.warning("[AIWorker] Unknown job type %r, marking failed", job.job_type)
                await self._fail_job(job, f"Unknown job type: {job.job_type}")
                return

            result_data = await asyncio.wait_for(handler(job), timeout=timeout_seconds)
            await self._complete_job(job, result_data)
        except asyncio.TimeoutError:
            logger.error("[AIWorker] Job %d (%s) timed out after %ds", job.id, job.job_type, timeout_seconds)
            job.retry_count += 1
            if job.retry_count >= job.max_retries:
                job.status = "failed"
                job.error_message = f"Timed out after {timeout_seconds}s"
            else:
                from datetime import timedelta
                job.scheduled_for = datetime.utcnow() + timedelta(minutes=2**job.retry_count)
                job.status = "pending"
            try:
                async with self.get_session_factory() as session:
                    await session.merge(job)
                    await session.commit()
            except Exception:
                logger.exception("[AIWorker] Error updating job %d", job.id)
        except Exception:
            logger.exception("[AIWorker] Job %d failed", job.id)
            job.retry_count += 1
            if job.retry_count >= job.max_retries:
                job.status = "failed"
            else:
                # Reschedule with exponential backoff
                from datetime import timedelta
                job.scheduled_for = datetime.utcnow() + timedelta(minutes=2**job.retry_count)
                job.status = "pending"
            try:
                async with self.get_session_factory() as session:
                    await session.merge(job)
                    await session.commit()
            except Exception:
                logger.exception("[AIWorker] Error updating job %d", job.id)
        finally:
            self._semaphore.release()

    async def _complete_job(self, job, result_data: Optional[dict] = None):
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        if result_data:
            job.result = result_data
        async with self.get_session_factory() as session:
            await session.merge(job)
            await session.commit()

    async def _fail_job(self, job, error_msg: str):
        job.status = "failed"
        job.error_message = error_msg
        job.completed_at = datetime.utcnow()
        async with self.get_session_factory() as session:
            await session.merge(job)
            await session.commit()

    # ------------------------------------------------------------------
    # Job Handlers
    # ------------------------------------------------------------------
    async def _handle_company_report(self, job) -> dict:
        """Generate company intelligence report via Ollama and persist to DB."""
        logger.info("[AIWorker] Processing company report for asset_id=%d", job.target_id)

        payload = job.payload or {}
        ticker = payload.get("ticker", "")
        model = payload.get("model")  # Optional model override from frontend
        async with self.get_session_factory() as session:
            # 1. Resolve asset + ticker
            if not ticker:
                at_row = await session.execute(
                    select(AssetTicker).where(
                        AssetTicker.asset_id == job.target_id,
                        AssetTicker.is_primary.is_(True),
                    )
                )
                at_obj = at_row.scalar_one_or_none()
                ticker = at_obj.ticker if at_obj else ""

            if not ticker:
                logger.warning("[AIWorker] No ticker for asset_id=%d, skipping", job.target_id)
                return {"status": "skipped", "reason": "no_ticker"}

            # 2. Read per-asset analysis config (defaults: 7 days, 15 articles)
            asset_cfg = await session.execute(
                select(Asset.analysis_window_days, Asset.max_articles_per_analysis, Asset.name)
                .where(Asset.id == job.target_id)
            )
            cfg_row = asset_cfg.first()
            if cfg_row:
                window_days = max(1, min(90, cfg_row[0] or 7))
                max_articles = max(5, min(30, cfg_row[1] or 15))
                company_name = cfg_row[2]
            else:
                window_days = 7
                max_articles = 15
                company_name = None

            # Fetch more candidates than needed so scoring can pick the best ones
            articles_result = await session.execute(
                select(NewsArticle)
                .where(
                    NewsArticle.ticker == ticker.upper(),
                    NewsArticle.pub_date >= datetime.utcnow() - timedelta(days=window_days),
                )
            )
            all_candidates = list(articles_result.scalars().all())

            # 2b. Rank by relevance (ticker mentions, recency, summary quality, source)
            ranked = rank_articles(all_candidates, ticker.upper(), now=datetime.utcnow())
            articles = ranked[:max_articles]

            if not articles:
                logger.info("[AIWorker] No recent articles for %s, skipping report", ticker)
                return {"status": "skipped", "reason": "no_articles", "ticker": ticker}

            # 3. Fetch current price data from Finnhub
            price_data = await self._fetch_price_data(ticker)

            # 4. Build Ollama request
            from backend.services.ollama_service import generate_analysis, check_ollama_connection

            connected = await check_ollama_connection()
            if not connected:
                logger.warning("[AIWorker] Ollama unreachable, deferring report for %s", ticker)
                return {"status": "deferred", "reason": "ollama_unreachable"}

            news_reqs = [
                NewsArticleRequest(
                    title=a.title or "",
                    summary=a.summary,
                    published_at=a.pub_date.isoformat() if a.pub_date else None,
                    source=a.provider_name,
                    url=a.article_url,
                )
                for a in articles
            ]

            analysis_request = FinancialAnalysisRequest(
                ticker=ticker.upper(),
                company_name=company_name,
                news_articles=news_reqs,
                price_data=price_data,
                analysis_date=datetime.utcnow().isoformat(),
            )

            # 5. Call Ollama (use model override if provided, else default)
            effective_model = model or OLLAMA_MODEL
            result = await generate_analysis(analysis_request, model=effective_model)

            # 6. Persist report to DB (filter by both asset_id AND ticker to prevent cross-ticker contamination)
            existing = await session.execute(
                select(AICompanyReport).where(
                    AICompanyReport.asset_id == job.target_id,
                    AICompanyReport.ticker == ticker.upper(),
                )
            )
            existing_report = existing.scalar_one_or_none()

            report_dict = result.model_dump(exclude={"report_id"})

            # Populate articles_used provenance so frontend can display source links
            report_dict["articles_used"] = [
                {
                    "title": a.title or "",
                    "url": a.article_url or "",
                    "published_at": a.pub_date.isoformat() if a.pub_date else None,
                }
                for a in articles
            ]

            # Import history model for audit trail
            from backend.models.ai_report_history import AICompanyReportHistory
            
            if existing_report:
                # Save a snapshot to history before overwriting
                history_row = AICompanyReportHistory(
                    original_report_id=existing_report.id,
                    ticker=ticker.upper(),
                    overall_sentiment=existing_report.overall_sentiment or "",
                    confidence_score=existing_report.confidence_score or 0,
                    articles_count=existing_report.articles_count or 0,
                    model_used=existing_report.model_used or "",
                    prompt_version=existing_report.prompt_version or "1.0",
                    price_snapshot=existing_report.price_snapshot,
                    report_data_snapshot=existing_report.report_data,
                )
                session.add(history_row)
                
                # Explicitly set updated_at so frontend polling detects the change
                existing_report.updated_at = datetime.utcnow()
                existing_report.report_data = report_dict
                existing_report.overall_sentiment = result.overall_sentiment
                existing_report.confidence_score = result.confidence_score
                existing_report.articles_count = len(articles)
                existing_report.model_used = effective_model
                existing_report.price_snapshot = price_data.current_price
                logger.info("[AIWorker] Updated report for %s", ticker)
            else:
                new_report = AICompanyReport(
                    asset_id=job.target_id,
                    ticker=ticker.upper(),
                    report_data=report_dict,
                    overall_sentiment=result.overall_sentiment,
                    confidence_score=result.confidence_score,
                    articles_count=len(articles),
                    model_used=effective_model,
                    prompt_version="1.0",
                    price_snapshot=price_data.current_price,
                )
                session.add(new_report)
                logger.info("[AIWorker] Created report for %s", ticker)

            # Handle race: concurrent job may have already INSERTed the same ticker
            try:
                await session.commit()
            except Exception as commit_err:
                if "unique constraint" in str(commit_err).lower() or "duplicate key" in str(commit_err).lower():
                    logger.warning("[AIWorker] Duplicate report for %s (concurrent job won race), skipping insert", ticker)
                    await session.rollback()
                else:
                    raise

            # --- Auto-trigger sector report if this company's sector exists ---
            try:
                asset_result = await session.execute(
                    select(Asset.sector).where(Asset.id == job.target_id)
                )
                sector = asset_result.scalar_one_or_none()
                if sector:
                    # Only enqueue sector report periodically (not every company update)
                    # Check if a sector report already exists and is recent (< 1 hour old)
                    from backend.models.ai_reports import AISectorReport
                    sector_report_check = await session.execute(
                        select(AISectorReport.id).where(
                            AISectorReport.sector == sector,
                            AISectorReport.created_at >= datetime.utcnow() - timedelta(hours=1),
                        ).limit(1)
                    )
                    if not sector_report_check.scalar_one_or_none():
                        await enqueue_job(
                            session=session,
                            job_type="sector_report",
                            target_type="sector",
                            target_id=0,
                            payload={"sector": sector},
                            priority=20,
                        )
                        logger.info("[AIWorker] Auto-queued sector report for %s (triggered by %s)", sector, ticker)
            except Exception as e:
                logger.warning("[AIWorker] Failed to auto-trigger sector report: %s", e)

        return {
            "ticker": ticker.upper(),
            "asset_id": job.target_id,
            "sentiment": result.overall_sentiment,
            "confidence": result.confidence_score,
            "articles_analyzed": len(articles),
        }

    async def _fetch_price_data(self, ticker: str) -> PriceDataRequest:
        """Fetch current market price data from Finnhub."""
        try:
            client = get_finnhub_client()
            quote = client.quote(ticker.upper())
            if quote and isinstance(quote, dict) and quote.get("c"):
                # Fetch profile for beta + market cap
                profile = {}
                try:
                    profile = client.company_profile2(symbol=ticker.upper()) or {}
                except Exception:
                    pass

                return PriceDataRequest(
                    current_price=quote.get("c", 0),
                    daily_change_percent=(quote.get("d", 0) / quote.get("c", 1) * 100) if quote.get("c") else 0,
                    weekly_change_percent=None,
                    monthly_change_percent=None,
                    fifty_two_week_high=quote.get("h", 0),
                    fifty_two_week_low=quote.get("l", 0),
                    trading_volume=int(quote.get("v", 0)),
                    beta=float(profile.get("beta", 0)) if profile.get("beta") else None,
                    market_cap=float(profile.get("marketCapitalization", 0)) if profile.get("marketCapitalization") else None,
                )
        except Exception as e:
            logger.warning("[AIWorker] Failed to fetch price data for %s: %s", ticker, e)

        # Fallback: zero-price record so Ollama still runs
        return PriceDataRequest(
            current_price=0.0,
            daily_change_percent=0.0,
            fifty_two_week_high=0.0,
            fifty_two_week_low=0.0,
            trading_volume=0,
        )

    async def _handle_sector_report(self, job) -> dict:
        """Aggregate company reports into sector intelligence."""
        sector = (job.payload or {}).get("sector", "")
        if not sector:
            logger.warning("[AIWorker] Sector report job missing sector payload")
            return {"status": "skipped", "reason": "no_sector"}

        logger.info("[AIWorker] Processing sector report for sector=%s", sector)

        async with self.get_session_factory() as session:
            # 1. Gather all company reports in this sector (FIX: single JOIN instead of N+1)
            asset_ids_in_sector = await session.execute(
                select(Asset.id).where(
                    text("LOWER(sector) = :sector"),
                ).params(sector=sector.lower())
            )
            sector_asset_ids = [row[0] for row in asset_ids_in_sector.fetchall()]

            if not sector_asset_ids:
                logger.info("[AIWorker] No assets in sector %s, skipping", sector)
                return {"status": "skipped", "reason": "no_assets_in_sector", "sector": sector}

            company_reports = await session.execute(
                select(AICompanyReport).where(
                    AICompanyReport.asset_id.in_(sector_asset_ids)
                )
            )
            sector_reports = list(company_reports.scalars().all())

            if not sector_reports:
                logger.info("[AIWorker] No company reports for sector %s, skipping", sector)
                return {"status": "skipped", "reason": "no_company_reports", "sector": sector}

            # 2. Build prompt from company reports
            company_summaries = []
            total_confidence = 0
            sentiment_scores = {"Very Bullish": 5, "Bullish": 4, "Neutral": 3, "Bearish": 2, "Very Bearish": 1}
            total_sentiment_score = 0

            for report in sector_reports:
                data = report.report_data or {}
                company_summaries.append(
                    f"- {report.ticker}: Sentiment={report.overall_sentiment}, "
                    f"Confidence={report.confidence_score}/100, "
                    f"Summary: {(data.get('executive_summary', 'N/A'))}"
                )
                total_confidence += report.confidence_score
                total_sentiment_score += sentiment_scores.get(report.overall_sentiment, 3)

            avg_confidence = int(total_confidence / len(sector_reports))
            avg_sentiment_score = total_sentiment_score / len(sector_reports)

            # Determine overall sector sentiment from average score
            reversed_scores = {v: k for k, v in sentiment_scores.items()}
            if avg_sentiment_score >= 4.5:
                overall_sentiment = "Very Bullish"
            elif avg_sentiment_score >= 3.5:
                overall_sentiment = "Bullish"
            elif avg_sentiment_score >= 2.5:
                overall_sentiment = "Neutral"
            elif avg_sentiment_score >= 1.5:
                overall_sentiment = "Bearish"
            else:
                overall_sentiment = "Very Bearish"

            # Identify top movers (highest and lowest confidence + most extreme sentiment)
            top_bullish = sorted(
                [r for r in sector_reports if r.overall_sentiment in ("Bullish", "Very Bullish")],
                key=lambda x: x.confidence_score, reverse=True
            )[:3]
            top_bearish = sorted(
                [r for r in sector_reports if r.overall_sentiment in ("Bearish", "Very Bearish")],
                key=lambda x: x.confidence_score, reverse=True
            )[:3]

            # Collect major risks across companies
            all_risks = []
            for report in sector_reports:
                data = report.report_data or {}
                risks = data.get("key_risks", [])
                if isinstance(risks, list):
                    for risk in risks[:2]:
                        if isinstance(risk, dict):
                            all_risks.append(f"  - {report.ticker}: {risk.get('risk', 'N/A')} (Severity: {risk.get('severity', 'N/A')})")
                        else:
                            all_risks.append(f"  - {report.ticker}: {risk}")

            report_dict = {
                "sector": sector,
                "overall_sentiment": overall_sentiment,
                "confidence_score": avg_confidence,
                "assets_count": len(sector_reports),
                "company_summaries": company_summaries[:10],
                "top_bullish_tickers": [r.ticker for r in top_bullish],
                "top_bearish_tickers": [r.ticker for r in top_bearish],
                "major_risks": all_risks[:10] if all_risks else ["No major risks identified"],
                "market_reaction_analysis": f"Sector has {len(sector_reports)} tracked companies with average confidence {avg_confidence}/100",
                "actionable_insights": [
                    f"Sector sentiment is {overall_sentiment.lower()} based on aggregated company intelligence.",
                    f"Top bullish signals from: {', '.join([r.ticker for r in top_bullish]) or 'No strong bullish signals'}",
                    f"Top bearish signals from: {', '.join([r.ticker for r in top_bearish]) or 'No strong bearish signals'}",
                ],
                "executive_summary": (
                    f"The {sector} sector shows an overall {overall_sentiment.lower()} sentiment "
                    f"with a confidence score of {avg_confidence}/100, based on analysis of "
                    f"{len(sector_reports)} companies."
                ),
            }

            # 3. Store or update sector report
            from backend.models.ai_reports import AISectorReport

            existing = await session.execute(
                select(AISectorReport).where(AISectorReport.sector == sector)
            )
            existing_report = existing.scalar_one_or_none()

            if existing_report:
                existing_report.report_data = report_dict
                existing_report.overall_sentiment = overall_sentiment
                existing_report.confidence_score = avg_confidence
                existing_report.assets_count = len(sector_reports)
                logger.info("[AIWorker] Updated sector report for %s", sector)
            else:
                new_report = AISectorReport(
                    sector=sector,
                    report_data=report_dict,
                    overall_sentiment=overall_sentiment,
                    confidence_score=avg_confidence,
                    assets_count=len(sector_reports),
                    model_used="aggregated_company_reports",
                    prompt_version="1.0",
                )
                session.add(new_report)
                logger.info("[AIWorker] Created sector report for %s", sector)

            await session.commit()

        return {
            "sector": sector,
            "sentiment": overall_sentiment,
            "confidence": avg_confidence,
            "assets_count": len(sector_reports),
        }

    async def _handle_market_report(self, job) -> dict:
        """Daily market-wide intelligence summary."""
        logger.info("[AIWorker] Processing daily market report")

        async with self.get_session_factory() as session:
            from sqlalchemy import func
            from backend.models.ai_reports import AIMarketReport

            # 1. Gather all company reports (latest per asset)
            all_company_reports = await session.execute(
                select(AICompanyReport).order_by(AICompanyReport.asset_id, AICompanyReport.updated_at.desc())
            )
            rows = list(all_company_reports.scalars().all())

            # Deduplicate: keep only the latest report per asset
            latest_by_asset = {}
            for r in rows:
                if r.asset_id not in latest_by_asset:
                    latest_by_asset[r.asset_id] = r
            company_reports = list(latest_by_asset.values())

            if not company_reports:
                logger.info("[AIWorker] No company reports available, skipping market report")
                return {"status": "skipped", "reason": "no_company_reports"}

            # 2. Aggregate sentiment across all companies
            sentiment_scores = {"Very Bullish": 5, "Bullish": 4, "Neutral": 3, "Bearish": 2, "Very Bearish": 1}
            total_score = sum(sentiment_scores.get(r.overall_sentiment, 3) for r in company_reports)
            avg_score = total_score / len(company_reports)

            if avg_score >= 4.5:
                overall_sentiment = "Very Bullish"
                risk_level = "Low"
            elif avg_score >= 3.5:
                overall_sentiment = "Bullish"
                risk_level = "Low-Medium"
            elif avg_score >= 2.5:
                overall_sentiment = "Neutral"
                risk_level = "Medium"
            elif avg_score >= 1.5:
                overall_sentiment = "Bearish"
                risk_level = "High"
            else:
                overall_sentiment = "Very Bearish"
                risk_level = "Very High"

            avg_confidence = int(sum(r.confidence_score for r in company_reports) / len(company_reports))

            # 3. Identify top movers by sentiment extremes
            bullish_companies = sorted(
                [r for r in company_reports if r.overall_sentiment in ("Bullish", "Very Bullish")],
                key=lambda x: x.confidence_score, reverse=True
            )[:5]
            bearish_companies = sorted(
                [r for r in company_reports if r.overall_sentiment in ("Bearish", "Very Bearish")],
                key=lambda x: x.confidence_score, reverse=True
            )[:5]

            # 4. Sector breakdown (FIX: single batch JOIN instead of N+1 per-asset lookups)
            asset_ids = [r.asset_id for r in company_reports]
            asset_sectors_result = await session.execute(
                select(Asset.id, Asset.sector).where(Asset.id.in_(asset_ids))
            )
            asset_sector_map = {row[0]: (row[1] or "Unknown") for row in asset_sectors_result.fetchall()}

            sector_map = {}
            for r in company_reports:
                s = asset_sector_map.get(r.asset_id, "Unknown")
                if s not in sector_map:
                    sector_map[s] = {"count": 0, "score": 0}
                sector_map[s]["count"] += 1
                sector_map[s]["score"] += sentiment_scores.get(r.overall_sentiment, 3)

            sector_summary = []
            for sec, data in sorted(sector_map.items(), key=lambda x: x[1]["score"] / x[1]["count"], reverse=True):
                avg_s = data["score"] / data["count"]
                if avg_s >= 4: s_sentiment = "Bullish"
                elif avg_s >= 3: s_sentiment = "Neutral"
                else: s_sentiment = "Bearish"
                sector_summary.append(f"{sec}: {s_sentiment} ({data['count']} companies)")

            # Collect top headlines from recent articles
            recent_articles = await session.execute(
                select(NewsArticle.title, NewsArticle.ticker)
                .where(NewsArticle.pub_date >= datetime.utcnow() - timedelta(days=1))
                .order_by(NewsArticle.pub_date.desc())
                .limit(5)
            )
            top_headlines = [f"{a[0]} ({a[1]})" for a in recent_articles.fetchall()]

            report_dict = {
                "report_type": "daily_market",
                "overall_sentiment": overall_sentiment,
                "risk_level": risk_level,
                "confidence_score": avg_confidence,
                "total_companies_analyzed": len(company_reports),
                "sector_breakdown": sector_summary,
                "top_bullish": [r.ticker for r in bullish_companies],
                "top_bearish": [r.ticker for r in bearish_companies],
                "major_headlines": top_headlines[:5] if top_headlines else ["No major headlines today"],
                "actionable_insights": [
                    f"Market sentiment is {overall_sentiment.lower()} with a risk level of {risk_level}.",
                    f"Bullish leaders: {', '.join([r.ticker for r in bullish_companies]) or 'No strong bullish signals'}",
                    f"Bearish laggards: {', '.join([r.ticker for r in bearish_companies]) or 'No strong bearish signals'}",
                ],
                "executive_summary": (
                    f"Daily market intelligence based on {len(company_reports)} companies. "
                    f"Overall sentiment: {overall_sentiment.lower()}, Risk level: {risk_level}. "
                    f"Average confidence: {avg_confidence}/100."
                ),
            }

            # 5. Store daily market report
            today = datetime.utcnow().date()
            existing = await session.execute(
                select(AIMarketReport).where(
                    func.date(AIMarketReport.report_date) == today
                )
            )

            existing_report = existing.scalar_one_or_none()

            if existing_report:
                existing_report.report_data = report_dict
                existing_report.overall_sentiment = overall_sentiment
                existing_report.risk_level = risk_level
                existing_report.confidence_score = avg_confidence
                logger.info("[AIWorker] Updated daily market report for %s", today)
            else:
                new_report = AIMarketReport(
                    report_date=datetime.utcnow(),
                    report_data=report_dict,
                    overall_sentiment=overall_sentiment,
                    risk_level=risk_level,
                    confidence_score=avg_confidence,
                    model_used="aggregated_market_intelligence",
                    prompt_version="1.0",
                )
                session.add(new_report)
                logger.info("[AIWorker] Created daily market report for %s", today)

            await session.commit()

        return {
            "sentiment": overall_sentiment,
            "risk_level": risk_level,
            "confidence": avg_confidence,
            "companies_analyzed": len(company_reports),
        }


# ------------------------------------------------------------------
# Queue helper — enqueue a job
# ------------------------------------------------------------------
async def enqueue_job(session: AsyncSession, job_type: str, target_type: str, target_id: int, payload: Optional[dict] = None, priority: int = 10) -> bool:
    """Enqueue an AI processing job. Returns True if queued."""
    from backend.models.ai_job_queue import AIJobQueue

    # Deduplicate: check for existing pending/processing job for same target+type
    exists_stmt = (
        select(AIJobQueue.id)
        .where(
            and_(
                AIJobQueue.job_type == job_type,
                AIJobQueue.target_type == target_type,
                AIJobQueue.target_id == target_id,
                AIJobQueue.status.in_(["pending", "processing"]),
            )
        )
        .limit(1)
    )
    exists_result = await session.execute(exists_stmt)
    if exists_result.scalar_one_or_none():
        logger.debug("[AIWorker] Job %s for %s:%d already pending, skipping", job_type, target_type, target_id)
        return False

    job = AIJobQueue(
        job_type=job_type,
        target_type=target_type,
        target_id=target_id,
        payload=payload or {},
        priority=priority,
        status="pending",
    )
    session.add(job)
    await session.commit()
    logger.info("[AIWorker] Enqueued %s for %s:%d (priority=%d)", job_type, target_type, target_id, priority)
    return True


# ------------------------------------------------------------------
# Daily market report scheduler
# ------------------------------------------------------------------
async def _daily_market_report_loop(get_session_factory):
    """Background loop that enqueues one market_report job per day."""
    from zoneinfo import ZoneInfo
    est = ZoneInfo("US/Eastern")
    last_date = None

    while True:
        now_est = datetime.now(est)
        current_date = now_est.date()

        # Only enqueue once per calendar day
        if last_date != current_date:
            try:
                async with get_session_factory() as session:
                    await enqueue_job(
                        session=session,
                        job_type="market_report",
                        target_type="market",
                        target_id=0,
                        payload={"date": str(current_date)},
                        priority=5,
                    )
                last_date = current_date
                logger.info("[MarketScheduler] Enqueued daily market report for %s", current_date)
            except Exception:
                logger.exception("[MarketScheduler] Failed to enqueue market report")

        # Sleep 1 hour between checks
        await asyncio.sleep(3600)
