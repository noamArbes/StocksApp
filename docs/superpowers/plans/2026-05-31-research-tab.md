# Research Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Research tab to the StocksApp with two features: Find Tickers (filter + presets) and Analyze Stock (full report with AI summary).

**Architecture:** A new `research.py` module handles all Finnhub and TASE data fetching. Flask routes in `app.py` call `research.py` and serve JSON to the frontend. A new `templates/research.html` renders the Research tab with async JS fetches so the page never fully refreshes.

**Tech Stack:** Python/Flask (existing), Finnhub REST API (via `urllib.request`), existing `tase.py` for Israeli stocks, Anthropic SDK for AI summary, `yfinance` (already installed) as fallback for fundamentals.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `research.py` | Create | All data fetching: Finnhub quote, analyst data, technicals, fundamentals, news, AI summary |
| `app.py` | Modify | Add 6 new Flask routes for research features; add `_PRESETS_PATH` |
| `presets.json` | Create (auto) | Saved filter presets, written at runtime |
| `templates/research.html` | Create | Research tab UI with filter panel, results, analysis sections |
| `templates/dashboard.html` | Modify | Add Research tab to the tab bar |
| `tests/test_research.py` | Create | Unit tests for `research.py` logic |

---

## Task 1: Set up `research.py` skeleton and Finnhub quote fetching

**Files:**
- Create: `research.py`
- Create: `tests/test_research.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_research.py
import pytest
from unittest.mock import patch, MagicMock
import json
import research


def test_is_tase_ticker():
    assert research.is_tase_ticker("TEVA.TA") is False
    assert research.is_tase_ticker("1082") is True
    assert research.is_tase_ticker("AAPL") is False


def test_finnhub_quote_returns_expected_keys():
    mock_data = {
        "c": 150.0, "h": 155.0, "l": 148.0,
        "pc": 149.0, "dp": 0.67
    }
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = mock_data
        result = research.get_quote("AAPL")
    assert result["price"] == 150.0
    assert result["prev_close"] == 149.0
    assert result["day_high"] == 155.0
    assert result["day_low"] == 148.0
    assert result["change_pct"] == 0.67


def test_finnhub_quote_returns_none_on_empty():
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = {}
        result = research.get_quote("AAPL")
    assert result is None
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_research.py -v
```
Expected: ImportError or AttributeError — `research` doesn't exist yet.

- [ ] **Step 3: Write `research.py` with skeleton and quote fetching**

```python
# research.py
import json
import os
import urllib.request
import urllib.parse
import urllib.error

_FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
_BASE = "https://finnhub.io/api/v1"


def _finnhub_get(path: str, params: dict) -> dict:
    """Make a GET request to Finnhub. Returns parsed JSON or {} on failure."""
    params["token"] = _FINNHUB_KEY
    url = f"{_BASE}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "StocksApp/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[WARN] Finnhub request failed {path}: {e}")
        return {}


def is_tase_ticker(ticker: str) -> bool:
    """Returns True if ticker looks like a TASE numeric ID."""
    return ticker.isdigit()


def get_quote(ticker: str) -> dict | None:
    """Fetch current price data for a US ticker. Returns None on failure."""
    data = _finnhub_get("/quote", {"symbol": ticker})
    if not data or data.get("c") in (None, 0):
        return None
    return {
        "price": data.get("c"),
        "prev_close": data.get("pc"),
        "day_high": data.get("h"),
        "day_low": data.get("l"),
        "change_pct": data.get("dp"),
        "week52_high": data.get("h"),
        "week52_low": data.get("l"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_research.py -v
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add research.py skeleton with Finnhub quote fetching"
```

---

## Task 2: Analyst data and company profile

**Files:**
- Modify: `research.py`
- Modify: `tests/test_research.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_research.py`:

```python
def test_get_analyst_data_maps_recommendation():
    mock_rec = {"buy": 10, "hold": 5, "sell": 2, "strongBuy": 8, "strongSell": 1}
    mock_target = {"targetMean": 180.0, "targetHigh": 200.0, "targetLow": 160.0}
    with patch("research._finnhub_get") as mock_get:
        mock_get.side_effect = [mock_rec, mock_target]
        result = research.get_analyst_data("AAPL", current_price=150.0)
    assert result["recommendation"] == "Strong Buy"
    assert result["target_mean"] == 180.0
    assert result["upside_pct"] == pytest.approx(20.0, rel=0.01)
    assert result["num_analysts"] == 26


def test_get_analyst_data_returns_none_on_empty():
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = {}
        result = research.get_analyst_data("AAPL", current_price=150.0)
    assert result is None


def test_get_company_profile_returns_summary():
    mock_profile = {
        "name": "Apple Inc",
        "finnhubIndustry": "Technology",
        "marketCapitalization": 2800000.0,
        "description": "Apple designs and sells consumer electronics."
    }
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = mock_profile
        result = research.get_company_profile("AAPL")
    assert result["name"] == "Apple Inc"
    assert result["sector"] == "Technology"
    assert result["market_cap"] == 2800000.0
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_research.py::test_get_analyst_data_maps_recommendation -v
```
Expected: AttributeError — functions don't exist yet.

- [ ] **Step 3: Add analyst and profile functions to `research.py`**

Add after `get_quote`:

