# research.py
import json
import os
import uuid as _uuid
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
    """Fetch current price data for a US ticker.
    Tries Finnhub first; falls back to yfinance if Finnhub fails or key is missing."""
    data = _finnhub_get("/quote", {"symbol": ticker})
    if data and data.get("c") not in (None, 0):
        return {
            "price": data.get("c"),
            "prev_close": data.get("pc"),
            "day_high": data.get("h"),
            "day_low": data.get("l"),
            "change_pct": data.get("dp"),
            "week52_high": data.get("52WeekHigh"),
            "week52_low": data.get("52WeekLow"),
        }
    # Fallback: yfinance (no API key required)
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        price = info.last_price
        prev = info.previous_close
        if not price:
            return None
        change_pct = round((price - prev) / prev * 100, 2) if prev else None
        return {
            "price": round(price, 2),
            "prev_close": round(prev, 2) if prev else None,
            "day_high": round(info.day_high, 2) if info.day_high else None,
            "day_low": round(info.day_low, 2) if info.day_low else None,
            "change_pct": change_pct,
            "week52_high": round(info.year_high, 2) if info.year_high else None,
            "week52_low": round(info.year_low, 2) if info.year_low else None,
        }
    except Exception as e:
        print(f"[WARN] yfinance quote fallback failed for {ticker}: {e}")
        return None


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
    """Fetch analyst recommendation and price target using Yahoo Finance (no API key needed)."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        rec_df = t.recommendations
        targets = t.analyst_price_targets or {}
    except Exception as e:
        print(f"[WARN] Yahoo analyst data failed for {ticker}: {e}")
        return None

    if rec_df is None or rec_df.empty:
        return None

    row = rec_df.iloc[0]
    counts = {
        "strongBuy":  int(row.get("strongBuy", 0)),
        "buy":        int(row.get("buy", 0)),
        "hold":       int(row.get("hold", 0)),
        "sell":       int(row.get("sell", 0)),
        "strongSell": int(row.get("strongSell", 0)),
    }
    total = sum(counts.values())
    if total == 0:
        return None

    score = (
        counts["strongBuy"] * 2 +
        counts["buy"] * 1 +
        counts["hold"] * 0 +
        counts["sell"] * -1 +
        counts["strongSell"] * -2
    ) / total

    if score >= 0.75:
        rec_key = "strongBuy"
    elif score >= 0.25:
        rec_key = "buy"
    elif score >= -0.25:
        rec_key = "hold"
    elif score >= -0.75:
        rec_key = "sell"
    else:
        rec_key = "strongSell"

    target_mean = targets.get("mean")
    upside_pct = None
    if target_mean and current_price:
        upside_pct = round((target_mean - current_price) / current_price * 100, 1)

    return {
        "recommendation": _REC_LABELS[rec_key],
        "color": _REC_COLORS[_REC_LABELS[rec_key]],
        "target_mean": round(target_mean, 2) if target_mean else None,
        "target_high": targets.get("high"),
        "target_low": targets.get("low"),
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


_BULLISH_WORDS = {"surge", "soar", "beat", "record", "profit", "gain", "rally", "upgrade",
                  "crush", "crushes", "strong", "growth", "bullish", "positive", "rise", "raises"}
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
    import pandas as pd
    return round(float(val), 2) if not pd.isna(val) else None


def _calc_macd(prices: "pd.Series") -> tuple[float | None, float | None]:
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    m = macd_line.iloc[-1]
    s = signal.iloc[-1]
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

    change_pct = quote.get("change_pct") or 0
    prompt = f"""You are a financial analyst. Write a 2-3 sentence summary for {ticker} based on the data below.
Cover: what the company does (briefly), the key opportunity or risk right now, and the overall outlook.
Be factual and concise. Do not use bullet points.

