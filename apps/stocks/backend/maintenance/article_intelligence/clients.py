"""Thin local HTTP clients for the production maintenance protocol."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from backend.maintenance.article_intelligence.contracts import (
    ExportArticle, ExportSessionCreate, ImportBatchRequest, ImportOutcome,
)
from backend.maintenance.article_intelligence.prompts import PromptCompatibility


class MaintenanceClientError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class _BaseClient:
    def __init__(self, base_url: str, token: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport
        self.timeout = timeout

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, transport=self.transport, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.token}"},
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise MaintenanceClientError(str(exc), retryable=True) from exc
        if response.is_error:
            retryable = response.status_code in {408, 425, 429, 500, 502, 503, 504}
            try:
                body = response.json() if response.content else {}
                detail = body.get("detail", response.text) if isinstance(body, dict) else response.text
            except ValueError:
                detail = response.text or response.reason_phrase
            raise MaintenanceClientError(str(detail)[:1000], retryable=retryable, status_code=response.status_code)
        return response.json()


class PromptCompatibilityClient(_BaseClient):
    async def get(self) -> PromptCompatibility:
        return PromptCompatibility.model_validate(await self._request(
            "GET", "/api/maintenance/article-intelligence/v1/prompt-compatibility",
        ))


class ExportClient(_BaseClient):
    async def create(self, request: ExportSessionCreate) -> dict:
        return await self._request(
            "POST", "/api/maintenance/article-intelligence/v1/export-sessions",
            json=request.model_dump(mode="json"),
        )

    async def items(self, batch_id: UUID, *, page_size: int = 50) -> list[ExportArticle]:
        offset = 0
        result: list[ExportArticle] = []
        while True:
            payload = await self._request(
                "GET", f"/api/maintenance/article-intelligence/v1/export-sessions/{batch_id}/items",
                params={"offset": offset, "limit": page_size},
            )
            page = [ExportArticle.model_validate(item) for item in payload["items"]]
            result.extend(page)
            if len(page) < page_size:
                return result
            offset += len(page)


class PublisherClient(_BaseClient):
    async def publish(self, request: ImportBatchRequest, *, dry_run: bool) -> list[ImportOutcome]:
        suffix = "/imports/dry-run" if dry_run else "/imports"
        payload = await self._request(
            "POST", f"/api/maintenance/article-intelligence/v1{suffix}",
            json=request.model_dump(mode="json"),
        )
        return [ImportOutcome.model_validate(item) for item in payload["outcomes"]]