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


def checkpoint_root() -> Path:
    """Shared root that contains every user's per-user checkpoint directory."""
    return _db_parent_dir() / "checkpoints"


def checkpoint_dir(username: str | None = None) -> Path:
    """Checkpoint directory.

    When ``username`` is given, return that user's isolated directory so one
    user can never read or clear another user's checkpoints. With no username
    (legacy/global callers) return the shared root for backward compatibility.
    """
    if username:
        return checkpoint_root() / safe_username(username)
    return checkpoint_root()


def user_cache_dir(username: str) -> Path:
    """Per-user ``data_cache_dir`` for the TradingAgents framework.

    The upstream framework derives its checkpoint location from
    ``config["data_cache_dir"] + "/checkpoints"`` (see
    ``tradingagents/graph/checkpointer.py``). To isolate checkpoints per user
    without modifying the framework, we point each user at their own cache
    directory; the framework then writes ``<user-cache>/checkpoints/<TICKER>.db``
    under it.
    """
    return _db_parent_dir() / "user-cache" / safe_username(username)
