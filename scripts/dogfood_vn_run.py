#!/usr/bin/env python3
"""Dogfood: run the full agent graph on a real VN ticker, end to end.

Unit tests cover each piece in isolation; this exercises the whole LangGraph
pipeline (4 analysts -> debate -> trader -> risk -> portfolio manager) on live
VN data with a real LLM, which is the only way to catch integration issues:
prompt quality, token bloat from the new tools, Vietnamese report readability,
and whether agents actually use foreign flow / depth / ratings.

Usage:
    # set ONE provider key, then:
    .venv/bin/python scripts/dogfood_vn_run.py            # defaults: FPT, today
    .venv/bin/python scripts/dogfood_vn_run.py VNM 2026-06-06

Picks the cheapest sane model for whichever key is present. Pre-flights the VN
data path (no LLM spend) before running the graph.
"""

from __future__ import annotations

import os
import sys
import warnings
from datetime import date

warnings.filterwarnings("ignore")

# (env var, provider, quick model, deep model)
_PROVIDERS = [
    ("OPENAI_API_KEY", "openai", "gpt-4.1-mini", "gpt-4.1"),
    ("ANTHROPIC_API_KEY", "anthropic", "claude-haiku-4-5", "claude-sonnet-4-6"),
    ("GOOGLE_API_KEY", "google", "gemini-2.5-flash", "gemini-2.5-pro"),
    ("DEEPSEEK_API_KEY", "deepseek", "deepseek-chat", "deepseek-chat"),
    ("OPENROUTER_API_KEY", "openrouter", "openai/gpt-4.1-mini", "openai/gpt-4.1"),
]


def _pick_provider():
    # Custom OpenAI-compatible endpoint takes precedence when a backend URL is set.
    if os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL") and os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-4.1")
        quick = os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", model)
        return "openai", quick, model
    for env, provider, quick, deep in _PROVIDERS:
        if os.environ.get(env):
            return provider, quick, deep
    return None


def _preflight(ticker: str, trade_date: str) -> bool:
    """Verify the VN data path returns real data before spending LLM tokens."""
    from tradingagents.dataflows.interface import route_to_vendor
    from tradingagents.dataflows.vn_microstructure import get_foreign_flow
    from tradingagents.dataflows.simplize_provider import get_analyst_ratings

    print(f"== Pre-flight VN data for {ticker} ==")
    ok = True
    try:
        px = route_to_vendor("get_stock_data", ticker, "2026-01-02", trade_date)
        line = px.splitlines()[1] if len(px.splitlines()) > 1 else px[:60]
        print(f"  price       : {line}")
        if "NO_DATA" in px:
            ok = False
    except Exception as e:
        print(f"  price       : ERROR {type(e).__name__}: {e}")
        ok = False
    for label, fn in (
        ("fundamentals", lambda: route_to_vendor("get_fundamentals", ticker, trade_date)),
        ("news", lambda: route_to_vendor("get_news", ticker, "2026-05-01", trade_date)),
        ("foreign flow", lambda: get_foreign_flow(ticker, trade_date)),
        ("analyst rate", lambda: get_analyst_ratings(ticker)),
    ):
        try:
            out = fn()
            print(f"  {label:12}: {out.splitlines()[0][:70]}")
        except Exception as e:
            print(f"  {label:12}: ERROR {type(e).__name__}: {e}")
    return ok


def main() -> int:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "FPT"
    trade_date = sys.argv[2] if len(sys.argv) > 2 else date.today().isoformat()

    picked = _pick_provider()
    if not picked:
        print("No LLM API key found in the environment.")
        print("Set one of: " + ", ".join(p[0] for p in _PROVIDERS))
        print("Pre-flight (data only, no LLM) still runs below:\n")
        _preflight(ticker, trade_date)
        return 2

    provider, quick, deep = picked
    print(f"Provider: {provider} | quick={quick} | deep={deep}")
    if not _preflight(ticker, trade_date):
        print("\nPre-flight FAILED — VN data unavailable; aborting before LLM spend.")
        return 1

    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = provider
    config["quick_think_llm"] = quick
    config["deep_think_llm"] = deep
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["online_tools"] = True
    # Honor a custom OpenAI-compatible endpoint when provided.
    backend = os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL")
    if backend:
        config["backend_url"] = backend
        print(f"Backend URL: {backend}")

    print(f"\n== Running full graph on {ticker} @ {trade_date} (debate=1, risk=1) ==\n")
    ta = TradingAgentsGraph(debug=True, config=config)
    _, decision = ta.propagate(ticker, trade_date)

    print("\n================ FINAL DECISION ================")
    print(decision)
    print("===============================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
