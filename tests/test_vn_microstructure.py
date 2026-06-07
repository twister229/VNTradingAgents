"""vn_microstructure: foreign flow + market depth parsing (mocked price_board)."""

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import vn_microstructure
from tradingagents.dataflows.symbol_utils import NoMarketDataError


def _price_board(extra_drop=None):
    """Build a fake single-row MultiIndex price_board like vnstock returns."""
    data = {
        ("listing", "symbol"): ["FPT"],
        ("listing", "ceiling"): [81400],
        ("listing", "floor"): [70800],
        ("listing", "ref_price"): [76100],
        ("match", "accumulated_volume"): [11218100],
        ("match", "accumulated_value"): [840238],
        ("match", "foreign_buy_volume"): [4942580],
        ("match", "foreign_sell_volume"): [3257910],
        ("match", "foreign_buy_value"): [370158955000],
        ("match", "foreign_sell_value"): [244042104000],
        ("match", "current_room"): [328313102],
        ("match", "total_room"): [834718489],
        ("bid_ask", "bid_1_price"): [74900],
        ("bid_ask", "bid_1_volume"): [22900],
        ("bid_ask", "ask_1_price"): [75000],
        ("bid_ask", "ask_1_volume"): [39500],
    }
    if extra_drop:
        for k in extra_drop:
            data.pop(k, None)
    df = pd.DataFrame(data)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


@pytest.mark.unit
class MicrostructureTests(unittest.TestCase):
    def _patch_board(self, df):
        fake = MagicMock()
        fake.price_board.return_value = df
        return patch("vnstock.api.trading.Trading", return_value=fake)

    def test_foreign_flow_net_value(self):
        with self._patch_board(_price_board()):
            out = vn_microstructure.get_foreign_flow("FPT")
        # net value = 370,158,955,000 - 244,042,104,000 = 126,116,851,000
        self.assertIn("126,116,851,000", out)
        self.assertIn("net BUY", out)
        self.assertIn("khối ngoại", out)

    def test_market_depth_levels(self):
        with self._patch_board(_price_board()):
            out = vn_microstructure.get_market_depth("FPT")
        self.assertIn("Ceiling: 81,400", out)
        self.assertIn("bid 74,900", out)
        self.assertIn("ask 75,000", out)

    def test_missing_foreign_column_raises(self):
        df = _price_board(extra_drop=[("match", "foreign_buy_value")])
        with self._patch_board(df):
            with self.assertRaises(NoMarketDataError):
                vn_microstructure.get_foreign_flow("FPT")

    def test_empty_board_raises(self):
        empty = pd.DataFrame()
        with self._patch_board(empty):
            with self.assertRaises(NoMarketDataError):
                vn_microstructure.get_foreign_flow("FPT")

    def test_snapshot_caveat_for_past_date(self):
        with self._patch_board(_price_board()):
            out = vn_microstructure.get_foreign_flow("FPT", "2024-01-02")
        self.assertIn("not 2024-01-02", out)

    def test_no_caveat_without_date(self):
        with self._patch_board(_price_board()):
            out = vn_microstructure.get_foreign_flow("FPT")
        self.assertNotIn("NOTE:", out)


if __name__ == "__main__":
    unittest.main()
