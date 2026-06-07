"""vn_news vendor: vnstock primary, cafef RSS fallback, macro, look-ahead guard.

All network boundaries are mocked: vnstock's Company and the requests.get used
by _parse_rss. No live calls.
"""

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import vn_news


def _vnstock_news_df():
    return pd.DataFrame({
        "news_title": ["FPT ký hợp đồng lớn", "FPT chia cổ tức"],
        "news_short_content": ["Nội dung 1", "Nội dung 2"],
        "news_source_link": ["http://x/1", "http://x/2"],
        "public_date": ["2026-05-10T09:00:00", "2026-05-20T09:00:00"],
    })


_RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>FPT tin thi truong</title><link>http://c/1</link>
<description>FPT abc</description><pubDate>Mon, 11 May 2026 08:00:00 +0700</pubDate></item>
<item><title>Vi mo Viet Nam</title><link>http://c/2</link>
<description>macro</description><pubDate>Tue, 12 May 2026 08:00:00 +0700</pubDate></item>
<item><title>Tin tuong lai</title><link>http://c/3</link>
<description>future</description><pubDate>Wed, 31 Dec 2031 08:00:00 +0700</pubDate></item>
</channel></rss>"""


class _Resp:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")


@pytest.mark.unit
class VNNewsTests(unittest.TestCase):
    def test_vnstock_primary_used_when_available(self):
        fake_company = MagicMock()
        fake_company.news.return_value = _vnstock_news_df()
        with patch("vnstock.api.company.Company", return_value=fake_company):
            out = vn_news.get_news("FPT", "2026-05-01", "2026-06-07")
        self.assertIn("source: vnstock", out)
        self.assertIn("FPT ký hợp đồng lớn", out)

    def test_falls_back_to_cafef_when_vnstock_empty(self):
        fake_company = MagicMock()
        fake_company.news.return_value = pd.DataFrame()
        with patch("vnstock.api.company.Company", return_value=fake_company), \
             patch("tradingagents.dataflows.vn_news.requests.get", return_value=_Resp(_RSS)):
            out = vn_news.get_news("FPT", "2026-05-01", "2026-06-07")
        self.assertIn("source: cafef", out)
        self.assertIn("FPT tin thi truong", out)

    def test_vnstock_exception_falls_back(self):
        fake_company = MagicMock()
        fake_company.news.side_effect = RuntimeError("endpoint changed")
        with patch("vnstock.api.company.Company", return_value=fake_company), \
             patch("tradingagents.dataflows.vn_news.requests.get", return_value=_Resp(_RSS)):
            out = vn_news.get_news("FPT", "2026-05-01", "2026-06-07")
        self.assertIn("source: cafef", out)

    def test_both_empty_returns_no_news_string_not_exception(self):
        fake_company = MagicMock()
        fake_company.news.return_value = pd.DataFrame()
        with patch("vnstock.api.company.Company", return_value=fake_company), \
             patch("tradingagents.dataflows.vn_news.requests.get", return_value=_Resp(b"<rss/>")):
            out = vn_news.get_news("ZZZ", "2026-05-01", "2026-06-07")
        self.assertTrue(out.startswith("No news found"))

    def test_broken_feed_returns_empty_list(self):
        with patch("tradingagents.dataflows.vn_news.requests.get", return_value=_Resp(b"", 404)):
            self.assertEqual(vn_news._parse_rss("http://x"), [])

    def test_global_news_lookahead_guard(self):
        # The 2031 item must be dropped when curr_date is 2026.
        with patch("tradingagents.dataflows.vn_news.requests.get", return_value=_Resp(_RSS)):
            out = vn_news.get_global_news("2026-06-07", 7, 10)
        self.assertIn("Vi mo Viet Nam", out)
        self.assertNotIn("Tin tuong lai", out)

    def test_get_news_items_returns_list_vnstock(self):
        fake_company = MagicMock()
        fake_company.news.return_value = _vnstock_news_df()
        with patch("vnstock.api.company.Company", return_value=fake_company):
            items = vn_news.get_news_items("FPT", "2026-05-01", "2026-06-07")
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 2)
        self.assertIn("title", items[0])

    def test_get_news_items_falls_back_to_cafef(self):
        fake_company = MagicMock()
        fake_company.news.return_value = pd.DataFrame()
        with patch("vnstock.api.company.Company", return_value=fake_company), \
             patch("tradingagents.dataflows.vn_news.requests.get", return_value=_Resp(_RSS)):
            items = vn_news.get_news_items("FPT", "2026-05-01", "2026-06-07")
        self.assertTrue(any("FPT" in it["title"] for it in items))


if __name__ == "__main__":
    unittest.main()
