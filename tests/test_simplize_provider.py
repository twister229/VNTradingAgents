"""simplize_provider: parse ratings; always degrade, never raise."""

import copy
import unittest
from unittest.mock import MagicMock, patch

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows import simplize_provider


def _resp(payload, status=200):
    r = MagicMock()
    r.json.return_value = payload
    r.status_code = status

    def _raise():
        if status >= 400:
            import requests
            raise requests.HTTPError(str(status))

    r.raise_for_status.side_effect = _raise
    return r


_ROWS = {
    "status": 200,
    "total": 2,
    "data": [
        {"ticker": "FPT", "source": "BSC", "recommend": "MUA",
         "targetPrice": 89600.0, "issueDate": "18/05/2026", "title": "Hồi phục"},
        {"ticker": "FPT", "source": "SSI", "recommend": "BÁN",
         "targetPrice": 70000.0, "issueDate": "22/04/2026", "title": "Thận trọng"},
    ],
}


@pytest.mark.unit
class SimplizeTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(set_config, copy.deepcopy(default_config.DEFAULT_CONFIG))
        set_config(copy.deepcopy(default_config.DEFAULT_CONFIG))

    def test_parses_ratings_and_consensus(self):
        with patch("tradingagents.dataflows.simplize_provider.requests.get",
                   return_value=_resp(_ROWS)):
            out = simplize_provider.get_analyst_ratings("FPT")
        self.assertIn("BSC", out)
        self.assertIn("89,600 VND", out)
        self.assertIn("1 buy / 1 sell", out)

    def test_http_error_degrades_not_raises(self):
        with patch("tradingagents.dataflows.simplize_provider.requests.get",
                   return_value=_resp({}, status=500)):
            out = simplize_provider.get_analyst_ratings("FPT")
        self.assertIn("unavailable", out.lower())  # no exception

    def test_timeout_degrades(self):
        import requests
        with patch("tradingagents.dataflows.simplize_provider.requests.get",
                   side_effect=requests.Timeout("slow")):
            out = simplize_provider.get_analyst_ratings("FPT")
        self.assertIn("unavailable", out.lower())

    def test_bad_json_shape_degrades(self):
        with patch("tradingagents.dataflows.simplize_provider.requests.get",
                   return_value=_resp({"unexpected": True})):
            out = simplize_provider.get_analyst_ratings("FPT")
        self.assertIn("No analyst reports", out)

    def test_disabled_skips_network(self):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        cfg["simplize_enabled"] = False
        set_config(cfg)
        with patch("tradingagents.dataflows.simplize_provider.requests.get") as g:
            out = simplize_provider.get_analyst_ratings("FPT")
        g.assert_not_called()
        self.assertIn("disabled", out.lower())


if __name__ == "__main__":
    unittest.main()