Price: ${quote.get('price')} ({change_pct:+.1f}% today)
Analyst consensus: {analyst.get('recommendation')} | Target: ${analyst.get('target_mean')} | Upside: {analyst.get('upside_pct')}% | Analysts: {analyst.get('num_analysts')}
P/E: {fundamentals.get('pe_ratio')} | EPS: {fundamentals.get('eps')} | Revenue growth: {fundamentals.get('revenue_growth_pct')}% | Profit margin: {fundamentals.get('profit_margin_pct')}%
Recent news:
{news_lines}"""

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "ERROR: ANTHROPIC_API_KEY is not set in environment variables."
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
        return f"ERROR: {e}"


_REC_RANK = {
    "Strong Buy": 5, "Buy": 4, "Hold": 3, "Sell": 2, "Strong Sell": 1, None: 0
}

_MARKET_CAP_RANGES = {
    "small":  (0,          2_000_000_000),
    "mid":    (2_000_000_000, 10_000_000_000),
    "large":  (10_000_000_000, float("inf")),
}

# Yahoo Finance sector/industry filter map
# Value is (field, yahoo_value) — field is either "sector" or "industry"
_YF_SECTOR_MAP: dict[str, tuple[str, str]] = {
    # Broad sectors
    "Technology":      ("sector",   "Technology"),
    "Healthcare":      ("sector",   "Healthcare"),
    "Finance":         ("sector",   "Financial Services"),
    "Energy":          ("sector",   "Energy"),
    "Consumer":        ("sector",   "Consumer Cyclical"),
    "Industrials":     ("sector",   "Industrials"),
    "Real Estate":     ("sector",   "Real Estate"),
    "Utilities":       ("sector",   "Utilities"),
    # Technology sub-categories
    "Semiconductors":  ("industry", "Semiconductors"),
    "Software":        ("industry", "Software—Application"),
    "Cloud & SaaS":    ("industry", "Software—Infrastructure"),
    "Cybersecurity":   ("industry", "Software—Infrastructure"),
    # Other industries
    "Aerospace":       ("industry", "Aerospace & Defense"),
}


def _screen_yahoo(security_type: str | None, sector: str | None,
                  market_cap: str | None, limit: int) -> list[dict]:
    """
    Run Yahoo Finance screener and return raw quote dicts (already contain price/name/sector).
    Falls back to a broad screen on failure.
    """
    from yfinance import EquityQuery, screen

    clauses: list = []
    clauses.append(EquityQuery("is-in", ["exchange", "NMS", "NYQ"]))

    if sector and sector in _YF_SECTOR_MAP:
        field, value = _YF_SECTOR_MAP[sector]
        clauses.append(EquityQuery("eq", [field, value]))

    if market_cap and market_cap in _MARKET_CAP_RANGES:
        lo, hi = _MARKET_CAP_RANGES[market_cap]
        if lo > 0:
            clauses.append(EquityQuery("gt", ["intradaymarketcap", lo]))
        if hi < float("inf"):
            clauses.append(EquityQuery("lt", ["intradaymarketcap", hi]))

    query = EquityQuery("and", clauses) if len(clauses) > 1 else clauses[0]

    try:
        result = screen(query, sortField="percentchange", sortAsc=False, size=limit)
        return [q for q in result.get("quotes", []) if q.get("symbol") and "." not in q["symbol"]]
    except Exception as e:
        print(f"[WARN] Yahoo Finance screener failed: {e}")
        try:
            fallback = EquityQuery("is-in", ["exchange", "NMS", "NYQ"])
            result = screen(fallback, sortField="percentchange", sortAsc=False, size=limit)
            return [q for q in result.get("quotes", []) if q.get("symbol") and "." not in q["symbol"]]
        except Exception:
            return []


def _get_israel_candidates(security_type: str | None, sector: str | None,
                           tase_cache: list[dict]) -> list[dict]:
    """Return TASE securities matching filters. Each item has id, name, ticker, type."""
    results = []
    for item in tase_cache:
        if security_type == "stock" and item.get("type") != "security":
            continue
        if security_type in ("etf", "fund") and item.get("type") != "fund":
            continue
        results.append(item)
    return results[:60]


def find_tickers(market: str, security_type: str | None, sector: str | None,
                 momentum: str | None, market_cap: str | None, limit: int = 10,
                 tase_cache: list | None = None) -> list[dict]:
    """
    Search for tickers matching the given filters.
    market: 'us' or 'israel'
    security_type: 'stock', 'etf', 'fund', or None
    sector: sector string or None (US only)
    momentum: '1d', '1w', '1m', or None
    market_cap: 'small', 'mid', 'large', or None (US only)
    tase_cache: pass loaded TASE cache for israel market
    Returns list of dicts with ticker, name, recommendation, target_mean, upside_pct, num_analysts, price, change_pct.
    """
    if market == "israel":
        return _find_tickers_israel(security_type, tase_cache or [], limit)

    # Yahoo screener returns price/name/sector — no extra API calls needed for basic data
    yf_quotes = _screen_yahoo(security_type, sector, market_cap, limit=limit * 3)
    results = []

    for yq in yf_quotes:
        if len(results) >= limit * 2:
            break

        ticker = yq["symbol"]
        price = yq.get("regularMarketPrice") or yq.get("ask") or 0
        change_pct = yq.get("regularMarketChangePercent")

        if not price:
            continue

        # Momentum filter: only keep tickers with positive today's change
        if momentum and (change_pct or 0) <= 0:
            continue

        # Analyst data — single Finnhub call (rec + target = 2 calls)
        analyst = get_analyst_data(ticker, price)

        results.append({
            "ticker": ticker,
            "name": yq.get("shortName") or yq.get("longName") or ticker,
            "sector": yq.get("sector") or sector,
            "recommendation": analyst.get("recommendation") if analyst else None,
            "color": analyst.get("color") if analyst else "gray",
            "target_mean": analyst.get("target_mean") if analyst else None,
            "upside_pct": analyst.get("upside_pct") if analyst else None,
            "num_analysts": analyst.get("num_analysts") if analyst else 0,
            "price": price,
            "change_pct": change_pct,
        })

    return results


def _find_tickers_israel(security_type: str | None, tase_cache: list[dict],
                         limit: int) -> list[dict]:
    """Find Israeli securities using the TASE cache + live prices."""
    import tase as tase_module
    candidates = _get_israel_candidates(security_type, None, tase_cache)
    results = []
    for item in candidates:
        if len(results) >= limit * 2:
            break
        try:
            price = tase_module.get_price(item["id"], item["type"])
        except Exception:
            continue
        if not price:
            continue
        results.append({
            "ticker": item.get("ticker") or item["id"],
            "name": item.get("name", ""),
            "sector": None,
            "recommendation": None,
            "color": "gray",
            "target_mean": None,
            "upside_pct": None,
            "num_analysts": 0,
            "price": price,
            "change_pct": None,
        })
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
    # "alpha" and unknown values: sort alphabetically
    return sorted(results, key=lambda r: r.get("ticker", ""))


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
