"""Run execution: real (tradingagents graph stream) and mock modes.

Both modes share the same persistence layer (RunRecorder) so the DB shape
is identical whichever path produced it. Each run executes on its own
daemon thread; sqlite connections are opened per operation (see db.py).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

from . import db
from .options import ANALYST_AGENT_LABELS, REPORT_SECTIONS

logger = logging.getLogger("tradingweb.runner")

REPORT_TO_AGENT = {
    "market_report": "Market Analyst",
    "sentiment_report": "Sentiment Analyst",
    "news_report": "News Analyst",
    "fundamentals_report": "Fundamentals Analyst",
}

POST_ANALYST_AGENTS = [
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Neutral Analyst",
    "Conservative Analyst",
    "Portfolio Manager",
]

RESEARCH_TEAM = ["Bull Researcher", "Bear Researcher", "Research Manager"]
RISK_TEAM = ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"]


def initial_agent_statuses(analyst_keys: List[str]) -> Dict[str, str]:
    statuses: Dict[str, str] = {}
    for key in analyst_keys:
        statuses[ANALYST_AGENT_LABELS[key]] = "pending"
    for agent in POST_ANALYST_AGENTS:
        statuses[agent] = "pending"
    return statuses


class RunRecorder:
    """Shared persistence helper used by both the real and mock runners."""

    def __init__(self, run_id: int, agent_statuses: Dict[str, str]) -> None:
        self.run_id = run_id
        self.agent_statuses = dict(agent_statuses)
        self._seen_message_ids: set = set()
        self._report_history: Dict[str, str] = {}

    # -- steps ---------------------------------------------------------
    def info(self, content: str, agent: Optional[str] = None) -> None:
        db.add_step(self.run_id, "info", agent, content)

    def message(self, agent: Optional[str], content: str) -> None:
        db.add_step(self.run_id, "message", agent, content)

    def tool_call(self, name: str, args: Any) -> None:
        try:
            args_str = json.dumps(args, default=str)
        except (TypeError, ValueError):
            args_str = str(args)
        db.add_step(self.run_id, "tool_call", name, args_str)

    def error_step(self, content: str) -> None:
        db.add_step(self.run_id, "error", None, content)

    # -- agent statuses --------------------------------------------------
    def set_status(self, agent: str, status: str) -> None:
        if agent not in self.agent_statuses or self.agent_statuses[agent] == status:
            return
        self.agent_statuses[agent] = status
        db.add_step(self.run_id, "status", agent, status)
        db.set_agent_statuses(self.run_id, self.agent_statuses)

    def complete_all(self) -> None:
        for agent, status in self.agent_statuses.items():
            if status != "completed":
                self.set_status(agent, "completed")

    # -- reports ----------------------------------------------------------
    def report(self, section: str, content: str) -> None:
        if not content or self._report_history.get(section) == content:
            return
        self._report_history[section] = content
        db.upsert_report(self.run_id, section, content)
        db.add_step(self.run_id, "report_update", section, content)

    def append_report(self, section: str, heading: str, content: str) -> None:
        """CLI-style sectioned update: replace section with heading + content."""
        block = f"### {heading}\n{content}"
        existing = self._report_history.get(section, "")
        if heading in existing:
            # Heading already present: rebuild that block.
            parts = [p for p in existing.split("### ") if p.strip()]
            rebuilt: List[str] = []
            replaced = False
            for part in parts:
                if part.startswith(heading):
                    rebuilt.append(f"{heading}\n{content}")
                    replaced = True
                else:
                    rebuilt.append(part.rstrip("\n"))
            if not replaced:
                rebuilt.append(f"{heading}\n{content}")
            merged = "### " + "\n\n### ".join(rebuilt)
        else:
            merged = f"{existing}\n\n{block}".strip() if existing else block
        self.report(section, merged)

    # -- message dedupe -----------------------------------------------------
    def is_new_message(self, msg_id: Optional[str]) -> bool:
        if msg_id is None:
            return True
        if msg_id in self._seen_message_ids:
            return False
        self._seen_message_ids.add(msg_id)
        return True


def _normalize_content(content: Any) -> str:
    """Flatten LangChain message content (str or list of parts) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", item)))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content) if content is not None else ""


