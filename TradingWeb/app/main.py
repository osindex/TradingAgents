"""TradingWeb FastAPI application.

Run from the TradingWeb directory:
    uvicorn app.main:app --port 8731
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tradingweb")

_TRADINGWEB_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _TRADINGWEB_DIR.parent
_STATIC_DIR = _TRADINGWEB_DIR / "static"

# Make `import tradingagents` work without installing the package.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_dotenv(path: Path) -> None:
    """Minimal .env parser (repo does not depend on python-dotenv)."""
    if not path.is_file():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as exc:
        logger.warning("Could not read .env at %s: %s", path, exc)


_load_dotenv(_REPO_ROOT / ".env")

from . import db  # noqa: E402
from .auth import (  # noqa: E402
    check_credentials,
    clear_session_cookie,
    is_admin,
    require_user,
    set_session_cookie,
)
from .options import (  # noqa: E402
    detect_asset_type,
    default_provider_profiles,
    get_model_options_payload,
    get_options_payload,
    known_provider_keys,
    provider_default_base_url,
    validate_ticker,
)
from .runtime_paths import (
    checkpoint_dir,
    checkpoint_root,
    memory_log_path,
)
from .runner import initial_agent_statuses, start_run_thread  # noqa: E402
from .runner import cancel_run  # noqa: E402
from .schemas import (  # noqa: E402
    BatchRunRequest,
    BatchRunResponse,
    CreateRunRequest,
    CreateRunResponse,
    LoginRequest,
    LoginResponse,
    RunDetailResponse,
    RunListResponse,
    RunSummary,
    StepItem,
    StepsResponse,
)

MOCK_MODE = os.environ.get("TRADINGWEB_MOCK", "").strip() in ("1", "true", "yes", "on")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VALID_ANALYSTS = {"market", "social", "news", "fundamentals"}

app = FastAPI(title="TradingWeb", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    db.ensure_provider_profiles(default_provider_profiles())
    # Runs execute on in-memory daemon threads, so a restart leaves any
    # in-flight run stuck in 'running'/'pending' forever. Reconcile them to a
    # terminal 'error' state on boot so the UI is never stuck.
    reconciled = db.reconcile_orphaned_runs()
    if reconciled:
        logger.warning(
            "Reconciled %d orphaned run(s) left 'running'/'pending' by a previous restart",
            reconciled,
        )
    if MOCK_MODE:
        logger.info("TradingWeb running in MOCK mode (TRADINGWEB_MOCK=1)")


# ------------------------------------------------------------------- auth

@app.post("/api/login", response_model=LoginResponse)
def login(body: LoginRequest, response: Response) -> LoginResponse:
    if not check_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    set_session_cookie(response, body.username)
    return LoginResponse(username=body.username)


@app.post("/api/logout", status_code=204)
def logout(response: Response) -> Response:
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@app.get("/api/me", response_model=LoginResponse)
def me(username: str = Depends(require_user)) -> LoginResponse:
    return LoginResponse(username=username)


# ---------------------------------------------------------------- options

@app.get("/api/options")
def options(username: str = Depends(require_user)) -> Dict[str, Any]:
    payload = get_options_payload(MOCK_MODE)
    payload["provider_profiles"] = [
        {
            "id": p["id"],
            "name": p["name"],
            "label": p["name"],
            "provider_key": p["provider_key"],
            "base_url": p.get("base_url") if is_admin(username) else None,
            "api_key_env": p.get("api_key_env") if is_admin(username) else None,
            "quick_think_llm": p.get("quick_think_llm"),
            "deep_think_llm": p.get("deep_think_llm"),
            "output_language": p.get("output_language"),
            "google_thinking_level": p.get("google_thinking_level"),
            "openai_reasoning_effort": p.get("openai_reasoning_effort"),
            "anthropic_effort": p.get("anthropic_effort"),
            "enabled": bool(p.get("enabled", 1)),
        }
        for p in db.list_provider_profiles()
    ]
    return payload


@app.get("/api/options/models")
def model_options(
    provider: str = Query(...), username: str = Depends(require_user)
) -> Dict[str, Any]:
    return get_model_options_payload(provider)


@app.get("/api/provider-profiles")
def provider_profiles(username: str = Depends(require_user)) -> Dict[str, Any]:
    if not is_admin(username):
        raise HTTPException(status_code=403, detail="Admin only")
    return {"profiles": db.list_provider_profiles()}


@app.post("/api/provider-profiles", response_model=Dict[str, Any], status_code=201)
def create_provider_profile(body: Dict[str, Any], username: str = Depends(require_user)) -> Dict[str, Any]:
    if not is_admin(username):
        raise HTTPException(status_code=403, detail="Admin only")
    profile_id = db.create_provider_profile(body)
    profile = db.get_provider_profile(profile_id)
    return profile or {"id": profile_id}


@app.put("/api/provider-profiles/{profile_id}")
def update_provider_profile(profile_id: int, body: Dict[str, Any], username: str = Depends(require_user)) -> Dict[str, Any]:
    if not is_admin(username):
        raise HTTPException(status_code=403, detail="Admin only")
    if not db.update_provider_profile(profile_id, body):
        raise HTTPException(status_code=404, detail="Provider profile not found")
    profile = db.get_provider_profile(profile_id)
    return profile or {"id": profile_id}


@app.delete("/api/provider-profiles/{profile_id}", status_code=204)
def remove_provider_profile(profile_id: int, username: str = Depends(require_user)) -> Response:
    if not is_admin(username):
        raise HTTPException(status_code=403, detail="Admin only")
    if not db.delete_provider_profile(profile_id):
        raise HTTPException(status_code=404, detail="Provider profile not found")
    return Response(status_code=204)


# ------------------------------------------------------------------- runs

def _validate_run_request(body: CreateRunRequest) -> tuple[str, list[str], Dict[str, Any]]:
    """Validate; return (asset_type, ordered analyst keys, resolved profile). Raises 400."""
    ticker = body.ticker.strip().upper()
    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail="Invalid ticker: alphanumeric plus . _ - ^ only, max 32 chars",
        )
    if not _DATE_RE.match(body.analysis_date):
        raise HTTPException(status_code=400, detail="analysis_date must be YYYY-MM-DD")
    try:
        datetime.strptime(body.analysis_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="analysis_date is not a valid date")

    analysts = [a.lower() for a in body.analysts]
    unknown = [a for a in analysts if a not in _VALID_ANALYSTS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown analysts: {unknown}")
    if not analysts:
        raise HTTPException(status_code=400, detail="Select at least one analyst")

    asset_type = detect_asset_type(ticker)
    if asset_type == "crypto" and "fundamentals" in analysts:
        raise HTTPException(
            status_code=400,
            detail="Fundamentals analyst is not available for crypto tickers",
        )

    if body.research_depth not in (1, 3, 5):
        raise HTTPException(status_code=400, detail="research_depth must be 1, 3 or 5")

    profile: Dict[str, Any] = {}
    if body.provider_profile_id is not None:
        profile = db.get_provider_profile(body.provider_profile_id) or {}
        if not profile:
            raise HTTPException(status_code=400, detail=f"Unknown provider_profile_id: {body.provider_profile_id}")

    provider = (profile.get("provider_key") or body.llm_provider).lower()
    if provider not in known_provider_keys():
        raise HTTPException(status_code=400, detail=f"Unknown llm_provider: {provider}")

    quick_model = (profile.get("quick_think_llm") or body.quick_think_llm).strip()
    deep_model = (profile.get("deep_think_llm") or body.deep_think_llm).strip()
    if not quick_model or not deep_model:
        raise HTTPException(status_code=400, detail="Both quick and deep models are required")

    # API key presence check (real mode only; ollama needs no key).
    if not MOCK_MODE and provider != "ollama":
        try:
            from tradingagents.llm_clients.api_key_env import get_api_key_env

            env_var = get_api_key_env(provider)
        except ImportError:
            env_var = None
        if env_var and not os.environ.get(env_var):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Missing API key for provider '{provider}': set {env_var} "
                    "in the server environment (.env)"
                ),
            )

    # Preserve canonical order: market, social, news, fundamentals.
    ordered = [a for a in ("market", "social", "news", "fundamentals") if a in analysts]
    # Non-admin users must choose from admin-managed provider profiles only.
    if not body.provider_profile_id:
        raise HTTPException(status_code=403, detail="provider_profile_id is required; raw provider config is admin-only")
    return asset_type, ordered, profile


@app.post("/api/runs", status_code=201, response_model=CreateRunResponse)
def create_run(
    body: CreateRunRequest, username: str = Depends(require_user)
) -> CreateRunResponse:
    asset_type, analyst_keys, profile = _validate_run_request(body)
    ticker = body.ticker.strip().upper()
    provider = (profile.get("provider_key") or body.llm_provider).lower()
    backend_url = profile.get("base_url") or body.backend_url or provider_default_base_url(provider)
    quick_model = (profile.get("quick_think_llm") or body.quick_think_llm).strip()
    deep_model = (profile.get("deep_think_llm") or body.deep_think_llm).strip()
    provider_profile_id = profile.get("id") if profile else body.provider_profile_id
    provider_profile_name = profile.get("name") if profile else None

    selections: Dict[str, Any] = body.model_dump()
    selections["ticker"] = ticker
    selections["llm_provider"] = provider
    selections["backend_url"] = backend_url
    selections["provider_profile_id"] = provider_profile_id
    selections["provider_profile_name"] = provider_profile_name
    selections["quick_think_llm"] = quick_model
    selections["deep_think_llm"] = deep_model
    selections["analysts"] = analyst_keys

    config_summary = {
        "llm_provider": provider,
        "backend_url": backend_url,
        "provider_profile_id": provider_profile_id,
        "provider_profile_name": provider_profile_name,
        "quick_think_llm": quick_model,
        "deep_think_llm": deep_model,
        "max_debate_rounds": body.research_depth,
        "max_risk_discuss_rounds": body.research_depth,
        "output_language": body.output_language,
        "google_thinking_level": body.google_thinking_level,
        "openai_reasoning_effort": body.openai_reasoning_effort,
        "anthropic_effort": body.anthropic_effort,
        "checkpoint_enabled": bool(body.checkpoint_enabled),
    }
    if body.checkpoint_enabled and username:
        config_summary["checkpoint_dir"] = str(checkpoint_dir(username))
    if username:
        config_summary["memory_log_path"] = str(memory_log_path(username))

    run_id = db.create_run(
        username=username,
        ticker=ticker,
        analysis_date=body.analysis_date,
        asset_type=asset_type,
        config=config_summary,
        selections=selections,
        agent_statuses=initial_agent_statuses(analyst_keys),
    )
    start_run_thread(run_id, username, selections, asset_type, analyst_keys, MOCK_MODE)
    return CreateRunResponse(id=run_id)


@app.post("/api/runs/batch", response_model=BatchRunResponse, status_code=201)
def batch_run(body: BatchRunRequest, username: str = Depends(require_user)) -> BatchRunResponse:
    ids: list[int] = []
    for ticker in body.tickers:
        single = CreateRunRequest(
            ticker=ticker,
            analysis_date=body.analysis_date,
            analysts=body.analysts,
            research_depth=body.research_depth,
            provider_profile_id=body.provider_profile_id,
            llm_provider=body.llm_provider,
            backend_url=body.backend_url,
            quick_think_llm=body.quick_think_llm,
            deep_think_llm=body.deep_think_llm,
            output_language=body.output_language,
            google_thinking_level=body.google_thinking_level,
            openai_reasoning_effort=body.openai_reasoning_effort,
            anthropic_effort=body.anthropic_effort,
            checkpoint_enabled=body.checkpoint_enabled,
        )
        resp = create_run(single, username)
        ids.append(resp.id)
    return BatchRunResponse(ids=ids)


@app.post("/api/runs/{run_id}/rerun", status_code=201, response_model=CreateRunResponse)
def rerun_with_previous_config(run_id: int, username: str = Depends(require_user)) -> CreateRunResponse:
    run = _get_owned_run(run_id, username)
    selections = _json_or_empty(run.get("selections_json"))
    if not selections:
        raise HTTPException(status_code=400, detail="Run has no stored configuration")
    body = CreateRunRequest(**{k: v for k, v in selections.items() if k in CreateRunRequest.model_fields})
    if not body.provider_profile_id:
        raise HTTPException(status_code=400, detail="Cannot rerun legacy runs without provider_profile_id")
    return create_run(body, username)


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: int, format: str = Query("json"), username: str = Depends(require_user)) -> Response:
    run = _get_owned_run(run_id, username)
    if format == "json":
        payload = {
            "run": run,
            "reports": db.get_reports(run_id),
            "steps": db.get_steps(run_id),
        }
        return JSONResponse(payload)
    if format == "md":
        reports = db.get_reports(run_id)
        lines = [f"# TradingWeb Run {run_id}", ""]
        lines.append(f"- Ticker: {run['ticker']}")
        lines.append(f"- Date: {run['analysis_date']}")
        lines.append(f"- Status: {run['status']}")
        lines.append(f"- Decision: {run.get('decision') or '—'}")
        lines.append("")
        for key, value in reports.items():
            lines.append(f"## {key}")
            lines.append(str(value or ""))
            lines.append("")
        return Response(content="\n".join(lines), media_type="text/markdown; charset=utf-8")
    raise HTTPException(status_code=400, detail="format must be json or md")


@app.get("/api/memory")
def list_memory(username: str = Depends(require_user)) -> Dict[str, Any]:
    path = memory_log_path(username)
    if not path.exists():
        return {"path": str(path), "entries": []}
    try:
        from tradingagents.agents.utils.memory import TradingMemoryLog

        log = TradingMemoryLog({"memory_log_path": str(path)})
        return {"path": str(path), "entries": log.load_entries()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to read memory: {exc}") from exc


@app.delete("/api/memory", status_code=204)
def clear_memory(username: str = Depends(require_user)) -> Response:
    path = memory_log_path(username)
    if path.exists():
        path.unlink()
    return Response(status_code=204)


@app.get("/api/checkpoints")
def checkpoint_info(
    scope: str = Query("self"),
    username: str = Depends(require_user),
) -> Dict[str, Any]:
    """List checkpoint DBs for the current user (or all users for admins).

    Each user only ever sees their own checkpoints. Admins may pass
    ``?scope=all`` to inspect every user's checkpoints for maintenance.
    """
    if scope == "all" and is_admin(username):
        root = checkpoint_root()
        # Layout: <root>/<user>/checkpoints/<TICKER>.db
        files = sorted(str(p) for p in root.glob("*/checkpoints/*.db")) if root.exists() else []
        return {"scope": "all", "files": files}

    cp_dir = checkpoint_dir(username)
    if not cp_dir.exists():
        return {"scope": "self", "directory": str(cp_dir), "files": []}
    files = sorted(str(p) for p in cp_dir.glob("*.db"))
    return {"scope": "self", "directory": str(cp_dir), "files": files}


@app.delete("/api/checkpoints", status_code=204)
def clear_checkpoints(username: str = Depends(require_user)) -> Response:
    """Clear only the current user's checkpoints."""
    cp_dir = checkpoint_dir(username)
    if cp_dir.exists():
        for p in cp_dir.glob("*.db"):
            p.unlink()
    return Response(status_code=204)