```python
_REC_LABELS = {
    "strongBuy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "sell": "Sell",
    "strongSell": "Strong Sell",
}

_REC_COLORS = {
    "Strong Buy": "green-dark",
    "Buy": "green",
    "Hold": "yellow",
    "Sell": "red",
    "Strong Sell": "red-dark",
}


def get_analyst_data(ticker: str, current_price: float) -> dict | None:
    """Fetch analyst recommendation and price target for a US ticker."""
    rec_data = _finnhub_get("/stock/recommendation", {"symbol": ticker})
    target_data = _finnhub_get("/stock/price-target", {"symbol": ticker})
    if not rec_data or not target_data:
        return None

    # rec_data is a list sorted by period; use most recent
    if isinstance(rec_data, list):
        rec_data = rec_data[0] if rec_data else {}

    counts = {k: rec_data.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
    total = sum(counts.values())
    if total == 0:
        return None

    # Weighted score: strongBuy=2, buy=1, hold=0, sell=-1, strongSell=-2
    score = (
        counts["strongBuy"] * 2 +
        counts["buy"] * 1 +
        counts["hold"] * 0 +
        counts["sell"] * -1 +
        counts["strongSell"] * -2
    ) / total

    if score >= 1.5:
        rec_key = "strongBuy"
    elif score >= 0.5:
        rec_key = "buy"
    elif score >= -0.5:
        rec_key = "hold"
    elif score >= -1.5:
        rec_key = "sell"
    else:
        rec_key = "strongSell"

    target_mean = target_data.get("targetMean")
    upside_pct = None
    if target_mean and current_price:
        upside_pct = round((target_mean - current_price) / current_price * 100, 1)

    return {
        "recommendation": _REC_LABELS[rec_key],
        "color": _REC_COLORS[_REC_LABELS[rec_key]],
        "target_mean": target_mean,
        "target_high": target_data.get("targetHigh"),
        "target_low": target_data.get("targetLow"),
        "upside_pct": upside_pct,
        "num_analysts": total,
        "counts": counts,
    }


def get_company_profile(ticker: str) -> dict | None:
    """Fetch company name, sector, market cap."""
    data = _finnhub_get("/stock/profile2", {"symbol": ticker})
    if not data or not data.get("name"):
        return None
    return {
        "name": data.get("name"),
        "sector": data.get("finnhubIndustry"),
        "market_cap": data.get("marketCapitalization"),
        "description": data.get("description", ""),
    }
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_research.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add analyst data and company profile fetching"
```

---

## Task 3: News fetching and sentiment tagging

**Files:**
- Modify: `research.py`
- Modify: `tests/test_research.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research.py`:

```python
def test_get_news_returns_sentiment_tagged_headlines():
    from datetime import date
    today = date.today().isoformat()
    mock_news = [
        {"headline": "Apple crushes earnings expectations", "datetime": 1700000000, "url": "http://a.com"},
        {"headline": "Apple faces antitrust probe", "datetime": 1700000001, "url": "http://b.com"},
    ]
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = mock_news
        result = research.get_news("AAPL", limit=5)
    assert len(result) == 2
    assert result[0]["headline"] == "Apple crushes earnings expectations"
    assert result[0]["sentiment"] in ("bullish", "bearish", "neutral")
    assert "url" in result[0]
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_research.py::test_get_news_returns_sentiment_tagged_headlines -v
```
Expected: AttributeError.

- [ ] **Step 3: Add `get_news` to `research.py`**

Add after `get_company_profile`:

```python
_BULLISH_WORDS = {"surge", "soar", "beat", "record", "profit", "gain", "rally", "upgrade",
                  "crush", "strong", "growth", "bullish", "positive", "rise", "raises"}
_BEARISH_WORDS = {"fall", "drop", "miss", "loss", "decline", "downgrade", "risk", "probe",
                  "lawsuit", "cut", "weak", "bearish", "negative", "plunge", "warning", "layoff"}


def _sentiment(headline: str) -> str:
    words = set(headline.lower().split())
    if words & _BULLISH_WORDS:
        return "bullish"
    if words & _BEARISH_WORDS:
        return "bearish"
    return "neutral"


def get_news(ticker: str, limit: int = 5) -> list[dict]:
    """Fetch recent news headlines for a US ticker with sentiment tags."""
    from datetime import date, timedelta
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=7)).isoformat()
    data = _finnhub_get("/company-news", {
        "symbol": ticker, "from": from_date, "to": to_date
    })
    if not isinstance(data, list):
        return []
    results = []
    for item in data[:limit]:
        headline = item.get("headline", "")
        if not headline:
            continue
        results.append({
            "headline": headline,
            "url": item.get("url", ""),
            "sentiment": _sentiment(headline),
        })
    return results
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_research.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add news fetching with keyword-based sentiment tagging"
```

---

## Task 4: Technical indicators (RSI, MACD, moving averages)

**Files:**
- Modify: `research.py`
- Modify: `tests/test_research.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research.py`:

```python
def test_get_technicals_returns_expected_keys():
    with patch("research._get_yfinance_history") as mock_hist:
        import pandas as pd
        # 60 days of fake closing prices
        prices = [100 + i * 0.5 for i in range(60)]
        mock_hist.return_value = pd.Series(prices)
        result = research.get_technicals("AAPL")
    assert "rsi" in result
    assert "ma50" in result
    assert "ma200" in result
    assert "macd" in result
    assert "macd_signal" in result
    assert isinstance(result["rsi"], float)


def test_get_technicals_returns_none_on_insufficient_data():
    with patch("research._get_yfinance_history") as mock_hist:
        import pandas as pd
        mock_hist.return_value = pd.Series([100.0, 101.0])
        result = research.get_technicals("AAPL")
    assert result is None
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_research.py::test_get_technicals_returns_expected_keys -v
```
Expected: AttributeError.

- [ ] **Step 3: Add `get_technicals` to `research.py`**

Add after `get_news`:

