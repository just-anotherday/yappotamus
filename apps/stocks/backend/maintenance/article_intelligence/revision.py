"""Production-owned revision allocation boundary."""

from typing import Protocol

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.intelligence import ArticleIntelligence


class RevisionAllocator(Protocol):
    async def allocate(
        self, *, article_id: int, source_content_hash: str, prompt_hash: str, input_hash: str,
    ) -> int: ...


class PostgreSQLRevisionAllocator:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def allocate(
        self, *, article_id: int, source_content_hash: str, prompt_hash: str, input_hash: str,
    ) -> int:
        identity = f"{article_id}:{source_content_hash}:{prompt_hash}:{input_hash}"
        await self._session.execute(text(
            "SELECT pg_advisory_xact_lock(hashtext(:namespace), hashtext(:identity))"
        ), {"namespace": "article_intelligence_generation", "identity": identity})
        latest = (await self._session.execute(select(func.max(ArticleIntelligence.generation_revision)).where(
            ArticleIntelligence.article_id == article_id,
            ArticleIntelligence.source_content_hash == source_content_hash,
            ArticleIntelligence.prompt_hash == prompt_hash,
            ArticleIntelligence.input_hash == input_hash,
        ))).scalar_one_or_none() or 0
        return latest + 1