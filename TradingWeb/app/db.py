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


def get_run(run_id: int, username: str) -> Optional[Dict[str, Any]]:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM runs WHERE id = ? AND username = ?", (run_id, username)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_runs(username: str, limit: int, offset: int) -> tuple[List[Dict[str, Any]], int]:
    conn = connect()
    try:
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


def delete_run(run_id: int, username: str) -> bool:
    conn = connect()
    try:
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
