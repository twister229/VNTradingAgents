"""Analyst ratings from simplize.vn — EXPERIMENTAL, non-fatal source.

simplize.vn publishes Vietnamese broker research: target prices and Buy/Sell
recommendations that vnstock does not expose. This module reads its unofficial
JSON API:

    GET https://api.simplize.vn/api/company/analysis-report/list?ticker=FPT
    -> {status, total, data: [{ticker, source, title, targetPrice,
                               recommend, issueDate, attachedLink}, ...]}

Because the endpoint is unofficial and has no contract, this source is treated
as OPTIONAL: every failure path (disabled, HTTP error, timeout, JSON shape
change) degrades to a plain "unavailable" string. It NEVER raises, so a
simplize outage can never fail an analysis run. Gated by ``simplize_enabled``.
"""

from __future__ import annotations

import logging
from typing import Annotated

import requests

from .config import get_config

logger = logging.getLogger(__name__)

_API = "https://api.simplize.vn/api/company/analysis-report/list"
_UA = "Mozilla/5.0 (compatible; VNTradingAgents/1.0)"
_TIMEOUT = 15

# Vietnamese recommendation tokens -> normalized direction for the consensus tally.
_BUY = {"MUA", "BUY", "OUTPERFORM", "TÍCH LŨY", "TICH LUY", "KHẢ QUAN", "KHA QUAN"}
_SELL = {"BÁN", "BAN", "SELL", "UNDERPERFORM", "KÉM KHẢ QUAN", "KEM KHA QUAN"}


def _classify(recommend: str) -> str:
    r = (recommend or "").strip().upper()
    if r in _BUY:
        return "buy"
    if r in _SELL:
        return "sell"
    return "hold/other"


def get_analyst_ratings(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Latest broker target prices + recommendations for a VN ticker.

    Experimental source — always returns a string, never raises.
    """
    config = get_config()
    sym = ticker.strip().upper()

    if not config.get("simplize_enabled", True):
        return f"Analyst ratings disabled for {sym} (simplize_enabled=false)."

    limit = config.get("analyst_report_limit", 5)

    try:
        resp = requests.get(
            _API,
            params={"ticker": sym},
            timeout=_TIMEOUT,
            headers={"User-Agent": _UA, "Accept": "application/json"},
        )
        resp.raise_for_status()
        rows = (resp.json() or {}).get("data", []) or []
    except Exception as e:  # noqa: BLE001 — experimental source must never raise
        logger.warning("simplize: %s fetching ratings for %s", type(e).__name__, sym)
        return f"Analyst ratings unavailable for {sym} (experimental source)."

    if not rows:
        return f"No analyst reports found for {sym}."

    latest = rows[:limit]
    tally = {"buy": 0, "sell": 0, "hold/other": 0}
    lines = [
        f"## Analyst ratings for {sym} (source: simplize.vn, experimental)",
        f"# Latest {len(latest)} of {len(rows)} broker reports. Target prices in VND.",
        "# Treat as third-party broker opinion, not fact; weigh against fundamentals.",
        "",
    ]
    for r in latest:
        try:
            broker = r.get("source") or "?"
            rec = r.get("recommend") or "?"
            tp = r.get("targetPrice")
            issued = r.get("issueDate") or "?"
            title = (r.get("title") or "").strip()
            tally[_classify(rec)] += 1
            tp_s = f"{int(tp):,} VND" if isinstance(tp, (int, float)) and tp else "n/a"
            lines.append(f"- {issued} | {broker}: {rec}, target {tp_s} — {title}")
        except Exception:  # noqa: BLE001 — one bad row must not break the report
            continue

    lines.append("")
    lines.append(
        f"Consensus (last {len(latest)}): {tally['buy']} buy / "
        f"{tally['sell']} sell / {tally['hold/other']} hold/other."
    )
    return "\n".join(lines)