```python
def _get_yfinance_history(ticker: str) -> "pd.Series":
    """Fetch 1y of closing prices via yfinance. Returns pd.Series."""
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="1y")
    return hist["Close"]


def _calc_rsi(prices: "pd.Series", period: int = 14) -> float | None:
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 2) if not (val != val) else None  # NaN check


def _calc_macd(prices: "pd.Series") -> tuple[float | None, float | None]:
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    m = macd_line.iloc[-1]
    s = signal.iloc[-1]
    nan = float("nan")
    return (round(float(m), 4) if m == m else None,
            round(float(s), 4) if s == s else None)


def get_technicals(ticker: str) -> dict | None:
    """Calculate RSI, MACD, and moving averages from 1y price history."""
    try:
        closes = _get_yfinance_history(ticker)
    except Exception:
        return None
    if len(closes) < 30:
        return None
    rsi = _calc_rsi(closes)
    macd, macd_signal = _calc_macd(closes)
    ma50 = round(float(closes.tail(50).mean()), 2) if len(closes) >= 50 else None
    ma200 = round(float(closes.tail(200).mean()), 2) if len(closes) >= 200 else None
    return {
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_signal,
        "ma50": ma50,
        "ma200": ma200,
    }
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_research.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add technical indicators (RSI, MACD, moving averages)"
```

---

## Task 5: Fundamentals fetching

**Files:**
- Modify: `research.py`
- Modify: `tests/test_research.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research.py`:

```python
def test_get_fundamentals_returns_expected_keys():
    mock_data = {
        "metric": {
            "peNormalizedAnnual": 28.5,
            "epsNormalizedAnnual": 6.13,
            "revenueGrowthTTMYoy": 0.08,
            "netProfitMarginAnnual": 0.25,
        }
    }
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = mock_data
        result = research.get_fundamentals("AAPL")
    assert result["pe_ratio"] == 28.5
    assert result["eps"] == 6.13
    assert result["revenue_growth_pct"] == pytest.approx(8.0)
    assert result["profit_margin_pct"] == pytest.approx(25.0)
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_research.py::test_get_fundamentals_returns_expected_keys -v
```
Expected: AttributeError.

- [ ] **Step 3: Add `get_fundamentals` to `research.py`**

Add after `get_technicals`:

```python
def get_fundamentals(ticker: str) -> dict | None:
    """Fetch P/E, EPS, revenue growth, profit margin from Finnhub basic financials."""
    data = _finnhub_get("/stock/metric", {"symbol": ticker, "metric": "all"})
    m = data.get("metric", {})
    if not m:
        return None
    rev_growth = m.get("revenueGrowthTTMYoy")
    margin = m.get("netProfitMarginAnnual")
    return {
        "pe_ratio": m.get("peNormalizedAnnual"),
        "eps": m.get("epsNormalizedAnnual"),
        "revenue_growth_pct": round(rev_growth * 100, 1) if rev_growth is not None else None,
        "profit_margin_pct": round(margin * 100, 1) if margin is not None else None,
    }
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_research.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add fundamentals fetching (P/E, EPS, revenue growth, profit margin)"
```

---

## Task 6: AI summary via Claude API

**Files:**
- Modify: `research.py`
- Modify: `tests/test_research.py`

First install the Anthropic SDK if not present:

```
pip install anthropic
```

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research.py`:

```python
def test_get_ai_summary_returns_string():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Apple is a technology company with strong fundamentals.")]
    )
    with patch("research._get_anthropic_client", return_value=mock_client):
        result = research.get_ai_summary("AAPL", {
            "quote": {"price": 150.0, "change_pct": 0.5},
            "analyst": {"recommendation": "Buy", "target_mean": 180.0, "upside_pct": 20.0, "num_analysts": 20},
            "fundamentals": {"pe_ratio": 28.0, "eps": 6.0, "revenue_growth_pct": 8.0, "profit_margin_pct": 25.0},
            "news": [{"headline": "Apple beats earnings", "sentiment": "bullish"}],
        })
    assert isinstance(result, str)
    assert len(result) > 10
```

- [ ] **Step 2: Run to verify it fails**

```
pytest tests/test_research.py::test_get_ai_summary_returns_string -v
```
Expected: AttributeError.

- [ ] **Step 3: Add `get_ai_summary` to `research.py`**

Add after `get_fundamentals`:

```python
def _get_anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def get_ai_summary(ticker: str, data: dict) -> str:
    """Call Claude to generate a 2-3 sentence analysis summary."""
    quote = data.get("quote") or {}
    analyst = data.get("analyst") or {}
    fundamentals = data.get("fundamentals") or {}
    news = data.get("news") or []

    news_lines = "\n".join(f"- {n['headline']} ({n['sentiment']})" for n in news[:5])

    prompt = f"""You are a financial analyst. Write a 2-3 sentence summary for {ticker} based on the data below.
Cover: what the company does (briefly), the key opportunity or risk right now, and the overall outlook.
Be factual and concise. Do not use bullet points.

Price: ${quote.get('price')} ({quote.get('change_pct', 0):+.1f}% today)
Analyst consensus: {analyst.get('recommendation')} | Target: ${analyst.get('target_mean')} | Upside: {analyst.get('upside_pct')}% | Analysts: {analyst.get('num_analysts')}
P/E: {fundamentals.get('pe_ratio')} | EPS: {fundamentals.get('eps')} | Revenue growth: {fundamentals.get('revenue_growth_pct')}% | Profit margin: {fundamentals.get('profit_margin_pct')}%
Recent news:
{news_lines}"""

    try:
        client = _get_anthropic_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[WARN] AI summary failed for {ticker}: {e}")
        return ""
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_research.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add AI summary via Claude Haiku"
```

---

## Task 7: Find-tickers search logic

**Files:**
- Modify: `research.py`
- Modify: `tests/test_research.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research.py`:

```python
def test_find_tickers_filters_by_market_us():
    mock_results = [
        {"symbol": "AAPL", "description": "Apple Inc", "type": "Common Stock"},
        {"symbol": "MSFT", "description": "Microsoft", "type": "Common Stock"},
    ]
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = mock_results
        results = research.find_tickers(market="us", security_type="stock", sector=None,
                                        momentum=None, market_cap=None, limit=10)
    assert len(results) > 0
    assert all("ticker" in r for r in results)


