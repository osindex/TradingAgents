"""CLI launcher that reads provider profiles from SQLite and starts the
original tradingagents CLI without modifying CLI source code.

This is the escape hatch for users who want the web-managed provider
configuration to be reused by the existing CLI entrypoint.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

if __name__ == "__main__":
    _TRADINGWEB_DIR = Path(__file__).resolve().parent.parent
    _REPO_ROOT = _TRADINGWEB_DIR.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from . import db  # noqa: E402
from .runtime_paths import memory_log_path  # noqa: E402


def _load_profile(profile_id: Optional[int], profile_name: Optional[str]) -> Dict[str, Any]:
    profiles = db.list_provider_profiles()
    if profile_id is not None:
        for p in profiles:
            if int(p["id"]) == int(profile_id):
                return p
        raise SystemExit(f"Provider profile id not found: {profile_id}")
    if profile_name:
        for p in profiles:
            if p["name"] == profile_name:
                return p
        raise SystemExit(f"Provider profile not found: {profile_name}")
    if not profiles:
        raise SystemExit("No provider profiles available")
    return profiles[0]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Launch TradingAgents CLI using a stored provider profile")
    parser.add_argument("--profile-id", type=int, default=None, help="SQLite provider profile id")
    parser.add_argument("--profile", default=None, help="SQLite provider profile name")
    parser.add_argument("--username", default=None, help="TradingWeb username used to isolate memory logs")
    parser.add_argument("--", dest="separator", action="store_true")
    parser.add_argument("remainder", nargs=argparse.REMAINDER, help="Arguments passed to tradingagents CLI")
    args = parser.parse_args(argv)

    profile = _load_profile(args.profile_id, args.profile)
    env = os.environ.copy()

    env_var = profile.get("api_key_env")
    if env_var:
        value = env.get(env_var) or os.environ.get(env_var)
        if not value:
            raise SystemExit(f"Missing required API key env var for profile {profile['name']}: {env_var}")

    if profile.get("provider_key"):
        env["TRADINGAGENTS_LLM_PROVIDER"] = profile["provider_key"]
    if profile.get("base_url"):
        env["TRADINGAGENTS_LLM_BACKEND_URL"] = profile["base_url"]
    if profile.get("quick_think_llm"):
        env["TRADINGAGENTS_QUICK_THINK_LLM"] = profile["quick_think_llm"]
    if profile.get("deep_think_llm"):
        env["TRADINGAGENTS_DEEP_THINK_LLM"] = profile["deep_think_llm"]
    if profile.get("output_language"):
        env["TRADINGAGENTS_OUTPUT_LANGUAGE"] = profile["output_language"]
    if profile.get("google_thinking_level"):
        env["TRADINGAGENTS_GOOGLE_THINKING_LEVEL"] = profile["google_thinking_level"]
    if profile.get("openai_reasoning_effort"):
        env["TRADINGAGENTS_OPENAI_REASONING_EFFORT"] = profile["openai_reasoning_effort"]
    if profile.get("anthropic_effort"):
        env["TRADINGAGENTS_ANTHROPIC_EFFORT"] = profile["anthropic_effort"]

    username = args.username or os.environ.get("TRADINGWEB_USERNAME")
    if username:
        env["TRADINGAGENTS_MEMORY_LOG_PATH"] = str(memory_log_path(username))

    cmd = ["tradingagents"]
    if args.remainder:
        cmd.extend(args.remainder[1:] if args.remainder and args.remainder[0] == "--" else args.remainder)
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
