"""Sentiment analyst — multi-source sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches three complementary data sources before
the LLM is invoked and injects them into the prompt as structured blocks:

  1. News headlines     — Yahoo Finance (institutional framing)
  2. StockTwits messages — retail-trader posts indexed by cashtag, with
                           user-labeled Bullish/Bearish sentiment tags
  3. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

The agent does not use tool-calling; the data is in the prompt from
turn 0. Output uses the structured-output pattern (json_schema for
OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic), falling
back to free-text generation for providers that lack native support, so
the sentiment header (band + score + confidence) is deterministic across
runs and providers instead of free-form per-model prose.

See: https://github.com/TauricResearch/TradingAgents/issues/557
See: https://github.com/TauricResearch/TradingAgents/issues/796
"""

from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import (
    SentimentBand,
    SentimentReport,
    render_sentiment_report,
)
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.vn_news import get_news_items


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Fetches Vietnamese ticker news (vnstock + cafef) as the sentiment input.
    A code-enforced F2 guardrail abstains (deterministic Neutral / low
    confidence, no LLM call) when too few usable news items exist, so the
    analyst can never fabricate sentiment from thin data. Above the threshold,
    it produces a structured report (with a free-text fallback).
    """
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)

        # VN sentiment input: ticker news (vnstock Company.news + cafef fallback).
        # Reddit / StockTwits are not used — they carry no Vietnamese-market data.
        news_items = get_news_items(ticker, start_date, end_date)

        # --- F2 guardrail (code-enforced, BEFORE the LLM) ---------------------
        # For a research tool, a confident sentiment read on thin data is worse
        # than an explicit abstention. If too few usable items exist, build a
        # deterministic Neutral / low-confidence report and skip the LLM so it
        # can never infer sentiment from noise.
        min_items = get_config().get("sentiment_min_items", 3)
        if len(news_items) < min_items:
            report = SentimentReport(
                overall_band=SentimentBand.NEUTRAL,
                overall_score=5.0,
                confidence="low",
                narrative=(
                    f"Insufficient sentiment data: only {len(news_items)} usable "
                    f"news item(s) found for {ticker} between {start_date} and "
                    f"{end_date} (minimum required: {min_items}). The Sentiment "
                    f"Analyst abstains rather than infer sentiment from too little "
                    f"data. Treat sentiment as unavailable for this ticker and "
                    f"weight fundamentals and technicals accordingly."
                ),
            )
            report_text = render_sentiment_report(report)
            return {
                "messages": [AIMessage(content=report_text)],
                "sentiment_report": report_text,
            }

        # --- Enough signal: let the analyst reason over the VN news ----------
        news_block = _format_news_items(news_items)
        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # Format the template into a concrete message list so the structured
        # and free-text paths receive the same input. No bind_tools — the
        # data is already in the prompt.
        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        return {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }

    return sentiment_analyst_node


def _format_news_items(items: list[dict]) -> str:
    """Render VN news item dicts into a prompt block."""
    block = ""
    for it in items:
        block += f"- {it.get('title', '').strip()}"
        if it.get("pub_date"):
            block += f" ({it['pub_date'].strftime('%Y-%m-%d')})"
        block += "\n"
        if it.get("description"):
            block += f"  {it['description'].strip()}\n"
    return block or "<no news>"


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
) -> str:
    """Assemble the sentiment-analyst system message from VN news.

    Vietnamese-market scope: the only sentiment source is ticker news
    (vnstock Company.news + cafef). There is no reliable VN retail-social feed
    (Reddit/StockTwits carry no VN data), so the analyst derives sentiment from
    news framing, volume, and recurring themes — and the node-level F2 guardrail
    has already guaranteed there is enough news to reason over.
    """
    return f"""You are a Vietnamese stock market sentiment analyst. Produce a sentiment report for {ticker} covering {start_date} to {end_date}, based on the company news collected for you below.

## Data source (pre-fetched, in this prompt)

### Vietnamese company news (vnstock / cafef)
News framing for the ticker over the window. This is the available sentiment signal; there is no reliable Vietnamese retail-social feed, so do not reference Reddit, StockTwits, or X.

<start_of_news>
{news_block}
<end_of_news>

## How to analyze this data

1. **Read the news framing.** Are headlines predominantly positive (contract wins, profit growth, dividends, foreign buying) or negative (losses, regulatory issues, selling pressure)?
2. **Weight by recency and volume.** More items on a theme = stronger signal. A single item is weak evidence.
3. **Distinguish event from opinion.** A reported event (earnings, ESOP, M&A) is harder signal than commentary.
4. **Identify recurring themes** across the items — the dominant narrative driving current sentiment.
5. **Be honest about data limits.** News-only sentiment is narrower than a multi-source read; reflect that in the `confidence` field.
6. **Past sentiment is not predictive.** Frame conclusions as one input for the trader to weigh alongside fundamentals and technicals, not a price call.

## Output fields

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish.
- **overall_score**: 0 (max bearish) to 10 (max bullish); 5 is neutral. Keep consistent with overall_band.
- **confidence**: low / medium / high, based on news volume and clarity. News-only input should rarely be "high".
- **narrative**: Theme-by-theme breakdown, dominant narrative, catalysts and risks, and a markdown summary table of key signals (direction, supporting evidence).

{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