def test_sort_ticker_results_by_upside():
    results = [
        {"ticker": "A", "upside_pct": 5.0, "recommendation": "Buy", "num_analysts": 10},
        {"ticker": "B", "upside_pct": 20.0, "recommendation": "Strong Buy", "num_analysts": 15},
        {"ticker": "C", "upside_pct": 10.0, "recommendation": "Hold", "num_analysts": 5},
    ]
    sorted_results = research.sort_ticker_results(results, sort_by="upside")
    assert sorted_results[0]["ticker"] == "B"
    assert sorted_results[1]["ticker"] == "C"


def test_sort_ticker_results_by_conviction():
    results = [
        {"ticker": "A", "upside_pct": 5.0, "recommendation": "Buy", "num_analysts": 10},
        {"ticker": "B", "upside_pct": 20.0, "recommendation": "Strong Buy", "num_analysts": 15},
        {"ticker": "C", "upside_pct": 10.0, "recommendation": "Hold", "num_analysts": 5},
    ]
    sorted_results = research.sort_ticker_results(results, sort_by="conviction")
    assert sorted_results[0]["ticker"] == "B"
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_research.py::test_find_tickers_filters_by_market_us -v
```
Expected: AttributeError.

- [ ] **Step 3: Add `find_tickers` and `sort_ticker_results` to `research.py`**

Add after `get_ai_summary`:

```python
_REC_RANK = {
    "Strong Buy": 5, "Buy": 4, "Hold": 3, "Sell": 2, "Strong Sell": 1, None: 0
}

_MARKET_CAP_RANGES = {
    "small": (0, 2_000),          # under $2B (in millions)
    "mid": (2_000, 10_000),
    "large": (10_000, float("inf")),
}


def find_tickers(market: str, security_type: str | None, sector: str | None,
                 momentum: str | None, market_cap: str | None, limit: int = 10) -> list[dict]:
    """
    Search for tickers matching the given filters.
    market: 'us' or 'israel'
    security_type: 'stock', 'etf', 'fund', or None
    sector: sector string or None
    momentum: '1d', '1w', '1m', or None
    market_cap: 'small', 'mid', 'large', or None
    Returns list of dicts with ticker, name, recommendation, target_mean, upside_pct, num_analysts, summary.
    """
    if market == "israel":
        # TASE search is handled separately — return empty here
        return []

    # Use Finnhub symbol search to get candidate tickers
    query = sector or security_type or "S&P 500"
    raw = _finnhub_get("/search", {"q": query})
    candidates = raw.get("result", []) if isinstance(raw, dict) else []

    results = []
    for item in candidates[:50]:
        ticker = item.get("symbol", "")
        if not ticker or "." in ticker:  # skip non-US (e.g. AAPL.MX)
            continue

        # Type filter
        item_type = item.get("type", "").lower()
        if security_type == "stock" and item_type not in ("common stock", ""):
            continue
        if security_type == "etf" and "etf" not in item_type:
            continue

        # Fetch quote and analyst data
        quote = get_quote(ticker)
        if not quote:
            continue

        analyst = get_analyst_data(ticker, quote["price"])
        profile = get_company_profile(ticker)

        # Market cap filter
        if market_cap and profile:
            cap = profile.get("market_cap") or 0
            lo, hi = _MARKET_CAP_RANGES.get(market_cap, (0, float("inf")))
            if not (lo <= cap < hi):
                continue

        results.append({
            "ticker": ticker,
            "name": profile.get("name", ticker) if profile else ticker,
            "sector": profile.get("sector") if profile else None,
            "recommendation": analyst.get("recommendation") if analyst else None,
            "color": analyst.get("color") if analyst else "gray",
            "target_mean": analyst.get("target_mean") if analyst else None,
            "upside_pct": analyst.get("upside_pct") if analyst else None,
            "num_analysts": analyst.get("num_analysts") if analyst else 0,
            "price": quote["price"],
            "change_pct": quote["change_pct"],
        })

        if len(results) >= limit * 2:
            break

    return results


def sort_ticker_results(results: list[dict], sort_by: str) -> list[dict]:
    """Sort find-ticker results. sort_by: 'upside', 'conviction', 'momentum', 'alpha'."""
    if sort_by == "upside":
        return sorted(results, key=lambda r: r.get("upside_pct") or -999, reverse=True)
    if sort_by == "conviction":
        return sorted(results,
                      key=lambda r: (_REC_RANK.get(r.get("recommendation"), 0),
                                     r.get("num_analysts") or 0),
                      reverse=True)
    if sort_by == "momentum":
        return sorted(results, key=lambda r: r.get("change_pct") or -999, reverse=True)
    return sorted(results, key=lambda r: r.get("ticker", ""))
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_research.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add find_tickers and sort_ticker_results logic"
```

---

## Task 8: Presets storage

**Files:**
- Modify: `research.py`
- Modify: `tests/test_research.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_research.py`:

```python
def test_save_and_load_preset(tmp_path):
    path = str(tmp_path / "presets.json")
    research.save_preset(path, "Israeli Tech", {
        "market": "israel", "security_type": "stock",
        "sector": "Technology", "momentum": None, "market_cap": None
    })
    presets = research.load_presets(path)
    assert len(presets) == 1
    assert presets[0]["name"] == "Israeli Tech"
    assert presets[0]["filters"]["market"] == "israel"


