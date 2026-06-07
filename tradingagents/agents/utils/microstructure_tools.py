from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.vn_microstructure import (
    get_foreign_flow as _get_foreign_flow,
    get_market_depth as _get_market_depth,
)


@tool
def get_foreign_flow(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "the current trading date, YYYY-mm-dd"],
) -> str:
    """Foreign investor net buy/sell ("khối ngoại") for the latest session.

    Returns foreign buy/sell volume and value, the net flow (a key Vietnamese
    retail sentiment signal — sustained foreign buying is bullish, selling
    bearish), and remaining foreign room. This is a current-session snapshot,
    not history; for a past analysis date treat it as current context only.
    """
    return _get_foreign_flow(ticker, curr_date)


@tool
def get_market_depth(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "the current trading date, YYYY-mm-dd"],
) -> str:
    """Order-book depth and session match stats for the latest trading session.

    Returns reference/ceiling/floor, accumulated match volume and value, and the
    top three bid/ask levels — liquidity and buy/sell pressure context. Snapshot
    of the current session, not history.
    """
    return _get_market_depth(ticker, curr_date)
