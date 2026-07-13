import json
import os
import re
from datetime import datetime, timezone

import anthropic

import checker
import tase

_claude_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _claude_client


_SYSTEM_PROMPT = """You are a portfolio analyst. You will be given a list of a user's stock and ETF \
holdings (ticker, name, category, region, and current value in ILS), plus the total combined value.

Return ONLY valid JSON (no markdown fences, no explanation) with exactly this shape:
{
  "sector_by_region": {
    "us": {"<sector name>": <pct of that region's stock+ETF value, 0-100>, ...},
    "israel": {"<sector name>": <pct>, ...}
  },
  "stock_exposure": [
    {"ticker": "<ticker>", "name": "<company name>", "pct": <pct of TOTAL portfolio value, 0-100>},
    ...
  ]
}

Rules:
- "sector_by_region" only covers holdings tagged region "us" or region "israel". Percentages within \
each region should sum to approximately 100.
- For ETFs, estimate their sector composition and top constituent stocks from your own knowledge of \
that fund (do not ask for external data — use your best estimate of the fund's typical holdings).
- "stock_exposure" is portfolio-wide (all regions). For each ETF, look through to its estimated top \
constituent stocks and compute each stock's dollar contribution (ETF value * estimated weight in \
the ETF), then sum that with any direct share holdings of the same underlying company. Report the \
combined total as a percentage of the TOTAL portfolio value given to you.
- Return at most the top 15 tickers in "stock_exposure", sorted descending by pct.
- If there are no holdings for a region, omit or leave that region's object empty."""


def _build_prompt(holdings_summary: list[dict]) -> str:
    total = sum(h["value_ils"] for h in holdings_summary)
    lines = [f"Total combined value: ₪{total:,.0f}", "", "Holdings:"]
    for h in holdings_summary:
        lines.append(
            f"- {h['ticker']} | {h['name']} | {h['category']} | "
            f"region={h['region'] or 'unclassified'} | ₪{h['value_ils']:,.0f}"
        )
    return "\n".join(lines)


def compute_analysis(holdings_summary: list[dict]) -> dict:
    """Calls Claude to analyze sector/exposure breakdown. Raises on failure."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    if not holdings_summary:
        return {"sector_by_region": {"us": {}, "israel": {}}, "stock_exposure": []}

    prompt = _build_prompt(holdings_summary)
    client = _get_claude_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Claude response did not contain JSON: {text[:200]}")
    result = json.loads(match.group())

    sector_by_region = result.get("sector_by_region") or {}
    stock_exposure = result.get("stock_exposure") or []
    stock_exposure = sorted(
        ({"ticker": s.get("ticker", ""), "name": s.get("name", ""),
          "pct": float(s.get("pct") or 0)} for s in stock_exposure),
        key=lambda s: s["pct"], reverse=True,
    )[:15]

    return {
        "sector_by_region": {
            "us": sector_by_region.get("us") or {},
            "israel": sector_by_region.get("israel") or {},
        },
        "stock_exposure": stock_exposure,
    }


def _compute_holding_values(holdings: list) -> list[dict]:
    """Resolves each non-MMF holding's current ILS value. Standalone (no Flask app
    context needed) so it can run from the scheduler."""
    usd_to_ils = checker.get_usd_to_ils()
    result = []
    for h in holdings:
        if h.get("category") == "mmf":
            continue
        ticker = h.get("ticker")
        if not ticker:
            continue
        try:
            if h.get("source") == "tase":
                price = tase.get_price(h["tase_id"], h["tase_type"])
                rate = 1.0
            else:
                price, _ = checker.get_price_with_change(ticker)
                rate = usd_to_ils if h.get("currency") == "USD" else 1.0
            if price is None:
                continue
            value_ils = price * (h.get("shares") or 0) * rate
        except Exception:
            continue
        if value_ils <= 0:
            continue
        result.append({
            "ticker": ticker,
            "name": h.get("name") or ticker,
            "category": h.get("category"),
            "region": h.get("region"),
            "value_ils": value_ils,
        })
    return result


def run(savings_path: str | None = None, analysis_path: str | None = None) -> dict | None:
    """Entry point for the scheduler and the manual refresh route.
    On failure, logs a warning and leaves any existing cache file untouched."""
    savings_path = savings_path or checker.get_savings_path()
    analysis_path = analysis_path or checker.get_portfolio_analysis_path()

    try:
        holdings = checker.load_savings(savings_path)
    except Exception as e:
        print(f"[PortfolioAnalysis] Failed to load savings: {e}")
        return None

    holdings_summary = _compute_holding_values(holdings)

    try:
        result = compute_analysis(holdings_summary)
    except Exception as e:
        print(f"[PortfolioAnalysis] Claude analysis failed: {e}")
        return None

    result["computed_at"] = datetime.now(timezone.utc).isoformat()
    checker.save_portfolio_analysis(result, analysis_path)
    print("[PortfolioAnalysis] Analysis refreshed and cached")
    return result
