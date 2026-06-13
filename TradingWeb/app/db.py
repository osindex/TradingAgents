"""SQLite persistence layer for TradingWeb.

Stdlib sqlite3 only. A new connection is opened per operation (WAL mode
makes this cheap and safe across the runner threads and request handlers).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tradingweb.db"

_init_lock = threading.Lock()
_initialized = False


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def db_path() -> Path:
    return Path(os.environ.get("TRADINGWEB_DB_PATH", str(_DEFAULT_DB_PATH)))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    ticker TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    config_json TEXT,
    selections_json TEXT,
    status TEXT NOT NULL,
    decision TEXT,
    error TEXT,
    agent_statuses_json TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    agent TEXT,
    content TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_steps_run_id_id ON run_steps(run_id, id);
CREATE TABLE IF NOT EXISTS run_reports (
    run_id INTEGER NOT NULL,
    section TEXT NOT NULL,
    content TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(run_id, section)
);
CREATE TABLE IF NOT EXISTS provider_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    provider_key TEXT NOT NULL,
    base_url TEXT,
    api_key_env TEXT,
    quick_think_llm TEXT NOT NULL,
    deep_think_llm TEXT NOT NULL,
    output_language TEXT NOT NULL DEFAULT 'English',
    google_thinking_level TEXT,
    openai_reasoning_effort TEXT,
    anthropic_effort TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def ensure_provider_profiles(default_profiles: List[Dict[str, Any]]) -> None:
    """Seed provider profiles once if the table is empty."""
    conn = connect()
    try:
        count = conn.execute("SELECT COUNT(*) FROM provider_profiles").fetchone()[0]
        if count:
            return
        now = utc_now_iso()
        for profile in default_profiles:
            conn.execute(
                "INSERT INTO provider_profiles "
                "(name, provider_key, base_url, api_key_env, quick_think_llm, deep_think_llm, "
                " output_language, google_thinking_level, openai_reasoning_effort, anthropic_effort, "
                " enabled, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    profile["name"],
                    profile["provider_key"],
                    profile.get("base_url"),
                    profile.get("api_key_env"),
                    profile["quick_think_llm"],
                    profile["deep_think_llm"],
                    profile.get("output_language", "English"),
                    profile.get("google_thinking_level"),
                    profile.get("openai_reasoning_effort"),
                    profile.get("anthropic_effort"),
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- runs

def create_run(
    username: str,
    ticker: str,
    analysis_date: str,
    asset_type: str,
    config: Dict[str, Any],
    selections: Dict[str, Any],
    agent_statuses: Dict[str, str],
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO runs (username, ticker, analysis_date, asset_type, config_json,"
            " selections_json, status, agent_statuses_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                username,
                ticker,
                analysis_date,
                asset_type,
                json.dumps(config, default=str),
                json.dumps(selections, default=str),
                json.dumps(agent_statuses),
                utc_now_iso(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def update_run(run_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    conn = connect()
    try:
        conn.execute(
            f"UPDATE runs SET {cols} WHERE id = ?",
            (*fields.values(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_agent_statuses(run_id: int, statuses: Dict[str, str]) -> None:
    update_run(run_id, agent_statuses_json=json.dumps(statuses))


def reconcile_orphaned_runs() -> int:
    """Mark runs left in-flight by a process restart as errored.

    Runs execute on in-memory daemon threads, so a container restart kills any
    'running'/'pending' run mid-flight without ever writing its terminal
    status. Such rows would otherwise stay 'running' forever. Called on
    startup: flip them to 'error' with an explanatory message and a
    finished_at, so the UI shows a final state and the user can re-run.
    Returns the number of rows reconciled.
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id FROM runs WHERE status IN ('running', 'pending')"
        ).fetchall()
        if not rows:
            return 0
        msg = (
            "Run interrupted by a server restart; the in-memory analysis "
            "thread did not survive. Please re-run."
        )
        now = utc_now_iso()
        conn.execute(
            "UPDATE runs SET status = 'error', error = ?, finished_at = ? "
            "WHERE status IN ('running', 'pending')",
            (msg, now),
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def get_run(run_id: int, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = connect()
    try:
        if username is None:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM runs WHERE id = ? AND username = ?", (run_id, username)
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_runs(
    username: Optional[str],
    limit: int,
    offset: int,
) -> tuple[List[Dict[str, Any]], int]:
    conn = connect()
    try:
        if username is None:
            total = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        else:
            total = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE username = ?", (username,)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT * FROM runs WHERE username = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (username, limit, offset),
            ).fetchall()
        return [dict(r) for r in rows], int(total)
    finally:
        conn.close()


def delete_run(run_id: int, username: Optional[str] = None) -> bool:
    conn = connect()
    try:
        if username is None:
            cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        else:
            cur = conn.execute(
                "DELETE FROM runs WHERE id = ? AND username = ?", (run_id, username)
            )
        if cur.rowcount == 0:
            conn.commit()
            return False
        conn.execute("DELETE FROM run_steps WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM run_reports WHERE run_id = ?", (run_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------------------------------------------------------- steps

def add_step(run_id: int, kind: str, agent: Optional[str], content: str) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO run_steps (run_id, ts, kind, agent, content) VALUES (?, ?, ?, ?, ?)",
            (run_id, utc_now_iso(), kind, agent, content),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def get_steps(run_id: int, after_id: int = 0, limit: int = 500) -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, ts, kind, agent, content FROM run_steps"
            " WHERE run_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
            (run_id, after_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# -------------------------------------------------------------- reports

def upsert_report(run_id: int, section: str, content: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO run_reports (run_id, section, content, updated_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(run_id, section) DO UPDATE SET content = excluded.content,"
            " updated_at = excluded.updated_at",
            (run_id, section, content, utc_now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def get_reports(run_id: int) -> Dict[str, str]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT section, content FROM run_reports WHERE run_id = ?", (run_id,)
        ).fetchall()
        return {r["section"]: r["content"] for r in rows}
    finally:
        conn.close()


# ---------------------------------------------------------- provider profiles

def list_provider_profiles() -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM provider_profiles WHERE enabled = 1 ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_provider_profile(profile_id: int) -> Optional[Dict[str, Any]]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM provider_profiles WHERE id = ? AND enabled = 1", (profile_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_provider_profile(values: Dict[str, Any]) -> int:
    conn = connect()
    try:
        now = utc_now_iso()
        cur = conn.execute(
            "INSERT INTO provider_profiles "
            "(name, provider_key, base_url, api_key_env, quick_think_llm, deep_think_llm, "
            " output_language, google_thinking_level, openai_reasoning_effort, anthropic_effort, "
            " enabled, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                values["name"],
                values["provider_key"],
                values.get("base_url"),
                values.get("api_key_env"),
                values["quick_think_llm"],
                values["deep_think_llm"],
                values.get("output_language", "English"),
                values.get("google_thinking_level"),
                values.get("openai_reasoning_effort"),
                values.get("anthropic_effort"),
                1 if values.get("enabled", True) else 0,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()


def update_provider_profile(profile_id: int, values: Dict[str, Any]) -> bool:
    if not values:
        return False
    values = dict(values)
    values["updated_at"] = utc_now_iso()
    cols = ", ".join(f"{k} = ?" for k in values)
    conn = connect()
    try:
        cur = conn.execute(
            f"UPDATE provider_profiles SET {cols} WHERE id = ?",
            (*values.values(), profile_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_provider_profile(profile_id: int) -> bool:
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM provider_profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
