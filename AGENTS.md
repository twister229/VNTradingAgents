# VNTradingAgents

Multi-agent LLM trading framework (built on LangGraph), customized for the
**Vietnamese stock market**. Data flows through vnstock (VCI source) by default;
agents analyze HOSE/HNX/UPCOM tickers (e.g. FPT, VNM, HPG) and produce reports
in Vietnamese.

## Skill routing (gstack)

When the user's request matches an available gstack skill, invoke it via the
Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas / brainstorming → invoke /office-hours
- Strategy / scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system / plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs / errors → invoke /investigate
- QA / testing site behavior → invoke /qa or /qa-only
- Code review / diff check → invoke /review
- Visual polish → invoke /design-review
- Ship / deploy / PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Web browsing → invoke /browse (never use mcp__claude-in-chrome__* tools)

## Project specifics

- **Data vendor:** vnstock is the default (`data_vendors` in
  `tradingagents/default_config.py`). The vendor router lives in
  `tradingagents/dataflows/interface.py`; `load_ohlcv` in
  `tradingagents/dataflows/stockstats_utils.py` is vendor-aware — keep it that
  way so indicators and the verified market snapshot follow the configured vendor.
- **VN symbols:** bare 3-letter codes (FPT, VNM, SSI). `normalize_symbol(sym, "VN")`
  short-circuits the Yahoo `=X` / `-USD` rules — do not let VN tickers hit them.
- **Market flag:** `config["market"] == "VN"` drives symbol normalization and the
  VN-Index benchmark fallback.
- **Tests:** `python -m pytest tests/ -q` (use a venv with the package installed
  editable plus vnstock + pytest).
- **Roadmap & decisions:** see `plans/2026-06-07-vn-market-phase1.md` and the
  design doc at `~/.gstack/projects/vntradingagents/2026-06-07-design-vn-market-only.md`.

## Conventions

- On missing/empty market data, raise `NoMarketDataError` — never return prose
  and never swallow an endpoint failure into an empty string (the router
  fallback and any data canary depend on the distinction).
- Internal agent debate stays in English for reasoning quality; final reports
  render in Vietnamese (`output_language`).
