"""Static option tables (providers, analysts, depths, languages) and the
bridge to tradingagents' shared model catalog."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, List, Optional

CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")

REPORT_SECTIONS = [
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
]

LANGUAGES = [
    "English",
    "Chinese",
    "Japanese",
    "Korean",
    "Hindi",
    "Spanish",
    "Portuguese",
    "French",
    "German",
    "Arabic",
    "Russian",
]

ANALYSTS: List[Dict[str, Any]] = [
    {"key": "market", "label": "Market Analyst", "crypto_supported": True},
    {"key": "social", "label": "Sentiment Analyst", "crypto_supported": True},
    {"key": "news", "label": "News Analyst", "crypto_supported": True},
    {"key": "fundamentals", "label": "Fundamentals Analyst", "crypto_supported": False},
]

ANALYST_AGENT_LABELS = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}

DEPTHS = [
    {"value": 1, "label": "Shallow", "description": "Quick research, few debate and strategy discussion rounds"},
    {"value": 3, "label": "Medium", "description": "Middle ground, moderate debate rounds and strategy discussion"},
    {"value": 5, "label": "Deep", "description": "Comprehensive research, in-depth debate and strategy discussion"},
]


def _thinking(config_key: str, label: str, values: List[str], default: str) -> Dict[str, Any]:
    return {
        "config_key": config_key,
        "label": label,
        "options": [{"value": v, "label": v.capitalize()} for v in values],
        "default": default,
    }


def _providers() -> List[Dict[str, Any]]:
    ollama_url = os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    return [
        {"key": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1",
         "thinking": _thinking("openai_reasoning_effort", "Reasoning effort", ["medium", "high", "low"], "medium")},
        {"key": "google", "label": "Google (Gemini)", "base_url": None,
         "thinking": _thinking("google_thinking_level", "Thinking level", ["high", "minimal"], "high")},
        {"key": "anthropic", "label": "Anthropic (Claude)", "base_url": None,
         "thinking": _thinking("anthropic_effort", "Effort level", ["high", "medium", "low"], "high")},
        {"key": "xai", "label": "xAI (Grok)", "base_url": "https://api.x.ai/v1", "thinking": None},
        {"key": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com", "thinking": None},
        {"key": "qwen", "label": "Qwen (International)", "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "thinking": None},
        {"key": "qwen-cn", "label": "Qwen (China)", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "thinking": None},
        {"key": "glm", "label": "GLM (Z.AI International)", "base_url": "https://api.z.ai/api/paas/v4/", "thinking": None},
        {"key": "glm-cn", "label": "GLM (BigModel China)", "base_url": "https://open.bigmodel.cn/api/paas/v4/", "thinking": None},
        {"key": "minimax", "label": "MiniMax (Global)", "base_url": "https://api.minimax.io/v1", "thinking": None},
        {"key": "minimax-cn", "label": "MiniMax (China)", "base_url": "https://api.minimaxi.com/v1", "thinking": None},
        {"key": "openrouter", "label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "thinking": None},
        {"key": "ollama", "label": "Ollama (local)", "base_url": ollama_url, "thinking": None},
        {"key": "azure", "label": "Azure OpenAI", "base_url": os.environ.get("AZURE_OPENAI_ENDPOINT"), "thinking": None},
    ]


def known_provider_keys() -> List[str]:
    return [p["key"] for p in _providers()]


def provider_default_base_url(provider: str) -> Optional[str]:
    for p in _providers():
        if p["key"] == provider:
            return p["base_url"]
    return None


def detect_asset_type(ticker: str) -> str:
    upper = ticker.upper()
    return "crypto" if upper.endswith(CRYPTO_SUFFIXES) else "stock"


def validate_ticker(ticker: str) -> bool:
    if not ticker or len(ticker) > 32:
        return False
    return all(c.isalnum() or c in "._-^" for c in ticker)


def get_options_payload(mock: bool) -> Dict[str, Any]:
    return {
        "providers": _providers(),
        "analysts": ANALYSTS,
        "depths": DEPTHS,
        "languages": LANGUAGES,
        "defaults": {
            "ticker": "SPY",
            "analysis_date": date.today().strftime("%Y-%m-%d"),
        },
        "mock": mock,
    }


def get_model_options_payload(provider: str) -> Dict[str, Any]:
    """Normalize tradingagents' (label, value) tuples to [{value,label}].

    Never raises: azure / unknown providers return empty lists.
    """
    quick: List[Dict[str, str]] = []
    deep: List[Dict[str, str]] = []
    try:
        from tradingagents.llm_clients.model_catalog import get_model_options

        for mode, bucket in (("quick", quick), ("deep", deep)):
            try:
                for label, value in get_model_options(provider, mode):
                    if value == "custom":
                        # CLI sentinel for "type your own"; the web UI exposes
                        # allow_custom instead.
                        continue
                    bucket.append({"value": value, "label": label})
            except KeyError:
                bucket.clear()
    except ImportError:
        pass
    return {"quick": quick, "deep": deep, "allow_custom": True}
