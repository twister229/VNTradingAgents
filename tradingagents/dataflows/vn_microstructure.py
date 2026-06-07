"""Vietnamese market microstructure from vnstock's price board.

Two standalone signals derived from ``Trading.price_board`` (VCI source), which
is verified stable:

  * ``get_foreign_flow`` — foreign investor net buy/sell ("khối ngoại"), the
    most-watched Vietnamese retail indicator.
  * ``get_market_depth`` — ceiling/floor/reference, accumulated match volume,
    and the top bid/ask levels (liquidity / pressure context).

``price_board`` returns a **current trading-session snapshot**, not a historical
series, so both outputs are explicitly labeled as the latest session. When an
analysis date earlier than today is supplied, the output adds a look-ahead
caveat (the snapshot reflects "now", not that date). Historical foreign flow
needs the ``foreign_trade`` endpoint, which is currently unstable and deferred.

These are core/stable signals: missing foreign columns or an empty board raise
``NoMarketDataError`` so the agent never fabricates a number.
"""

from __future__ import annotations

import contextlib
import io
from datetime import date, datetime
from typing import Annotated, Optional

from .symbol_utils import NoMarketDataError


@contextlib.contextmanager
def _quiet():
    """Suppress vnstock's promotional stdout banners during library calls."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield


def _norm(ticker: str) -> str:
    return ticker.strip().upper().rstrip("+")


def _price_board(ticker: str):
    """Fetch the single-row price board for a ticker (MultiIndex DataFrame)."""
    from vnstock.api.trading import Trading

    sym = _norm(ticker)
    try:
        with _quiet():
            pb = Trading(symbol=sym, source="VCI").price_board([sym])
    except ValueError as e:
        # vnstock raises ValueError for invalid/unknown symbols.
        if "symbol" in str(e).lower():
            raise NoMarketDataError(ticker, sym, str(e))
        raise

    if pb is None or len(pb) == 0:
        raise NoMarketDataError(ticker, sym, "price_board returned no rows")
    return pb, sym


def _match(pb, name: str, required: bool, ticker: str, sym: str):
    """Read a ('match', name) cell; raise (if required) or return None when absent."""
    key = ("match", name)
    if key not in pb.columns:
        if required:
            raise NoMarketDataError(ticker, sym, f"price_board missing column {key}")
        return None
    return pb[key].iloc[0]


def _listing(pb, name: str):
    key = ("listing", name)
    return pb[key].iloc[0] if key in pb.columns else None


def _bidask(pb, name: str):
    key = ("bid_ask", name)
    return pb[key].iloc[0] if key in pb.columns else None


def _snapshot_caveat(curr_date: Optional[str]) -> str:
    """Look-ahead note when the analysis date is not today."""
    if not curr_date:
        return ""
    try:
        d = datetime.strptime(curr_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return ""
    if d != date.today():
        return (
            f"\n> NOTE: this is the latest live trading session, not {curr_date}. "
            f"For a historical analysis date, treat it as current context only.\n"
        )
    return ""


def _fmt_int(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "n/a"


def get_foreign_flow(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "the current trading date, YYYY-mm-dd"] = None,
) -> str:
    """Foreign investor net buy/sell (khối ngoại) for the latest session."""
    pb, sym = _price_board(ticker)
    fbv = _match(pb, "foreign_buy_volume", True, ticker, sym)
    fsv = _match(pb, "foreign_sell_volume", True, ticker, sym)
    fbval = _match(pb, "foreign_buy_value", True, ticker, sym)
    fsval = _match(pb, "foreign_sell_value", True, ticker, sym)
    room = _match(pb, "current_room", False, ticker, sym)
    total_room = _match(pb, "total_room", False, ticker, sym)

    net_vol = (fbv or 0) - (fsv or 0)
    net_val = (fbval or 0) - (fsval or 0)
    direction = "net BUY" if net_val > 0 else ("net SELL" if net_val < 0 else "flat")

    lines = [
        f"## Foreign flow (khối ngoại) for {sym} — latest trading session",
        "# Source: vnstock price_board (VCI). Values in VND / shares.",
        "",
        f"- Foreign buy:  {_fmt_int(fbv)} shares / {_fmt_int(fbval)} VND",
        f"- Foreign sell: {_fmt_int(fsv)} shares / {_fmt_int(fsval)} VND",
        f"- Foreign NET:  {_fmt_int(net_vol)} shares / {_fmt_int(net_val)} VND ({direction})",
    ]
    if room is not None:
        lines.append(f"- Current foreign room: {_fmt_int(room)}"
                     + (f" / {_fmt_int(total_room)} total" if total_room is not None else ""))
    caveat = _snapshot_caveat(curr_date)
    if caveat:
        lines.append(caveat)
    return "\n".join(lines)


def get_market_depth(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "the current trading date, YYYY-mm-dd"] = None,
) -> str:
    """Order-book depth + session match stats for the latest trading session."""
    pb, sym = _price_board(ticker)

    ceiling = _listing(pb, "ceiling")
    floor = _listing(pb, "floor")
    ref = _listing(pb, "ref_price")
    acc_vol = _match(pb, "accumulated_volume", False, ticker, sym)
    acc_val = _match(pb, "accumulated_value", False, ticker, sym)

    lines = [
        f"## Market depth for {sym} — latest trading session",
        "# Source: vnstock price_board (VCI). Prices/values in VND.",
        "",
        f"- Reference: {_fmt_int(ref)} | Ceiling: {_fmt_int(ceiling)} | Floor: {_fmt_int(floor)}",
        f"- Accumulated: {_fmt_int(acc_vol)} shares / {_fmt_int(acc_val)} VND",
        "",
        "Order book (top 3):",
    ]
    for i in (1, 2, 3):
        bp, bv = _bidask(pb, f"bid_{i}_price"), _bidask(pb, f"bid_{i}_volume")
        ap, av = _bidask(pb, f"ask_{i}_price"), _bidask(pb, f"ask_{i}_volume")
        lines.append(
            f"- L{i}  bid {_fmt_int(bp)} x {_fmt_int(bv)}   |   ask {_fmt_int(ap)} x {_fmt_int(av)}"
        )
    caveat = _snapshot_caveat(curr_date)
    if caveat:
        lines.append(caveat)
    return "\n".join(lines)
