# Research Tab — Design Spec
**Date:** 2026-05-31

## Overview

Add a "Research" tab to the StocksApp with two integrated features:
1. **Find Tickers** — filter and discover stocks/ETFs with analyst data
2. **Analyze Stock** — full analysis report for a single ticker

Both features live in one tab. Clicking a Find Tickers result opens its analysis automatically.

---

## Architecture

- `research.py` — new module handling all data fetching (Finnhub for US, existing `tase.py` for TASE)
- `app.py` — new Flask routes calling `research.py`
- `templates/research.html` — new tab template with light JavaScript for async loading (no full page refreshes)
- `FINNHUB_API_KEY` — environment variable, read via `os.environ.get("FINNHUB_API_KEY")`

**Ticker routing:** app auto-detects US vs TASE based on ticker format. TASE tickers route to `tase.py`, all others to Finnhub.

---

## Feature 1: Find Tickers

### Filters
- Market (Israel or US)
- Security Type (Stock, ETF, Mutual Fund)
- Sector / Industry
- Momentum (% change over 1d / 1w / 1m)
- Market Cap (Small / Mid / Large)

### Presets
- "Save as Preset" button names and stores any filter combination
- Saved presets appear as clickable chips above the filter panel
- One click fills filters and runs the search

### Results
- 5–10 cards per page, "Load More" button for additional results
- Sort dropdown: Highest Upside % (default), Strongest Conviction, Best Momentum, Alphabetical
- Each card shows:
  - Ticker + company name
  - Recommendation badge — color-coded (Strong Buy → Strong Sell)
  - Analyst price target
  - Upside % (calculated: `(target - current) / current`)
  - Number of analysts
  - One-sentence company summary
- Clicking a card opens the Analyze Stock view for that ticker

---

## Feature 2: Analyze Stock

### Entry
- Search box at top of Research tab — accepts any US or TASE ticker
- Results load asynchronously in sections below (no full page refresh)

### Sections (in order)
1. **Price Summary** — current price, day range, 52-week high/low, % change today
2. **Analyst Consensus** — color-coded recommendation badge, price target, upside %, number of analysts
3. **Technical Indicators** — RSI, MACD, 50-day MA, 200-day MA
4. **Fundamentals** — P/E ratio, EPS, revenue growth, profit margin
5. **Recent News** — 5 latest headlines, each tagged bullish or bearish
6. **AI Summary** — loads last with a spinner; Claude reads all data above and writes a short paragraph covering: what the company does, key risks, and overall outlook

### Data Sources
- US stocks: Finnhub API
- Israeli stocks: existing TASE API (`tase.py`)

---

## Out of Scope
- Charting / price history graphs
- Portfolio integration (linking research to existing holdings)
- Alerts based on analyst changes
