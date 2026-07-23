"""Test environment defaults loaded before backend modules are imported."""

import os
import sys
from pathlib import Path


STOCKS_ROOT = Path(__file__).resolve().parents[1]
if str(STOCKS_ROOT) not in sys.path:
    sys.path.insert(0, str(STOCKS_ROOT))

os.environ.setdefault("APP_ACCESS_TOKEN", "test-app-token")
os.environ.setdefault("MAINTENANCE_API_TOKEN", "test-maintenance-token")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("AI_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_MODEL", "test-ollama")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")
os.environ.setdefault("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")