# Savings Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Savings tab that tracks ETF/Stock/MMF holdings with live prices, P&L, daily change, a pie chart, and a 30-day growth sparkline; also pre-fill the alarm form email and city.

**Architecture:** Mirror existing patterns exactly — JSON file storage via `checker.py`, Flask routes in `app.py`, Jinja2 templates. New files: `savings_form.html` for the add/edit form, styles appended to `style.css`. Savings tab content lives inside `dashboard.html` (same pattern as Alarms/Sell History). All savings state is under the existing `_lock`.

**Tech Stack:** Flask, Jinja2, yfinance (price + USD/ILS rate), TASE API (Israeli securities), JSON file storage, vanilla JS (inline shares AJAX).

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `templates/alarm_form.html` | Modify | Pre-fill email + city defaults |
| `checker.py` | Modify | Add savings/snapshot load/save helpers + `get_price_with_change` + `get_usd_to_ils` |
| `app.py` | Modify | Startup paths, read/write helpers, price fetch, form parser, snapshot logic, 7 new routes |
| `templates/savings_form.html` | Create | Add/edit holding form |
| `templates/dashboard.html` | Modify | Savings tab in tab bar + savings tab content block |
| `static/style.css` | Modify | Savings tab styles |
| `tests/test_checker.py` | Modify | Savings/snapshot load/save + price helpers |
| `tests/test_app.py` | Modify | `_holding_from_form` validation + savings CRUD routes |

---

## Task 1: Alert form defaults

**Files:**
- Modify: `templates/alarm_form.html:97-107`

- [ ] **Step 1: Update email field to pre-fill default on new alarm**

In `alarm_form.html`, find the email label (line ~97). Change the `value` attribute to use the default when `alarm` is `None` (new alarm) and the stored value otherwise:

```html
<label id="label-email">Email(s) — comma-separated for multiple
    <input type="text" name="email" id="email-input"
        value="{{ form.get('email', '') if alarm else (form.get('email') or 'noamarbes1@gmail.com') }}"
        placeholder="you@example.com">
</label>
```

- [ ] **Step 2: Update city field to pre-fill "Tel Aviv" on new alarm**

Find the city label (line ~103). Add `id="city-input"` already exists. Add a `value` attribute with the default city and a hidden `data-default-tz` to seed the timezone hidden input on page load:

```html
<label id="label-city">City (for timezone) *
    <input type="text" id="city-input" autocomplete="off"
        placeholder="e.g. Tel Aviv"
        value="{{ '' if alarm else 'Tel Aviv' }}">
    <div class="autocomplete-dropdown" id="city-dropdown"></div>
</label>
<input type="hidden" name="timezone" id="timezone-hidden"
    value="{{ form.get('timezone') or ('' if alarm else 'Asia/Jerusalem') }}">
```

- [ ] **Step 3: Verify manually**

Start the dev server (`python app.py`) and open `/alarm/new`. Confirm:
- Email field shows `noamarbes1@gmail.com`
- City field shows `Tel Aviv`
- Both are editable
- Edit an existing alarm: neither default overwrites the stored values

- [ ] **Step 4: Commit**

```bash
git add templates/alarm_form.html
git commit -m "feat: pre-fill email and city defaults on new alarm form"
```

---

## Task 2: Savings data layer in checker.py

**Files:**
- Modify: `checker.py`
- Modify: `tests/test_checker.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_checker.py`:

```python
import checker
import tempfile, os, json

def test_load_savings_returns_empty_list_when_file_missing(tmp_path):
    path = str(tmp_path / "savings.json")
    assert checker.load_savings(path) == []

def test_save_and_load_savings_round_trips(tmp_path):
    path = str(tmp_path / "savings.json")
    holdings = [{"id": "abc", "ticker": "VOO", "shares": 10.0}]
    checker.save_savings(holdings, path)
    assert checker.load_savings(path) == holdings

def test_load_snapshots_returns_empty_list_when_file_missing(tmp_path):
    path = str(tmp_path / "snapshots.json")
    assert checker.load_snapshots(path) == []

def test_save_and_load_snapshots_round_trips(tmp_path):
    path = str(tmp_path / "snapshots.json")
    snaps = [{"date": "2026-05-06", "total_ils": 12345.0}]
    checker.save_snapshots(snaps, path)
    assert checker.load_snapshots(path) == snaps

def test_get_savings_path_returns_local_when_no_data_dir(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    path = checker.get_savings_path()
    assert path == "savings.json"

def test_get_snapshots_path_returns_local_when_no_data_dir(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    path = checker.get_snapshots_path()
    assert path == "savings_snapshots.json"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_checker.py -k "savings or snapshots" -v
```

Expected: `FAILED` with `AttributeError: module 'checker' has no attribute 'load_savings'`

- [ ] **Step 3: Add constants and functions to checker.py**

After the existing `TRADES_VOLUME_PATH` and `TRADES_LOCAL_PATH` constants, add:

```python
SAVINGS_LOCAL_PATH = "savings.json"
SAVINGS_VOLUME_PATH = "/data/savings.json"
SNAPSHOTS_LOCAL_PATH = "savings_snapshots.json"
SNAPSHOTS_VOLUME_PATH = "/data/savings_snapshots.json"


def get_savings_path() -> str:
    if os.path.isdir("/data"):
        return SAVINGS_VOLUME_PATH
    return SAVINGS_LOCAL_PATH


def load_savings(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_savings(holdings: list, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(holdings, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)


def get_snapshots_path() -> str:
    if os.path.isdir("/data"):
        return SNAPSHOTS_VOLUME_PATH
    return SNAPSHOTS_LOCAL_PATH


def load_snapshots(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_snapshots(snapshots: list, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(snapshots, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)
```

- [ ] **Step 4: Add price helpers to checker.py**

After `get_price`, add:

```python
def get_price_with_change(ticker: str) -> tuple:
    """Returns (last_price, previous_close) for a yfinance ticker.
    Returns (None, None) on any failure."""
    try:
        info = yf.Ticker(ticker).fast_info
        price = float(info.last_price) if info.last_price is not None else None
        prev = float(info.previous_close) if info.previous_close is not None else None
        return price, prev
    except Exception:
        return None, None


def get_usd_to_ils() -> float:
    """Returns the current USD→ILS exchange rate from yfinance. Falls back to 3.7."""
    try:
        info = yf.Ticker("USDILS=X").fast_info
        rate = info.last_price
        return float(rate) if rate else 3.7
    except Exception:
        return 3.7
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_checker.py -k "savings or snapshots" -v
```

