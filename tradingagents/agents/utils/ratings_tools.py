from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.simplize_provider import (
    get_analyst_ratings as _get_analyst_ratings,
)


@tool
def get_analyst_ratings(
    ticker: Annotated[str, "ticker symbol of the company"],
) -> str:
    """Vietnamese broker analyst ratings and target prices (simplize.vn).

    Returns the most recent broker reports — source broker, Buy/Sell
    recommendation, target price (VND), and date — plus a consensus tally.
    This is an experimental third-party source: treat ratings as broker opinion,
    not fact, and weigh them against the fundamentals. If the source is
    unavailable it returns a note rather than failing.
    """
    return _get_analyst_ratings(ticker)
