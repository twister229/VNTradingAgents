"""VN market config defaults and benchmark resolution."""

import copy
import unittest
from unittest.mock import MagicMock

import pytest

import tradingagents.default_config as default_config
from tradingagents.graph.trading_graph import TradingAgentsGraph


@pytest.mark.unit
class VNConfigDefaultsTests(unittest.TestCase):
    def test_market_flag_is_vn(self):
        self.assertEqual(default_config.DEFAULT_CONFIG["market"], "VN")

    def test_default_vendors_are_vnstock(self):
        vendors = default_config.DEFAULT_CONFIG["data_vendors"]
        for category in ("core_stock_apis", "technical_indicators",
                         "fundamental_data", "news_data"):
            self.assertEqual(vendors[category], "vnstock", category)

    def test_output_language_is_vietnamese(self):
        self.assertEqual(default_config.DEFAULT_CONFIG["output_language"], "Vietnamese")

    def test_vn_benchmark_present(self):
        self.assertIn(".VN", default_config.DEFAULT_CONFIG["benchmark_map"])
        self.assertEqual(default_config.DEFAULT_CONFIG["benchmark_map"][".VN"], "^VNINDEX")

    def test_market_env_override_registered(self):
        self.assertEqual(
            default_config._ENV_OVERRIDES.get("TRADINGAGENTS_MARKET"), "market"
        )


@pytest.mark.unit
class VNBenchmarkResolutionTests(unittest.TestCase):
    def _graph(self, config):
        g = MagicMock(spec=TradingAgentsGraph)
        g.config = config
        return g

    def test_bare_vn_ticker_resolves_to_vn_index(self):
        # FPT carries no exchange suffix; under market=VN it must fall back to
        # the VN-Index, not the US SPY default.
        g = self._graph({
            "benchmark_ticker": None,
            "market": "VN",
            "benchmark_map": {".VN": "^VNINDEX", "": "SPY"},
        })
        self.assertEqual(TradingAgentsGraph._resolve_benchmark(g, "FPT"), "^VNINDEX")
        self.assertEqual(TradingAgentsGraph._resolve_benchmark(g, "VNM"), "^VNINDEX")

    def test_dotted_vn_suffix_resolves_to_vn_index(self):
        g = self._graph({
            "benchmark_ticker": None,
            "market": "VN",
            "benchmark_map": {".VN": "^VNINDEX", "": "SPY"},
        })
        self.assertEqual(TradingAgentsGraph._resolve_benchmark(g, "FPT.VN"), "^VNINDEX")

    def test_non_vn_market_still_defaults_to_spy(self):
        # No market key -> original US behavior preserved.
        g = self._graph({
            "benchmark_ticker": None,
            "benchmark_map": {".VN": "^VNINDEX", "": "SPY"},
        })
        self.assertEqual(TradingAgentsGraph._resolve_benchmark(g, "NVDA"), "SPY")


if __name__ == "__main__":
    unittest.main()
