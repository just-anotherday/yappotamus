"""Environment-backed local configuration for Article Intelligence maintenance."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class MaintenanceCLIConfig:
    production_url: str
    api_token: str
    run_store_path: Path
    model: str
    timeout: float = 30.0

    @classmethod
    def load(cls, env_file: str | Path | None = None) -> "MaintenanceCLIConfig":
        load_dotenv(dotenv_path=env_file, override=False)
        production_url = os.getenv("MAINTENANCE_PRODUCTION_URL", "").strip()
        api_token = os.getenv("MAINTENANCE_API_TOKEN", "").strip()
        if not production_url:
            raise EnvironmentError("MAINTENANCE_PRODUCTION_URL is required")
        if not api_token:
            raise EnvironmentError("MAINTENANCE_API_TOKEN is required")
        model = os.getenv("MAINTENANCE_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2")).strip()
        if not model:
            raise EnvironmentError("MAINTENANCE_OLLAMA_MODEL must not be empty")
        path = Path(os.getenv("MAINTENANCE_RUN_STORE_PATH", ".maintenance/article-intelligence.sqlite3"))
        timeout = float(os.getenv("MAINTENANCE_HTTP_TIMEOUT_S", "30"))
        if timeout <= 0:
            raise EnvironmentError("MAINTENANCE_HTTP_TIMEOUT_S must be positive")
        return cls(production_url, api_token, path, model, timeout)
