"""The 3 new tools are importable from agent_utils and call their dataflow fns."""

import unittest
from unittest.mock import patch

import pytest


@pytest.mark.unit
class NewToolWiringTests(unittest.TestCase):
    def test_tools_reexported_from_agent_utils(self):
        from tradingagents.agents.utils.agent_utils import (
            get_foreign_flow,
            get_market_depth,
            get_analyst_ratings,
        )
        # They are langchain @tool objects exposing .func.
        for t in (get_foreign_flow, get_market_depth, get_analyst_ratings):
            self.assertTrue(hasattr(t, "func"))

    def test_foreign_flow_tool_delegates(self):
        from tradingagents.agents.utils import microstructure_tools as mt
        with patch.object(mt, "_get_foreign_flow", return_value="FF") as f:
            self.assertEqual(mt.get_foreign_flow.func("FPT", "2026-06-07"), "FF")
        f.assert_called_once_with("FPT", "2026-06-07")

    def test_market_depth_tool_delegates(self):
        from tradingagents.agents.utils import microstructure_tools as mt
        with patch.object(mt, "_get_market_depth", return_value="MD") as f:
            self.assertEqual(mt.get_market_depth.func("FPT", "2026-06-07"), "MD")
        f.assert_called_once()

    def test_analyst_ratings_tool_delegates(self):
        from tradingagents.agents.utils import ratings_tools as rt
        with patch.object(rt, "_get_analyst_ratings", return_value="AR") as f:
            self.assertEqual(rt.get_analyst_ratings.func("FPT"), "AR")
        f.assert_called_once_with("FPT")

    def test_market_analyst_includes_new_tools(self):
        import tradingagents.agents.analysts.market_analyst as ma
        import inspect
        src = inspect.getsource(ma.create_market_analyst)
        self.assertIn("get_foreign_flow", src)
        self.assertIn("get_market_depth", src)

    def test_fundamentals_analyst_includes_ratings(self):
        import tradingagents.agents.analysts.fundamentals_analyst as fa
        import inspect
        src = inspect.getsource(fa.create_fundamentals_analyst)
        self.assertIn("get_analyst_ratings", src)


if __name__ == "__main__":
    unittest.main()
