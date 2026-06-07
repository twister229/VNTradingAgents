"""VN symbol normalization: Vietnamese tickers bypass Yahoo rewrite rules."""

import unittest

import pytest

from tradingagents.dataflows.symbol_utils import normalize_symbol


@pytest.mark.unit
class VNSymbolNormalizationTests(unittest.TestCase):
    def test_vn_tickers_pass_through_unchanged(self):
        for sym in ("FPT", "VNM", "HPG", "SSI", "VIC", "MWG"):
            self.assertEqual(normalize_symbol(sym, "VN"), sym)

    def test_vn_uppercases_and_strips(self):
        self.assertEqual(normalize_symbol("  fpt ", "VN"), "FPT")
        self.assertEqual(normalize_symbol("vnm", "VN"), "VNM")

    def test_vn_strips_broker_suffix(self):
        self.assertEqual(normalize_symbol("FPT+", "VN"), "FPT")

    def test_ssi_is_not_treated_as_alias_in_vn(self):
        # SSI is a real HOSE ticker; the VN short-circuit must keep it intact
        # rather than letting any future alias/forex rule touch it.
        self.assertEqual(normalize_symbol("SSI", "VN"), "SSI")

    def test_non_vn_rules_intact(self):
        # Without market="VN" the existing Yahoo rules still apply.
        self.assertEqual(normalize_symbol("XAUUSD"), "GC=F")
        self.assertEqual(normalize_symbol("BTCUSD"), "BTC-USD")
        self.assertEqual(normalize_symbol("EURUSD"), "EURUSD=X")
        self.assertEqual(normalize_symbol("AAPL"), "AAPL")

    def test_default_market_is_backward_compatible(self):
        # market defaults to None -> identical to the original single-arg call.
        self.assertEqual(normalize_symbol("XAUUSD", None), "GC=F")


if __name__ == "__main__":
    unittest.main()
