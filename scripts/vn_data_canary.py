#!/usr/bin/env python3
"""VN data canary: fail loudly when vnstock's unofficial endpoints drift.

vnstock wraps undocumented VCI/TCBS endpoints that can change without notice.
This canary fetches a known-liquid ticker (FPT) and exits non-zero if the OHLCV
pull breaks, so a scheduled CI run turns red the day the endpoint changes —
before a user hits broken data. News is checked too, but only as a warning
(news coverage is allowed to be sparse).

Exit codes:
  0  OHLCV fetch returned rows (news may warn)
  1  OHLCV fetch failed or returned no rows
"""

from __future__ import annotations

import sys
import warnings
from datetime import date, timedelta

warnings.filterwarnings("ignore")

CANARY_TICKER = "FPT"
LOOKBACK_DAYS = 14


def main() -> int:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    start_s, end_s = start.isoformat(), end.isoformat()

    # --- OHLCV (fatal) ---
    try:
        from tradingagents.dataflows.vnstock_provider import get_vnstock_ohlcv

        df = get_vnstock_ohlcv(CANARY_TICKER, start_s, end_s)
    except Exception as e:  # noqa: BLE001 - canary reports any failure
        print(f"CANARY FAIL: vnstock OHLCV fetch for {CANARY_TICKER} raised "
              f"{type(e).__name__}: {e}")
        return 1

    if df is None or len(df) == 0 or "Close" not in df.columns:
        print(f"CANARY FAIL: vnstock returned no usable OHLCV for {CANARY_TICKER} "
              f"({start_s}..{end_s})")
        return 1

    print(f"CANARY OK: vnstock OHLCV for {CANARY_TICKER} = {len(df)} rows "
          f"({start_s}..{end_s}), last close {df['Close'].iloc[-1]}")

    # --- News (warning only) ---
    try:
        from tradingagents.dataflows.vn_news import get_news

        news = get_news(CANARY_TICKER, start_s, end_s)
        if news.startswith("No news found"):
            print(f"CANARY WARN: no {CANARY_TICKER} news in window (sources may be sparse)")
        else:
            print(f"CANARY OK: news fetch returned {len(news)} chars")
    except Exception as e:  # noqa: BLE001
        print(f"CANARY WARN: news fetch raised {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
