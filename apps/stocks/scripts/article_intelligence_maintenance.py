"""Executable adapter for the Article Intelligence maintenance CLI."""

from __future__ import annotations

import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from backend.maintenance.article_intelligence.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
