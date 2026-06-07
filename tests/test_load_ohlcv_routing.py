"""F1 regression: load_ohlcv must follow the configured data vendor.

The indicator path, the verified market snapshot, and the reflection alpha
calc all flow through load_ohlcv. Before this fix it hardcoded yfinance, which
silently broke Vietnamese tickers even when data_vendors said "vnstock". These
tests lock the vendor-aware dispatch in place.
"""

import copy
import unittest
from unittest.mock import patch

import pandas as pd
import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows import stockstats_utils


def _fake_ohlcv():
    return pd.DataFrame({
        "Date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        "Open": [100.0, 101.0, 102.0],
        "High": [103.0, 104.0, 105.0],
        "Low": [99.0, 100.0, 101.0],
        "Close": [102.0, 103.0, 104.0],
        "Volume": [1000, 1100, 1200],
    })


@pytest.mark.unit
class LoadOhlcvVendorRoutingTests(unittest.TestCase):
    def setUp(self):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        cfg["data_cache_dir"] = self._tmp()
        self.cfg = cfg

    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="vn-ohlcv-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        return d

    def test_vnstock_vendor_calls_vnstock_not_yfinance(self):
        self.cfg["data_vendors"]["core_stock_apis"] = "vnstock"
        self.cfg["market"] = "VN"
        set_config(self.cfg)
        self.addCleanup(set_config, copy.deepcopy(default_config.DEFAULT_CONFIG))

        with patch(
            "tradingagents.dataflows.vnstock_provider.get_vnstock_ohlcv",
            return_value=_fake_ohlcv(),
        ) as vn, patch("tradingagents.dataflows.stockstats_utils.yf.download") as yf_dl:
            out = stockstats_utils.load_ohlcv("FPT", "2024-01-04")

        vn.assert_called_once()
        yf_dl.assert_not_called()
        self.assertIn("Close", out.columns)
        self.assertEqual(len(out), 3)

    def test_yfinance_vendor_calls_yfinance_not_vnstock(self):
        self.cfg["data_vendors"]["core_stock_apis"] = "yfinance"
        self.cfg["market"] = None
        set_config(self.cfg)
        self.addCleanup(set_config, copy.deepcopy(default_config.DEFAULT_CONFIG))

        with patch(
            "tradingagents.dataflows.stockstats_utils.yf.download",
            return_value=_fake_ohlcv(),
        ) as yf_dl, patch(
            "tradingagents.dataflows.vnstock_provider.get_vnstock_ohlcv"
        ) as vn:
            stockstats_utils.load_ohlcv("AAPL", "2024-01-04")

        yf_dl.assert_called_once()
        vn.assert_not_called()

    def test_cache_filename_namespaced_by_vendor(self):
        # vnstock and yfinance caches for the same ticker must not collide.
        self.cfg["data_vendors"]["core_stock_apis"] = "vnstock"
        self.cfg["market"] = "VN"
        set_config(self.cfg)
        self.addCleanup(set_config, copy.deepcopy(default_config.DEFAULT_CONFIG))

        import os
        with patch(
            "tradingagents.dataflows.vnstock_provider.get_vnstock_ohlcv",
            return_value=_fake_ohlcv(),
        ), patch("tradingagents.dataflows.stockstats_utils.yf.download"):
            stockstats_utils.load_ohlcv("FPT", "2024-01-04")

        files = os.listdir(self.cfg["data_cache_dir"])
        self.assertTrue(any("vnstock" in f for f in files), files)
        self.assertFalse(any("YFin" in f for f in files), files)


if __name__ == "__main__":
    unittest.main()
