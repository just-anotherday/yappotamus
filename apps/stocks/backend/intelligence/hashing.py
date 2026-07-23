"""Canonical hashes used for generation reuse and source-set identity."""

import hashlib
import json
from typing import Any, Iterable


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_set_hash(article_intelligence_ids: Iterable[int]) -> str:
    return canonical_hash(sorted(set(article_intelligence_ids)))