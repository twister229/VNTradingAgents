"""vnstock data vendor — Vietnamese market data via the vnstock library.

This provider mirrors the method surface of ``y_finance.py`` so the vendor
router in ``interface.py`` can route Vietnamese tickers (FPT, VNM, HPG, ...)
through the same agent tools the US path uses.

Built on vnstock's ``vnstock.api`` module (the ``Vnstock().stock(...)`` facade
is deprecated as of vnstock 4.x). Data comes from the VCI source by default.

Contract (from the eng review):
  * On empty / missing data, raise ``NoMarketDataError`` — never return prose
    and never let an empty result masquerade as success. The router turns the
    typed error into a single "no data" sentinel so agents never fabricate.
  * On an endpoint / network failure, let the original exception propagate.
    "Endpoint broke" must stay distinguishable from "symbol has no data" so the
    router fallback chain and the CI data canary can both react correctly. Do
    NOT wrap the whole body in ``except Exception: return ""``.

vnstock prints promotional banners to stdout on import and on some calls; we
silence stdout around library calls so the agent data channel stays clean.
"""

from __future__ import annotations

import contextlib
import io
import os
from datetime import datetime
from typing import Annotated

import pandas as pd

from .symbol_utils import NoMarketDataError
from .vn_cache import cached_call

# vnstock OHLCV columns -> the names stockstats / the rest of the pipeline expect.
_OHLCV_RENAME = {
    "time": "Date",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}

_DEFAULT_SOURCE = "VCI"


@contextlib.contextmanager
def _quiet():
    """Suppress vnstock's promotional stdout banners during library calls."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield


def _norm_vn(symbol: str) -> str:
    return symbol.strip().upper().rstrip("+")


def get_vnstock_ohlcv(symbol: str, start_str: str, end_str: str) -> pd.DataFrame:
    """Fetch daily OHLCV for a VN ticker as a normalized DataFrame.

    Returns a DataFrame with columns Date/Open/High/Low/Close/Volume. Raises
    ``NoMarketDataError`` when vnstock returns no rows. Network / endpoint
    failures propagate unchanged (see module docstring contract).
    """
    from vnstock.api.quote import Quote

    sym = _norm_vn(symbol)
    try:
        with _quiet():
            q = Quote(symbol=sym, source=_DEFAULT_SOURCE)
            df = q.history(start=start_str, end=end_str, interval="1D")
    except ValueError as e:
        # vnstock raises ValueError("Invalid symbol...") for unknown/malformed
        # tickers. That is a "no data" condition (invalid or delisted), not an
        # endpoint failure, so surface it as the typed no-data error. Genuine
        # network / endpoint errors are NOT ValueError and propagate below.
        if "symbol" in str(e).lower():
            raise NoMarketDataError(symbol, sym, str(e))
        raise

    if df is None or len(df) == 0:
        raise NoMarketDataError(
            symbol, sym, f"vnstock returned no rows between {start_str} and {end_str}"
        )

    df = df.rename(columns=_OHLCV_RENAME)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
    return df


def get_stock(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """OHLCV price data for a VN ticker as a CSV string with a header block."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    sym = _norm_vn(symbol)
    data = get_vnstock_ohlcv(sym, start_date, end_date)

    numeric_columns = ["Open", "High", "Low", "Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv(index=False)
    header = f"# Stock data for {sym} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    header += "# Source: vnstock (VCI) — prices in VND\n\n"
    return header + csv_string


def _fetch_financial(symbol: str, statement: str, freq: str) -> pd.DataFrame:
    """Fetch a financial statement DataFrame from vnstock.

    ``statement`` is one of: balance_sheet, cash_flow, income_statement, ratio.
    ``freq`` is "quarterly" or anything else (treated as yearly).
    """
    from vnstock.api.financial import Finance

    sym = _norm_vn(symbol)
    period = "quarter" if str(freq).lower().startswith("q") else "year"
    try:
        with _quiet():
            fin = Finance(symbol=sym, source=_DEFAULT_SOURCE)
            method = getattr(fin, statement)
            df = method(period=period, lang="en")
    except ValueError as e:
        if "symbol" in str(e).lower():
            raise NoMarketDataError(symbol, sym, str(e))
        raise

    if df is None or len(df) == 0:
        raise NoMarketDataError(symbol, sym, f"vnstock returned no {statement}")
    return df


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (unused for vnstock)"] = None,
) -> str:
    """Company fundamentals overview (financial ratios) for a VN ticker."""
    def _produce() -> str:
        df = _fetch_financial(ticker, "ratio", "year")
        sym = _norm_vn(ticker)
        header = f"# Fundamentals (financial ratios) for {sym}\n"
        header += "# Source: vnstock (VCI) — values in VND where applicable\n\n"
        return header + df.to_csv(index=False)

    return cached_call("get_fundamentals", [_norm_vn(ticker)], _produce)


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "reporting frequency: 'annual' or 'quarterly'"] = "annual",
    curr_date: Annotated[str, "current date (unused for vnstock)"] = None,
) -> str:
    """Balance sheet for a VN ticker."""
    def _produce() -> str:
        df = _fetch_financial(ticker, "balance_sheet", freq)
        return f"# Balance sheet for {_norm_vn(ticker)} ({freq}) — vnstock (VCI)\n\n" + df.to_csv(index=False)

    return cached_call("get_balance_sheet", [_norm_vn(ticker), freq], _produce)


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "reporting frequency: 'annual' or 'quarterly'"] = "annual",
    curr_date: Annotated[str, "current date (unused for vnstock)"] = None,
) -> str:
    """Cash flow statement for a VN ticker."""
    def _produce() -> str:
        df = _fetch_financial(ticker, "cash_flow", freq)
        return f"# Cash flow for {_norm_vn(ticker)} ({freq}) — vnstock (VCI)\n\n" + df.to_csv(index=False)

    return cached_call("get_cashflow", [_norm_vn(ticker), freq], _produce)


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "reporting frequency: 'annual' or 'quarterly'"] = "annual",
    curr_date: Annotated[str, "current date (unused for vnstock)"] = None,
) -> str:
    """Income statement for a VN ticker."""
    def _produce() -> str:
        df = _fetch_financial(ticker, "income_statement", freq)
        return f"# Income statement for {_norm_vn(ticker)} ({freq}) — vnstock (VCI)\n\n" + df.to_csv(index=False)

    return cached_call("get_income_statement", [_norm_vn(ticker), freq], _produce)
