"""F2 sentiment guardrail: abstain in code when VN news is too thin.

The Sentiment Analyst must never reason over noise. These tests prove that
below the configured item threshold the node returns a deterministic Neutral /
low-confidence report and does NOT invoke the LLM, and that above the threshold
the LLM reasoning path runs.
"""

import unittest
from unittest.mock import patch

import pytest

from tradingagents.agents.analysts import sentiment_analyst


def _items(n):
    return [
        {"title": f"FPT tin {i}", "description": "noi dung", "link": "", "pub_date": None}
        for i in range(n)
    ]


def _state():
    return {
        "company_of_interest": "FPT",
        "trade_date": "2026-06-07",
        "messages": [],
    }


@pytest.mark.unit
class SentimentGuardrailTests(unittest.TestCase):
    def setUp(self):
        # A dummy LLM whose structured binding would be used IF the LLM path ran.
        self._llm = object()

    def _run_with_items(self, n):
        node = None
        with patch.object(sentiment_analyst, "bind_structured", return_value="STRUCTURED_LLM"), \
             patch.object(sentiment_analyst, "get_config", return_value={"sentiment_min_items": 3}), \
             patch.object(sentiment_analyst, "get_instrument_context_from_state", return_value=""), \
             patch.object(sentiment_analyst, "get_news_items", return_value=_items(n)), \
             patch.object(sentiment_analyst, "invoke_structured_or_freetext") as invoke:
            node = sentiment_analyst.create_sentiment_analyst(self._llm)
            result = node(_state())
        return result, invoke

    def test_zero_items_abstains_without_llm(self):
        result, invoke = self._run_with_items(0)
        invoke.assert_not_called()
        self.assertIn("Insufficient sentiment data", result["sentiment_report"])
        self.assertIn("Neutral", result["sentiment_report"])
        self.assertIn("Low", result["sentiment_report"])

    def test_below_threshold_abstains_without_llm(self):
        result, invoke = self._run_with_items(2)
        invoke.assert_not_called()
        self.assertIn("only 2 usable news item", result["sentiment_report"])

    def test_at_threshold_invokes_llm(self):
        with patch.object(sentiment_analyst, "bind_structured", return_value="STRUCTURED_LLM"), \
             patch.object(sentiment_analyst, "get_config", return_value={"sentiment_min_items": 3}), \
             patch.object(sentiment_analyst, "get_instrument_context_from_state", return_value=""), \
             patch.object(sentiment_analyst, "get_news_items", return_value=_items(4)), \
             patch.object(sentiment_analyst, "invoke_structured_or_freetext", return_value="LLM REPORT") as invoke:
            node = sentiment_analyst.create_sentiment_analyst(self._llm)
            result = node(_state())
        invoke.assert_called_once()
        self.assertEqual(result["sentiment_report"], "LLM REPORT")

    def test_abstain_report_is_well_formed(self):
        result, _ = self._run_with_items(1)
        # Returns the standard message + report channels.
        self.assertIn("sentiment_report", result)
        self.assertIn("messages", result)
        self.assertEqual(result["messages"][0].content, result["sentiment_report"])


if __name__ == "__main__":
    unittest.main()
