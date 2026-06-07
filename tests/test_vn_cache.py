"""vn_cache: opt-in response cache for reproducible research runs."""

import copy
import os
import tempfile
import unittest

import pytest

import tradingagents.default_config as default_config
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows import vn_cache


@pytest.mark.unit
class VNCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="vn-cache-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))
        self.addCleanup(set_config, copy.deepcopy(default_config.DEFAULT_CONFIG))

    def _cfg(self, enabled):
        cfg = copy.deepcopy(default_config.DEFAULT_CONFIG)
        cfg["data_cache_dir"] = self._tmp
        cfg["vnstock_cache_enabled"] = enabled
        set_config(cfg)

    def test_disabled_is_passthrough_no_files(self):
        self._cfg(False)
        calls = {"n": 0}

        def producer():
            calls["n"] += 1
            return "real data"

        self.assertEqual(vn_cache.cached_call("get_news", ["FPT"], producer), "real data")
        self.assertEqual(vn_cache.cached_call("get_news", ["FPT"], producer), "real data")
        self.assertEqual(calls["n"], 2)  # producer called every time
        self.assertFalse(os.path.exists(os.path.join(self._tmp, "responses")))

    def test_enabled_hit_skips_producer(self):
        self._cfg(True)
        calls = {"n": 0}

        def producer():
            calls["n"] += 1
            return "frozen data"

        first = vn_cache.cached_call("get_news", ["FPT", "2026-05-01"], producer)
        second = vn_cache.cached_call("get_news", ["FPT", "2026-05-01"], producer)
        self.assertEqual(first, "frozen data")
        self.assertEqual(second, "frozen data")
        self.assertEqual(calls["n"], 1)  # producer called once, second served from disk

    def test_empty_and_error_not_cached(self):
        self._cfg(True)
        for sentinel in ("No news found for FPT", "Error fetching", "", "NO_DATA_AVAILABLE: x"):
            calls = {"n": 0}

            def producer(s=sentinel):
                calls["n"] += 1
                return s

            vn_cache.cached_call("get_news", [sentinel[:5]], producer)
            vn_cache.cached_call("get_news", [sentinel[:5]], producer)
            self.assertEqual(calls["n"], 2, f"sentinel {sentinel!r} should not be cached")

    def test_distinct_keys_isolated(self):
        self._cfg(True)
        vn_cache.cached_call("get_fundamentals", ["FPT"], lambda: "fpt data")
        vn_cache.cached_call("get_fundamentals", ["VNM"], lambda: "vnm data")
        self.assertEqual(
            vn_cache.cached_call("get_fundamentals", ["FPT"], lambda: "WRONG"), "fpt data"
        )
        self.assertEqual(
            vn_cache.cached_call("get_fundamentals", ["VNM"], lambda: "WRONG"), "vnm data"
        )


if __name__ == "__main__":
    unittest.main()
