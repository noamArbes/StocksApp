# Israeli Securities Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add alarms for Israeli TASE stocks, ETFs, and mutual funds via a market toggle in the alarm form, plus remove the copy-alarm feature and add a manual reference price field.

**Architecture:** A new `tase.py` module handles all TASE API interaction (cache load, search, price fetch). `checker.py` and `app.py` route price fetching based on a new `source` field on each alarm. Alarm form gets a market toggle that swaps the ticker autocomplete for TASE name search and populates hidden `tase_id`/`tase_type` fields.

**Tech Stack:** Python 3.11, Flask, yfinance (existing), `api.tase.co.il` + `mayaapi.tase.co.il` (new, no auth required), Jinja2 templates, vanilla JS

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tase.py` | **Create** | TASE API: cache load, search, price fetch |
| `tests/test_tase.py` | **Create** | Unit tests for tase.py |
| `checker.py` | **Modify** | Add `currency` param to format functions; route price fetch by `source` in `run()` |
| `tests/test_checker.py` | **Modify** | Tests for currency param and TASE routing |
| `app.py` | **Modify** | Startup cache, `/api/tase-search` endpoint, `_alarm_from_form` updates, dashboard routing, remove duplicate route |
| `tests/test_app.py` | **Modify** | Tests for new endpoint, TASE alarm creation, removed duplicate route |
| `templates/alarm_form.html` | **Modify** | Market toggle, TASE autocomplete, hidden fields, reference price field, currency labels |
| `templates/dashboard.html` | **Modify** | Currency symbol per alarm, remove duplicate button |

---

## Task 1: Create `tase.py` — securities cache and search

**Files:**
- Create: `tase.py`
- Create: `tests/test_tase.py`

- [ ] **Step 1: Write failing tests for `load_securities_cache` and `search`**

Create `tests/test_tase.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tase.py -v
```
Expected: `ModuleNotFoundError: No module named 'tase'`

- [ ] **Step 3: Create `tase.py` with `load_securities_cache` and `search`**

```python
import json
import urllib.request
import urllib.error

_BASE_HEADERS = {
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; FSL 7.0.6.01001)",
    "Referer": "https://www.tase.co.il/",
    "Cache-Control": "no-cache",
}

_MAYA_HEADERS = {
    **_BASE_HEADERS,
    "X-Maya-With": "allow",
    "Accept-Language": "en-US",
}