def test_delete_preset(tmp_path):
    path = str(tmp_path / "presets.json")
    research.save_preset(path, "Test", {"market": "us"})
    presets = research.load_presets(path)
    preset_id = presets[0]["id"]
    research.delete_preset(path, preset_id)
    assert research.load_presets(path) == []
```

- [ ] **Step 2: Run to verify they fail**

```
pytest tests/test_research.py::test_save_and_load_preset -v
```
Expected: AttributeError.

- [ ] **Step 3: Add preset functions to `research.py`**

Add at the top of the file after imports:

```python
import uuid as _uuid
```

Add after `sort_ticker_results`:

```python
def load_presets(path: str) -> list[dict]:
    """Load saved filter presets from JSON file."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_preset(path: str, name: str, filters: dict) -> dict:
    """Append a named preset. Returns the new preset dict."""
    presets = load_presets(path)
    preset = {"id": str(_uuid.uuid4())[:8], "name": name, "filters": filters}
    presets.append(preset)
    with open(path, "w") as f:
        json.dump(presets, f, indent=2)
    return preset


def delete_preset(path: str, preset_id: str) -> None:
    """Remove a preset by id."""
    presets = [p for p in load_presets(path) if p.get("id") != preset_id]
    with open(path, "w") as f:
        json.dump(presets, f, indent=2)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_research.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add research.py tests/test_research.py
git commit -m "feat: add preset save/load/delete for find-tickers filters"
```

---

## Task 9: Flask routes in `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add `_PRESETS_PATH` to startup block in `app.py`**

After the existing path constants (around line 37), add:

```python
_PRESETS_PATH = os.path.join(os.path.dirname(__file__), "presets.json")
```

Also add `import research` at the top with the other imports.

- [ ] **Step 2: Add the 6 research routes**

Add this block before the `if __name__ == "__main__":` line at the bottom of `app.py`:

```python
# --- Research routes ---

@app.route("/research")
@login_required
def research_tab():
    return render_template("research.html")


@app.route("/api/research/analyze")
@login_required
def research_analyze():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    if research.is_tase_ticker(ticker):
        return jsonify({"error": "TASE analysis not yet supported"}), 400
    quote = research.get_quote(ticker)
    if not quote:
        return jsonify({"error": f"Could not fetch data for {ticker}"}), 404
    analyst = research.get_analyst_data(ticker, quote["price"])
    profile = research.get_company_profile(ticker)
    technicals = research.get_technicals(ticker)
    fundamentals = research.get_fundamentals(ticker)
    news = research.get_news(ticker)
    return jsonify({
        "ticker": ticker,
        "quote": quote,
        "analyst": analyst,
        "profile": profile,
        "technicals": technicals,
        "fundamentals": fundamentals,
        "news": news,
    })


@app.route("/api/research/ai-summary")
@login_required
def research_ai_summary():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    quote = research.get_quote(ticker)
    analyst = research.get_analyst_data(ticker, quote["price"]) if quote else None
    fundamentals = research.get_fundamentals(ticker)
    news = research.get_news(ticker)
    summary = research.get_ai_summary(ticker, {
        "quote": quote, "analyst": analyst,
        "fundamentals": fundamentals, "news": news,
    })
    return jsonify({"summary": summary})


@app.route("/api/research/find-tickers")
@login_required
def research_find_tickers():
    market = request.args.get("market", "us")
    security_type = request.args.get("security_type") or None
    sector = request.args.get("sector") or None
    momentum = request.args.get("momentum") or None
    market_cap = request.args.get("market_cap") or None
    sort_by = request.args.get("sort_by", "upside")
    offset = int(request.args.get("offset", 0))
    limit = 10
    results = research.find_tickers(
        market=market, security_type=security_type, sector=sector,
        momentum=momentum, market_cap=market_cap, limit=offset + limit
    )
    sorted_results = research.sort_ticker_results(results, sort_by)
    page = sorted_results[offset:offset + limit]
    return jsonify({"results": page, "has_more": len(sorted_results) > offset + limit})


@app.route("/api/research/presets", methods=["GET"])
@login_required
def research_presets_list():
    return jsonify(research.load_presets(_PRESETS_PATH))


@app.route("/api/research/presets", methods=["POST"])
@login_required
def research_presets_save():
    body = request.get_json()
    if not body or not body.get("name"):
        return jsonify({"error": "name required"}), 400
    preset = research.save_preset(_PRESETS_PATH, body["name"], body.get("filters", {}))
    return jsonify(preset)


@app.route("/api/research/presets/<preset_id>", methods=["DELETE"])
@login_required
def research_presets_delete(preset_id):
    research.delete_preset(_PRESETS_PATH, preset_id)
    return jsonify({"ok": True})
```

- [ ] **Step 3: Run all tests to make sure nothing broke**

```
pytest tests/ -v
```
Expected: all existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add research Flask routes (analyze, find-tickers, presets, ai-summary)"
```

---

## Task 10: Add Research tab to `dashboard.html`

**Files:**
- Modify: `templates/dashboard.html`

- [ ] **Step 1: Add the Research tab link to the tab bar**

In `templates/dashboard.html`, find the tab bar block (around line 11–21):

```html
<div class="tab-bar">
    <a href="{{ url_for('dashboard') }}"
       class="tab {% if tab not in ('history', 'savings') %}tab-active{% endif %}">Alarms</a>
    <a href="{{ url_for('dashboard', tab='history') }}"
       class="tab {% if tab == 'history' %}tab-active{% endif %}">Trade History</a>
    <a href="{{ url_for('savings') }}"
       class="tab {% if tab == 'savings' %}tab-active{% endif %}">Savings</a>
    {% if tab == 'history' %}
    <a href="{{ url_for('trade_new') }}" class="btn btn-primary" style="margin-left:auto">+ Add Trade</a>
    {% endif %}
</div>
```

Replace with:

```html
<div class="tab-bar">
    <a href="{{ url_for('dashboard') }}"
       class="tab {% if tab not in ('history', 'savings') %}tab-active{% endif %}">Alarms</a>
    <a href="{{ url_for('dashboard', tab='history') }}"
       class="tab {% if tab == 'history' %}tab-active{% endif %}">Trade History</a>
    <a href="{{ url_for('savings') }}"
       class="tab {% if tab == 'savings' %}tab-active{% endif %}">Savings</a>
    <a href="{{ url_for('research_tab') }}"
       class="tab">Research</a>
    {% if tab == 'history' %}
    <a href="{{ url_for('trade_new') }}" class="btn btn-primary" style="margin-left:auto">+ Add Trade</a>
    {% endif %}
</div>
```

- [ ] **Step 2: Verify the app starts without errors**

```
python app.py
```
Expected: starts on port 5000, no import or template errors.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat: add Research tab link to dashboard tab bar"
```

---

## Task 11: Build `research.html` — Find Tickers UI

**Files:**
- Create: `templates/research.html`

- [ ] **Step 1: Create the template**

```html
{% extends "base.html" %}
{% block content %}
<div class="toolbar">
  <h2>Research</h2>
</div>

<div class="tab-bar">
  <button class="tab tab-active" id="tab-find" onclick="switchTab('find')">Find Tickers</button>
  <button class="tab" id="tab-analyze" onclick="switchTab('analyze')">Analyze Stock</button>
</div>

{# ── Find Tickers ── #}
<div id="panel-find">

  {# Preset chips #}
  <div id="preset-chips" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px"></div>

  {# Filter panel #}
  <div class="card" style="margin-bottom:16px">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
      <div>
        <label class="form-label">Market</label>
        <select id="f-market" class="form-input">
          <option value="us">United States</option>
          <option value="israel">Israel (TASE)</option>
        </select>
      </div>
      <div>
        <label class="form-label">Type</label>
        <select id="f-type" class="form-input">
          <option value="">Any</option>
          <option value="stock">Stock</option>
          <option value="etf">ETF</option>
          <option value="fund">Fund</option>
        </select>
      </div>
      <div>
        <label class="form-label">Sector</label>
        <select id="f-sector" class="form-input">
          <option value="">Any</option>
          <option>Technology</option>
          <option>Healthcare</option>
          <option>Finance</option>
          <option>Energy</option>
          <option>Consumer</option>
          <option>Industrials</option>
          <option>Real Estate</option>
          <option>Utilities</option>
        </select>
      </div>
      <div>
        <label class="form-label">Momentum</label>
        <select id="f-momentum" class="form-input">
          <option value="">Any</option>
          <option value="1d">Today</option>
          <option value="1w">This Week</option>
          <option value="1m">This Month</option>
        </select>
      </div>
      <div>
        <label class="form-label">Market Cap</label>
        <select id="f-marketcap" class="form-input">
          <option value="">Any</option>
          <option value="small">Small (&lt;$2B)</option>
          <option value="mid">Mid ($2B–$10B)</option>
          <option value="large">Large (&gt;$10B)</option>
        </select>
      </div>
      <div>
        <label class="form-label">Sort By</label>
        <select id="f-sort" class="form-input">
          <option value="upside">Highest Upside %</option>
          <option value="conviction">Strongest Conviction</option>
          <option value="momentum">Best Momentum</option>
          <option value="alpha">Alphabetical</option>
        </select>
      </div>
    </div>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn btn-primary" onclick="runSearch(0)">Search</button>
      <button class="btn" onclick="openSavePreset()">Save as Preset</button>
    </div>
  </div>

  {# Save preset modal #}
  <div id="preset-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:100;align-items:center;justify-content:center">
    <div class="card" style="width:320px">
      <h3 style="margin-bottom:12px">Save Preset</h3>
      <input id="preset-name-input" class="form-input" placeholder="e.g. Israeli Tech Stocks" style="margin-bottom:12px">
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" onclick="confirmSavePreset()">Save</button>
        <button class="btn" onclick="closePresetModal()">Cancel</button>
      </div>
    </div>
  </div>

  {# Results #}
  <div id="find-results"></div>
  <div id="find-load-more" style="display:none;text-align:center;margin-top:12px">
    <button class="btn" onclick="loadMore()">Load More</button>
  </div>
</div>

{# ── Analyze Stock ── #}
<div id="panel-analyze" style="display:none">
  <div class="card" style="margin-bottom:16px;display:flex;gap:8px">
    <input id="analyze-ticker" class="form-input" placeholder="Enter ticker (e.g. AAPL)" style="flex:1">
    <button class="btn btn-primary" onclick="runAnalysis()">Analyze</button>
  </div>
  <div id="analyze-results"></div>
</div>

{% endblock %}

{% block scripts %}
<script>
// ── Tab switching ──
function switchTab(tab) {
  document.getElementById('panel-find').style.display = tab === 'find' ? '' : 'none';
  document.getElementById('panel-analyze').style.display = tab === 'analyze' ? '' : 'none';
  document.getElementById('tab-find').className = 'tab' + (tab === 'find' ? ' tab-active' : '');
  document.getElementById('tab-analyze').className = 'tab' + (tab === 'analyze' ? ' tab-active' : '');
}

// ── Presets ──
let _currentOffset = 0;

async function loadPresets() {
  const res = await fetch('/api/research/presets');
  const presets = await res.json();
  const container = document.getElementById('preset-chips');
  container.innerHTML = '';
  presets.forEach(p => {
    const chip = document.createElement('span');
    chip.style.cssText = 'display:inline-flex;align-items:center;gap:4px;background:var(--surface);border:1px solid var(--border);border-radius:999px;padding:4px 12px;cursor:pointer;font-size:.85rem';
    chip.innerHTML = `${p.name} <button onclick="deletePreset('${p.id}',event)" style="background:none;border:none;cursor:pointer;opacity:.5;font-size:.75rem">✕</button>`;
    chip.onclick = () => applyPreset(p.filters);
    container.appendChild(chip);
  });
}

function applyPreset(filters) {
  if (filters.market) document.getElementById('f-market').value = filters.market;
  if (filters.security_type) document.getElementById('f-type').value = filters.security_type;
  if (filters.sector) document.getElementById('f-sector').value = filters.sector;
  if (filters.momentum) document.getElementById('f-momentum').value = filters.momentum;
  if (filters.market_cap) document.getElementById('f-marketcap').value = filters.market_cap;
  runSearch(0);
}

function openSavePreset() {
  document.getElementById('preset-modal').style.display = 'flex';
  document.getElementById('preset-name-input').focus();
}

function closePresetModal() {
  document.getElementById('preset-modal').style.display = 'none';
  document.getElementById('preset-name-input').value = '';
}

async function confirmSavePreset() {
  const name = document.getElementById('preset-name-input').value.trim();
  if (!name) return;
  const filters = currentFilters();
  await fetch('/api/research/presets', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, filters}),
  });
  closePresetModal();
  loadPresets();
}

async function deletePreset(id, e) {
  e.stopPropagation();
  await fetch(`/api/research/presets/${id}`, {method: 'DELETE'});
  loadPresets();
}

// ── Find Tickers ──
function currentFilters() {
  return {
    market: document.getElementById('f-market').value,
    security_type: document.getElementById('f-type').value || null,
    sector: document.getElementById('f-sector').value || null,
    momentum: document.getElementById('f-momentum').value || null,
    market_cap: document.getElementById('f-marketcap').value || null,
  };
}

async function runSearch(offset) {
  _currentOffset = offset;
  const f = currentFilters();
  const sort = document.getElementById('f-sort').value;
  const params = new URLSearchParams({
    market: f.market,
    sort_by: sort,
    offset,
    ...(f.security_type && {security_type: f.security_type}),
    ...(f.sector && {sector: f.sector}),
    ...(f.momentum && {momentum: f.momentum}),
    ...(f.market_cap && {market_cap: f.market_cap}),
  });
  const container = document.getElementById('find-results');
  if (offset === 0) container.innerHTML = '<p style="opacity:.5">Loading...</p>';
  const res = await fetch('/api/research/find-tickers?' + params);
  const data = await res.json();
  if (offset === 0) container.innerHTML = '';
  if (!data.results || data.results.length === 0) {
    if (offset === 0) container.innerHTML = '<p style="opacity:.5">No results found.</p>';
    document.getElementById('find-load-more').style.display = 'none';
    return;
  }
  data.results.forEach(r => container.appendChild(buildTickerCard(r)));
  document.getElementById('find-load-more').style.display = data.has_more ? 'block' : 'none';
}

function loadMore() {
  runSearch(_currentOffset + 10);
}

function buildTickerCard(r) {
  const upside = r.upside_pct != null ? `${r.upside_pct > 0 ? '+' : ''}${r.upside_pct}%` : '—';
  const change = r.change_pct != null ? `${r.change_pct > 0 ? '+' : ''}${r.change_pct.toFixed(2)}%` : '';
  const recColor = {'Strong Buy':'#16a34a','Buy':'#4ade80','Hold':'#ca8a04','Sell':'#f87171','Strong Sell':'#dc2626'}[r.recommendation] || '#888';
  const div = document.createElement('div');
  div.className = 'card';
  div.style.cssText = 'margin-bottom:8px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:12px';
  div.onclick = () => openAnalysis(r.ticker);
  div.innerHTML = `
    <div>
      <strong>${r.ticker}</strong>
      <span style="opacity:.6;font-size:.85rem;margin-left:6px">${r.name || ''}</span>
      ${r.sector ? `<span style="opacity:.4;font-size:.75rem;margin-left:6px">${r.sector}</span>` : ''}
    </div>
    <div style="display:flex;gap:16px;align-items:center;flex-shrink:0">
      <span style="font-size:.85rem;opacity:.7">${change}</span>
      ${r.recommendation ? `<span style="background:${recColor};color:#fff;padding:2px 8px;border-radius:999px;font-size:.8rem;font-weight:600">${r.recommendation}</span>` : ''}
      <div style="text-align:right;font-size:.85rem">
        ${r.target_mean ? `<div>Target: $${r.target_mean}</div>` : ''}
        <div style="opacity:.6">Upside: ${upside} · ${r.num_analysts || 0} analysts</div>
      </div>
    </div>`;
  return div;
}

function openAnalysis(ticker) {
  switchTab('analyze');
  document.getElementById('analyze-ticker').value = ticker;
  runAnalysis();
}

// ── Analyze Stock ──
async function runAnalysis() {
  const ticker = document.getElementById('analyze-ticker').value.trim().toUpperCase();
  if (!ticker) return;
  const container = document.getElementById('analyze-results');
  container.innerHTML = '<p style="opacity:.5">Loading...</p>';
  const res = await fetch('/api/research/analyze?ticker=' + encodeURIComponent(ticker));
  const data = await res.json();
  if (data.error) {
    container.innerHTML = `<p style="color:var(--red)">${data.error}</p>`;
    return;
  }
  container.innerHTML = buildAnalysis(ticker, data);
  // Fetch AI summary async
  fetchAiSummary(ticker);
}

function buildAnalysis(ticker, d) {
  const q = d.quote || {};
  const a = d.analyst || {};
  const t = d.technicals || {};
  const f = d.fundamentals || {};
  const news = d.news || [];
  const recColor = {'Strong Buy':'#16a34a','Buy':'#4ade80','Hold':'#ca8a04','Sell':'#f87171','Strong Sell':'#dc2626'}[a.recommendation] || '#888';
  const changeClass = (q.change_pct || 0) >= 0 ? 'value-positive' : 'value-negative';

  return `
    <div class="card" style="margin-bottom:12px">
      <h3>${ticker} ${d.profile ? '— ' + d.profile.name : ''}</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:8px">
        <div><div class="form-label">Price</div><strong>$${q.price}</strong> <span class="${changeClass}">${q.change_pct != null ? (q.change_pct > 0 ? '+' : '') + q.change_pct.toFixed(2) + '%' : ''}</span></div>
        <div><div class="form-label">Day Range</div>${q.day_low} – ${q.day_high}</div>
      </div>
    </div>
    ${a.recommendation ? `
    <div class="card" style="margin-bottom:12px">
      <h3>Analyst Consensus</h3>
      <div style="display:flex;align-items:center;gap:12px;margin-top:8px;flex-wrap:wrap">
        <span style="background:${recColor};color:#fff;padding:4px 14px;border-radius:999px;font-weight:700">${a.recommendation}</span>
        ${a.target_mean ? `<span>Target: <strong>$${a.target_mean}</strong></span>` : ''}
        ${a.upside_pct != null ? `<span class="${a.upside_pct >= 0 ? 'value-positive' : 'value-negative'}">Upside: ${a.upside_pct > 0 ? '+' : ''}${a.upside_pct}%</span>` : ''}
        <span style="opacity:.6">${a.num_analysts} analysts</span>
      </div>
    </div>` : ''}
    ${Object.values(t).some(v => v != null) ? `
    <div class="card" style="margin-bottom:12px">
      <h3>Technical Indicators</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:8px">
        ${t.rsi != null ? `<div><div class="form-label">RSI (14)</div><strong>${t.rsi}</strong></div>` : ''}
        ${t.macd != null ? `<div><div class="form-label">MACD</div><strong>${t.macd}</strong></div>` : ''}
        ${t.ma50 != null ? `<div><div class="form-label">MA 50d</div><strong>$${t.ma50}</strong></div>` : ''}
        ${t.ma200 != null ? `<div><div class="form-label">MA 200d</div><strong>$${t.ma200}</strong></div>` : ''}
      </div>
    </div>` : ''}
    ${Object.values(f).some(v => v != null) ? `
    <div class="card" style="margin-bottom:12px">
      <h3>Fundamentals</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:8px">
        ${f.pe_ratio != null ? `<div><div class="form-label">P/E Ratio</div><strong>${f.pe_ratio}</strong></div>` : ''}
        ${f.eps != null ? `<div><div class="form-label">EPS</div><strong>$${f.eps}</strong></div>` : ''}
        ${f.revenue_growth_pct != null ? `<div><div class="form-label">Revenue Growth</div><strong>${f.revenue_growth_pct > 0 ? '+' : ''}${f.revenue_growth_pct}%</strong></div>` : ''}
        ${f.profit_margin_pct != null ? `<div><div class="form-label">Profit Margin</div><strong>${f.profit_margin_pct}%</strong></div>` : ''}
      </div>
    </div>` : ''}
    ${news.length ? `
    <div class="card" style="margin-bottom:12px">
      <h3>Recent News</h3>
      <ul style="margin:8px 0 0;padding-left:0;list-style:none">
        ${news.map(n => `
        <li style="padding:6px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;gap:8px">
          <a href="${n.url}" target="_blank" style="color:inherit">${n.headline}</a>
          <span style="flex-shrink:0;font-size:.75rem;padding:2px 8px;border-radius:999px;background:${n.sentiment==='bullish'?'#dcfce7':n.sentiment==='bearish'?'#fee2e2':'#f3f4f6'};color:${n.sentiment==='bullish'?'#16a34a':n.sentiment==='bearish'?'#dc2626':'#6b7280'}">${n.sentiment}</span>
        </li>`).join('')}
      </ul>
    </div>` : ''}
    <div class="card" id="ai-summary-card">
      <h3>AI Summary</h3>
      <p id="ai-summary-text" style="opacity:.5;margin-top:8px">Generating summary...</p>
    </div>`;
}

async function fetchAiSummary(ticker) {
  const res = await fetch('/api/research/ai-summary?ticker=' + encodeURIComponent(ticker));
  const data = await res.json();
  const el = document.getElementById('ai-summary-text');
  if (el) el.textContent = data.summary || 'Could not generate summary.';
  if (el) el.style.opacity = '1';
}

// Init
loadPresets();
</script>
{% endblock %}
```

- [ ] **Step 2: Start the app and open the Research tab**

```
python app.py
```

Navigate to `http://localhost:5000` → log in → click **Research** tab. Verify both sub-tabs appear and the filter panel renders correctly.

- [ ] **Step 3: Test the full flow manually**
  - Enter `AAPL` in Analyze Stock → click Analyze → verify all sections load
  - Go to Find Tickers → select US, Technology, Stock → click Search → verify results appear
  - Click a result → verify it opens the Analyze tab for that ticker
  - Save a preset → verify the chip appears → click it → verify filters apply

- [ ] **Step 4: Commit**

```bash
git add templates/research.html
git commit -m "feat: add Research tab UI (find tickers + analyze stock)"
```

---

## Task 12: Run full test suite and final verification

- [ ] **Step 1: Run all tests**

```
pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 2: Verify `FINNHUB_API_KEY` is loaded**

```python
python -c "import os; print('Key loaded:', bool(os.environ.get('FINNHUB_API_KEY')))"
```
Expected: `Key loaded: True`

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat: Research tab complete — find tickers, analyze stock, AI summary"
```
