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
    """Shared root containing every user's per-user checkpoint base."""
    return _db_parent_dir() / "user-checkpoints"


def checkpoint_base(username: str | None = None) -> Path:
    """Per-user ``data_dir`` passed to the framework's checkpoint helpers.

    The upstream framework writes checkpoint DBs at ``<data_dir>/checkpoints/
    <TICKER>.db`` (see ``tradingagents/graph/checkpointer.py``). The web runner
    passes this per-user base as that ``data_dir`` so each user's checkpoints
    live under ``<root>/<user>/checkpoints/`` and never mix with other users —
    independent of the SHARED market-data cache (``data_cache_dir``).

    With no username (legacy callers) return the shared root.
    """
    if username:
        return checkpoint_root() / safe_username(username)
    return checkpoint_root()


def checkpoint_dir(username: str | None = None) -> Path:
    """Directory that actually holds this user's checkpoint ``*.db`` files.

    This is ``checkpoint_base(username)/checkpoints`` to match where the
    framework writes them; the API layer lists/clears files here.
    """
    return checkpoint_base(username) / "checkpoints"
