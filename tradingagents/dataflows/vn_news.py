"""Vietnamese news vendor.

Two news methods mirror the router contract used by the News / Sentiment
analysts:

  * ``get_news(ticker, start, end)`` — per-ticker VN news. Primary source is
    vnstock's ``Company.news()`` (same trusted library as price data); if that
    yields nothing or fails, fall back to filtering the cafef markets RSS feed
    for the ticker.
  * ``get_global_news(curr_date, ...)`` — VN macro headlines from cafef RSS
    (markets + macro sections), with a look-ahead guard.

Both return a formatted string (never raise ``NoMarketDataError``): the
analysts consume news as prose, and an empty result is a valid "no news"
signal, matching ``yfinance_news`` behavior. A broken feed degrades to an
empty list rather than crashing the run — but a genuine programming error is
not swallowed.

vnstock prints promotional banners to stdout; we silence stdout around library
calls so the agent data channel stays clean.
"""

from __future__ import annotations

import contextlib
import io
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

from .config import get_config
from .vn_cache import cached_call

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; VNTradingAgents/1.0)"
_HTTP_TIMEOUT = 15


@contextlib.contextmanager
def _quiet():
    """Suppress vnstock's promotional stdout banners during library calls."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield


def _parse_date(value: str) -> Optional[datetime]:
    """Parse a date that may be ISO (vnstock) or RFC822 (RSS). None on failure."""
    if not value:
        return None
    # ISO first (vnstock public_date, e.g. "2026-06-04T18:02:53").
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        pass
    # RFC822 (RSS pubDate, e.g. "Tue, 03 Jun 2025 18:02:53 +0700").
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError, IndexError):
        return None


def _parse_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS feed into a list of item dicts.

    Returns ``[]`` on any network / parse failure — a broken feed must never
    crash an analysis run. Each item: {title, link, description, pub_date}.
    """
    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT, headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError) as e:
        logger.warning("vn_news: RSS fetch/parse failed for %s: %s", url, e)
        return []

    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = _parse_date(item.findtext("pubDate") or "")
        if title:
            items.append(
                {"title": title, "link": link, "description": description, "pub_date": pub_date}
            )
    return items


def _vnstock_ticker_news(ticker: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    """Per-ticker news from vnstock Company.news(). [] on failure/empty."""
    try:
        from vnstock.api.company import Company

        with _quiet():
            df = Company(symbol=ticker, source="VCI").news()
    except Exception as e:  # vnstock endpoint surface is broad/undocumented
        logger.warning("vn_news: vnstock Company.news failed for %s: %s", ticker, e)
        return []

    if df is None or len(df) == 0:
        return []

    out = []
    for _, row in df.iterrows():
        title = row.get("news_title") or row.get("friendly_title") or ""
        if not title:
            continue
        pub = _parse_date(row.get("public_date") or "")
        if pub is not None and not (start_dt <= pub <= end_dt):
            continue
        out.append({
            "title": str(title).strip(),
            "description": str(row.get("news_short_content") or "").strip(),
            "link": str(row.get("news_source_link") or "").strip(),
            "pub_date": pub,
        })
    return out


def _cafef_ticker_news(ticker: str, start_dt: datetime, end_dt: datetime) -> list[dict]:
    """Fallback: filter the cafef markets RSS for items mentioning the ticker."""
    feeds = get_config().get("vn_news_feeds", {})
    url = feeds.get("markets")
    if not url:
        return []
    tk = ticker.upper()
    out = []
    for item in _parse_rss(url):
        haystack = f"{item['title']} {item['description']}".upper()
        if tk not in haystack:
            continue
        if item["pub_date"] is not None and not (start_dt <= item["pub_date"] <= end_dt):
            continue
        out.append(item)
    return out


def _format_news(header: str, items: list[dict]) -> str:
    body = ""
    for it in items:
        body += f"### {it['title']}\n"
        if it.get("description"):
            body += f"{it['description']}\n"
        if it.get("pub_date"):
            body += f"Date: {it['pub_date'].strftime('%Y-%m-%d')}\n"
        if it.get("link"):
            body += f"Link: {it['link']}\n"
        body += "\n"
    return header + body


def _collect_ticker_news(ticker: str, start_date: str, end_date: str) -> tuple[list[dict], str]:
    """Return (items, source) for a ticker: vnstock primary, cafef fallback.

    Single fetch path — the source label is derived from which provider
    actually produced the items, with no redundant second call.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    items = _vnstock_ticker_news(ticker, start_dt, end_dt)
    if items:
        return items, "vnstock"
    return _cafef_ticker_news(ticker, start_dt, end_dt), "cafef"


def get_news_items(ticker: str, start_date: str, end_date: str) -> list[dict]:
    """Per-ticker VN news as a list of item dicts (vnstock primary, cafef fallback).

    This is the single source of truth for "what counts as a usable news item",
    used both by ``get_news`` (formatting) and by the Sentiment Analyst's F2
    guardrail (counting). Each item: {title, description, link, pub_date}.
    """
    items, _ = _collect_ticker_news(ticker, start_date, end_date)
    return items


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Per-ticker VN news: vnstock primary, cafef RSS fallback."""
    def _produce() -> str:
        items, source = _collect_ticker_news(ticker, start_date, end_date)
        if not items:
            return f"No news found for {ticker} between {start_date} and {end_date}"
        header = f"## {ticker} News, {start_date} to {end_date} (source: {source}):\n\n"
        return _format_news(header, items)

    return cached_call("get_news", [ticker, start_date, end_date], _produce)


def get_global_news(
    curr_date: str,
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """VN macro headlines from cafef RSS feeds, with a look-ahead guard."""
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    feeds = config.get("vn_news_feeds", {})

    def _produce() -> str:
        seen = set()
        collected = []
        for url in feeds.values():
            for item in _parse_rss(url):
                title = item["title"]
                if title in seen:
                    continue
                # Look-ahead guard: skip items published after the analysis date.
                if item["pub_date"] is not None and item["pub_date"] > curr_dt:
                    continue
                seen.add(title)
                collected.append(item)
            if len(collected) >= limit:
                break

        if not collected:
            return f"No global news found for {curr_date}"

        start_date = (curr_dt.fromordinal(curr_dt.toordinal() - look_back_days)).strftime("%Y-%m-%d")
        header = f"## VN Market News, {start_date} to {curr_date} (source: cafef):\n\n"
        return _format_news(header, collected[:limit])

    return cached_call("get_global_news", [curr_date, look_back_days, limit], _produce)