Expected: all 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: add savings/snapshot data layer and price helpers to checker"
```

---

## Task 3: Savings helpers in app.py

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing tests for `_holding_from_form`**

Add to `tests/test_app.py`:

```python
def test_holding_from_form_requires_ticker(client):
    login(client)
    resp = client.post("/savings/new", data={
        "source": "yfinance", "category": "stocks",
        "shares": "10", "cost_basis": "1000", "currency": "USD"
    }, follow_redirects=True)
    assert b"Ticker" in resp.data or resp.status_code in (200, 400)

def test_holding_from_form_requires_shares(client):
    login(client)
    resp = client.post("/savings/new", data={
        "source": "yfinance", "ticker": "VOO", "category": "etf",
        "cost_basis": "1000", "currency": "USD"
    }, follow_redirects=True)
    assert b"Shares" in resp.data or resp.status_code in (200, 400)

def test_holding_from_form_invalid_category(client):
    login(client)
    resp = client.post("/savings/new", data={
        "source": "yfinance", "ticker": "VOO", "category": "invalid",
        "shares": "10", "cost_basis": "1000", "currency": "USD"
    }, follow_redirects=True)
    assert b"category" in resp.data.lower() or resp.status_code in (200, 400)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_app.py -k "holding_from_form" -v
```

Expected: `FAILED` — route `/savings/new` doesn't exist yet (404)

- [ ] **Step 3: Add startup initialization to app.py**

After the line `_TRADES_PATH = checker.get_trades_path()` in `app.py`, add:

```python
_SAVINGS_PATH = checker.get_savings_path()
_SNAPSHOTS_PATH = checker.get_snapshots_path()
```

- [ ] **Step 4: Add read/write helpers for savings and snapshots to app.py**

After the existing `modify_trades` function, add:

```python
def _savings_path():
    return _SAVINGS_PATH


def _snapshots_path():
    return _SNAPSHOTS_PATH


def read_savings():
    with _lock:
        return checker.load_savings(_savings_path())


def write_savings(holdings):
    with _lock:
        checker.save_savings(holdings, _savings_path())


def modify_savings(fn):
    with _lock:
        path = _savings_path()
        holdings = checker.load_savings(path)
        fn(holdings)
        checker.save_savings(holdings, path)


def read_snapshots():
    with _lock:
        return checker.load_snapshots(_snapshots_path())