def load_securities_cache() -> list[dict]:
    """Fetch all TASE securities. Filters to stocks/ETFs (type 1) and mutual funds (type 4).
    Returns [] on any failure — app starts normally without Israeli search."""
    url = "https://api.tase.co.il/api/content/searchentities?lang=1"
    req = urllib.request.Request(url, headers=_BASE_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[WARN] TASE securities cache load failed: {e}")
        return []

    results = []
    for item in data:
        t = item.get("Type")
        if t not in (1, 4):
            continue
        results.append({
            "id": str(item["Id"]),
            "name": item.get("Name") or "",
            "ticker": item.get("Smb"),
            "type": "fund" if t == 4 else "security",
        })
    return results


def search(query: str, cache: list[dict]) -> list[dict]:
    """Case-insensitive substring search on name and ticker. Returns top 10 matches."""
    q = query.lower()
    results = []
    for item in cache:
        name_match = q in item["name"].lower()
        ticker_match = item["ticker"] is not None and q in item["ticker"].lower()
        if name_match or ticker_match:
            results.append(item)
            if len(results) == 10:
                break
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_tase.py -v
```
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tase.py tests/test_tase.py
git commit -m "feat: add tase.py with securities cache and search"
```

---

## Task 2: Add `get_price` to `tase.py`

**Files:**
- Modify: `tase.py`
- Modify: `tests/test_tase.py`

- [ ] **Step 1: Add failing tests for `get_price`**

Append to `tests/test_tase.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tase.py::test_get_price_fund_returns_unit_value -v
```
Expected: FAIL with `AttributeError: module 'tase' has no attribute 'get_price'`

- [ ] **Step 3: Add `get_price` to `tase.py`**

Append to `tase.py` (after the `search` function):

```python
def get_price(tase_id: str, tase_type: str) -> float:
    """Fetch current price from TASE API.
    Raises ValueError if price is unavailable or request fails."""
    if tase_type == "fund":
        url = f"https://mayaapi.tase.co.il/api/fund/details?fundId={tase_id}"
        req = urllib.request.Request(url, headers=_MAYA_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ValueError(f"Could not fetch fund price for {tase_id}: {e}") from e
        price = data.get("UnitValuePrice")
    else:
        url = f"https://api.tase.co.il/api/company/securitydata?securityId={tase_id}&lang=1"
        req = urllib.request.Request(url, headers=_BASE_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ValueError(f"Could not fetch security price for {tase_id}: {e}") from e
        price = data.get("LastRate")

    if price is None:
        raise ValueError(f"Price not available for TASE id {tase_id}")
    return float(price)
```

- [ ] **Step 4: Run all tase tests to verify they pass**

```
pytest tests/test_tase.py -v
```
Expected: all 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tase.py tests/test_tase.py
git commit -m "feat: add tase.get_price for stocks, ETFs, and mutual funds"
```

---

## Task 3: Update `checker.py` — currency parameter + TASE routing

**Files:**
- Modify: `checker.py`
- Modify: `tests/test_checker.py`

- [ ] **Step 1: Add failing tests for currency parameter**

Append to `tests/test_checker.py`:

```python
from checker import format_subject, format_body, format_subject_pct, format_body_pct


def test_format_subject_default_currency():
    result = format_subject("AAPL", 150.00, "upper", 149.00)
    assert "$150.00" in result
    assert "$149.00" in result


def test_format_subject_shekel_currency():
    result = format_subject("ELTR", 185.30, "upper", 180.00, currency="₪")
    assert "₪185.30" in result
    assert "₪180.00" in result
    assert "$" not in result


def test_format_body_default_currency():
    result = format_body("AAPL", 150.00, "upper", 149.00)
    assert "$150.00" in result
    assert "$149.00" in result


def test_format_body_shekel_currency():
    result = format_body("ELTR", 185.30, "upper", 180.00, currency="₪")
    assert "₪185.30" in result
    assert "₪180.00" in result
    assert "$" not in result


def test_format_body_pct_default_currency():
    result = format_body_pct("AAPL", 155.0, "upper_pct", 5.0, 150.0, 3.33)
    assert "$155.00" in result
    assert "$150.00" in result


def test_format_body_pct_shekel_currency():
    result = format_body_pct("ELTR", 190.0, "upper_pct", 5.0, 180.0, 5.56, currency="₪")
    assert "₪190.00" in result
    assert "₪180.00" in result
    assert "$" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_checker.py::test_format_subject_shekel_currency -v
```
Expected: FAIL — `TypeError: format_subject() got an unexpected keyword argument 'currency'`

- [ ] **Step 3: Add `currency` parameter to all four format functions in `checker.py`**

Replace the four format functions (lines 66–100) with:

```python
def format_subject(ticker: str, price: float, limit_type: str, limit_value: float, currency: str = "$") -> str:
    return f"Stock Alert: {ticker} hit {currency}{price:.2f} ({limit_type} limit: {currency}{limit_value:.2f})"


def format_body(ticker: str, price: float, limit_type: str, limit_value: float, tz_name: str | None = None, currency: str = "$") -> str:
    now = _local_time_str(tz_name)
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: {currency}{price:.2f}\n"
        f"Limit Triggered: {limit_type} limit ({currency}{limit_value:.2f})\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )


def format_subject_pct(ticker: str, price: float, direction: str, pct_threshold: float, actual_pct: float, currency: str = "$") -> str:
    sign = "+" if actual_pct >= 0 else ""
    return f"Stock Alert: {ticker} moved {sign}{actual_pct:.1f}% (threshold: {pct_threshold:.1f}%)"


def format_body_pct(ticker: str, price: float, direction: str, pct_threshold: float, base_price: float, actual_pct: float, tz_name: str | None = None, currency: str = "$") -> str:
    now = _local_time_str(tz_name)
    sign = "+" if actual_pct >= 0 else ""
    direction_label = "risen" if direction == "upper_pct" else "fallen"
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: {currency}{price:.2f}\n"
        f"Base Price: {currency}{base_price:.2f}\n"
        f"Change: {sign}{actual_pct:.2f}% ({direction_label})\n"
        f"Threshold: {pct_threshold:.1f}%\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )
```

- [ ] **Step 4: Update `run()` in `checker.py` to route price fetch and pass `currency` to format functions**

At the top of `checker.py`, add the import after the existing imports:

```python
import tase
```

In the `run()` function, find the line `ticker = alarm["ticker"]` (around line 190). After it, replace the price fetch block:

Find this code (lines ~195–200):
```python
        try:
            price = get_price(ticker)
            print(f"[FETCH] {ticker}: ${price:.2f}")
        except Exception as e:
            print(f"[ERROR] Could not fetch price for {ticker}: {e}")
            continue
```

Replace with:
```python
        currency = "₪" if alarm.get("source") == "tase" else "$"
        try:
            if alarm.get("source") == "tase":
                price = tase.get_price(alarm["tase_id"], alarm["tase_type"])
            else:
                price = get_price(ticker)
            print(f"[FETCH] {ticker}: {currency}{price:.2f}")
        except Exception as e:
            print(f"[ERROR] Could not fetch price for {ticker}: {e}")
            continue
```

Then find the two `format_subject` / `format_body` call sites inside `run()` and add `currency=currency` to each:

Find (approximately line 253):
```python
                    subject = format_subject(ticker, price, limit_type, limit_value)
                    body = format_body(ticker, price, limit_type, limit_value, tz_name=tz_name)
```
Replace with:
```python
                    subject = format_subject(ticker, price, limit_type, limit_value, currency=currency)
                    body = format_body(ticker, price, limit_type, limit_value, tz_name=tz_name, currency=currency)
```

Find (approximately line 217):
```python
                    subject = format_subject_pct(ticker, price, direction, pct_threshold, actual_pct)
                    body = format_body_pct(ticker, price, direction, pct_threshold, alarm["base_price"], actual_pct, tz_name=tz_name)
```
Replace with:
```python
                    subject = format_subject_pct(ticker, price, direction, pct_threshold, actual_pct, currency=currency)
                    body = format_body_pct(ticker, price, direction, pct_threshold, alarm["base_price"], actual_pct, tz_name=tz_name, currency=currency)
```

- [ ] **Step 5: Run all checker tests**

```
pytest tests/test_checker.py -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: currency param in email format functions, TASE price routing in run()"
```

---

## Task 4: Update `app.py` — startup cache, `/api/tase-search`, dashboard routing

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_app.py`:

```python
from unittest.mock import patch


def test_tase_search_returns_results(client):
    login(client)
    sample_cache = [
        {"id": "1175819", "name": "Eltra Corp", "ticker": "ELTR", "type": "security"},
        {"id": "5118393", "name": "Migdal Bonds Fund", "ticker": None, "type": "fund"},
    ]
    with patch.object(app_module, "_tase_cache", sample_cache):
        resp = client.get("/api/tase-search?q=eltra")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) == 1
    assert data[0]["id"] == "1175819"


def test_tase_search_requires_login(client):
    resp = client.get("/api/tase-search?q=eltra")
    assert resp.status_code in (302, 401)


def test_tase_search_short_query_returns_empty(client):
    login(client)
    resp = client.get("/api/tase-search?q=e")
    assert resp.status_code == 200
    assert json.loads(resp.data) == []


def test_duplicate_route_removed(client):
    login(client)
    resp = client.post("/alarm/nonexistent/duplicate")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_app.py::test_tase_search_returns_results tests/test_app.py::test_duplicate_route_removed -v
```
Expected: `test_tase_search_returns_results` fails with 404, `test_duplicate_route_removed` fails with 302 (route still exists)

- [ ] **Step 3: Add `import tase` and `_tase_cache` to `app.py`**

After the existing imports block (after `import checker` and `import cities_data`), add:

```python
import tase
```

After the `_ALARMS_PATH = checker.get_alarms_path()` line, add:

```python
_tase_cache = tase.load_securities_cache()
```

- [ ] **Step 4: Add `/api/tase-search` endpoint to `app.py`**

After the `/timezone-to-city` route (around line 350), add:

```python
@app.route("/api/tase-search")
@login_required
def tase_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    return jsonify(tase.search(q, _tase_cache))
```

- [ ] **Step 5: Update dashboard route in `app.py` to route price fetch by source**

In the `/dashboard` route, find the price-fetching loop (around line 103):

```python
    for alarm in alarms:
        ticker = alarm.get("ticker")
        if ticker and ticker not in prices:
            try:
                prices[ticker] = checker.get_price(ticker)
            except Exception:
                prices[ticker] = None
```

Replace with:

```python
    for alarm in alarms:
        ticker = alarm.get("ticker")
        if not ticker or ticker in prices:
            continue
        try:
            if alarm.get("source") == "tase":
                prices[ticker] = tase.get_price(alarm["tase_id"], alarm["tase_type"])
            else:
                prices[ticker] = checker.get_price(ticker)
        except Exception:
            prices[ticker] = None
```

- [ ] **Step 6: Add currency to the distances string in the dashboard route**

In the `/dashboard` route, find the distances loop. Locate where `curr` per alarm can be set. The distances block looks like (around line 141–151):

```python
        else:
            t, _, _ = checker.condition_met(alarm, price)
            triggered[alarm_id] = t
            parts = []
            if alarm.get("upper_limit") is not None:
                diff = alarm["upper_limit"] - price
                parts.append("↑ triggered" if diff <= 0 else f"↑ ${diff:.2f} ({diff/price*100:.1f}%) to go")
            if alarm.get("lower_limit") is not None:
                diff = price - alarm["lower_limit"]
                parts.append("↓ triggered" if diff <= 0 else f"↓ ${diff:.2f} ({diff/price*100:.1f}%) to go")
            distances[alarm_id] = " · ".join(parts) or None
```

Replace with:

```python
        else:
            t, _, _ = checker.condition_met(alarm, price)
            triggered[alarm_id] = t
            curr = "₪" if alarm.get("source") == "tase" else "$"
            parts = []
            if alarm.get("upper_limit") is not None:
                diff = alarm["upper_limit"] - price
                parts.append("↑ triggered" if diff <= 0 else f"↑ {curr}{diff:.2f} ({diff/price*100:.1f}%) to go")
            if alarm.get("lower_limit") is not None:
                diff = price - alarm["lower_limit"]
                parts.append("↓ triggered" if diff <= 0 else f"↓ {curr}{diff:.2f} ({diff/price*100:.1f}%) to go")
            distances[alarm_id] = " · ".join(parts) or None
```

- [ ] **Step 7: Remove `alarm_duplicate` route and function from `app.py`**

Delete the entire `alarm_duplicate` function and its route decorator (lines ~220–242):

```python
# --- Duplicate alarm ---

@app.route("/alarm/<alarm_id>/duplicate", methods=["POST"])
@login_required
def alarm_duplicate(alarm_id):
    import uuid
    alarms = read_alarms()
    src = next((a for a in alarms if a.get("id") == alarm_id), None)
    if src is None:
        return redirect(url_for("dashboard"))
    new_alarm = dict(src)
    new_alarm["id"] = str(uuid.uuid4())[:8]
    new_alarm["enabled"] = False
    new_alarm["last_triggered"] = None
    new_alarm["history"] = []
    new_alarm["base_price"] = None
    new_alarm["created_at"] = datetime.now(timezone.utc).isoformat()
    try:
        new_alarm["initial_price"] = checker.get_price(src["ticker"])
    except Exception:
        new_alarm["initial_price"] = src.get("initial_price")
    def do_append(alarms):
        alarms.append(new_alarm)
    modify_alarms(do_append)
    return redirect(url_for("dashboard"))
```

- [ ] **Step 8: Also update `alarm_test_email` to route price fetch by source**

In the `/alarm/<alarm_id>/test-email` route (around line 260), find:

```python
    try:
        price = checker.get_price(ticker)
    except Exception:
        price = None
```

Replace with:

```python
    try:
        if alarm.get("source") == "tase":
            price = tase.get_price(alarm["tase_id"], alarm["tase_type"])
        else:
            price = checker.get_price(ticker)
    except Exception:
        price = None
```

- [ ] **Step 9: Run tests**

```
pytest tests/test_app.py -v
```
Expected: all tests PASS including new ones

- [ ] **Step 10: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: TASE cache at startup, tase-search endpoint, dashboard routing, remove duplicate"
```

---

## Task 5: Update `app.py` — `_alarm_from_form` TASE support + reference price

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_app.py`:

```python
def test_create_tase_alarm(client):
    login(client)
    with patch("tase.get_price", return_value=185.30):
        resp = client.post("/alarm/new", data={
            "ticker": "Eltra Corp",
            "source": "tase",
            "tase_id": "1175819",
            "tase_type": "security",
            "alarm_type": "price",
            "upper_limit": "200",
            "email": "test@example.com",
            "timezone": "Asia/Jerusalem",
            "snooze_hours": "72",
            "enabled": "on",
        }, follow_redirects=True)
    assert resp.status_code == 200
    alarms = json.loads(open(app_module._alarms_path()).read())
    assert len(alarms) == 1
    assert alarms[0]["source"] == "tase"
    assert alarms[0]["tase_id"] == "1175819"
    assert alarms[0]["initial_price"] == 185.30
    assert alarms[0]["ticker"] == "Eltra Corp"  # preserves case for TASE


def test_create_alarm_with_manual_reference_price(client):
    login(client)
    with patch("checker.get_price", return_value=155.0):
        resp = client.post("/alarm/new", data={
            "ticker": "AAPL",
            "alarm_type": "price",
            "upper_limit": "200",
            "email": "test@example.com",
            "timezone": "America/New_York",
            "snooze_hours": "72",
            "enabled": "on",
            "reference_price": "130.00",
        }, follow_redirects=True)
    assert resp.status_code == 200
    alarms = json.loads(open(app_module._alarms_path()).read())
    assert alarms[0]["initial_price"] == 130.0  # manual price used, not live fetch


def test_create_pct_alarm_with_manual_reference_price(client):
    login(client)
    with patch("checker.get_price", return_value=155.0):
        resp = client.post("/alarm/new", data={
            "ticker": "AAPL",
            "alarm_type": "pct",
            "upper_pct": "5",
            "email": "test@example.com",
            "timezone": "America/New_York",
            "snooze_hours": "72",
            "enabled": "on",
            "reference_price": "130.00",
        }, follow_redirects=True)
    assert resp.status_code == 200
    alarms = json.loads(open(app_module._alarms_path()).read())
    assert alarms[0]["base_price"] == 130.0
    assert alarms[0]["initial_price"] == 130.0


def test_create_tase_alarm_missing_tase_id_returns_error(client):
    login(client)
    resp = client.post("/alarm/new", data={
        "ticker": "Some Fund",
        "source": "tase",
        "tase_id": "",
        "tase_type": "fund",
        "alarm_type": "price",
        "upper_limit": "200",
        "email": "test@example.com",
        "timezone": "Asia/Jerusalem",
        "snooze_hours": "72",
        "enabled": "on",
    })
    assert resp.status_code == 200
    assert b"select a security" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_app.py::test_create_tase_alarm tests/test_app.py::test_create_alarm_with_manual_reference_price -v
```
Expected: FAIL

- [ ] **Step 3: Replace `_alarm_from_form` in `app.py`**

Find the entire `_alarm_from_form` function (lines ~355–425) and replace it with:

```python
def _alarm_from_form(form, existing=None):
    """Parse and validate form data. Returns (alarm_dict, error_str_or_None)."""
    import uuid

    source = form.get("source", "yfinance")
    is_tase = source == "tase"

    ticker_raw = form.get("ticker", "").strip()
    if not ticker_raw:
        return None, "Ticker is required"
    ticker = ticker_raw if is_tase else ticker_raw.upper()

    tase_id = form.get("tase_id", "").strip() if is_tase else None
    tase_type = form.get("tase_type", "").strip() if is_tase else None
    if is_tase and not tase_id:
        return None, "Please select a security from the dropdown"

    email_raw = form.get("email", "").strip()
    emails = [e.strip() for e in email_raw.split(",") if e.strip()]
    if not emails:
        return None, "At least one email is required"

    alarm_type = form.get("alarm_type", "price")
    tz = form.get("timezone", "").strip() or None
    if not tz:
        return None, "Timezone (city) is required"

    try:
        snooze_hours = int(form.get("snooze_hours", 72))
    except ValueError:
        snooze_hours = 72
    notes = form.get("notes", "").strip()

    # Manual reference price (overrides live fetch for initial_price / base_price)
    ref_price_raw = form.get("reference_price", "").strip()
    manual_ref = None
    if ref_price_raw:
        try:
            manual_ref = float(ref_price_raw)
        except ValueError:
            return None, "Reference price must be a number"

    alarm = {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "ticker": ticker,
        "enabled": form.get("enabled") == "on",
        "timezone": tz,
        "snooze_hours": snooze_hours,
        "notes": notes or None,
        "last_triggered": existing.get("last_triggered") if existing else None,
        "email": emails if len(emails) > 1 else emails[0],
    }

    if is_tase:
        alarm["source"] = "tase"
        alarm["tase_id"] = tase_id
        alarm["tase_type"] = tase_type

    if existing:
        alarm["created_at"] = existing.get("created_at")
        alarm["initial_price"] = existing.get("initial_price")
        alarm["history"] = existing.get("history", [])
    else:
        alarm["created_at"] = datetime.now(timezone.utc).isoformat()
        alarm["history"] = []
        if manual_ref is not None:
            alarm["initial_price"] = manual_ref
        else:
            try:
                if is_tase:
                    alarm["initial_price"] = tase.get_price(tase_id, tase_type)
                else:
                    alarm["initial_price"] = checker.get_price(ticker)
            except Exception:
                alarm["initial_price"] = None

    if alarm_type == "pct":
        upper_pct = form.get("upper_pct", "").strip()
        lower_pct = form.get("lower_pct", "").strip()
        try:
            alarm["upper_pct"] = float(upper_pct) if upper_pct else None
            alarm["lower_pct"] = float(lower_pct) if lower_pct else None
        except ValueError:
            return None, "Percentage values must be numbers"
        if alarm["upper_pct"] is None and alarm["lower_pct"] is None:
            return None, "At least one percentage threshold is required"
        if existing:
            alarm["base_price"] = existing.get("base_price")
        elif manual_ref is not None:
            alarm["base_price"] = manual_ref
        else:
            alarm["base_price"] = None
    else:
        upper = form.get("upper_limit", "").strip()
        lower = form.get("lower_limit", "").strip()
        try:
            alarm["upper_limit"] = float(upper) if upper else None
            alarm["lower_limit"] = float(lower) if lower else None
        except ValueError:
            return None, "Price limits must be numbers"
        if alarm["upper_limit"] is None and alarm["lower_limit"] is None:
            return None, "At least one price limit is required"

    return alarm, None
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: TASE support in _alarm_from_form, manual reference price field"
```

---

## Task 6: Update `alarm_form.html` — market toggle, TASE autocomplete, reference price

**Files:**
- Modify: `templates/alarm_form.html`

- [ ] **Step 1: Add market toggle and hidden TASE fields**

Replace the existing ticker label block (lines 7–15):

```html
        <label id="label-ticker">Ticker
            <input type="text" name="ticker" id="ticker-input"
                value="{{ form.get('ticker', '') }}"
                placeholder="e.g. AAPL" autocomplete="off"
                {% if alarm %}readonly{% endif %}>
            {% if not alarm %}
            <div class="autocomplete-dropdown" id="ticker-dropdown"></div>
            {% endif %}
        </label>
```

With:

```html
        {% set is_tase = form.get('source') == 'tase' %}

        {% if not alarm %}
        <div class="market-toggle" id="market-toggle">
            <button type="button" class="btn {% if not is_tase %}btn-primary{% endif %}" id="toggle-us">US (Yahoo Finance)</button>
            <button type="button" class="btn {% if is_tase %}btn-primary{% endif %}" id="toggle-il">Israeli (TASE)</button>
        </div>
        {% else %}
        <div class="market-toggle">
            <button type="button" class="btn {% if not is_tase %}btn-primary{% endif %}" disabled>US (Yahoo Finance)</button>
            <button type="button" class="btn {% if is_tase %}btn-primary{% endif %}" disabled>Israeli (TASE)</button>
        </div>
        {% endif %}

        <input type="hidden" name="source" id="source-hidden" value="{{ form.get('source', 'yfinance') }}">
        <input type="hidden" name="tase_id" id="tase-id-hidden" value="{{ form.get('tase_id', '') }}">
        <input type="hidden" name="tase_type" id="tase-type-hidden" value="{{ form.get('tase_type', '') }}">

        <label id="label-ticker" id="label-ticker-wrap">
            <span id="ticker-label-text">{% if is_tase %}Search Israeli Security{% else %}Ticker{% endif %}</span>
            <input type="text" name="ticker" id="ticker-input"
                value="{{ form.get('ticker', '') }}"
                placeholder="{% if is_tase %}e.g. מגדל or Migdal{% else %}e.g. AAPL{% endif %}"
                autocomplete="off"
                {% if alarm %}readonly{% endif %}>
            {% if not alarm %}
            <div class="autocomplete-dropdown" id="ticker-dropdown"></div>
            {% endif %}
        </label>
```

- [ ] **Step 2: Add reference price field**

After the closing `</div>` of `id="pct-fields"` (after line 66), insert:

```html
        <label id="label-ref-price">Reference Price — optional
            <span style="font-size:0.82rem;color:#7a6a5a" id="ref-price-hint">
                Leave blank to use the current market price at creation time.
            </span>
            <input type="number" step="0.01" name="reference_price" id="reference-price-input"
                value="{{ form.get('reference_price', '') }}"
                placeholder="e.g. 150.00">
        </label>
```

- [ ] **Step 3: Update currency labels in price-fields**

In the `id="price-fields"` block, replace the two currency labels:

```html
                        <span style="font-size:0.82rem;color:#7a6a5a">Upper Limit ($) — optional</span>
```
With:
```html
                        <span style="font-size:0.82rem;color:#7a6a5a">Upper Limit (<span class="curr-symbol">$</span>) — optional</span>
```

And:
```html
                        <span style="font-size:0.82rem;color:#7a6a5a">Lower Limit ($) — optional</span>
```
With:
```html
                        <span style="font-size:0.82rem;color:#7a6a5a">Lower Limit (<span class="curr-symbol">$</span>) — optional</span>
```

- [ ] **Step 4: Replace the existing ticker autocomplete block with a market-aware version**

In the `{% block scripts %}` section, find the existing ticker autocomplete block (lines 172–179):

```javascript
// ── Ticker autocomplete (new alarm only) ─────────────────────
const tickerInput = document.getElementById('ticker-input');
const tickerDropdown = document.getElementById('ticker-dropdown');
if (tickerDropdown) {
    makeAutocomplete(tickerInput, tickerDropdown,
        q => fetch('/ticker-search?q=' + encodeURIComponent(q)).then(r => r.json()).then(items =>
            items.map(i => ({ label: i.symbol + ' — ' + i.name, value: i.symbol }))
        ),
        item => { tickerInput.value = item.value; }
    );
}
```

Replace the entire block with:

```javascript
// ── Market toggle ────────────────────────────────────────────
const toggleUs = document.getElementById('toggle-us');
const toggleIl = document.getElementById('toggle-il');
const sourceHidden = document.getElementById('source-hidden');
const taseIdHidden = document.getElementById('tase-id-hidden');
const taseTypeHidden = document.getElementById('tase-type-hidden');
const tickerLabelText = document.getElementById('ticker-label-text');

function setMarket(market) {
    const isTase = market === 'tase';
    sourceHidden.value = isTase ? 'tase' : 'yfinance';
    if (toggleUs) {
        toggleUs.classList.toggle('btn-primary', !isTase);
        toggleIl.classList.toggle('btn-primary', isTase);
    }
    tickerLabelText.textContent = isTase ? 'Search Israeli Security' : 'Ticker';
    tickerInput.placeholder = isTase ? 'e.g. מגדל or Migdal' : 'e.g. AAPL';
    // Clear ticker and TASE fields when switching markets
    tickerInput.value = '';
    if (taseIdHidden) { taseIdHidden.value = ''; taseTypeHidden.value = ''; }
    document.querySelectorAll('.curr-symbol').forEach(el => { el.textContent = isTase ? '₪' : '$'; });
}

if (toggleUs) {
    toggleUs.addEventListener('click', () => setMarket('yfinance'));
    toggleIl.addEventListener('click', () => setMarket('tase'));
}

// Apply initial currency symbol based on current source
(function() {
    if (sourceHidden && sourceHidden.value === 'tase') {
        document.querySelectorAll('.curr-symbol').forEach(el => { el.textContent = '₪'; });
    }
})();

// ── TASE autocomplete ─────────────────────────────────────────
if (tickerDropdown) {
    // Override the existing ticker autocomplete to be market-aware
    tickerInput.addEventListener('input', () => {});  // remove any prior listener by replacing below

    makeAutocomplete(tickerInput, tickerDropdown,
        q => {
            const isTase = sourceHidden && sourceHidden.value === 'tase';
            if (isTase) {
                return fetch('/api/tase-search?q=' + encodeURIComponent(q))
                    .then(r => r.json())
                    .then(items => items.map(i => ({
                        label: i.name + (i.ticker ? ' (' + i.ticker + ')' : '') + ' — ' + (i.type === 'fund' ? 'Fund' : 'Stock/ETF'),
                        value: i.name,
                        taseId: i.id,
                        taseType: i.type,
                    })));
            } else {
                return fetch('/ticker-search?q=' + encodeURIComponent(q))
                    .then(r => r.json())
                    .then(items => items.map(i => ({ label: i.symbol + ' — ' + i.name, value: i.symbol })));
            }
        },
        item => {
            tickerInput.value = item.value;
            if (item.taseId && taseIdHidden) {
                taseIdHidden.value = item.taseId;
                taseTypeHidden.value = item.taseType;
            }
        }
    );
}
```

- [ ] **Step 5: Manual verification**

Start the app locally and verify:
1. New alarm form shows "US (Yahoo Finance)" / "Israeli (TASE)" toggle
2. Switching to Israeli changes label and placeholder
3. Typing "bank" in Israeli mode returns TASE results in dropdown
4. Selecting a result populates the hidden fields
5. Switching back to US clears the TASE fields
6. Reference price field is visible for both alarm types
7. Submitting with a manual reference price: the alarm's initial_price equals the entered value
8. Currency symbols show ₪ in price fields when Israeli mode is active

- [ ] **Step 7: Commit**

```bash
git add templates/alarm_form.html
git commit -m "feat: market toggle and TASE autocomplete in alarm form, reference price field"
```

---

## Task 7: Update `dashboard.html` — currency symbols, remove duplicate button

**Files:**
- Modify: `templates/dashboard.html`

- [ ] **Step 1: Add per-alarm currency variable and update all price displays**

At the top of the `{% for alarm in alarms %}` loop (after line 21), add:

```html
{% set curr = '₪' if alarm.get('source') == 'tase' else '$' %}
```

Then update every hardcoded `$` price display in the card body:

Line 47 — condition display for price limits:
```html
                {% if alarm.get('upper_limit') %}↑ ${{ "%.2f"|format(alarm.upper_limit) }}{% endif %}
                {% if alarm.get('lower_limit') %}↓ ${{ "%.2f"|format(alarm.lower_limit) }}{% endif %}
```
Replace with:
```html
                {% if alarm.get('upper_limit') %}↑ {{ curr }}{{ "%.2f"|format(alarm.upper_limit) }}{% endif %}
                {% if alarm.get('lower_limit') %}↓ {{ curr }}{{ "%.2f"|format(alarm.lower_limit) }}{% endif %}
```

Lines 53–57 — current price display:
```html
            {% if prices.get(alarm.ticker) is not none %}
                ${{ "%.2f"|format(prices[alarm.ticker]) }}
```
Replace with:
```html
            {% if prices.get(alarm.ticker) is not none %}
                {{ curr }}{{ "%.2f"|format(prices[alarm.ticker]) }}
```

Line 76 — initial price in card meta:
```html
            Initial: {% if alarm.get('initial_price') is not none %}${{ "%.2f"|format(alarm.initial_price) }}{% else %}N/A{% endif %}
```
Replace with:
```html
            Initial: {% if alarm.get('initial_price') is not none %}{{ curr }}{{ "%.2f"|format(alarm.initial_price) }}{% else %}N/A{% endif %}
```

History entries (lines 101–104) — threshold and price in history list:
```html
                    {{ entry.type.replace('_', ' ') }} ${{ "%.2f"|format(entry.threshold) }} hit at ${{ "%.2f"|format(entry.price) }}
```
Replace with:
```html
                    {{ entry.type.replace('_', ' ') }} {{ curr }}{{ "%.2f"|format(entry.threshold) }} hit at {{ curr }}{{ "%.2f"|format(entry.price) }}
```

- [ ] **Step 2: Remove the duplicate (Copy) button**

Find and delete the duplicate form in `card-actions` (lines 114–116):

```html
        <form method="post" action="/alarm/{{ alarm.id }}/duplicate" style="display:inline">
            <button type="submit" class="btn">Copy</button>
        </form>
```

- [ ] **Step 3: Manual verification**

Start the app locally and verify:
1. Existing US alarms still show `$` for all prices
2. A test TASE alarm (create one via the form) shows `₪` for all prices on the dashboard
3. The "Copy" button is gone from all alarm cards
4. History entries for TASE alarms show ₪ prices

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat: currency symbol per alarm on dashboard, remove copy button"
```

---

## Done

All tasks complete. Run the full test suite one final time:

```
pytest tests/ -v
```

Expected: all tests PASS with no warnings about missing routes or broken imports.
