import json
from unittest.mock import patch, MagicMock
import pytest


SAMPLE_CACHE = [
    {"id": "1175819", "name": "Eltra Corp", "ticker": "ELTR", "type": "security"},
    {"id": "5118393", "name": "Migdal Bonds Fund", "ticker": None, "type": "fund"},
    {"id": "1200001", "name": "Bank Hapoalim", "ticker": "POLI", "type": "security"},
]


def _fake_urlopen_cache(url_or_req, *args, **kwargs):
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps([
        {"Id": 1175819, "Name": "Eltra Corp", "Smb": "ELTR", "Type": 1},
        {"Id": 5118393, "Name": "Migdal Bonds Fund", "Smb": None, "Type": 4},
        {"Id": 99,      "Name": "Some Index",       "Smb": "IDX",  "Type": 2},
    ]).encode()
    return mock_resp


def test_load_securities_cache_filters_types():
    import tase
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_cache):
        cache = tase.load_securities_cache()
    assert len(cache) == 2
    ids = {item["id"] for item in cache}
    assert "1175819" in ids
    assert "5118393" in ids


def test_load_securities_cache_sets_correct_type_labels():
    import tase
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_cache):
        cache = tase.load_securities_cache()
    by_id = {item["id"]: item for item in cache}
    assert by_id["1175819"]["type"] == "security"
    assert by_id["5118393"]["type"] == "fund"
    assert by_id["5118393"]["ticker"] is None


def test_load_securities_cache_returns_empty_on_network_error():
    import tase
    with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
        cache = tase.load_securities_cache()
    assert cache == []


def test_search_matches_name():
    import tase
    results = tase.search("eltra", SAMPLE_CACHE)
    assert len(results) == 1
    assert results[0]["id"] == "1175819"


def test_search_matches_ticker():
    import tase
    results = tase.search("POLI", SAMPLE_CACHE)
    assert len(results) == 1
    assert results[0]["id"] == "1200001"


def test_search_case_insensitive():
    import tase
    results = tase.search("MIGDAL", SAMPLE_CACHE)
    assert len(results) == 1
    assert results[0]["id"] == "5118393"


def test_search_returns_max_10():
    import tase
    big_cache = [{"id": str(i), "name": f"Fund Alpha {i}", "ticker": None, "type": "fund"} for i in range(20)]
    results = tase.search("fund", big_cache)
    assert len(results) == 10


def test_search_empty_cache():
    import tase
    assert tase.search("anything", []) == []


def test_search_no_match():
    import tase
    assert tase.search("zzznomatch", SAMPLE_CACHE) == []


def _fake_urlopen_prices(url_or_req, *args, **kwargs):
    url = url_or_req.full_url if hasattr(url_or_req, "full_url") else str(url_or_req)
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    if "fund/details" in url:
        mock_resp.read.return_value = json.dumps({"UnitValuePrice": 126.49}).encode()
    else:
        mock_resp.read.return_value = json.dumps({"LastRate": 185.30}).encode()
    return mock_resp


def test_get_price_fund_returns_unit_value():
    import tase
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_prices):
        price = tase.get_price("5118393", "fund")
    assert price == 126.49


def test_get_price_security_returns_last_rate():
    import tase
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_prices):
        price = tase.get_price("1175819", "security")
    assert price == 185.30


def test_get_price_raises_value_error_when_price_is_none():
    import tase
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps({"UnitValuePrice": None}).encode()
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(ValueError, match="not available"):
            tase.get_price("5118393", "fund")


def test_get_price_raises_value_error_on_network_error():
    import tase
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
        with pytest.raises(ValueError):
            tase.get_price("1175819", "security")