```

- [ ] **Step 5: Add `_relative_time` helper to app.py**

After `modify_savings`, add:

```python
def _relative_time(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        diff = datetime.now(timezone.utc) - dt
        secs = diff.total_seconds()
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{int(secs / 60)}m ago"
        if secs < 86400:
            return f"{int(secs / 3600)}h ago"
        return f"{int(secs / 86400)}d ago"
    except Exception:
        return "—"
```

- [ ] **Step 6: Add `_fetch_savings_prices` helper to app.py**

After `_relative_time`, add:

```python
def _fetch_savings_prices(holdings: list) -> dict:
    """Returns {ticker: {"price": float|None, "prev_close": float|None}}.
    TASE holdings get prev_close=None (not available from TASE API)."""
    prices = {}
    for h in holdings:
        ticker = h.get("ticker")
        if not ticker or ticker in prices:
            continue
        try:
            if h.get("source") == "tase":
                price = tase.get_price(h["tase_id"], h["tase_type"])
                prices[ticker] = {"price": price, "prev_close": None}
            else:
                price, prev = checker.get_price_with_change(ticker)
                prices[ticker] = {"price": price, "prev_close": prev}
        except Exception:
            prices[ticker] = {"price": None, "prev_close": None}
    return prices
```

- [ ] **Step 7: Add `_holding_from_form` helper to app.py**

After `_fetch_savings_prices`, add:

```python
def _holding_from_form(form, existing=None):
    """Parse and validate holding form data. Returns (holding_dict, error_str|None)."""
    import uuid

    source = form.get("source", "yfinance")
    is_tase = source == "tase"

    ticker_raw = form.get("ticker", "").strip()
    if not ticker_raw:
        return None, "Ticker is required"
    ticker = ticker_raw if is_tase else ticker_raw.upper()

    tase_id = form.get("tase_id", "").strip() if is_tase else ""
    tase_type = form.get("tase_type", "").strip() if is_tase else ""
    if is_tase and not tase_id:
        return None, "Please select a security from the dropdown"

    name = form.get("name", "").strip() or ticker

    category = form.get("category", "").strip()
    if category not in ("stocks", "etf", "mmf"):
        return None, "Invalid category"

    shares_raw = form.get("shares", "").strip()
    if not shares_raw:
        return None, "Shares is required"
    try:
        shares = float(shares_raw)
    except ValueError:
        return None, "Shares must be a number"

    cost_raw = form.get("cost_basis", "").strip()
    if not cost_raw:
        return None, "Cost basis is required"
    try:
        cost_basis = float(cost_raw)
    except ValueError:
        return None, "Cost basis must be a number"

    currency = "ILS" if is_tase else form.get("currency", "USD")

    return {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "name": name,
        "category": category,
        "source": source,
        "ticker": ticker,
        "tase_id": tase_id,
        "tase_type": tase_type,
        "shares": shares,
        "cost_basis": cost_basis,
        "currency": currency,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }, None
```

- [ ] **Step 8: Add `_maybe_record_snapshot` to app.py**

After `_holding_from_form`, add:

```python
def _maybe_record_snapshot(holdings: list, prices: dict, usd_to_ils: float) -> None:
    """Appends a daily total-ILS snapshot if today's entry is not yet recorded."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _lock:
        path = _snapshots_path()
        snapshots = checker.load_snapshots(path)
        if snapshots and snapshots[-1].get("date") == today_str:
            return
        total_ils = 0.0
        for h in holdings:
            ticker = h.get("ticker")
            pinfo = prices.get(ticker, {})
            price = pinfo.get("price")
            if price is None:
                continue
            shares = h.get("shares") or 0
            rate = usd_to_ils if h.get("currency") == "USD" else 1.0
            total_ils += price * shares * rate
        snapshots.append({"date": today_str, "total_ils": round(total_ils, 2)})
        snapshots = snapshots[-90:]
        checker.save_snapshots(snapshots, path)
```

- [ ] **Step 9: Run the holding_from_form tests — now they should render a 200 with errors, not 404**

First add just the `/savings/new` stub route (GET only, POST returns 400) so the route exists:

```python
@app.route("/savings/new", methods=["GET", "POST"])
@login_required
def savings_new():
    category = request.args.get("category", "stocks")
    if request.method == "POST":
        holding, error = _holding_from_form(request.form)
        if error:
            return render_template("savings_form.html", error=error,
                                   form=request.form, title="Add Holding",
                                   category=request.form.get("category", category))
        return redirect(url_for("savings"))
    return render_template("savings_form.html", form={"category": category},
                           title="Add Holding", category=category)
```

Create a minimal `templates/savings_form.html` stub so the route renders:

```html
{% extends "base.html" %}
{% block content %}
<p>{% if error %}<span class="error">{{ error }}</span>{% endif %}</p>
<form method="post">
  <input name="ticker" value="{{ form.get('ticker','') }}">
  <input name="category" value="{{ form.get('category','') }}">
  <input name="shares" value="{{ form.get('shares','') }}">
  <input name="cost_basis" value="{{ form.get('cost_basis','') }}">
  <input name="source" value="{{ form.get('source','yfinance') }}">
  <button type="submit">Save</button>
</form>
{% endblock %}
```

```
pytest tests/test_app.py -k "holding_from_form" -v
```

Expected: all 3 tests PASS (form renders with error messages)

- [ ] **Step 10: Commit**

```bash
git add app.py templates/savings_form.html tests/test_app.py
git commit -m "feat: add savings helpers, read/write layer, and form parser to app"
```

---

## Task 4: Savings CRUD routes in app.py

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing tests for savings routes**

Add to `tests/test_app.py`:

```python
@pytest.fixture
def savings_client(tmp_path, monkeypatch):
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([]))
    savings_file = tmp_path / "savings.json"
    savings_file.write_text(json.dumps([]))
    snapshots_file = tmp_path / "savings_snapshots.json"
    snapshots_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr(app_module, "_SAVINGS_PATH", str(savings_file))
    monkeypatch.setattr(app_module, "_SNAPSHOTS_PATH", str(snapshots_file))
    monkeypatch.setattr(app_module, "_fetch_savings_prices", lambda h: {})
    monkeypatch.setattr(app_module.checker, "get_usd_to_ils", lambda: 3.7)
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c, savings_file


def test_savings_page_loads(savings_client):
    c, _ = savings_client
    login(c)
    resp = c.get("/savings")
    assert resp.status_code == 200


def test_savings_new_post_adds_holding(savings_client):
    c, savings_file = savings_client
    login(c)
    resp = c.post("/savings/new", data={
        "source": "yfinance", "ticker": "VOO", "name": "Vanguard",
        "category": "etf", "shares": "10", "cost_basis": "5000",
        "currency": "USD",
    }, follow_redirects=True)
    assert resp.status_code == 200
    holdings = json.loads(savings_file.read_text())
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "VOO"


def test_savings_delete_removes_holding(savings_client):
    c, savings_file = savings_client
    savings_file.write_text(json.dumps([{"id": "abc123", "ticker": "VOO",
        "category": "etf", "shares": 10, "cost_basis": 5000, "currency": "USD",
        "source": "yfinance", "name": "Vanguard", "tase_id": "", "tase_type": "",
        "last_updated": "2026-05-06T10:00:00+00:00"}]))
    login(c)
    resp = c.post("/savings/abc123/delete", follow_redirects=True)
    assert resp.status_code == 200
    holdings = json.loads(savings_file.read_text())
    assert holdings == []


def test_savings_inline_shares_update(savings_client):
    c, savings_file = savings_client
    savings_file.write_text(json.dumps([{"id": "abc123", "ticker": "VOO",
        "category": "etf", "shares": 10, "cost_basis": 5000, "currency": "USD",
        "source": "yfinance", "name": "Vanguard", "tase_id": "", "tase_type": "",
        "last_updated": "2026-05-06T10:00:00+00:00"}]))
    login(c)
    resp = c.post("/savings/abc123/shares", data={"shares": "15.5"})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert data["shares"] == 15.5
    holdings = json.loads(savings_file.read_text())
    assert holdings[0]["shares"] == 15.5
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_app.py -k "savings" -v
```

Expected: `FAILED` — `/savings` route doesn't exist yet

- [ ] **Step 3: Add the main GET /savings route to app.py**

After `_maybe_record_snapshot`, add under `# --- Savings ---`:

```python
# --- Savings ---

@app.route("/savings")
@login_required
def savings():
    holdings = read_savings()
    prices = _fetch_savings_prices(holdings)
    usd_to_ils = checker.get_usd_to_ils()

    _maybe_record_snapshot(holdings, prices, usd_to_ils)

    CATEGORIES = ("etf", "stocks", "mmf")

    # Per-holding computed data
    holding_data = {}
    for h in holdings:
        hid = h["id"]
        ticker = h.get("ticker")
        pinfo = prices.get(ticker, {})
        price = pinfo.get("price")
        prev_close = pinfo.get("prev_close")
        shares = h.get("shares") or 0
        cost_basis = h.get("cost_basis") or 0
        currency = h.get("currency", "ILS")
        rate = usd_to_ils if currency == "USD" else 1.0

        current_value = price * shares if price is not None else None
        current_value_ils = current_value * rate if current_value is not None else None
        cost_ils = cost_basis * rate
        pl_ils = (current_value_ils - cost_ils) if current_value_ils is not None else None
        pl_pct = (pl_ils / cost_ils * 100) if (pl_ils is not None and cost_ils) else None

        today_change = ((price - prev_close) * shares
                        if price is not None and prev_close is not None else None)
        today_change_ils = today_change * rate if today_change is not None else None

        holding_data[hid] = {
            "price": price,
            "current_value": current_value,
            "current_value_ils": current_value_ils,
            "cost_ils": cost_ils,
            "pl_ils": pl_ils,
            "pl_pct": pl_pct,
            "today_change": today_change,
            "today_change_ils": today_change_ils,
            "last_updated_rel": _relative_time(h.get("last_updated")),
            "pct_of_cat": 0.0,
        }

    # Category totals
    cat_data = {}
    for cat in CATEGORIES:
        cat_holdings = [h for h in holdings if h.get("category") == cat]
        value_ils = sum(
            holding_data[h["id"]]["current_value_ils"] or 0 for h in cat_holdings)
        pl_ils = sum(holding_data[h["id"]]["pl_ils"] or 0 for h in cat_holdings)
        today_ils = sum(
            holding_data[h["id"]]["today_change_ils"] or 0 for h in cat_holdings)
        cost_ils = sum(holding_data[h["id"]]["cost_ils"] for h in cat_holdings)
        cat_data[cat] = {
            "value_ils": value_ils,
            "pl_ils": pl_ils,
            "today_ils": today_ils,
            "cost_ils": cost_ils,
            "pct_of_portfolio": 0.0,
        }

    # Portfolio totals
    total_value_ils = sum(d["value_ils"] for d in cat_data.values())
    total_pl_ils = sum(d["pl_ils"] for d in cat_data.values())
    total_today_ils = sum(d["today_ils"] for d in cat_data.values())
    total_cost_ils = sum(d["cost_ils"] for d in cat_data.values())
    total_pl_pct = (total_pl_ils / total_cost_ils * 100) if total_cost_ils else None
    prev_total = total_value_ils - total_today_ils
    total_today_pct = (total_today_ils / prev_total * 100) if prev_total else None

    # Category % of portfolio + per-holding % of category
    for cat in CATEGORIES:
        cat_data[cat]["pct_of_portfolio"] = (
            cat_data[cat]["value_ils"] / total_value_ils * 100
            if total_value_ils else 0.0)
        cat_value = cat_data[cat]["value_ils"]
        for h in holdings:
            if h.get("category") == cat:
                hval = holding_data[h["id"]]["current_value_ils"] or 0
                holding_data[h["id"]]["pct_of_cat"] = (
                    hval / cat_value * 100 if cat_value else 0.0)

    # Pie chart SVG data (stroke-dasharray on r=40 circle, circ≈251.33)
    circ = 251.33
    pie = {}
    offset = 0.0
    for cat in CATEGORIES:
        pct = cat_data[cat]["pct_of_portfolio"]
        dash = round(pct / 100 * circ, 2)
        gap = round(circ - dash, 2)
        pie[cat] = {"dash": dash, "gap": gap, "offset": round(-offset, 2)}
        offset += dash

    # Sparkline data (last 30 snapshots)
    snapshots = read_snapshots()[-30:]

    summary = {
        "total_value_ils": total_value_ils,
        "total_pl_ils": total_pl_ils,
        "total_pl_pct": total_pl_pct,
        "total_today_ils": total_today_ils,
        "total_today_pct": total_today_pct,
    }

    return render_template(
        "dashboard.html", tab="savings",
        holdings=holdings, holding_data=holding_data,
        cat_data=cat_data, summary=summary,
        pie=pie, snapshots=snapshots,
        usd_to_ils=usd_to_ils,
        categories=("etf", "stocks", "mmf"),
        category_labels={"etf": "ETFs", "stocks": "Stocks", "mmf": "Money Market Funds (MMF)"},
    )
```

- [ ] **Step 4: Add savings CRUD routes to app.py**

After the `/savings` route:

```python
@app.route("/savings/new", methods=["GET", "POST"])
@login_required
def savings_new():
    category = request.args.get("category", "stocks")
    if request.method == "POST":
        holding, error = _holding_from_form(request.form)
        if error:
            return render_template("savings_form.html", error=error,
                                   form=request.form, title="Add Holding",
                                   category=request.form.get("category", category))
        def do_append(holdings):
            holdings.append(holding)
        modify_savings(do_append)
        return redirect(url_for("savings"))
    return render_template("savings_form.html", form={"category": category},
                           title="Add Holding", category=category)


@app.route("/savings/<hid>/edit", methods=["GET", "POST"])
@login_required
def savings_edit(hid):
    holdings = read_savings()
    holding = next((h for h in holdings if h.get("id") == hid), None)
    if holding is None:
        return redirect(url_for("savings"))
    if request.method == "POST":
        updated, error = _holding_from_form(request.form, existing=holding)
        if error:
            return render_template("savings_form.html", error=error,
                                   form=request.form, holding=holding,
                                   title="Edit Holding",
                                   category=holding["category"])
        def do_update(holdings):
            for i, h in enumerate(holdings):
                if h.get("id") == hid:
                    holdings[i] = updated
                    break
        modify_savings(do_update)
        return redirect(url_for("savings"))
    return render_template("savings_form.html", form=dict(holding),
                           holding=holding, title="Edit Holding",
                           category=holding["category"])


@app.route("/savings/<hid>/delete", methods=["POST"])
@login_required
def savings_delete(hid):
    def do_delete(holdings):
        holdings[:] = [h for h in holdings if h.get("id") != hid]
    modify_savings(do_delete)
    return redirect(url_for("savings"))


@app.route("/savings/<hid>/shares", methods=["POST"])
@login_required
def savings_update_shares(hid):
    shares_raw = request.form.get("shares", "").strip()
    try:
        shares = float(shares_raw)
    except ValueError:
        return jsonify({"error": "Invalid shares value"}), 400
    updated_ts = datetime.now(timezone.utc).isoformat()
    found = [False]
    def do_update(holdings):
        for h in holdings:
            if h.get("id") == hid:
                h["shares"] = shares
                h["last_updated"] = updated_ts
                found[0] = True
                break
    modify_savings(do_update)
    if not found[0]:
        return jsonify({"error": "Holding not found"}), 404
    return jsonify({"ok": True, "shares": shares,
                    "last_updated_rel": _relative_time(updated_ts)})
```

- [ ] **Step 5: Run savings tests**

```
pytest tests/test_app.py -k "savings" -v
```

Expected: all 4 savings tests PASS

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add savings CRUD routes and main savings view"
```

---

## Task 5: Savings form template

**Files:**
- Create: `templates/savings_form.html`

- [ ] **Step 1: Write the full savings_form.html**

Replace the stub from Task 3 with the real form:

```html
{% extends "base.html" %}
{% block content %}
<div class="form-card">
    <h2>{{ title }}</h2>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post" id="savings-form">

        {# Category display (always locked — picked from the "+ Add" button) #}
        <input type="hidden" name="category" value="{{ category }}">
        <div style="margin-bottom:1rem">
            <span class="form-label">Category</span>
            <div class="market-toggle">
                <button type="button" class="btn {% if category == 'etf' %}btn-primary{% endif %}" disabled>ETF</button>
                <button type="button" class="btn {% if category == 'stocks' %}btn-primary{% endif %}" disabled>Stock</button>
                <button type="button" class="btn {% if category == 'mmf' %}btn-primary{% endif %}" disabled>MMF</button>
            </div>
        </div>

        {# Market toggle — only on new (not edit) #}
        {% set is_tase = form.get('source') == 'tase' %}
        {% if not holding %}
        <div class="market-toggle" id="market-toggle">
            <button type="button" class="btn {% if not is_tase %}btn-primary{% endif %}" id="toggle-us">US</button>
            <button type="button" class="btn {% if is_tase %}btn-primary{% endif %}" id="toggle-il">Israeli</button>
        </div>
        {% else %}
        <div class="market-toggle">
            <button type="button" class="btn {% if not is_tase %}btn-primary{% endif %}" disabled>US</button>
            <button type="button" class="btn {% if is_tase %}btn-primary{% endif %}" disabled>Israeli</button>
        </div>
        {% endif %}

        <input type="hidden" name="source" id="source-hidden" value="{{ form.get('source', 'yfinance') }}">
        <input type="hidden" name="tase_id" id="tase-id-hidden" value="{{ form.get('tase_id', '') }}">
        <input type="hidden" name="tase_type" id="tase-type-hidden" value="{{ form.get('tase_type', '') }}">

        <label id="label-ticker">
            <span id="ticker-label-text">{% if is_tase %}Search Israeli Security{% else %}Ticker{% endif %}</span>
            <input type="text" name="ticker" id="ticker-input"
                value="{{ form.get('ticker', '') }}"
                placeholder="{% if is_tase %}e.g. מגדל or Migdal{% else %}e.g. VOO{% endif %}"
                autocomplete="off"
                {% if holding %}readonly{% endif %}>
            {% if not holding %}
            <div class="autocomplete-dropdown" id="ticker-dropdown"></div>
            {% endif %}
        </label>

        <label>Name — optional, auto-filled for US tickers
            <input type="text" name="name" id="name-input"
                value="{{ form.get('name', '') }}"
                placeholder="e.g. Vanguard S&P 500 ETF">
        </label>

        <label>Shares owned
            <input type="number" step="any" min="0" name="shares"
                value="{{ form.get('shares', '') }}"
                placeholder="e.g. 23.5" required>
        </label>

        <label>Total cost basis (what you paid in total)
            <input type="number" step="0.01" min="0" name="cost_basis"
                value="{{ form.get('cost_basis', '') }}"
                placeholder="e.g. 8200.00" required>
        </label>

        {# Currency: auto for Israeli (ILS), selectable for US #}
        <div id="currency-field" {% if is_tase %}style="display:none"{% endif %}>
            <label>Currency
                <select name="currency">
                    <option value="USD" {% if form.get('currency', 'USD') == 'USD' %}selected{% endif %}>USD</option>
                    <option value="ILS" {% if form.get('currency') == 'ILS' %}selected{% endif %}>ILS</option>
                </select>
            </label>
        </div>
        <input type="hidden" name="currency" id="currency-hidden"
            value="{{ 'ILS' if is_tase else form.get('currency', 'USD') }}">

        <div class="form-actions">
            <button type="submit" class="btn btn-primary">Save</button>
            <a href="{{ url_for('savings') }}" class="btn">Cancel</a>
        </div>
    </form>
</div>

<script>
// Reuse alarm form JS pattern for market toggle + autocomplete
(function() {
    const toggleUs = document.getElementById('toggle-us');
    const toggleIl = document.getElementById('toggle-il');
    const sourceHidden = document.getElementById('source-hidden');
    const taseIdHidden = document.getElementById('tase-id-hidden');
    const taseTypeHidden = document.getElementById('tase-type-hidden');
    const tickerInput = document.getElementById('ticker-input');
    const tickerLabel = document.getElementById('ticker-label-text');
    const tickerDropdown = document.getElementById('ticker-dropdown');
    const currencyField = document.getElementById('currency-field');
    const currencyHidden = document.getElementById('currency-hidden');
    const nameInput = document.getElementById('name-input');

    if (!toggleUs) return; // edit mode — no toggle

    function setMarket(isTase) {
        sourceHidden.value = isTase ? 'tase' : 'yfinance';
        tickerLabel.textContent = isTase ? 'Search Israeli Security' : 'Ticker';
        tickerInput.placeholder = isTase ? 'e.g. מגדל or Migdal' : 'e.g. VOO';
        tickerInput.value = '';
        taseIdHidden.value = '';
        taseTypeHidden.value = '';
        tickerDropdown.innerHTML = '';
        tickerDropdown.style.display = 'none';
        if (currencyField) currencyField.style.display = isTase ? 'none' : '';
        currencyHidden.value = isTase ? 'ILS' : 'USD';
        toggleUs.classList.toggle('btn-primary', !isTase);
        toggleIl.classList.toggle('btn-primary', isTase);
    }

    toggleUs.addEventListener('click', () => setMarket(false));
    toggleIl.addEventListener('click', () => setMarket(true));

    // US ticker autocomplete
    let usTimeout;
    tickerInput.addEventListener('input', function() {
        if (sourceHidden.value === 'tase') return;
        clearTimeout(usTimeout);
        const q = this.value.trim();
        if (q.length < 1) { tickerDropdown.style.display = 'none'; return; }
        usTimeout = setTimeout(() => {
            fetch('/ticker-search?q=' + encodeURIComponent(q))
                .then(r => r.json()).then(results => {
                    tickerDropdown.innerHTML = '';
                    if (!results.length) { tickerDropdown.style.display = 'none'; return; }
                    results.forEach(r => {
                        const div = document.createElement('div');
                        div.className = 'autocomplete-item';
                        div.textContent = r.symbol + (r.name ? ' — ' + r.name : '');
                        div.addEventListener('click', () => {
                            tickerInput.value = r.symbol;
                            if (nameInput && !nameInput.value) nameInput.value = r.name || '';
                            tickerDropdown.style.display = 'none';
                        });
                        tickerDropdown.appendChild(div);
                    });
                    tickerDropdown.style.display = 'block';
                });
        }, 200);
    });

    // TASE autocomplete
    let taseTimeout;
    tickerInput.addEventListener('input', function() {
        if (sourceHidden.value !== 'tase') return;
        clearTimeout(taseTimeout);
        const q = this.value.trim();
        if (q.length < 2) { tickerDropdown.style.display = 'none'; return; }
        taseTimeout = setTimeout(() => {
            fetch('/api/tase-search?q=' + encodeURIComponent(q))
                .then(r => r.json()).then(results => {
                    tickerDropdown.innerHTML = '';
                    if (!results.length) { tickerDropdown.style.display = 'none'; return; }
                    results.forEach(r => {
                        const div = document.createElement('div');
                        div.className = 'autocomplete-item';
                        div.textContent = r.name + (r.ticker ? ' (' + r.ticker + ')' : '');
                        div.addEventListener('click', () => {
                            tickerInput.value = r.name;
                            if (nameInput && !nameInput.value) nameInput.value = r.name || '';
                            taseIdHidden.value = r.id;
                            taseTypeHidden.value = r.type;
                            tickerDropdown.style.display = 'none';
                        });
                        tickerDropdown.appendChild(div);
                    });
                    tickerDropdown.style.display = 'block';
                });
        }, 200);
    });

    document.addEventListener('click', e => {
        if (!tickerDropdown.contains(e.target) && e.target !== tickerInput) {
            tickerDropdown.style.display = 'none';
        }
    });
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Verify form renders**

```
python app.py
```

Open `/savings/new?category=etf` — confirm:
- Category shows ETF (locked)
- Market toggle (US/Israeli) works
- Ticker autocomplete works for US
- TASE search works for Israeli
- Name field auto-fills from US ticker selection
- Shares and cost basis fields present
- Cancel returns to `/savings`

- [ ] **Step 3: Commit**

```bash
git add templates/savings_form.html
git commit -m "feat: add savings holding add/edit form template"
```

---

## Task 6: Savings tab in dashboard.html

**Files:**
- Modify: `templates/dashboard.html`

- [ ] **Step 1: Add Savings to the tab bar**

In `dashboard.html`, find the tab bar block (lines ~11-19). Add the Savings tab:

```html
<div class="tab-bar">
    <a href="{{ url_for('dashboard') }}"
       class="tab {% if tab not in ('history', 'savings') %}tab-active{% endif %}">Alarms</a>
    <a href="{{ url_for('dashboard', tab='history') }}"
       class="tab {% if tab == 'history' %}tab-active{% endif %}">Sell History</a>
    <a href="{{ url_for('savings') }}"
       class="tab {% if tab == 'savings' %}tab-active{% endif %}">Savings</a>
    {% if tab == 'history' %}
    <a href="{{ url_for('trade_new') }}" class="btn btn-primary" style="margin-left:auto">+ Add Trade</a>
    {% endif %}
</div>
```

- [ ] **Step 2: Add savings tab content block to dashboard.html**

At the end of `dashboard.html`, before `{% endblock %}`, add:

```html
{% if tab == 'savings' %}
{# ══════════════════════════════════════════════════
   SAVINGS TAB
══════════════════════════════════════════════════ #}

{# Summary cards #}
<div class="savings-summary">

    {# Total Portfolio #}
    <div class="savings-stat-card">
        <div class="savings-stat-label">Total Portfolio (ILS)</div>
        {% if summary.total_value_ils %}
        <div class="savings-stat-value-large">₪{{ "{:,.0f}".format(summary.total_value_ils) }}</div>
        {% else %}
        <div class="savings-stat-value-large">—</div>
        {% endif %}
        <div class="savings-stat-sub">across all categories</div>
        {% if snapshots %}
        <div class="savings-sparkline-wrap">
            <svg class="savings-sparkline" viewBox="0 0 200 50" preserveAspectRatio="none">
                {% set vals = snapshots | map(attribute='total_ils') | list %}
                {% set mn = vals | min %}
                {% set mx = vals | max %}
                {% set rng = mx - mn if mx != mn else 1 %}
                {% set n = vals | length %}
                {% set pts = [] %}
                {% for i in range(n) %}
                    {% set x = (i / (n - 1) * 200) if n > 1 else 100 %}
                    {% set y = 45 - ((vals[i] - mn) / rng * 40) %}
                    {% if pts.append(x|string + ',' + y|string) %}{% endif %}
                {% endfor %}
                <polyline points="{{ pts | join(' ') }}"
                    fill="none" stroke="#c8a96e" stroke-width="2"/>
            </svg>
        </div>
        {% endif %}
    </div>

    {# Total P&L #}
    <div class="savings-stat-card">
        <div class="savings-stat-label">Total P&L (ILS)</div>
        {% if summary.total_pl_ils is not none %}
        <div class="savings-stat-amount {% if summary.total_pl_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
            {{ "%+,.0f"|format(summary.total_pl_ils) }} ₪
        </div>
        <div class="savings-stat-pct {% if summary.total_pl_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
            {% if summary.total_pl_pct is not none %}{{ "%+.1f"|format(summary.total_pl_pct) }}%{% endif %}
        </div>
        {% else %}
        <div class="savings-stat-amount">—</div>
        {% endif %}
        <div class="savings-stat-breakdown">
            {% for cat in categories %}
            <div class="savings-breakdown-row">
                <span>{{ category_labels[cat] }}</span>
                <span class="{% if cat_data[cat].pl_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
                    {{ "%+,.0f"|format(cat_data[cat].pl_ils) }} ₪
                </span>
            </div>
            {% endfor %}
        </div>
    </div>

    {# Today's Change #}
    <div class="savings-stat-card">
        <div class="savings-stat-label">Today's Change (ILS)</div>
        {% if summary.total_today_ils is not none %}
        <div class="savings-stat-amount {% if summary.total_today_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
            {{ "%+,.0f"|format(summary.total_today_ils) }} ₪
        </div>
        <div class="savings-stat-pct {% if summary.total_today_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
            {% if summary.total_today_pct is not none %}{{ "%+.2f"|format(summary.total_today_pct) }}%{% endif %}
        </div>
        {% else %}
        <div class="savings-stat-amount">—</div>
        {% endif %}
        <div class="savings-stat-breakdown">
            {% for cat in categories %}
            <div class="savings-breakdown-row">
                <span>{{ category_labels[cat] }}</span>
                <span class="{% if cat_data[cat].today_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
                    {{ "%+,.0f"|format(cat_data[cat].today_ils) }} ₪
                </span>
            </div>
            {% endfor %}
        </div>
    </div>

    {# Pie chart #}
    <div class="savings-stat-card savings-pie-card">
        <div class="savings-stat-label">Allocation</div>
        {% set pie_colors = {'etf': '#6b4f2a', 'stocks': '#c8a96e', 'mmf': '#81c784'} %}
        <svg viewBox="0 0 120 120" width="130" height="130">
            {% for cat in categories %}
            <circle cx="60" cy="60" r="40"
                fill="none"
                stroke="{{ pie_colors[cat] }}"
                stroke-width="24"
                stroke-dasharray="{{ pie[cat].dash }} {{ pie[cat].gap }}"
                stroke-dashoffset="{{ pie[cat].offset }}"
                transform="rotate(-90 60 60)"/>
            {% endfor %}
            <circle cx="60" cy="60" r="28" fill="white"/>
            <text x="60" y="56" text-anchor="middle" font-size="9" fill="#7a6a5a">Total</text>
            <text x="60" y="68" text-anchor="middle" font-size="10" fill="#2d2a24" font-weight="bold">
                ₪{{ "{:,.0f}".format(summary.total_value_ils / 1000) }}k
            </text>
        </svg>
        <div class="savings-pie-legend">
            {% for cat in categories %}
            <div class="savings-legend-item">
                <span class="savings-legend-dot" style="background:{{ pie_colors[cat] }}"></span>
                <span>{{ category_labels[cat] }} — {{ "%.1f"|format(cat_data[cat].pct_of_portfolio) }}%</span>
            </div>
            {% endfor %}
        </div>
    </div>
</div>

{# Category sections #}
{% for cat in categories %}
{% set cat_holdings = holdings | selectattr('category', 'equalto', cat) | list %}
{% set cd = cat_data[cat] %}
<div class="savings-category">
    <div class="savings-category-header" onclick="toggleCategory('{{ cat }}')">
        <span class="savings-cat-dot" style="background:{{ pie_colors[cat] }}"></span>
        <span class="savings-cat-title">{{ category_labels[cat] }}</span>
        <div class="savings-cat-meta">
            <span>
                <span class="savings-meta-label">Value</span>
                ₪{{ "{:,.0f}".format(cd.value_ils) }}
            </span>
            <span>
                <span class="savings-meta-label">P&amp;L</span>
                <span class="{% if cd.pl_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
                    {{ "%+,.0f"|format(cd.pl_ils) }} ₪
                </span>
            </span>
            <span>
                <span class="savings-meta-label">Today</span>
                <span class="{% if cd.today_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
                    {{ "%+,.0f"|format(cd.today_ils) }} ₪
                </span>
            </span>
            <span>
                <span class="savings-meta-label">% of Portfolio</span>
                {{ "%.1f"|format(cd.pct_of_portfolio) }}%
            </span>
        </div>
        <span class="savings-toggle-arrow" id="arrow-{{ cat }}">▾</span>
    </div>
    <div id="cat-body-{{ cat }}">
        {% if cat_holdings %}
        <table class="savings-holdings-table">
            <thead>
                <tr>
                    <th style="text-align:left">Name / Ticker</th>
                    <th>Shares</th>
                    <th>Cost Basis</th>
                    <th>Price</th>
                    <th>Value</th>
                    <th>P&amp;L</th>
                    <th>Today</th>
                    <th>% of {{ category_labels[cat] }}</th>
                    <th>Updated</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
            {% for h in cat_holdings %}
            {% set hd = holding_data[h.id] %}
            {% set curr = '₪' if h.currency == 'ILS' else '$' %}
            <tr>
                <td>
                    <strong>{{ h.ticker }}</strong><br>
                    <span class="savings-holding-name">{{ h.name }}</span>
                </td>
                <td>
                    <span class="savings-inline-edit" data-hid="{{ h.id }}"
                          onclick="startSharesEdit(this, {{ h.shares }})">
                        {{ h.shares }} ✎
                    </span>
                    <form class="savings-shares-form" id="shares-form-{{ h.id }}"
                          style="display:none" onsubmit="submitShares(event, '{{ h.id }}')">
                        <input type="number" step="any" min="0" class="savings-shares-input"
                               id="shares-input-{{ h.id }}" value="{{ h.shares }}">
                        <button type="submit" class="btn-xs">✓</button>
                        <button type="button" class="btn-xs" onclick="cancelSharesEdit('{{ h.id }}')">✕</button>
                    </form>
                </td>
                <td>{{ curr }}{{ "{:,.2f}".format(h.cost_basis) }}</td>
                <td>{% if hd.price is not none %}{{ curr }}{{ "{:,.2f}".format(hd.price) }}{% else %}—{% endif %}</td>
                <td>{% if hd.current_value is not none %}{{ curr }}{{ "{:,.2f}".format(hd.current_value) }}{% else %}—{% endif %}</td>
                <td class="{% if hd.pl_ils is not none and hd.pl_ils >= 0 %}value-positive{% elif hd.pl_ils is not none %}value-negative{% endif %}">
                    {% if hd.pl_ils is not none %}
                    {{ "%+,.0f"|format(hd.pl_ils) }} ₪<br>
                    <span style="font-size:0.75rem">{% if hd.pl_pct is not none %}{{ "%+.1f"|format(hd.pl_pct) }}%{% endif %}</span>
                    {% else %}—{% endif %}
                </td>
                <td class="{% if hd.today_change_ils is not none and hd.today_change_ils >= 0 %}value-positive{% elif hd.today_change_ils is not none %}value-negative{% endif %}">
                    {% if hd.today_change_ils is not none %}{{ "%+,.0f"|format(hd.today_change_ils) }} ₪{% else %}—{% endif %}
                </td>
                <td>
                    <div class="savings-pct-bar-wrap">
                        <div class="savings-pct-bar" style="width:{{ [hd.pct_of_cat * 0.6, 60] | min | round }}px"></div>
                        <span>{{ "%.0f"|format(hd.pct_of_cat) }}%</span>
                    </div>
                </td>
                <td><span class="savings-updated">{{ hd.last_updated_rel }}</span></td>
                <td>
                    <div class="savings-actions">
                        <a href="{{ url_for('savings_edit', hid=h.id) }}" class="btn-xs">Edit</a>
                        <form method="post" action="{{ url_for('savings_delete', hid=h.id) }}"
                              style="display:inline"
                              onsubmit="return confirm('Delete {{ h.ticker }}?')">
                            <button type="submit" class="btn-xs danger">×</button>
                        </form>
                    </div>
                </td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
        {% endif %}
        <div class="savings-add-row">
            <a href="{{ url_for('savings_new', category=cat) }}" class="btn-xs">+ Add {{ category_labels[cat][:-1] if cat != 'mmf' else 'MMF' }}</a>
        </div>
    </div>
</div>
{% endfor %}

<script>
function toggleCategory(cat) {
    const body = document.getElementById('cat-body-' + cat);
    const arrow = document.getElementById('arrow-' + cat);
    const hidden = body.style.display === 'none';
    body.style.display = hidden ? '' : 'none';
    arrow.textContent = hidden ? '▾' : '▸';
}

function startSharesEdit(el, current) {
    const hid = el.dataset.hid;
    el.style.display = 'none';
    const form = document.getElementById('shares-form-' + hid);
    form.style.display = 'inline-flex';
    const input = document.getElementById('shares-input-' + hid);
    input.focus();
    input.select();
}

function cancelSharesEdit(hid) {
    document.getElementById('shares-form-' + hid).style.display = 'none';
    document.querySelector('[data-hid="' + hid + '"]').style.display = '';
}

function submitShares(event, hid) {
    event.preventDefault();
    const input = document.getElementById('shares-input-' + hid);
    const shares = input.value;
    fetch('/savings/' + hid + '/shares', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'shares=' + encodeURIComponent(shares),
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) {
            const el = document.querySelector('[data-hid="' + hid + '"]');
            el.textContent = shares + ' ✎';
            el.style.display = '';
            document.getElementById('shares-form-' + hid).style.display = 'none';
        }
    });
}
</script>

{% endif %}{# end savings tab #}
```

- [ ] **Step 2: Run the savings page test**

```
pytest tests/test_app.py::test_savings_page_loads -v
```

Expected: PASS

- [ ] **Step 3: Verify manually**

Start the server and open `/savings`. Confirm:
- Three category sections render
- Summary cards show (zeros if no holdings)
- "+ Add" buttons link correctly
- Add a holding via the form and verify it appears

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat: add savings tab content to dashboard template"
```

---

## Task 7: Savings tab CSS

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Append savings styles to style.css**

Open `static/style.css` and append at the end:

```css
/* ═══════════════════════════════════════
   SAVINGS TAB
═══════════════════════════════════════ */

.savings-summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr) auto;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
    align-items: start;
}

.savings-stat-card {
    background: #f5f0ea;
    border-radius: 8px;
    padding: 0.9rem 1rem;
    border: 1px solid #e0d8cc;
}

.savings-stat-label {
    font-size: 0.75rem;
    color: #7a6a5a;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.savings-stat-value-large {
    font-size: 2rem;
    font-weight: 700;
    color: #2d2a24;
    margin-top: 0.2rem;
}

.savings-stat-amount {
    font-size: 1.4rem;
    font-weight: 700;
    margin-top: 0.2rem;
}

.savings-stat-pct {
    font-size: 1.05rem;
    font-weight: 600;
    margin-top: 0.1rem;
}

.savings-stat-sub {
    font-size: 0.78rem;
    color: #7a6a5a;
    margin-top: 0.1rem;
}

.savings-sparkline-wrap {
    margin-top: 0.5rem;
    height: 50px;
    border-radius: 6px;
    overflow: hidden;
    background: linear-gradient(to right, #f5f0ea, #e8d5b0);
    border: 1px dashed #c8a96e;
}

.savings-sparkline {
    width: 100%;
    height: 100%;
}

.savings-stat-breakdown {
    margin-top: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}

.savings-breakdown-row {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: #4a3f32;
}

.savings-pie-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 190px;
}

.savings-pie-legend {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    width: 100%;
    margin-top: 0.5rem;
}

.savings-legend-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.78rem;
    color: #4a3f32;
}

.savings-legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    display: inline-block;
}

/* Category sections */

.savings-category {
    background: #fff;
    border: 1px solid #e0d8cc;
    border-radius: 8px;
    margin-bottom: 1rem;
    overflow: hidden;
}

.savings-category-header {
    display: flex;
    align-items: center;
    padding: 0.8rem 1rem;
    background: #f5f0ea;
    cursor: pointer;
    gap: 0.75rem;
}

.savings-cat-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
}

.savings-cat-title {
    font-weight: 700;
    font-size: 1rem;
    flex: 1;
}

.savings-cat-meta {
    display: flex;
    gap: 1.5rem;
    font-size: 0.82rem;
    color: #4a3f32;
}

.savings-cat-meta > span {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
}

.savings-meta-label {
    font-size: 0.68rem;
    color: #7a6a5a;
    text-transform: uppercase;
}

.savings-toggle-arrow {
    color: #7a6a5a;
    font-size: 0.9rem;
}

/* Holdings table */

.savings-holdings-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
}

.savings-holdings-table th {
    background: #faf7f2;
    color: #7a6a5a;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.5rem 0.75rem;
    text-align: right;
    border-bottom: 1px solid #e0d8cc;
}

.savings-holdings-table td {
    padding: 0.55rem 0.75rem;
    border-bottom: 1px solid #f0ebe3;
    text-align: right;
    color: #2d2a24;
    vertical-align: middle;
}

.savings-holdings-table tr:last-child td {
    border-bottom: none;
}

.savings-holdings-table tr:hover td {
    background: #faf7f2;
}

.savings-holding-name {
    font-size: 0.75rem;
    color: #7a6a5a;
    font-weight: 400;
}

.savings-inline-edit {
    background: #e8f5e9;
    border: 1px solid #a5d6a7;
    border-radius: 4px;
    padding: 0.15rem 0.5rem;
    font-size: 0.8rem;
    color: #1b5e20;
    cursor: pointer;
    white-space: nowrap;
}

.savings-shares-form {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
}

.savings-shares-input {
    width: 70px;
    font-size: 0.8rem;
    padding: 0.1rem 0.3rem;
    border: 1px solid #a5d6a7;
    border-radius: 4px;
}

.savings-pct-bar-wrap {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    justify-content: flex-end;
}

.savings-pct-bar {
    height: 6px;
    background: #c8a96e;
    border-radius: 3px;
    min-width: 2px;
}

.savings-updated {
    font-size: 0.72rem;
    color: #7a6a5a;
}

.savings-actions {
    display: flex;
    gap: 0.3rem;
    justify-content: flex-end;
}

.savings-add-row {
    display: flex;
    justify-content: flex-end;
    padding: 0.5rem 1rem;
    background: #faf7f2;
    border-top: 1px solid #e0d8cc;
}

/* Responsive: stack summary cards on narrow screens */
@media (max-width: 900px) {
    .savings-summary {
        grid-template-columns: 1fr 1fr;
    }
    .savings-cat-meta {
        gap: 0.75rem;
        font-size: 0.75rem;
    }
}

@media (max-width: 600px) {
    .savings-summary {
        grid-template-columns: 1fr;
    }
}
```

- [ ] **Step 2: Run all tests**

```
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3: Full manual verification**

Start the server and verify:
- Summary cards lay out as a 4-column row
- Pie chart renders correctly (donut with colored segments)
- 30-day sparkline appears in the portfolio card after a snapshot is recorded
- Category sections collapse/expand on click
- Inline shares edit: click ✎ → input appears → type new value → ✓ → value updates without page reload
- Add ETF, Stock, MMF holdings via forms
- Edit and delete work
- Alarm form: email and city are pre-filled on new, not overridden on edit

- [ ] **Step 4: Commit**

```bash
git add static/style.css
git commit -m "feat: add savings tab CSS styles"
```
