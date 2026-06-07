"""vnstock_provider: column normalization + error contract (mocked, no network)."""

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import vnstock_provider
from tradingagents.dataflows.symbol_utils import NoMarketDataError


def _raw_vnstock_df():
    # vnstock returns lowercase columns with a 'time' column.
    return pd.DataFrame({
        "time": pd.to_datetime(["2024-01-02", "2024-01-03"]),
        "open": [100.0, 101.0],
        "high": [103.0, 104.0],
        "low": [99.0, 100.0],
        "close": [102.0, 103.0],
        "volume": [1000, 1100],
    })


@pytest.mark.unit
class VNStockProviderTests(unittest.TestCase):
    def test_ohlcv_columns_normalized(self):
        fake_quote = MagicMock()
        fake_quote.history.return_value = _raw_vnstock_df()
        with patch("vnstock.api.quote.Quote", return_value=fake_quote):
            df = vnstock_provider.get_vnstock_ohlcv("FPT", "2024-01-02", "2024-01-03")
        self.assertEqual(
            set(df.columns), {"Date", "Open", "High", "Low", "Close", "Volume"}
        )
        self.assertEqual(len(df), 2)

    def test_empty_result_raises_no_market_data(self):
        fake_quote = MagicMock()
        fake_quote.history.return_value = pd.DataFrame()
        with patch("vnstock.api.quote.Quote", return_value=fake_quote):
            with self.assertRaises(NoMarketDataError):
                vnstock_provider.get_vnstock_ohlcv("ZZZZ", "2024-01-02", "2024-01-03")

    def test_invalid_symbol_valueerror_maps_to_no_market_data(self):
        fake_quote = MagicMock()
        fake_quote.history.side_effect = ValueError(
            "Invalid symbol. Your symbol format is not recognized!"
        )
        with patch("vnstock.api.quote.Quote", return_value=fake_quote):
            with self.assertRaises(NoMarketDataError):
                vnstock_provider.get_vnstock_ohlcv("BADSYM", "2024-01-02", "2024-01-03")

    def test_network_error_propagates(self):
        # A genuine endpoint failure must NOT be swallowed into "no data" — the
        # router fallback and the CI canary depend on seeing the real error.
        fake_quote = MagicMock()
        fake_quote.history.side_effect = ConnectionError("endpoint down")
        with patch("vnstock.api.quote.Quote", return_value=fake_quote):
            with self.assertRaises(ConnectionError):
                vnstock_provider.get_vnstock_ohlcv("FPT", "2024-01-02", "2024-01-03")

    def test_get_stock_emits_csv_with_header(self):
        fake_quote = MagicMock()
        fake_quote.history.return_value = _raw_vnstock_df()
        with patch("vnstock.api.quote.Quote", return_value=fake_quote):
            out = vnstock_provider.get_stock("FPT", "2024-01-02", "2024-01-03")
        self.assertIn("# Stock data for FPT", out)
        self.assertIn("vnstock", out)
        self.assertIn("Close", out)

    def test_insider_transactions_returns_clean_note_not_raise(self):
        # VN has no insider feed via vnstock. The provider returns an explicit
        # note (not NoMarketDataError) so the router short-circuits at vnstock
        # and never falls through to yfinance (which 404s on VN symbols).
        out = vnstock_provider.get_insider_transactions("FPT")
        self.assertIn("FPT", out)
        self.assertIn("not available", out.lower())


@pytest.mark.unit
class VNInsiderRoutingTests(unittest.TestCase):
    def test_router_uses_vnstock_insider_no_yfinance_fallthrough(self):
        from tradingagents.dataflows.interface import route_to_vendor, VENDOR_METHODS
        self.assertIn("vnstock", VENDOR_METHODS["get_insider_transactions"])
        out = route_to_vendor("get_insider_transactions", "FPT")
        # vnstock's string return short-circuits the chain; no NO_DATA sentinel
        # and no yfinance 404 path.
        self.assertIn("not available", out.lower())
        self.assertNotIn("NO_DATA_AVAILABLE", out)



if __name__ == "__main__":
    unittest.main()