def _classify_agent(message: Any) -> str:
    """Best-effort label for a streamed message (Tool / Reasoning / name)."""
    msg_type = getattr(message, "type", "") or message.__class__.__name__.lower()
    if "tool" in msg_type:
        return "Tool"
    if "human" in msg_type:
        return "Human"
    if "system" in msg_type:
        return "System"
    name = getattr(message, "name", None)
    return name or "Reasoning"


# ====================================================================== real

def build_config(selections: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the tradingagents config dict from validated selections."""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = selections["llm_provider"]
    config["backend_url"] = selections.get("backend_url")
    config["quick_think_llm"] = selections["quick_think_llm"]
    config["deep_think_llm"] = selections["deep_think_llm"]
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["output_language"] = selections.get("output_language", "English")
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")
    config["anthropic_effort"] = selections.get("anthropic_effort")
    config["checkpoint_enabled"] = False
    return config


def _process_chunk(rec: RunRecorder, chunk: Dict[str, Any]) -> None:
    """Port of the CLI per-chunk processing (cli/main.py L1135-1231)."""
    # Messages (dedupe by id) + tool calls.
    for message in chunk.get("messages", []) or []:
        if not rec.is_new_message(getattr(message, "id", None)):
            continue
        content = _normalize_content(getattr(message, "content", "")).strip()
        if content:
            rec.message(_classify_agent(message), content)
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    rec.tool_call(tc.get("name", "tool"), tc.get("args", {}))
                else:
                    rec.tool_call(getattr(tc, "name", "tool"), getattr(tc, "args", {}))

    # Analyst report sections: section present + non-empty → analyst done.
    for section in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
        value = chunk.get(section)
        if value:
            rec.report(section, str(value))
            agent = REPORT_TO_AGENT[section]
            rec.set_status(agent, "completed")
    # Any analyst still pending while another finished → mark in_progress
    # only for the first pending one (sequential execution heuristic).
    analyst_agents = [a for a in rec.agent_statuses if a.endswith("Analyst") and a in REPORT_TO_AGENT.values()]
    if any(rec.agent_statuses[a] == "completed" for a in analyst_agents):
        for a in analyst_agents:
            if rec.agent_statuses[a] == "pending":
                rec.set_status(a, "in_progress")
                break

    # Research team / investment debate.
    debate = chunk.get("investment_debate_state")
    if debate:
        bull = (debate.get("bull_history") or "").strip()
        bear = (debate.get("bear_history") or "").strip()
        judge = (debate.get("judge_decision") or "").strip()
        if bull or bear:
            for agent in RESEARCH_TEAM:
                if rec.agent_statuses.get(agent) != "completed":
                    rec.set_status(agent, "in_progress")
        if bull:
            rec.append_report("investment_plan", "Bull Researcher Analysis", bull)
        if bear:
            rec.append_report("investment_plan", "Bear Researcher Analysis", bear)
        if judge:
            rec.append_report("investment_plan", "Research Manager Decision", judge)
            for agent in RESEARCH_TEAM:
                rec.set_status(agent, "completed")
            rec.set_status("Trader", "in_progress")

    # Trader.
    trader_plan = chunk.get("trader_investment_plan")
    if trader_plan:
        rec.report("trader_investment_plan", str(trader_plan))
        if rec.agent_statuses.get("Trader") != "completed":
            rec.set_status("Trader", "completed")
            rec.set_status("Aggressive Analyst", "in_progress")

    # Risk management team.
    risk = chunk.get("risk_debate_state")
    if risk:
        agg = (risk.get("aggressive_history") or "").strip()
        con = (risk.get("conservative_history") or "").strip()
        neu = (risk.get("neutral_history") or "").strip()
        judge = (risk.get("judge_decision") or "").strip()
        if agg:
            if rec.agent_statuses.get("Aggressive Analyst") != "completed":
                rec.set_status("Aggressive Analyst", "in_progress")
            rec.append_report("final_trade_decision", "Aggressive Analyst Analysis", agg)
        if con:
            if rec.agent_statuses.get("Conservative Analyst") != "completed":
                rec.set_status("Conservative Analyst", "in_progress")
            rec.append_report("final_trade_decision", "Conservative Analyst Analysis", con)
        if neu:
            if rec.agent_statuses.get("Neutral Analyst") != "completed":
                rec.set_status("Neutral Analyst", "in_progress")
            rec.append_report("final_trade_decision", "Neutral Analyst Analysis", neu)
        if judge and rec.agent_statuses.get("Portfolio Manager") != "completed":
            rec.set_status("Portfolio Manager", "in_progress")
            rec.append_report("final_trade_decision", "Portfolio Manager Decision", judge)
            for agent in RISK_TEAM:
                rec.set_status(agent, "completed")
            rec.set_status("Portfolio Manager", "completed")


def _run_real(
    rec: RunRecorder,
    ticker: str,
    analysis_date: str,
    asset_type: str,
    analyst_keys: List[str],
    selections: Dict[str, Any],
) -> str:
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = build_config(selections)
    rec.info(f"Initializing TradingAgentsGraph (provider={config['llm_provider']})")
    graph = TradingAgentsGraph(analyst_keys, config=config, debug=False)

    instrument_context = graph.resolve_instrument_context(ticker, asset_type)
    state = graph.propagator.create_initial_state(
        ticker,
        analysis_date,
        asset_type=asset_type,
        instrument_context=instrument_context,
    )
    args = graph.propagator.get_graph_args()

    first_analyst = ANALYST_AGENT_LABELS[analyst_keys[0]]
    rec.set_status(first_analyst, "in_progress")
    rec.info(f"Analyzing {ticker} on {analysis_date}...")

    final_state: Dict[str, Any] = {}
    for chunk in graph.graph.stream(state, **args):
        _process_chunk(rec, chunk)
        final_state.update(chunk)

    decision = graph.process_signal(final_state["final_trade_decision"])

    # Final report sections from merged state.
    for section in REPORT_SECTIONS:
        value = final_state.get(section)
        if section == "investment_plan":
            value = (final_state.get("investment_debate_state") or {}).get("judge_decision") or value
        elif section == "final_trade_decision":
            value = (final_state.get("risk_debate_state") or {}).get("judge_decision") or value
        if value:
            rec.report(section, str(value))
    return str(decision)


# ====================================================================== mock

_MOCK_REPORT = """## {title}

*This is a mock report generated by TradingWeb mock mode (TRADINGWEB_MOCK=1).*

### Summary
- Placeholder analysis for **{ticker}** as of {date}.
- No LLM was called; this content exercises the persistence and polling pipeline.

### Details
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Indicator values,
sentiment scores, and headlines would appear here in a real run.
"""


def _run_mock(
    rec: RunRecorder,
    ticker: str,
    analysis_date: str,
    asset_type: str,
    analyst_keys: List[str],
) -> str:
    pause = 0.35
    rec.info(f"[mock] Starting analysis for {ticker} ({asset_type}) on {analysis_date}")

    analyst_sections = {
        "market": ("market_report", "Market Analysis"),
        "social": ("sentiment_report", "Sentiment Analysis"),
        "news": ("news_report", "News Analysis"),
        "fundamentals": ("fundamentals_report", "Fundamentals Analysis"),
    }
    for key in analyst_keys:
        agent = ANALYST_AGENT_LABELS[key]
        section, title = analyst_sections[key]
        rec.set_status(agent, "in_progress")
        rec.message(agent, f"Fetching data for {ticker}...")
        rec.tool_call(f"get_{key}_data", {"ticker": ticker, "date": analysis_date})
        time.sleep(pause)
        rec.report(section, _MOCK_REPORT.format(title=title, ticker=ticker, date=analysis_date))
        rec.set_status(agent, "completed")
        time.sleep(pause)

    # Research team.
    for agent in RESEARCH_TEAM:
        rec.set_status(agent, "in_progress")
    rec.message("Bull Researcher", f"Bull case: {ticker} momentum looks constructive.")
    rec.append_report("investment_plan", "Bull Researcher Analysis", f"Mock bull thesis for {ticker}.")
    time.sleep(pause)
    rec.message("Bear Researcher", f"Bear case: {ticker} valuation is stretched.")
    rec.append_report("investment_plan", "Bear Researcher Analysis", f"Mock bear thesis for {ticker}.")
    time.sleep(pause)
    rec.append_report("investment_plan", "Research Manager Decision", "Balanced view; proceed with caution. Mock decision.")
    for agent in RESEARCH_TEAM:
        rec.set_status(agent, "completed")
    time.sleep(pause)

    # Trader.
    rec.set_status("Trader", "in_progress")
    rec.message("Trader", "Drafting trade plan based on research conclusions...")
    time.sleep(pause)
    rec.report("trader_investment_plan", _MOCK_REPORT.format(title="Trader Investment Plan", ticker=ticker, date=analysis_date))
    rec.set_status("Trader", "completed")
    time.sleep(pause)

    # Risk team.
    for agent in RISK_TEAM:
        rec.set_status(agent, "in_progress")
        rec.message(agent, f"[mock] {agent} weighing risk for {ticker}.")
        heading = f"{agent} Analysis"
        rec.append_report("final_trade_decision", heading, f"Mock {agent.lower()} risk perspective.")
        time.sleep(pause)
    rec.set_status("Portfolio Manager", "in_progress")
    time.sleep(pause)
    rec.append_report("final_trade_decision", "Portfolio Manager Decision", "Final mock decision: **HOLD**.")
    for agent in RISK_TEAM:
        rec.set_status(agent, "completed")
    rec.set_status("Portfolio Manager", "completed")
    time.sleep(pause)
    return "HOLD"


# ================================================================== lifecycle

def start_run_thread(
    run_id: int,
    username: str,
    selections: Dict[str, Any],
    asset_type: str,
    analyst_keys: List[str],
    mock: bool,
) -> threading.Thread:
    thread = threading.Thread(
        target=_run_entry,
        args=(run_id, selections, asset_type, analyst_keys, mock),
        name=f"run-{run_id}",
        daemon=True,
    )
    thread.start()
    return thread


def _run_entry(
    run_id: int,
    selections: Dict[str, Any],
    asset_type: str,
    analyst_keys: List[str],
    mock: bool,
) -> None:
    rec = RunRecorder(run_id, initial_agent_statuses(analyst_keys))
    db.update_run(run_id, status="running")
    rec.info(f"Run {run_id} started ({'mock' if mock else 'real'} mode)")
    try:
        if mock:
            decision = _run_mock(
                rec, selections["ticker"], selections["analysis_date"], asset_type, analyst_keys
            )
        else:
            decision = _run_real(
                rec,
                selections["ticker"],
                selections["analysis_date"],
                asset_type,
                analyst_keys,
                selections,
            )
        rec.complete_all()
        rec.info(f"Completed analysis for {selections['analysis_date']}; decision: {decision}")
        db.update_run(
            run_id, status="completed", decision=decision, finished_at=db.utc_now_iso()
        )
    except Exception:  # noqa: BLE001 - top-level runner catch records traceback
        tb = traceback.format_exc()
        logger.exception("Run %s failed", run_id)
        rec.error_step(tb)
        for agent, status in rec.agent_statuses.items():
            if status == "in_progress":
                rec.set_status(agent, "error")
        db.update_run(run_id, status="error", error=tb, finished_at=db.utc_now_iso())
