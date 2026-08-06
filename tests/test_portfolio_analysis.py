import json
import os
from unittest.mock import MagicMock

os.environ.setdefault("UI_PASSWORD", "testpass")
os.environ.setdefault("SECRET_KEY", "testsecret")

import portfolio_analysis


def _mock_client(response_text):
    client = MagicMock()
    content_block = MagicMock()
    content_block.text = response_text
    response = MagicMock()
    response.content = [content_block]
    client.messages.create.return_value = response
    return client


def test_compute_analysis_parses_valid_json_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = {
        "sector_by_region": {"us": {"Technology": 60.0, "Healthcare": 40.0}, "israel": {"Finance": 100.0}},
        "stock_exposure": [
            {"ticker": "AAPL", "name": "Apple", "pct": 12.0},
            {"ticker": "MSFT", "name": "Microsoft", "pct": 18.0},
        ],
    }
    monkeypatch.setattr(portfolio_analysis, "_get_claude_client",
                         lambda: _mock_client(json.dumps(payload)))

    result = portfolio_analysis.compute_analysis(
        [{"ticker": "QQQ", "name": "Invesco QQQ", "category": "etf", "region": "us", "value_ils": 10000}]
    )

    assert result["sector_by_region"]["us"]["Technology"] == 60.0
    assert result["sector_by_region"]["israel"]["Finance"] == 100.0
    assert result["stock_exposure"][0]["ticker"] == "MSFT"
    assert result["stock_exposure"][0]["pct"] == 18.0


def test_compute_analysis_truncates_to_top_8(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    payload = {
        "sector_by_region": {"us": {}, "israel": {}},
        "stock_exposure": [{"ticker": f"T{i}", "name": f"Ticker {i}", "pct": float(i)} for i in range(20)],
    }
    monkeypatch.setattr(portfolio_analysis, "_get_claude_client",
                         lambda: _mock_client(json.dumps(payload)))

    result = portfolio_analysis.compute_analysis(
        [{"ticker": "QQQ", "name": "Invesco QQQ", "category": "etf", "region": "us", "value_ils": 10000}]
    )
    assert len(result["stock_exposure"]) == 8
    assert result["stock_exposure"][0]["ticker"] == "T19"


def test_compute_analysis_raises_on_malformed_response(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(portfolio_analysis, "_get_claude_client",
                         lambda: _mock_client("not json at all"))
    try:
        portfolio_analysis.compute_analysis(
            [{"ticker": "QQQ", "name": "Invesco QQQ", "category": "etf", "region": "us", "value_ils": 10000}]
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_compute_analysis_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        portfolio_analysis.compute_analysis(
            [{"ticker": "QQQ", "name": "Invesco QQQ", "category": "etf", "region": "us", "value_ils": 10000}]
        )
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_compute_holding_values_excludes_mmf(monkeypatch):
    monkeypatch.setattr(portfolio_analysis.checker, "get_usd_to_ils", lambda: 3.7)
    monkeypatch.setattr(portfolio_analysis.checker, "get_price_with_change", lambda t: (100.0, 99.0))

    holdings = [
        {"ticker": "AAPL", "name": "Apple", "category": "stocks", "region": "us",
         "shares": 10, "currency": "USD", "source": "yfinance"},
        {"ticker": "CASH", "name": "Money Market", "category": "mmf", "region": "us",
         "shares": 100, "currency": "USD", "source": "yfinance"},
    ]
    result = portfolio_analysis._compute_holding_values(holdings)
    tickers = {h["ticker"] for h in result}
    assert tickers == {"AAPL"}


def test_run_persists_result_and_computed_at(tmp_path, monkeypatch):
    savings_file = tmp_path / "savings.json"
    savings_file.write_text(json.dumps([
        {"id": "a", "ticker": "AAPL", "name": "Apple", "category": "stocks", "region": "us",
         "shares": 10, "currency": "USD", "source": "yfinance", "cost_basis": 1000,
         "tase_id": "", "tase_type": "", "last_updated": "2026-05-06T10:00:00+00:00"},
    ]))
    analysis_file = tmp_path / "ai_portfolio_analysis.json"

    monkeypatch.setattr(portfolio_analysis, "_compute_holding_values",
                         lambda holdings: [{"ticker": "AAPL", "name": "Apple", "category": "stocks",
                                             "region": "us", "value_ils": 3700.0}])
    monkeypatch.setattr(portfolio_analysis, "compute_analysis",
                         lambda summary: {"sector_by_region": {"us": {"Technology": 100.0}, "israel": {}},
                                           "stock_exposure": [{"ticker": "AAPL", "name": "Apple", "pct": 100.0}]})

    result = portfolio_analysis.run(savings_path=str(savings_file), analysis_path=str(analysis_file))

    assert result["sector_by_region"]["us"]["Technology"] == 100.0
    assert "computed_at" in result
    saved = json.loads(analysis_file.read_text())
    assert saved["stock_exposure"][0]["ticker"] == "AAPL"
    assert "computed_at" in saved


def test_run_leaves_cache_untouched_on_claude_failure(tmp_path, monkeypatch):
    savings_file = tmp_path / "savings.json"
    savings_file.write_text(json.dumps([]))
    analysis_file = tmp_path / "ai_portfolio_analysis.json"
    existing = {"sector_by_region": {"us": {"Technology": 50.0}, "israel": {}},
                "stock_exposure": [], "computed_at": "2026-05-06T10:00:00+00:00"}
    analysis_file.write_text(json.dumps(existing))

    def _raise(summary):
        raise RuntimeError("Claude unavailable")
    monkeypatch.setattr(portfolio_analysis, "_compute_holding_values", lambda holdings: [])
    monkeypatch.setattr(portfolio_analysis, "compute_analysis", _raise)

    result = portfolio_analysis.run(savings_path=str(savings_file), analysis_path=str(analysis_file))

    assert result is None
    saved = json.loads(analysis_file.read_text())
    assert saved == existing
