"""Regression: VN instrument identity resolves via vnstock, not yfinance.

Bug: resolve_instrument_identity called yf.Ticker(...).info for every ticker.
For VN symbols yfinance returns the wrong instrument (VNM -> VanEck Vietnam
ETF on NYSE Arca, not Vinamilk on HOSE), injecting a wrong company into every
agent prompt — the exact failure the function exists to prevent. Fix: when
config market == "VN", resolve from vnstock Company.overview().
"""

import copy
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import set_config
from tradingagents.agents.utils import agent_utils


def _vn_overview():
    return pd.DataFrame([{
        "symbol": "VNM",
        "organ_name": "Công ty Cổ phần Sữa Việt Nam",
        "organ_short_name": "VINAMILK",
        "sector": "Food & Beverage",
        "com_group_code": "VNINDEX",
    }])


@pytest.mark.unit
class VNIdentityResolutionTests(unittest.TestCase):
    def setUp(self):
        agent_utils.resolve_instrument_identity.cache_clear()
        self.addCleanup(agent_utils.resolve_instrument_identity.cache_clear)
        self.addCleanup(set_config, copy.deepcopy(default_config.DEFAULT_CONFIG))

    def _set_market(self, market):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        cfg["market"] = market
        set_config(cfg)

    def test_vn_market_resolves_via_vnstock_not_yfinance(self):
        self._set_market("VN")
        fake_company = MagicMock()
        fake_company.overview.return_value = _vn_overview()
        with patch("vnstock.api.company.Company", return_value=fake_company), \
             patch("tradingagents.agents.utils.agent_utils.yf.Ticker") as yf_ticker:
            idt = agent_utils.resolve_instrument_identity("VNM")
        # vnstock identity used; yfinance never touched for VN.
        yf_ticker.assert_not_called()
        self.assertEqual(idt["company_name"], "Công ty Cổ phần Sữa Việt Nam")
        self.assertEqual(idt["sector"], "Food & Beverage")

    def test_non_vn_market_still_uses_yfinance(self):
        self._set_market(None)
        fake_info = MagicMock()
        fake_info.info = {"longName": "NVIDIA Corporation", "sector": "Technology",
                          "exchange": "NMS", "quoteType": "EQUITY"}
        with patch("tradingagents.agents.utils.agent_utils.yf.Ticker", return_value=fake_info) as yf_ticker:
            idt = agent_utils.resolve_instrument_identity("NVDA")
        yf_ticker.assert_called_once()
        self.assertEqual(idt["company_name"], "NVIDIA Corporation")

    def test_vn_resolution_fails_open_on_error(self):
        self._set_market("VN")
        with patch("vnstock.api.company.Company", side_effect=RuntimeError("endpoint down")):
            idt = agent_utils.resolve_instrument_identity("VNM")
        self.assertEqual(idt, {})  # fail open, never block the run


if __name__ == "__main__":
    unittest.main()