@app.get("/api/batch")
def batch_placeholder(username: str = Depends(require_user)) -> Dict[str, Any]:
    return {"status": "available", "note": "Use /api/runs/batch"}


def _json_or_empty(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _selection_field(run: Dict[str, Any], key: str) -> Optional[str]:
    return _json_or_empty(run.get("selections_json")).get(key)


@app.get("/api/runs", response_model=RunListResponse)
def list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    username: str = Depends(require_user),
) -> RunListResponse:
    rows, total = db.list_runs(None if is_admin(username) else username, limit, offset)
    runs = []
    for row in rows:
        sel = _json_or_empty(row.get("selections_json"))
        runs.append(
            RunSummary(
                id=row["id"],
                username=row.get("username"),
                ticker=row["ticker"],
                analysis_date=row["analysis_date"],
                asset_type=row["asset_type"],
                status=row["status"],
                decision=row.get("decision"),
                provider_profile_id=sel.get("provider_profile_id"),
                provider_profile_name=sel.get("provider_profile_name"),
                llm_provider=sel.get("llm_provider"),
                deep_think_llm=sel.get("deep_think_llm"),
                quick_think_llm=sel.get("quick_think_llm"),
                created_at=row["created_at"],
                finished_at=row.get("finished_at"),
            )
        )
    return RunListResponse(runs=runs, total=total)


