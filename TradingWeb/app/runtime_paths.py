"""Helpers for per-user/per-run filesystem paths used by TradingWeb.

Keeping this in a tiny shared module lets the Web runner and the CLI launcher
agree on where user-isolated memory logs and checkpoint data live without
changing the upstream TradingAgents framework.
"""

from __future__ import annotations

import os
from pathlib import Path


def _db_parent_dir() -> Path:
    db_path = os.environ.get("TRADINGWEB_DB_PATH")
    if db_path:
        return Path(db_path).expanduser().resolve().parent
    return Path(__file__).resolve().parent.parent / "data"


def safe_username(username: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in username)


def memory_log_path(username: str) -> Path:
    return _db_parent_dir() / "memory" / safe_username(username) / "trading_memory.md"


def checkpoint_dir() -> Path:
    return _db_parent_dir() / "checkpoints"
