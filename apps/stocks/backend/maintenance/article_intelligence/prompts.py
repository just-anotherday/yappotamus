"""Production-owned prompt compatibility registry."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from backend.intelligence.article_service import ARTICLE_PROMPT_HASH, ARTICLE_PROMPT_VERSION
from backend.maintenance.article_intelligence.contracts import Sha256, StrictContract


OUTPUT_CONTRACT_REVISION = "article-output.v1"
REGISTRY_REVISION = "article-prompts.v1"


class CompatiblePrompt(StrictContract):
    version: str = Field(min_length=1, max_length=40)
    hash: Sha256
    output_contract_revision: str = Field(min_length=1, max_length=40)
    status: Literal["current", "accepted"]


class PromptCompatibility(StrictContract):
    schema_version: Literal["article-intelligence-maintenance.v1"] = "article-intelligence-maintenance.v1"
    artifact_type: Literal["article_intelligence"] = "article_intelligence"
    current: CompatiblePrompt
    accepted_versions: list[CompatiblePrompt]
    minimum_supported_version: str
    registry_revision: str
    generated_at: datetime


class PromptCompatibilityRegistry:
    """Resolves only production-approved prompt definitions."""

    def compatibility(self) -> PromptCompatibility:
        current = CompatiblePrompt(
            version=ARTICLE_PROMPT_VERSION,
            hash=ARTICLE_PROMPT_HASH,
            output_contract_revision=OUTPUT_CONTRACT_REVISION,
            status="current",
        )
        return PromptCompatibility(
            current=current,
            accepted_versions=[current],
            minimum_supported_version=ARTICLE_PROMPT_VERSION,
            registry_revision=REGISTRY_REVISION,
            generated_at=datetime.now(timezone.utc),
        )

    def require_compatible(self, version: str, prompt_hash: str) -> CompatiblePrompt:
        version_match = next((item for item in self.compatibility().accepted_versions
                              if item.version == version), None)
        if version_match is None:
            raise UnknownPromptVersion("prompt version is not production-compatible")
        if version_match.hash != prompt_hash:
            raise PromptHashMismatch("prompt hash is not production-compatible with this prompt version")
        return version_match


class UnknownPromptVersion(ValueError):
    pass


class PromptHashMismatch(ValueError):
    pass