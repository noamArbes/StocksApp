# Sell History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Sell History tab to the dashboard with a summary card and trade table; allow manual entry and one-click creation from owned alarm cards; store trades in a new `trades.json` file.

**Architecture:** `trades.json` alongside `alarms.json` using the same atomic load/save pattern already in `checker.py`. Dashboard gets a `?tab=` query param; trades are only loaded when `tab=history`. All trade CRUD and record-sale routes live in `app.py`. A single `trade_form.html` template handles Add, Edit, and Record Sale (title and optional delete-alarm checkbox vary by context).

**Tech Stack:** Python/Flask, Jinja2, vanilla JS, pytest

---

## File Map

| File | Change |
|---|---|
| `checker.py` | Add `TRADES_LOCAL_PATH`, `TRADES_VOLUME_PATH`, `get_trades_path()`, `load_trades()`, `save_trades()` |
| `app.py` | Add `_TRADES_PATH`, `_trades_path()`, `read_trades()`, `write_trades()`, `modify_trades()`, `_trade_from_form()`; add trade CRUD routes + record-sale route; update dashboard route for tab param |
| `templates/trade_form.html` | New template — shared by Add Trade, Edit Trade, Record Sale |
| `templates/alarm_form.html` | Add shares field (shown when owned is checked) |
| `templates/dashboard.html` | Add tab bar; wrap alarms content; add history tab (summary card + table + Record Sale button on owned cards) |
| `tests/test_checker.py` | Add `load_trades` / `save_trades` tests |
| `tests/test_app.py` | Add `_alarm_from_form` shares tests, trade CRUD tests, record-sale tests, dashboard history tab tests |

---

## Task 1: Trades persistence in checker.py

**Files:**
- Modify: `checker.py` (after line 135, after `save_alarms`)
- Modify: `tests/test_checker.py` (append at end)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_checker.py`:

```python
# --- load_trades / save_trades tests ---

def test_load_trades_returns_empty_list_when_file_missing():
    result = checker.load_trades("/tmp/nonexistent_trades_abc123.json")
    assert result == []


