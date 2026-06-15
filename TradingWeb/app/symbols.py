"""Symbol lookup/validation helpers for the new-analysis wizard.

This lives entirely in the TradingWeb layer and reuses yfinance (already
present in the image) plus the framework's deterministic identity resolver.
It does NOT modify the upstream framework, so shipping it only requires
rebuilding the web image.

Design notes from live testing against Yahoo Finance:
  * A-share Shanghai uses ``.SS`` (users often wrongly type ``.SH``).
  * A-share Shenzhen uses ``.SZ``.
  * Hong Kong uses ``.HK`` with the exchange's own zero-padding
    (e.g. Tencent is ``0700.HK``; ``700.HK`` / ``00700.HK`` do NOT resolve).
    So we never strip/pad HK codes ourselves — we search variants and let
    Yahoo's results decide which one is real.
  * US tickers carry no suffix.
  * Name search works for Latin names (``Tencent`` -> ``0700.HK``) but not
    Chinese text.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tradingweb.symbols")

# exchDisp (from yfinance search) -> coarse market bucket used by the UI.
_EXCH_TO_MARKET = {
    "Shanghai": "SH",
    "Shenzhen": "SZ",
    "Hong Kong": "HK",
    "NASDAQ": "US",
    "NYSE": "US",
    "NYSEArca": "US",
    "NYSE American": "US",
    "OTC Markets": "US",
}

# Quote types we surface as tradeable instruments (filter out currencies,
# options, etc. that pollute fuzzy results).
_ALLOWED_QUOTE_TYPES = {"EQUITY", "ETF", "MUTUALFUND", "INDEX", "CRYPTOCURRENCY"}


def _market_of(exch_disp: Optional[str]) -> str:
    if not exch_disp:
        return "OTHER"
    return _EXCH_TO_MARKET.get(exch_disp, "OTHER")


def _expand_query_variants(q: str, market: str) -> List[str]:
    """Build candidate query strings to work around common code mistakes.

    Pure A-share/HK numeric inputs frequently lack (or mis-spell) the suffix,
    so we probe a few plausible variants. Name searches and already-suffixed
    inputs are passed through unchanged (deduped first-wins downstream).
    """
    q = q.strip()
    variants: List[str] = [q]
    upper = q.upper()

    # Common A-share mistake: .SH should be .SS
    if upper.endswith(".SH"):
        variants.append(q[:-3] + ".SS")

    # Bare 6-digit Chinese A-share codes: guess the exchange by prefix.
    if re.fullmatch(r"\d{6}", q):
        if q[0] == "6":
            variants.append(f"{q}.SS")
        elif q[0] in ("0", "3"):
            variants.append(f"{q}.SZ")
        else:
            variants.extend([f"{q}.SS", f"{q}.SZ"])

    # Market hint from the UI selector adds a targeted suffix variant.
    if market == "SH" and not upper.endswith(".SS"):
        variants.append(f"{q}.SS")
    elif market == "SZ" and not upper.endswith(".SZ"):
        variants.append(f"{q}.SZ")
    elif market == "HK" and not upper.endswith(".HK"):
        variants.append(f"{q}.HK")

    # Dedup, preserve order.
    seen = set()
    out = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def search_symbols(query: str, market: str = "all", limit: int = 8) -> List[Dict[str, Any]]:
    """Return tradeable-instrument candidates for ``query``.

    ``market`` is one of ``all|US|HK|SH|SZ`` and filters results by exchange.
    Best-effort and fail-open: any yfinance error yields an empty list so the
    caller can degrade gracefully rather than erroring the request.
    """
    query = (query or "").strip()
    if not query:
        return []

    import yfinance as yf

    results: List[Dict[str, Any]] = []
    seen_symbols: set[str] = set()

    for variant in _expand_query_variants(query, market):
        try:
            search = yf.Search(query=variant, max_results=limit, enable_fuzzy_query=True)
            quotes = getattr(search, "quotes", []) or []
        except Exception as exc:  # noqa: BLE001 - fail open
            logger.debug("symbol search failed for %r: %s", variant, exc)
            continue

        for r in quotes:
            symbol = r.get("symbol")
            if not symbol or symbol in seen_symbols:
                continue
            quote_type = (r.get("quoteType") or "").upper()
            if quote_type and quote_type not in _ALLOWED_QUOTE_TYPES:
                continue
            exch_disp = r.get("exchDisp")
            mkt = _market_of(exch_disp)
            if market != "all" and mkt != market:
                continue
            seen_symbols.add(symbol)
            results.append({
                "symbol": symbol,
                "name": r.get("shortname") or r.get("longname") or "",
                "exchange": exch_disp or "",
                "type": quote_type or "",
                "market": mkt,
            })
            if len(results) >= limit:
                return results

    return results


def validate_symbol(symbol: str) -> Dict[str, Any]:
    """Validate a ticker via the framework's deterministic identity resolver.

    Returns ``{valid, symbol, company_name, exchange, sector, industry}``.
    ``valid`` is False when Yahoo has no data for the symbol (wrong code,
    delisted, or unsupported format).
    """
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"valid": False, "symbol": symbol}

    try:
        from tradingagents.agents.utils.agent_utils import resolve_instrument_identity

        identity = resolve_instrument_identity(symbol) or {}
    except Exception as exc:  # noqa: BLE001 - fail open
        logger.debug("symbol validation failed for %r: %s", symbol, exc)
        identity = {}

    valid = bool(identity.get("company_name"))
    return {
        "valid": valid,
        "symbol": symbol,
        "company_name": identity.get("company_name"),
        "exchange": identity.get("exchange"),
        "sector": identity.get("sector"),
        "industry": identity.get("industry"),
    }