def _get_owned_run(run_id: int, username: str) -> Dict[str, Any]:
    run = db.get_run(run_id, None if is_admin(username) else username)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/runs/{run_id}", response_model=RunDetailResponse)
def run_detail(run_id: int, username: str = Depends(require_user)) -> RunDetailResponse:
    run = _get_owned_run(run_id, username)
    return RunDetailResponse(
        id=run["id"],
        username=run.get("username"),
        ticker=run["ticker"],
        analysis_date=run["analysis_date"],
        asset_type=run["asset_type"],
        status=run["status"],
        decision=run.get("decision"),
        error=run.get("error"),
        provider_profile_id=_json_or_empty(run.get("selections_json")).get("provider_profile_id"),
        provider_profile_name=_json_or_empty(run.get("selections_json")).get("provider_profile_name"),
        created_at=run["created_at"],
        finished_at=run.get("finished_at"),
        selections=_json_or_empty(run.get("selections_json")),
        agent_statuses=_json_or_empty(run.get("agent_statuses_json")),
        reports=db.get_reports(run_id),
    )


@app.get("/api/runs/{run_id}/steps", response_model=StepsResponse)
def run_steps(
    run_id: int,
    after_id: int = Query(0, ge=0),
    username: str = Depends(require_user),
) -> StepsResponse:
    run = _get_owned_run(run_id, username)
    steps = db.get_steps(run_id, after_id=after_id, limit=500)
    return StepsResponse(
        steps=[StepItem(**s) for s in steps],
        status=run["status"],
        decision=run.get("decision"),
        agent_statuses=_json_or_empty(run.get("agent_statuses_json")),
        reports=db.get_reports(run_id),
    )


@app.delete("/api/runs/{run_id}", status_code=204)
def remove_run(run_id: int, username: str = Depends(require_user)) -> Response:
    if not db.delete_run(run_id, None if is_admin(username) else username):
        raise HTTPException(status_code=404, detail="Run not found")
    return Response(status_code=204)


@app.post("/api/runs/{run_id}/cancel", status_code=204)
def cancel_existing_run(run_id: int, username: str = Depends(require_user)) -> Response:
    run = _get_owned_run(run_id, username)
    if run["status"] not in ("pending", "running"):
        return Response(status_code=204)
    cancel_run(run_id)
    db.update_run(run_id, status="error", error="Run cancelled by user", finished_at=db.utc_now_iso())
    return Response(status_code=204)


# ----------------------------------------------------------- static / SPA

_PLACEHOLDER_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>TradingWeb</title></head>
<body><h1>TradingWeb backend is running</h1>
<p>The frontend has not been built yet (TradingWeb/static/index.html missing).
The API is available under <code>/api</code>.</p></body></html>"""

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> Response:
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    index = _STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return HTMLResponse(_PLACEHOLDER_HTML)
