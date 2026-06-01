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

    if isinstance(rec_data, list):
        rec_data = rec_data[0] if rec_data else {}

    counts = {k: rec_data.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")}
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
    return round(float(val), 2) if not (val != val) else None


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
