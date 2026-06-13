"""Cookie/HMAC session auth for TradingWeb.

Users come from TRADINGWEB_USERS ("alice:secret1,bob:secret2"); the session
cookie is base64(username|expiry_ts) + "." + hmac_sha256 hex signature.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Dict, Optional

from fastapi import HTTPException, Request, Response

logger = logging.getLogger("tradingweb.auth")

COOKIE_NAME = "tw_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600

_secret: Optional[bytes] = None
_users: Optional[Dict[str, str]] = None


def _load_secret() -> bytes:
    global _secret
    if _secret is None:
        raw = os.environ.get("TRADINGWEB_SECRET")
        if not raw:
            logger.warning(
                "TRADINGWEB_SECRET not set; using a random per-process secret "
                "(sessions will not survive a restart)."
            )
            raw = secrets.token_hex(32)
        _secret = raw.encode("utf-8")
    return _secret


def _load_users() -> Dict[str, str]:
    global _users
    if _users is None:
        raw = os.environ.get("TRADINGWEB_USERS", "")
        users: Dict[str, str] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            name, _, pw = pair.partition(":")
            if name:
                users[name] = pw
        if not users:
            logger.warning(
                "TRADINGWEB_USERS not set; falling back to default credentials "
                "admin:admin — set TRADINGWEB_USERS in production."
            )
            users = {"admin": "admin"}
        _users = users
    return _users


def check_credentials(username: str, password: str) -> bool:
    users = _load_users()
    expected = users.get(username)
    if expected is None:
        # Constant-time-ish dummy compare to avoid user enumeration timing.
        hmac.compare_digest(password, password)
        return False
    return hmac.compare_digest(expected.encode("utf-8"), password.encode("utf-8"))


def _sign(payload: bytes) -> str:
    return hmac.new(_load_secret(), payload, hashlib.sha256).hexdigest()


def make_session_token(username: str) -> str:
    expiry = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{username}|{expiry}".encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload).decode("ascii")
    return f"{b64}.{_sign(payload)}"


def parse_session_token(token: str) -> Optional[str]:
    """Return the username for a valid, unexpired token; else None."""
    try:
        b64, _, sig = token.partition(".")
        if not b64 or not sig:
            return None
        payload = base64.urlsafe_b64decode(b64.encode("ascii"))
        expected_sig = _sign(payload)
        if not hmac.compare_digest(expected_sig, sig):
            return None
        text = payload.decode("utf-8")
        username, _, expiry_str = text.rpartition("|")
        if not username or int(expiry_str) < time.time():
            return None
        return username
    except (ValueError, UnicodeDecodeError):
        return None


def set_session_cookie(response: Response, username: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_session_token(username),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def require_user(request: Request) -> str:
    """FastAPI dependency: return the logged-in username or raise 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = parse_session_token(token)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return username