def test_load_trades_returns_list():
    trades = [{"id": "t1", "ticker": "WDC", "buy_price": 42.10, "sell_price": 67.80,
               "buy_date": "2026-01-15", "sell_date": "2026-04-10", "shares": 20,
               "source": "yfinance", "created_at": "2026-04-10T14:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(trades, f)
        path = f.name
    try:
        result = checker.load_trades(path)
        assert isinstance(result, list)
        assert result[0]["ticker"] == "WDC"
        assert result[0]["shares"] == 20
    finally:
        os.unlink(path)


def test_save_and_reload_trades():
    trades = [{"id": "t2", "ticker": "AAPL", "buy_price": 150.0, "sell_price": 160.0,
               "buy_date": "2026-01-01", "sell_date": "2026-02-01", "shares": None,
               "source": "yfinance", "created_at": "2026-02-01T00:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        checker.save_trades(trades, path)
        result = checker.load_trades(path)
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["shares"] is None
    finally:
        os.unlink(path)


def test_save_trades_writes_valid_json():
    trades = [{"id": "t3", "ticker": "TSLA", "buy_price": 200.0, "sell_price": 250.0,
               "buy_date": "2026-01-01", "sell_date": "2026-03-01", "shares": 5,
               "source": "yfinance", "created_at": "2026-03-01T00:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        checker.save_trades(trades, path)
        with open(path) as f:
            data = json.load(f)
        assert data[0]["ticker"] == "TSLA"
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_checker.py::test_load_trades_returns_empty_list_when_file_missing tests/test_checker.py::test_load_trades_returns_list tests/test_checker.py::test_save_and_reload_trades tests/test_checker.py::test_save_trades_writes_valid_json -v
```

Expected: 4 FAILED — `checker` has no attribute `load_trades`

- [ ] **Step 3: Add trades persistence to checker.py**

In `checker.py`, after `LOCAL_PATH = "alarms.json"` (line 105), add:

```python
TRADES_LOCAL_PATH = "trades.json"
TRADES_VOLUME_PATH = "/data/trades.json"
```

After `save_alarms` (after line 134), insert:

```python
def get_trades_path() -> str:
    """Returns the path to trades.json — volume path on Railway, local path otherwise."""
    data_dir = "/data"
    if os.path.isdir(data_dir):
        return os.path.join(data_dir, "trades.json")
    return TRADES_LOCAL_PATH


def load_trades(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_trades(trades: list, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(trades, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)
```

- [ ] **Step 4: Run tests — expect all 4 to pass**

```
py -m pytest tests/test_checker.py::test_load_trades_returns_empty_list_when_file_missing tests/test_checker.py::test_load_trades_returns_list tests/test_checker.py::test_save_and_reload_trades tests/test_checker.py::test_save_trades_writes_valid_json -v
```

Expected: 4 PASSED

- [ ] **Step 5: Run the full checker test suite to check for regressions**

```
py -m pytest tests/test_checker.py -v
```

Expected: all previously-passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: add trades persistence to checker.py"
```

---

## Task 2: Shares field on alarm form + _alarm_from_form

**Files:**
- Modify: `app.py` (`_alarm_from_form`, lines ~421–431)
- Modify: `templates/alarm_form.html` (after owned checkbox, ~line 134; scripts section)
- Modify: `tests/test_app.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_alarm_from_form_shares_set():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("alarm_type", "price"), ("upper_limit", "200"),
        ("email", "a@b.com"), ("timezone", "America/New_York"),
        ("enabled", "on"), ("owned", "on"), ("shares", "20"),
    ])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["shares"] == 20


def test_alarm_from_form_shares_blank():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("alarm_type", "price"), ("upper_limit", "200"),
        ("email", "a@b.com"), ("timezone", "America/New_York"), ("enabled", "on"),
    ])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["shares"] is None


def test_alarm_from_form_shares_invalid():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("alarm_type", "price"), ("upper_limit", "200"),
        ("email", "a@b.com"), ("timezone", "America/New_York"),
        ("enabled", "on"), ("owned", "on"), ("shares", "abc"),
    ])
    _, error = _alarm_from_form(form)
    assert error == "Shares must be a whole number"
```

- [ ] **Step 2: Run to confirm they fail**

```
py -m pytest tests/test_app.py::test_alarm_from_form_shares_set tests/test_app.py::test_alarm_from_form_shares_blank tests/test_app.py::test_alarm_from_form_shares_invalid -v
```

Expected: 3 FAILED — `alarm` dict has no `shares` key yet

- [ ] **Step 3: Add shares parsing to _alarm_from_form in app.py**

In `_alarm_from_form()`, after `notes = form.get("notes", "").strip()` and before the `alarm = {...}` dict (around line 410), add:

```python
    shares_raw = form.get("shares", "").strip()
    if shares_raw:
        try:
            shares = int(shares_raw)
        except ValueError:
            return None, "Shares must be a whole number"
    else:
        shares = None
```

In the `alarm = {...}` dict (lines ~421–431), add `"shares": shares,` after `"owned": form.get("owned") == "on",`:

```python
    alarm = {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "ticker": ticker,
        "enabled": form.get("enabled") == "on",
        "owned": form.get("owned") == "on",
        "shares": shares,
        "timezone": tz,
        "snooze_hours": snooze_hours,
        "notes": notes or None,
        "last_triggered": existing.get("last_triggered") if existing else None,
        "email": emails if len(emails) > 1 else emails[0],
    }
```

- [ ] **Step 4: Run the shares tests — expect all 3 to pass**

```
py -m pytest tests/test_app.py::test_alarm_from_form_shares_set tests/test_app.py::test_alarm_from_form_shares_blank tests/test_app.py::test_alarm_from_form_shares_invalid -v
```

Expected: 3 PASSED

- [ ] **Step 5: Add shares field to alarm_form.html**

In `templates/alarm_form.html`, after the owned checkbox label block (after `</label>` closing the owned checkbox, around line 134), insert:

```html
        <div id="shares-field" style="display:none">
            <label>Number of shares — optional
                <input type="number" step="1" min="1" name="shares"
                    value="{{ form.get('shares') or '' }}"
                    placeholder="e.g. 20">
            </label>
        </div>
```

In `templates/alarm_form.html`, in the `{% block scripts %}` section, after the `updateFields()` call and the `radios.forEach(...)` line (after line ~162), add:

```javascript
// ── Owned / Shares toggle ────────────────────────────────────
const ownedCheckbox = document.querySelector('[name=owned]');
const sharesField = document.getElementById('shares-field');
function updateSharesVisibility() {
    sharesField.style.display = ownedCheckbox.checked ? '' : 'none';
}
ownedCheckbox.addEventListener('change', updateSharesVisibility);
updateSharesVisibility();
```

- [ ] **Step 6: Run the full test suite to check for regressions**

```
py -m pytest tests/ -v
```

Expected: all previously-passing tests still pass; new 3 shares tests pass

- [ ] **Step 7: Commit**

```bash
git add app.py templates/alarm_form.html tests/test_app.py
git commit -m "feat: add shares field to owned alarm form and data model"
```

---

## Task 3: Trade CRUD routes + trade_form.html

**Files:**
- Modify: `app.py` (add after `alarm_toggle_owned` route, around line 248)
- Create: `templates/trade_form.html`
- Modify: `tests/test_app.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_trade_from_form_valid():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("source", "yfinance"),
        ("shares", "20"), ("buy_price", "42.10"), ("buy_date", "2026-01-15"),
        ("sell_price", "67.80"), ("sell_date", "2026-04-10"),
    ])
    trade, error = _trade_from_form(form)
    assert error is None
    assert trade["ticker"] == "WDC"
    assert trade["shares"] == 20
    assert trade["buy_price"] == 42.10
    assert trade["sell_price"] == 67.80
    assert trade["buy_date"] == "2026-01-15"
    assert trade["sell_date"] == "2026-04-10"
    assert trade["source"] == "yfinance"
    assert "id" in trade
    assert "created_at" in trade


def test_trade_from_form_shares_optional():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "AAPL"), ("source", "yfinance"),
        ("buy_price", "150.0"), ("buy_date", "2026-01-01"),
        ("sell_price", "160.0"), ("sell_date", "2026-02-01"),
    ])
    trade, error = _trade_from_form(form)
    assert error is None
    assert trade["shares"] is None


def test_trade_from_form_missing_ticker():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", ""), ("buy_price", "42.0"), ("buy_date", "2026-01-01"),
        ("sell_price", "50.0"), ("sell_date", "2026-02-01"),
    ])
    _, error = _trade_from_form(form)
    assert error == "Ticker is required"


def test_trade_from_form_missing_sell_price():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("buy_price", "42.0"), ("buy_date", "2026-01-01"),
        ("sell_price", ""), ("sell_date", "2026-02-01"),
    ])
    _, error = _trade_from_form(form)
    assert error == "Sell price is required"


def test_trade_from_form_missing_buy_date():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("buy_price", "42.0"), ("buy_date", ""),
        ("sell_price", "50.0"), ("sell_date", "2026-02-01"),
    ])
    _, error = _trade_from_form(form)
    assert error == "Buy date is required"


def test_trade_from_form_preserves_id_on_edit():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    existing = {"id": "abc12345", "created_at": "2026-01-01T00:00:00+00:00"}
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("source", "yfinance"),
        ("buy_price", "42.0"), ("buy_date", "2026-01-01"),
        ("sell_price", "50.0"), ("sell_date", "2026-02-01"),
    ])
    trade, error = _trade_from_form(form, existing=existing)
    assert error is None
    assert trade["id"] == "abc12345"
    assert trade["created_at"] == "2026-01-01T00:00:00+00:00"


def test_create_trade_via_post(client, tmp_path, monkeypatch):
    import app as app_module
    trades_file = tmp_path / "trades.json"
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/trade/new", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "20", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "67.80", "sell_date": "2026-04-10",
    })
    assert resp.status_code == 302
    assert "tab=history" in resp.headers["Location"]
    saved = json.loads(trades_file.read_text())
    assert len(saved) == 1
    assert saved[0]["ticker"] == "WDC"


def test_edit_trade_via_post(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [{"id": "tr1", "ticker": "WDC", "source": "yfinance", "shares": 20,
               "buy_price": 42.10, "buy_date": "2026-01-15",
               "sell_price": 67.80, "sell_date": "2026-04-10",
               "created_at": "2026-04-10T00:00:00+00:00"}]
    trades_file = tmp_path / "trades_edit.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/trade/tr1/edit", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "25", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "70.00", "sell_date": "2026-04-11",
    })
    assert resp.status_code == 302
    saved = json.loads(trades_file.read_text())
    assert saved[0]["shares"] == 25
    assert saved[0]["sell_price"] == 70.00


def test_delete_trade(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [{"id": "tr2", "ticker": "AAPL", "source": "yfinance", "shares": None,
               "buy_price": 150.0, "buy_date": "2026-01-01",
               "sell_price": 160.0, "sell_date": "2026-02-01",
               "created_at": "2026-02-01T00:00:00+00:00"}]
    trades_file = tmp_path / "trades_del.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/trade/tr2/delete")
    assert resp.status_code == 302
    saved = json.loads(trades_file.read_text())
    assert saved == []


def test_trade_routes_require_login(client):
    assert client.post("/trade/new").status_code == 302
    assert client.post("/trade/abc/delete").status_code == 302
```

- [ ] **Step 2: Run to confirm they fail**

```
py -m pytest tests/test_app.py::test_trade_from_form_valid tests/test_app.py::test_trade_from_form_shares_optional tests/test_app.py::test_trade_from_form_missing_ticker tests/test_app.py::test_trade_from_form_missing_sell_price tests/test_app.py::test_trade_from_form_missing_buy_date tests/test_app.py::test_trade_from_form_preserves_id_on_edit tests/test_app.py::test_create_trade_via_post tests/test_app.py::test_edit_trade_via_post tests/test_app.py::test_delete_trade tests/test_app.py::test_trade_routes_require_login -v
```

Expected: all 10 FAILED (routes/functions don't exist yet)

- [ ] **Step 3: Add trades infrastructure and _trade_from_form to app.py**

In `app.py`, after `_ALARMS_PATH = checker.get_alarms_path()` (line 30), add:

```python
_TRADES_PATH = checker.get_trades_path()
```

After the `modify_alarms` function (after line 56), add:

```python
def _trades_path():
    return _TRADES_PATH


def read_trades():
    with _lock:
        path = _trades_path()
        return checker.load_trades(path)


def write_trades(trades):
    with _lock:
        path = _trades_path()
        checker.save_trades(trades, path)


def modify_trades(fn):
    """Read trades, apply fn(trades), write back — all under a single lock."""
    with _lock:
        path = _trades_path()
        trades = checker.load_trades(path)
        fn(trades)
        checker.save_trades(trades, path)
```

At the end of `app.py`, before `if __name__ == "__main__":`, add `_trade_from_form`:

```python
def _trade_from_form(form, existing=None):
    """Parse and validate trade form data. Returns (trade_dict, error_str_or_None)."""
    import uuid

    ticker = form.get("ticker", "").strip()
    if not ticker:
        return None, "Ticker is required"

    source = form.get("source", "yfinance")

    shares_raw = form.get("shares", "").strip()
    if shares_raw:
        try:
            shares = int(shares_raw)
        except ValueError:
            return None, "Shares must be a whole number"
    else:
        shares = None

    buy_price_raw = form.get("buy_price", "").strip()
    sell_price_raw = form.get("sell_price", "").strip()
    try:
        buy_price = float(buy_price_raw) if buy_price_raw else None
        sell_price = float(sell_price_raw) if sell_price_raw else None
    except ValueError:
        return None, "Prices must be numbers"
    if buy_price is None:
        return None, "Buy price is required"
    if sell_price is None:
        return None, "Sell price is required"

    buy_date = form.get("buy_date", "").strip()
    sell_date = form.get("sell_date", "").strip()
    if not buy_date:
        return None, "Buy date is required"
    if not sell_date:
        return None, "Sell date is required"

    return {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "ticker": ticker,
        "source": source,
        "shares": shares,
        "buy_price": buy_price,
        "buy_date": buy_date,
        "sell_price": sell_price,
        "sell_date": sell_date,
        "created_at": existing["created_at"] if existing else datetime.now(timezone.utc).isoformat(),
    }, None
```

- [ ] **Step 4: Add trade CRUD routes to app.py**

After the `alarm_toggle_owned` route (after line 247), insert:

```python
@app.route("/trade/new", methods=["GET", "POST"])
@login_required
def trade_new():
    if request.method == "POST":
        trade, error = _trade_from_form(request.form)
        if error:
            return render_template("trade_form.html", error=error, form=request.form, title="Add Trade")
        def do_append(trades):
            trades.append(trade)
        modify_trades(do_append)
        return redirect(url_for("dashboard", tab="history"))
    return render_template("trade_form.html", form={}, title="Add Trade")


@app.route("/trade/<trade_id>/edit", methods=["GET", "POST"])
@login_required
def trade_edit(trade_id):
    trades = read_trades()
    trade = next((t for t in trades if t.get("id") == trade_id), None)
    if trade is None:
        return redirect(url_for("dashboard", tab="history"))
    if request.method == "POST":
        updated, error = _trade_from_form(request.form, existing=trade)
        if error:
            return render_template("trade_form.html", error=error, form=request.form,
                                   trade=trade, title="Edit Trade")
        def do_update(trades):
            for i, t in enumerate(trades):
                if t.get("id") == trade_id:
                    trades[i] = updated
                    break
        modify_trades(do_update)
        return redirect(url_for("dashboard", tab="history"))
    return render_template("trade_form.html", form=dict(trade), trade=trade, title="Edit Trade")


@app.route("/trade/<trade_id>/delete", methods=["POST"])
@login_required
def trade_delete(trade_id):
    def do_delete(trades):
        trades[:] = [t for t in trades if t.get("id") != trade_id]
    modify_trades(do_delete)
    return redirect(url_for("dashboard", tab="history"))
```

- [ ] **Step 5: Create templates/trade_form.html**

```html
{% extends "base.html" %}
{% block content %}
<div class="form-card">
    <h2>{{ title }}</h2>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post">
        <input type="hidden" name="source" value="{{ form.get('source') or 'yfinance' }}">

        <label>Ticker / Stock name *
            <input type="text" name="ticker"
                value="{{ form.get('ticker') or '' }}"
                placeholder="e.g. AAPL"
                {% if trade %}readonly{% endif %}>
        </label>

        <label>Number of shares — optional
            <input type="number" step="1" min="1" name="shares"
                value="{{ form.get('shares') or '' }}"
                placeholder="e.g. 20">
        </label>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem">
            <label>Buy Price *
                <input type="number" step="0.01" name="buy_price"
                    value="{{ form.get('buy_price') or '' }}"
                    placeholder="e.g. 42.10">
            </label>
            <label>Buy Date *
                <input type="date" name="buy_date"
                    value="{{ form.get('buy_date') or '' }}">
            </label>
            <label>Sell Price *
                <input type="number" step="0.01" name="sell_price"
                    value="{{ form.get('sell_price') or '' }}"
                    placeholder="e.g. 67.80">
            </label>
            <label>Sell Date *
                <input type="date" name="sell_date"
                    value="{{ form.get('sell_date') or '' }}">
            </label>
        </div>

        {% if is_record_sale %}
        <label class="checkbox-label">
            <input type="checkbox" name="delete_alarm">
            Delete alarm after saving
        </label>
        {% endif %}

        <div class="form-actions">
            <button type="submit" class="btn btn-primary">Save Trade</button>
            <a href="{{ url_for('dashboard', tab='history') }}" class="btn">Cancel</a>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 6: Run the trade tests — expect all 10 to pass**

```
py -m pytest tests/test_app.py::test_trade_from_form_valid tests/test_app.py::test_trade_from_form_shares_optional tests/test_app.py::test_trade_from_form_missing_ticker tests/test_app.py::test_trade_from_form_missing_sell_price tests/test_app.py::test_trade_from_form_missing_buy_date tests/test_app.py::test_trade_from_form_preserves_id_on_edit tests/test_app.py::test_create_trade_via_post tests/test_app.py::test_edit_trade_via_post tests/test_app.py::test_delete_trade tests/test_app.py::test_trade_routes_require_login -v
```

Expected: 10 PASSED

- [ ] **Step 7: Run the full test suite to check for regressions**

```
py -m pytest tests/ -v
```

Expected: all previously-passing tests still pass

- [ ] **Step 8: Commit**

```bash
git add app.py templates/trade_form.html tests/test_app.py
git commit -m "feat: add trade CRUD routes and trade_form template"
```

---

## Task 4: Record Sale route + button on owned alarm cards

**Files:**
- Modify: `app.py` (add after `trade_delete` route)
- Modify: `templates/dashboard.html` (add Record Sale button to owned alarm cards)
- Modify: `tests/test_app.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_record_sale_get_prefills_from_alarm(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "rs1", "ticker": "WDC", "source": "yfinance", "owned": True,
               "initial_price": 42.10, "shares": 20,
               "created_at": "2026-01-15T10:00:00+00:00",
               "enabled": True, "upper_limit": 280.0, "lower_limit": None,
               "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_rs.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.get("/alarm/rs1/record-sale")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "WDC" in body
    assert "42.1" in body
    assert "2026-01-15" in body


def test_record_sale_post_saves_trade(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "rs2", "ticker": "WDC", "source": "yfinance", "owned": True,
               "initial_price": 42.10, "shares": 20,
               "created_at": "2026-01-15T10:00:00+00:00",
               "enabled": True, "upper_limit": 280.0, "lower_limit": None,
               "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_rs2.json"
    alarms_file.write_text(json.dumps(alarms))
    trades_file = tmp_path / "trades_rs2.json"
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/alarm/rs2/record-sale", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "20", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "67.80", "sell_date": "2026-04-10",
    })
    assert resp.status_code == 302
    assert "tab=history" in resp.headers["Location"]
    saved = json.loads(trades_file.read_text())
    assert len(saved) == 1
    assert saved[0]["ticker"] == "WDC"
    # Alarm is NOT deleted (checkbox not checked)
    alarms_saved = json.loads(alarms_file.read_text())
    assert len(alarms_saved) == 1


def test_record_sale_post_deletes_alarm_when_checked(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "rs3", "ticker": "WDC", "source": "yfinance", "owned": True,
               "initial_price": 42.10, "shares": 20,
               "created_at": "2026-01-15T10:00:00+00:00",
               "enabled": True, "upper_limit": 280.0, "lower_limit": None,
               "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_rs3.json"
    alarms_file.write_text(json.dumps(alarms))
    trades_file = tmp_path / "trades_rs3.json"
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/alarm/rs3/record-sale", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "20", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "67.80", "sell_date": "2026-04-10",
        "delete_alarm": "on",
    })
    assert resp.status_code == 302
    alarms_saved = json.loads(alarms_file.read_text())
    assert alarms_saved == []


def test_record_sale_requires_login(client):
    resp = client.get("/alarm/any/record-sale")
    assert resp.status_code == 302
    assert "dashboard" not in resp.headers.get("Location", "")
```

- [ ] **Step 2: Run to confirm they fail**

```
py -m pytest tests/test_app.py::test_record_sale_get_prefills_from_alarm tests/test_app.py::test_record_sale_post_saves_trade tests/test_app.py::test_record_sale_post_deletes_alarm_when_checked tests/test_app.py::test_record_sale_requires_login -v
```

Expected: 4 FAILED (route doesn't exist yet)

- [ ] **Step 3: Add record-sale route to app.py**

After the `trade_delete` route, insert:

```python
@app.route("/alarm/<alarm_id>/record-sale", methods=["GET", "POST"])
@login_required
def alarm_record_sale(alarm_id):
    alarms = read_alarms()
    alarm = next((a for a in alarms if a.get("id") == alarm_id), None)
    if alarm is None:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        trade, error = _trade_from_form(request.form)
        if error:
            return render_template("trade_form.html", error=error, form=request.form,
                                   title="Record Sale", is_record_sale=True)
        def do_append(trades):
            trades.append(trade)
        modify_trades(do_append)
        if request.form.get("delete_alarm") == "on":
            def do_delete(alarms):
                alarms[:] = [a for a in alarms if a.get("id") != alarm_id]
            modify_alarms(do_delete)
        return redirect(url_for("dashboard", tab="history"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    buy_date = (alarm.get("created_at") or "")[:10] or today
    form_data = {
        "ticker": alarm.get("ticker", ""),
        "source": alarm.get("source", "yfinance"),
        "shares": alarm.get("shares") or "",
        "buy_price": alarm.get("initial_price") or "",
        "buy_date": buy_date,
        "sell_price": "",
        "sell_date": today,
    }
    return render_template("trade_form.html", form=form_data, title="Record Sale",
                           is_record_sale=True, alarm=alarm)
```

- [ ] **Step 4: Add Record Sale button to dashboard.html**

In `templates/dashboard.html`, in the `card-actions` div (currently lines 125–131):

```html
    <div class="card-actions">
        <a href="/alarm/{{ alarm.id }}/edit?sort={{ sort }}&owned={{ owned_filter }}" class="btn">Edit</a>
        <form method="post" action="/alarm/{{ alarm.id }}/delete" style="display:inline"
              onsubmit="return confirm('Delete {{ alarm.ticker }} alarm?')">
            <button type="submit" class="btn btn-danger">Delete</button>
        </form>
        {% if alarm.get('owned') %}
        <a href="/alarm/{{ alarm.id }}/record-sale" class="btn" style="margin-left:auto">Record Sale</a>
        {% endif %}
    </div>
```

- [ ] **Step 5: Run the record-sale tests — expect all 4 to pass**

```
py -m pytest tests/test_app.py::test_record_sale_get_prefills_from_alarm tests/test_app.py::test_record_sale_post_saves_trade tests/test_app.py::test_record_sale_post_deletes_alarm_when_checked tests/test_app.py::test_record_sale_requires_login -v
```

Expected: 4 PASSED

- [ ] **Step 6: Run the full test suite to check for regressions**

```
py -m pytest tests/ -v
```

Expected: all previously-passing tests still pass

- [ ] **Step 7: Commit**

```bash
git add app.py templates/dashboard.html tests/test_app.py
git commit -m "feat: add record-sale route and button on owned alarm cards"
```

---

## Task 5: Dashboard tab UI (tab bar + history tab)

**Files:**
- Modify: `app.py` (dashboard route, lines 93–167)
- Modify: `templates/dashboard.html`
- Modify: `tests/test_app.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_dashboard_history_tab_shows_trades(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [{"id": "dt1", "ticker": "WDC", "source": "yfinance", "shares": 20,
               "buy_price": 42.10, "buy_date": "2026-01-15",
               "sell_price": 67.80, "sell_date": "2026-04-10",
               "created_at": "2026-04-10T00:00:00+00:00"}]
    trades_file = tmp_path / "trades_dash.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.get("/dashboard?tab=history")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "WDC" in body
    assert "67" in body  # sell price


def test_dashboard_history_tab_shows_summary(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [
        {"id": "dt2", "ticker": "WDC", "source": "yfinance", "shares": 10,
         "buy_price": 40.0, "buy_date": "2026-01-01",
         "sell_price": 60.0, "sell_date": "2026-03-01",
         "created_at": "2026-03-01T00:00:00+00:00"},
        {"id": "dt3", "ticker": "AAPL", "source": "yfinance", "shares": None,
         "buy_price": 150.0, "buy_date": "2026-01-01",
         "sell_price": 165.0, "sell_date": "2026-03-15",
         "created_at": "2026-03-15T00:00:00+00:00"},
    ]
    trades_file = tmp_path / "trades_sum.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.get("/dashboard?tab=history")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Summary: 2 trades, WDC is best (+50%)
    assert "2" in body
    assert "WDC" in body


def test_dashboard_alarms_tab_does_not_load_trades(client, tmp_path, monkeypatch):
    import app as app_module
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    # Default tab=alarms — should not try to read trades at all (no trades file patched)
    resp = client.get("/dashboard")
    assert resp.status_code == 200


def test_dashboard_tab_bar_rendered(client, tmp_path, monkeypatch):
    import app as app_module
    trades_file = tmp_path / "trades_tabs.json"
    trades_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.get("/dashboard?tab=history")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Sell History" in body
    assert "Alarms" in body
```

- [ ] **Step 2: Run to confirm they fail**

```
py -m pytest tests/test_app.py::test_dashboard_history_tab_shows_trades tests/test_app.py::test_dashboard_history_tab_shows_summary tests/test_app.py::test_dashboard_alarms_tab_does_not_load_trades tests/test_app.py::test_dashboard_tab_bar_rendered -v
```

Expected: 4 FAILED (tab param not handled yet)

- [ ] **Step 3: Update the dashboard route in app.py**

Replace the entire `dashboard` function (lines 93–167) with:

```python
@app.route("/dashboard")
@login_required
def dashboard():
    tab = request.args.get("tab", "alarms")

    # --- History tab ---
    if tab == "history":
        trades = read_trades()
        pct_changes = [
            (t["sell_price"] - t["buy_price"]) / t["buy_price"] * 100
            for t in trades
        ]
        pl_values = [
            (t["sell_price"] - t["buy_price"]) * t["shares"]
            for t in trades if t.get("shares")
        ]
        avg_pct = sum(pct_changes) / len(pct_changes) if pct_changes else None
        best = max(
            trades,
            key=lambda t: (t["sell_price"] - t["buy_price"]) / t["buy_price"] * 100,
            default=None,
        )
        summary = {
            "count": len(trades),
            "total_pl": sum(pl_values) if pl_values else None,
            "avg_pct": avg_pct,
            "best_ticker": best["ticker"] if best else None,
            "best_pct": (best["sell_price"] - best["buy_price"]) / best["buy_price"] * 100
                        if best else None,
        }
        trade_pcts = {t["id"]: pct_changes[i] for i, t in enumerate(trades)}
        trade_pls = {
            t["id"]: (t["sell_price"] - t["buy_price"]) * t["shares"]
            if t.get("shares") else None
            for t in trades
        }
        return render_template("dashboard.html", tab=tab, trades=trades,
                               summary=summary, trade_pcts=trade_pcts,
                               trade_pls=trade_pls)

    # --- Alarms tab ---
    alarms = read_alarms()
    sort = request.args.get("sort", "newest")
    if sort == "oldest":
        alarms.sort(key=lambda a: a.get("created_at") or "")
    elif sort == "az":
        alarms.sort(key=lambda a: a.get("ticker", ""))
    else:
        alarms.sort(key=lambda a: a.get("created_at") or "", reverse=True)

    owned_filter = request.args.get("owned", "all")
    if owned_filter == "owned":
        alarms = [a for a in alarms if a.get("owned", False)]
    elif owned_filter == "watching":
        alarms = [a for a in alarms if not a.get("owned", False)]

    prices = {}
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

    triggered = {}
    distances = {}
    price_changes = {}
    for alarm in alarms:
        alarm_id = alarm.get("id")
        ticker = alarm.get("ticker")
        price = prices.get(ticker)
        initial = alarm.get("initial_price")
        price_changes[alarm_id] = (price - initial) / initial * 100 if (price and initial) else None
        if price is None:
            triggered[alarm_id] = False
            distances[alarm_id] = None
            continue
        is_pct = alarm.get("upper_pct") is not None or alarm.get("lower_pct") is not None
        if is_pct:
            base = alarm.get("base_price")
            if base is None:
                triggered[alarm_id] = False
                distances[alarm_id] = None
            else:
                t, _, actual_pct = checker.condition_met_pct(alarm, price)
                triggered[alarm_id] = t
                parts = []
                if alarm.get("upper_pct") is not None:
                    rem = alarm["upper_pct"] - actual_pct
                    parts.append(f"↑ triggered" if rem <= 0 else f"↑ {rem:.1f}% to go")
                if alarm.get("lower_pct") is not None:
                    rem = alarm["lower_pct"] + actual_pct
                    parts.append(f"↓ triggered" if rem <= 0 else f"↓ {rem:.1f}% to go")
                distances[alarm_id] = " · ".join(parts) or None
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

    return render_template("dashboard.html", tab=tab, alarms=alarms, prices=prices,
                           sort=sort, triggered=triggered, distances=distances,
                           price_changes=price_changes, owned_filter=owned_filter)
```

- [ ] **Step 4: Update dashboard.html — add tab bar and history tab content**

Replace the entire contents of `templates/dashboard.html` with:

```html
{% extends "base.html" %}
{% block content %}
<div class="toolbar">
    <h2>Alarms</h2>
    {% if tab != 'history' %}
    <a href="{{ url_for('alarm_new') }}" class="btn btn-primary">+ Add</a>
    {% endif %}
</div>

{# ── Tab bar ── #}
<div class="tab-bar">
    <a href="{{ url_for('dashboard') }}"
       class="tab {% if tab != 'history' %}tab-active{% endif %}">Alarms</a>
    <a href="{{ url_for('dashboard', tab='history') }}"
       class="tab {% if tab == 'history' %}tab-active{% endif %}">Sell History</a>
    {% if tab == 'history' %}
    <a href="{{ url_for('trade_new') }}" class="btn btn-primary" style="margin-left:auto">+ Add Trade</a>
    {% endif %}
</div>

{% if tab == 'history' %}
{# ══════════════════════════════════════════════════
   SELL HISTORY TAB
══════════════════════════════════════════════════ #}

{# Summary card #}
<div class="history-summary">
    <div class="history-stat">
        <div class="history-stat-label">Trades</div>
        <div class="history-stat-value">{{ summary.count }}</div>
    </div>
    <div class="history-stat">
        <div class="history-stat-label">Total P&amp;L</div>
        {% if summary.total_pl is not none %}
        <div class="history-stat-value {% if summary.total_pl >= 0 %}value-positive{% else %}value-negative{% endif %}">
            {{ "%+.2f"|format(summary.total_pl) }}
        </div>
        {% else %}
        <div class="history-stat-value">—</div>
        {% endif %}
    </div>
    <div class="history-stat">
        <div class="history-stat-label">Avg Return</div>
        {% if summary.avg_pct is not none %}
        <div class="history-stat-value {% if summary.avg_pct >= 0 %}value-positive{% else %}value-negative{% endif %}">
            {{ "%+.1f"|format(summary.avg_pct) }}%
        </div>
        {% else %}
        <div class="history-stat-value">—</div>
        {% endif %}
    </div>
    <div class="history-stat">
        <div class="history-stat-label">Best Trade</div>
        {% if summary.best_ticker %}
        <div class="history-stat-value value-positive">
            {{ "%+.1f"|format(summary.best_pct) }}% {{ summary.best_ticker }}
        </div>
        {% else %}
        <div class="history-stat-value">—</div>
        {% endif %}
    </div>
</div>

{% if trades %}
<div class="history-table-wrap">
<table class="history-table">
    <thead>
        <tr>
            <th>Stock</th>
            <th>Shares</th>
            <th>Buy Price</th>
            <th>Buy Date</th>
            <th>Sell Price</th>
            <th>Sell Date</th>
            <th>% Change</th>
            <th>Total P&amp;L</th>
            <th></th>
        </tr>
    </thead>
    <tbody>
    {% for trade in trades %}
    {% set curr = '₪' if trade.get('source') == 'tase' else '$' %}
    {% set pct = trade_pcts.get(trade.id) %}
    {% set pl = trade_pls.get(trade.id) %}
    <tr>
        <td class="trade-ticker">{{ trade.ticker }}</td>
        <td>{{ trade.shares if trade.shares else '—' }}</td>
        <td>{{ curr }}{{ "%.2f"|format(trade.buy_price) }}</td>
        <td>{{ trade.buy_date }}</td>
        <td>{{ curr }}{{ "%.2f"|format(trade.sell_price) }}</td>
        <td>{{ trade.sell_date }}</td>
        <td class="{% if pct >= 0 %}value-positive{% else %}value-negative{% endif %}">
            {{ "%+.1f"|format(pct) }}%
        </td>
        <td>
            {% if pl is not none %}
            <span class="{% if pl >= 0 %}value-positive{% else %}value-negative{% endif %}">
                {{ curr }}{{ "%+.2f"|format(pl) }}
            </span>
            {% else %}—{% endif %}
        </td>
        <td class="trade-actions">
            <a href="{{ url_for('trade_edit', trade_id=trade.id) }}" class="btn">Edit</a>
            <form method="post" action="{{ url_for('trade_delete', trade_id=trade.id) }}"
                  style="display:inline"
                  onsubmit="return confirm('Delete {{ trade.ticker }} trade?')">
                <button type="submit" class="btn btn-danger">Delete</button>
            </form>
        </td>
    </tr>
    {% endfor %}
    </tbody>
</table>
</div>
{% else %}
<p class="empty">No trades yet. <a href="{{ url_for('trade_new') }}">Add one</a>.</p>
{% endif %}

{% else %}
{# ══════════════════════════════════════════════════
   ALARMS TAB
══════════════════════════════════════════════════ #}

<div class="sort-controls">
    <a href="{{ url_for('dashboard', sort='newest', owned=owned_filter if owned_filter != 'all' else None) }}"
       class="btn {% if sort == 'newest' %}btn-primary{% endif %}">Newest</a>
    <a href="{{ url_for('dashboard', sort='oldest', owned=owned_filter if owned_filter != 'all' else None) }}"
       class="btn {% if sort == 'oldest' %}btn-primary{% endif %}">Oldest</a>
    <a href="{{ url_for('dashboard', sort='az', owned=owned_filter if owned_filter != 'all' else None) }}"
       class="btn {% if sort == 'az' %}btn-primary{% endif %}">A–Z</a>
    <span class="sort-sep">|</span>
    <a href="{{ url_for('dashboard', sort=sort) }}"
       class="btn {% if owned_filter == 'all' %}btn-primary{% endif %}">All</a>
    <a href="{{ url_for('dashboard', sort=sort, owned='owned') }}"
       class="btn {% if owned_filter == 'owned' %}btn-primary{% endif %}">Owned</a>
    <a href="{{ url_for('dashboard', sort=sort, owned='watching') }}"
       class="btn {% if owned_filter == 'watching' %}btn-primary{% endif %}">Watching</a>
</div>

<div class="search-bar">
    <input type="text" id="alarm-search" placeholder="Filter by ticker…" autocomplete="off">
</div>

{% for alarm in alarms %}
{% set is_triggered = triggered.get(alarm.id, false) %}
{% set curr = '₪' if alarm.get('source') == 'tase' else '$' %}
<div class="card {% if not alarm.enabled %}card-disabled{% endif %} {% if is_triggered %}card-triggered{% endif %}"
     data-ticker="{{ alarm.ticker }}">
    <div class="card-header">
        <span class="ticker">
            {{ alarm.ticker }}
            {% if is_triggered %}<span class="triggered-badge">FIRING</span>{% endif %}
        </span>
        <form method="post" action="/alarm/{{ alarm.id }}/toggle" style="display:inline">
            <button type="submit" class="toggle {{ 'toggle-on' if alarm.enabled else 'toggle-off' }}">
                {{ "ON" if alarm.enabled else "OFF" }}
            </button>
        </form>
        <form method="post" action="/alarm/{{ alarm.id }}/toggle-owned?sort={{ sort }}&owned={{ owned_filter }}" style="display:inline">
            <button type="submit" class="btn btn-owned {% if alarm.get('owned') %}btn-owned-yes{% else %}btn-owned-no{% endif %}">
                {{ "Owned" if alarm.get('owned') else "Watching" }}
            </button>
        </form>
    </div>
    <div class="card-body">
        <div class="condition">
            {% if alarm.get('upper_pct') or alarm.get('lower_pct') %}
                {% if alarm.get('upper_pct') and alarm.get('lower_pct') %}
                    ↑{{ alarm.upper_pct }}% / ↓{{ alarm.lower_pct }}%
                {% elif alarm.get('upper_pct') %}
                    ↑ {{ alarm.upper_pct }}%
                {% else %}
                    ↓ {{ alarm.lower_pct }}%
                {% endif %}
            {% else %}
                {% if alarm.get('upper_limit') %}↑ {{ curr }}{{ "%.2f"|format(alarm.upper_limit) }}{% endif %}
                {% if alarm.get('lower_limit') %}↓ {{ curr }}{{ "%.2f"|format(alarm.lower_limit) }}{% endif %}
            {% endif %}
        </div>
        <div class="price-col">
            <div class="price">
                {% if prices.get(alarm.ticker) is not none %}
                    {{ curr }}{{ "%.2f"|format(prices[alarm.ticker]) }}
                {% else %}
                    unavailable
                {% endif %}
            </div>
            {% set pc = price_changes.get(alarm.id) %}
            {% if pc is not none %}
            <div class="price-change {% if pc >= 0 %}price-change-up{% else %}price-change-down{% endif %}">
                {{ "%+.1f"|format(pc) }}% since created
            </div>
            {% endif %}
        </div>
        {% set dist = distances.get(alarm.id) %}
        {% if dist %}
        <div class="distance {% if is_triggered %}distance-triggered{% endif %}">{{ dist }}</div>
        {% endif %}
        <div class="last-triggered">
            Last alert: {{ alarm.last_triggered[:10] if alarm.last_triggered else "Never" }}
        </div>
        <div class="card-meta">
            Created: {% if alarm.get('created_at') %}{{ alarm.created_at[:10] }}{% else %}N/A{% endif %}
            &middot;
            Initial: {% if alarm.get('initial_price') is not none %}{{ curr }}{{ "%.2f"|format(alarm.initial_price) }}{% else %}N/A{% endif %}
            &middot;
            Cooldown: {% set sh = alarm.get('snooze_hours', 72) %}
            {% if sh < 24 %}{{ sh }}h{% elif sh == 24 %}1 day{% elif sh == 72 %}3 days{% elif sh == 168 %}1 week{% else %}{{ sh }}h{% endif %}
        </div>
    </div>
    {% if alarm.get('notes') %}
    <div class="card-notes">{{ alarm.notes }}</div>
    {% endif %}
    <div class="chart-controls">
        <button class="btn chart-period-btn active" data-period="5d" data-alarm="{{ alarm.id }}">1W</button>
        <button class="btn chart-period-btn" data-period="1mo" data-alarm="{{ alarm.id }}">1M</button>
        <button class="btn chart-period-btn" data-period="1y" data-alarm="{{ alarm.id }}">1Y</button>
    </div>
    <div class="card-chart">
        <canvas id="chart-{{ alarm.id }}" height="160"></canvas>
    </div>
    <details class="card-history">
        <summary>History</summary>
        {% if alarm.get('history') %}
        <ul class="history-list">
            {% for entry in alarm.history|reverse %}
            <li>
                {{ entry.triggered_at[:10] }} —
                {% if entry.type in ('upper_limit', 'lower_limit', 'upper', 'lower') %}
                    {{ entry.type.replace('_', ' ') }} {{ curr }}{{ "%.2f"|format(entry.threshold) }} hit at {{ curr }}{{ "%.2f"|format(entry.price) }}
                {% else %}
                    {{ entry.type.replace('_', ' ') }} {{ "%.1f"|format(entry.threshold) }}% at {{ curr }}{{ "%.2f"|format(entry.price) }}
                {% endif %}
            </li>
            {% endfor %}
        </ul>
        {% else %}
        <p class="history-empty">No alerts sent yet.</p>
        {% endif %}
    </details>
    <div class="card-actions">
        <a href="/alarm/{{ alarm.id }}/edit?sort={{ sort }}&owned={{ owned_filter }}" class="btn">Edit</a>
        <form method="post" action="/alarm/{{ alarm.id }}/delete" style="display:inline"
              onsubmit="return confirm('Delete {{ alarm.ticker }} alarm?')">
            <button type="submit" class="btn btn-danger">Delete</button>
        </form>
        {% if alarm.get('owned') %}
        <a href="/alarm/{{ alarm.id }}/record-sale" class="btn" style="margin-left:auto">Record Sale</a>
        {% endif %}
    </div>
</div>
{% else %}
<p class="empty">No alarms yet. <a href="{{ url_for('alarm_new') }}">Add one</a>.</p>
{% endfor %}
{% endif %}
{% endblock %}

{% block scripts %}
{% if tab != 'history' %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
const _charts = {};

function _renderChart(alarmId, period) {
    const periodLabel = {'5d': '1W', '1mo': '1M', '1y': '1Y'}[period] || '1W';
    fetch('/alarm/' + alarmId + '/chart-data?period=' + period)
        .then(r => r.json())
        .then(data => {
            if (data.error) return;
            const prices = data.prices;
            const high = Math.max(...prices);
            const low = Math.min(...prices);
            const firstPrice = prices[0];
            const pctMin = (low - firstPrice) / firstPrice * 100;
            const pctMax = (high - firstPrice) / firstPrice * 100;
            if (_charts[alarmId]) { _charts[alarmId].destroy(); }
            _charts[alarmId] = new Chart(document.getElementById('chart-' + alarmId), {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: 'Price',
                            data: prices,
                            borderColor: '#d4922a',
                            borderWidth: 1.5,
                            pointRadius: 0,
                            fill: false,
                            tension: 0.1,
                        },
                        {
                            label: periodLabel + ' High: $' + high.toFixed(2),
                            data: prices.map(() => high),
                            borderColor: '#22c55e',
                            borderWidth: 1,
                            borderDash: [6, 3],
                            pointRadius: 0,
                            fill: false,
                        },
                        {
                            label: periodLabel + ' Low: $' + low.toFixed(2),
                            data: prices.map(() => low),
                            borderColor: '#ef4444',
                            borderWidth: 1,
                            borderDash: [6, 3],
                            pointRadius: 0,
                            fill: false,
                        },
                    ]
                },
                options: {
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: { boxWidth: 12, font: { size: 11 }, color: '#f5e6d3' },
                        }
                    },
                    scales: {
                        x: {
                            display: true,
                            ticks: {
                                maxTicksLimit: 5,
                                maxRotation: 0,
                                font: { size: 10 },
                                color: '#c8a07a',
                                callback: function(val, idx) {
                                    const label = this.getLabelForValue(val);
                                    return label ? label.slice(5) : '';
                                }
                            },
                            grid: { display: false },
                        },
                        y: {
                            display: true,
                            min: low,
                            max: high,
                            ticks: {
                                maxTicksLimit: 4,
                                font: { size: 10 },
                                color: '#c8a07a',
                                callback: val => '$' + val.toFixed(0),
                            },
                            grid: { color: 'rgba(255,255,255,0.07)' },
                        },
                        y2: {
                            display: true,
                            position: 'right',
                            min: pctMin,
                            max: pctMax,
                            afterBuildTicks: axis => {
                                axis.ticks.push({ value: pctMin }, { value: pctMax });
                                const seen = new Set();
                                axis.ticks = axis.ticks
                                    .filter(t => { const k = t.value.toFixed(1); return seen.has(k) ? false : seen.add(k); })
                                    .sort((a, b) => a.value - b.value);
                            },
                            ticks: {
                                maxTicksLimit: 6,
                                font: { size: 10 },
                                color: '#c8a07a',
                                callback: val => (val >= 0 ? '+' : '') + val.toFixed(1) + '%',
                            },
                            grid: { display: false },
                        }
                    },
                    animation: false,
                }
            });
        })
        .catch(() => {});
}

{% for alarm in alarms %}
_renderChart('{{ alarm.id }}', '5d');
{% endfor %}

document.querySelectorAll('.chart-period-btn').forEach(btn => {
    btn.addEventListener('click', function() {
        const alarmId = this.dataset.alarm;
        const period = this.dataset.period;
        document.querySelectorAll('.chart-period-btn[data-alarm="' + alarmId + '"]')
            .forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        _renderChart(alarmId, period);
    });
});

// Ticker search filter
document.getElementById('alarm-search').addEventListener('input', function() {
    const q = this.value.trim().toLowerCase();
    document.querySelectorAll('.card[data-ticker]').forEach(card => {
        const ticker = card.dataset.ticker.toLowerCase();
        card.style.display = (!q || ticker.includes(q)) ? '' : 'none';
    });
});
</script>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Add CSS for new classes to static/style.css**

Open `static/style.css` and append at the end:

```css
/* ── Tab bar ───────────────────────────────── */
.tab-bar {
    display: flex;
    align-items: center;
    gap: 4px;
    border-bottom: 2px solid #3a2a1a;
    margin-bottom: 1.25rem;
}
.tab {
    padding: 8px 20px;
    font-size: 0.9rem;
    border-radius: 6px 6px 0 0;
    border: 1px solid transparent;
    border-bottom: none;
    color: #d4922a;
    text-decoration: none;
    background: #2a1f0f;
}
.tab-active {
    background: #d4922a;
    color: #1a0f00;
    font-weight: 700;
    border-color: #3a2a1a;
}

/* ── History summary card ──────────────────── */
.history-summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 1.25rem;
}
.history-stat {
    background: #2a1f0f;
    border-radius: 8px;
    padding: 14px;
    text-align: center;
}
.history-stat-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #7a6a5a;
    margin-bottom: 6px;
}
.history-stat-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: #d4922a;
}
.value-positive { color: #22c55e; }
.value-negative { color: #ef4444; }

/* ── History table ─────────────────────────── */
.history-table-wrap {
    overflow-x: auto;
}
.history-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
}
.history-table thead tr {
    border-bottom: 1px solid #3a2a1a;
    color: #7a6a5a;
    text-align: left;
}
.history-table th,
.history-table td {
    padding: 10px 12px;
    white-space: nowrap;
}
.history-table tbody tr {
    border-bottom: 1px solid #2a1f0f;
    color: #c8a07a;
}
.history-table tbody tr:last-child {
    border-bottom: none;
}
.trade-ticker {
    font-weight: 700;
    color: #d4922a;
}
.trade-actions {
    display: flex;
    gap: 6px;
}
```

- [ ] **Step 6: Run the dashboard tab tests — expect all 4 to pass**

```
py -m pytest tests/test_app.py::test_dashboard_history_tab_shows_trades tests/test_app.py::test_dashboard_history_tab_shows_summary tests/test_app.py::test_dashboard_alarms_tab_does_not_load_trades tests/test_app.py::test_dashboard_tab_bar_rendered -v
```

Expected: 4 PASSED

- [ ] **Step 7: Run the full test suite — expect all tests to pass**

```
py -m pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add app.py templates/dashboard.html static/style.css tests/test_app.py
git commit -m "feat: add sell history tab to dashboard with summary card and trade table"
```

---

## Self-Review

**Spec coverage:**
- [x] Tab on dashboard (Alarms / Sell History) via `?tab=` param — Task 5
- [x] Summary card: trades count, total P&L, avg return, best trade — Task 5
- [x] Table: stock, shares, buy price, buy date, sell price, sell date, % change, total P&L, actions — Task 5
- [x] % change computed always; total P&L only when shares present — Task 5
- [x] Currency symbol from `source` field — Task 5
- [x] + Add Trade button → `/trade/new` — Task 3 + 5
- [x] Edit / Delete per trade row — Task 3 + 5
- [x] Record Sale button on owned alarm cards — Task 4
- [x] Record Sale form pre-filled from alarm (ticker, shares, buy_price, buy_date, today as sell_date) — Task 4
- [x] All pre-filled fields are editable — trade_form.html (Task 3)
- [x] "Delete alarm after saving" checkbox — Task 4
- [x] Shares field on alarm form, visible only when owned is checked — Task 2
- [x] `shares` stored in alarm dict — Task 2
- [x] `trades.json` persistence via `load_trades` / `save_trades` — Task 1
- [x] Railway `/data/trades.json` path — Task 1

**Placeholder scan:** No TBDs, no "similar to" references, no vague steps. All code blocks are complete.

**Type consistency:**
- `_trades_path` is a function (monkeypatchable), same as `_alarms_path` — consistent throughout
- `trade_pcts` and `trade_pls` are dicts keyed by `trade.id` — used correctly in template
- `_trade_from_form` returns `(trade_dict, error_or_None)` — same signature as `_alarm_from_form`
- `modify_trades(fn)` takes a function `fn(trades)` — same pattern as `modify_alarms`
