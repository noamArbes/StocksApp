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


def test_get_news_returns_sentiment_tagged_headlines():
    mock_news = [
        {"headline": "Apple crushes earnings expectations", "datetime": 1700000000, "url": "http://a.com"},
        {"headline": "Apple faces antitrust probe", "datetime": 1700000001, "url": "http://b.com"},
    ]
    with patch("research._finnhub_get") as mock_get:
        mock_get.return_value = mock_news
        result = research.get_news("AAPL", limit=5)
    assert len(result) == 2
    assert result[0]["headline"] == "Apple crushes earnings expectations"
    assert result[0]["sentiment"] == "bullish"
    assert result[1]["sentiment"] == "bearish"
    assert "url" in result[0]


def test_get_analyst_data_handles_list_response():
    mock_rec = [{"buy": 10, "hold": 5, "sell": 2, "strongBuy": 8, "strongSell": 1, "period": "2024-01-01"}]
    mock_target = {"targetMean": 180.0, "targetHigh": 200.0, "targetLow": 160.0}
    with patch("research._finnhub_get") as mock_get:
        mock_get.side_effect = [mock_rec, mock_target]
        result = research.get_analyst_data("AAPL", current_price=150.0)
    assert result is not None
    assert result["recommendation"] in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")


def test_get_technicals_returns_expected_keys():
    with patch("research._get_yfinance_history") as mock_hist:
        import pandas as pd
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
