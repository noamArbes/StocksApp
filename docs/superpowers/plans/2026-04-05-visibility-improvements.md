# Visibility Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add alert history, creation metadata, alarm sorting, and multi-timeframe charts to the StocksApp dashboard.

**Architecture:** Extend each alarm in `alarms.json` with `created_at`, `initial_price`, and `history` fields. Sorting is server-side via a query parameter. Chart timeframes are handled by adding a `?period=` param to the existing chart endpoint and re-fetching in JS when the user clicks a period button.

**Tech Stack:** Python/Flask, Jinja2, Chart.js 4, yfinance, pytest

---

## File Map

| File | Changes |
|---|---|
| `app.py` | Add `datetime` import; update `chart_data`, `dashboard`, `_alarm_from_form` |
| `checker.py` | Append history entries after `send_email` in both alarm paths |
| `templates/dashboard.html` | Add sort buttons, card metadata, history section, chart period buttons, refactor chart JS |
| `static/style.css` | Add styles for sort controls, card metadata, history section, chart period buttons |
| `tests/test_app.py` | Add tests for period param, sorting, creation metadata |
| `tests/test_checker.py` | Add tests for history appending and capping |

---

## Task 1: Chart endpoint period parameter

**Files:**
- Modify: `app.py` (the `chart_data` function, lines 162–178)
- Modify: `tests/test_app.py` (add two tests at end of file)

- [ ] **Step 1: Write failing tests**

Add to the end of `tests/test_app.py`:

```python
def test_chart_data_accepts_valid_period(client, tmp_path, monkeypatch):
    import app as app_module
    import pandas as pd
    alarms = [{"id": "cp1", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_cp1.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    captured = {}
    import yfinance as yf
    class FakeTicker:
        def history(self, period):
            captured["period"] = period
            dates = pd.date_range("2026-01-01", periods=3, tz="UTC")
            return pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=dates)
    monkeypatch.setattr(yf, "Ticker", lambda t: FakeTicker())
    login(client)
    resp = client.get("/alarm/cp1/chart-data?period=1y")
    assert resp.status_code == 200
    assert captured["period"] == "1y"


def test_chart_data_invalid_period_falls_back_to_default(client, tmp_path, monkeypatch):
    import app as app_module
    import pandas as pd
    alarms = [{"id": "cp2", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_cp2.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    captured = {}
    import yfinance as yf
    class FakeTicker:
        def history(self, period):
            captured["period"] = period
            dates = pd.date_range("2026-01-01", periods=3, tz="UTC")
            return pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=dates)
    monkeypatch.setattr(yf, "Ticker", lambda t: FakeTicker())
    login(client)
    resp = client.get("/alarm/cp2/chart-data?period=badvalue")
    assert resp.status_code == 200
    assert captured["period"] == "1mo"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_app.py::test_chart_data_accepts_valid_period tests/test_app.py::test_chart_data_invalid_period_falls_back_to_default -v
```

Expected: FAIL (endpoint ignores period param)

- [ ] **Step 3: Update `chart_data` in `app.py`**

Replace the existing `chart_data` function (lines 162–178) with:

```python
@app.route("/alarm/<alarm_id>/chart-data")
@login_required
def chart_data(alarm_id):
    alarms = read_alarms()
    alarm = next((a for a in alarms if a.get("id") == alarm_id), None)
    if alarm is None:
        return jsonify({"error": "not found"}), 404
    ticker = alarm.get("ticker")
    period = request.args.get("period", "1mo")
    if period not in ("5d", "1mo", "1y"):
        period = "1mo"
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=period)
        labels = [str(d.date()) for d in hist.index]
        prices = [round(float(p), 2) for p in hist["Close"]]
        return jsonify({"labels": labels, "prices": prices})
    except Exception as e:
        app.logger.error(f"Chart data fetch failed for {ticker}: {e}")
        return jsonify({"error": "Could not fetch chart data"}), 500
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_app.py::test_chart_data_accepts_valid_period tests/test_app.py::test_chart_data_invalid_period_falls_back_to_default -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```
pytest tests/ -v
```

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: chart endpoint accepts period param (5d, 1mo, 1y)"
```

---

## Task 2: Dashboard sorting

**Files:**
- Modify: `app.py` (the `dashboard` function, lines 84–96)
- Modify: `templates/dashboard.html` (add sort buttons above alarm list)
- Modify: `static/style.css` (add `.sort-controls` styles)
- Modify: `tests/test_app.py` (add sorting tests)

- [ ] **Step 1: Write failing tests**

Add to the end of `tests/test_app.py`:

```python
def test_dashboard_sort_az(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [
        {"id": "s1", "ticker": "TSLA", "enabled": True, "upper_limit": 100.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-01T00:00:00+00:00"},
        {"id": "s2", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-02T00:00:00+00:00"},
    ]
    alarms_file = tmp_path / "alarms_sort.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard?sort=az")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert body.index("AAPL") < body.index("TSLA")


def test_dashboard_sort_oldest(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [
        {"id": "s3", "ticker": "TSLA", "enabled": True, "upper_limit": 100.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-02T00:00:00+00:00"},
        {"id": "s4", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-01T00:00:00+00:00"},
    ]
    alarms_file = tmp_path / "alarms_sort2.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard?sort=oldest")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert body.index("AAPL") < body.index("TSLA")
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_app.py::test_dashboard_sort_az tests/test_app.py::test_dashboard_sort_oldest -v
```

Expected: FAIL

- [ ] **Step 3: Update `dashboard` route in `app.py`**

Replace the `dashboard` function (lines 84–96) with:

```python
@app.route("/dashboard")
@login_required
def dashboard():
    alarms = read_alarms()
    sort = request.args.get("sort", "newest")
    if sort == "oldest":
        alarms.sort(key=lambda a: a.get("created_at") or "")
    elif sort == "az":
        alarms.sort(key=lambda a: a.get("ticker", ""))
    else:
        alarms.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    prices = {}
    for alarm in alarms:
        ticker = alarm.get("ticker")
        if ticker and ticker not in prices:
            try:
                prices[ticker] = checker.get_price(ticker)
            except Exception:
                prices[ticker] = None
    return render_template("dashboard.html", alarms=alarms, prices=prices, sort=sort)
```

- [ ] **Step 4: Add sort buttons to `templates/dashboard.html`**

Add this block immediately after the `<div class="toolbar">...</div>` block (after line 6, before the `{% for alarm in alarms %}` loop):

```html
<div class="sort-controls">
    <a href="{{ url_for('dashboard', sort='newest') }}"
       class="btn {% if sort == 'newest' %}btn-primary{% endif %}">Newest</a>
    <a href="{{ url_for('dashboard', sort='oldest') }}"
       class="btn {% if sort == 'oldest' %}btn-primary{% endif %}">Oldest</a>
    <a href="{{ url_for('dashboard', sort='az') }}"
       class="btn {% if sort == 'az' %}btn-primary{% endif %}">A–Z</a>
</div>
```

- [ ] **Step 5: Add `.sort-controls` CSS to `static/style.css`**

Add after the `.toolbar` block (after line 95):

```css
/* ── Sort controls ───────────────────────────────── */
.sort-controls {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
}
.sort-controls .btn {
    padding: 0.35rem 0.75rem;
    font-size: 0.82rem;
}
```

- [ ] **Step 6: Run tests to confirm they pass**

```
pytest tests/test_app.py::test_dashboard_sort_az tests/test_app.py::test_dashboard_sort_oldest -v
```

Expected: PASS

- [ ] **Step 7: Run full test suite**

```
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app.py templates/dashboard.html static/style.css tests/test_app.py
git commit -m "feat: dashboard sorting by newest, oldest, and A-Z"
```

---

## Task 3: Alarm creation metadata

**Files:**
- Modify: `app.py` (add `datetime` import; update `_alarm_from_form`)
- Modify: `tests/test_app.py` (add creation metadata tests)

- [ ] **Step 1: Write failing tests**

Add to the end of `tests/test_app.py`:

```python
def test_alarm_creation_sets_created_at_and_initial_price(client, tmp_path, monkeypatch):
    import app as app_module
    alarms_file = tmp_path / "alarms_meta.json"
    alarms_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 123.45)
    login(client)
    client.post("/alarm/new", data={
        "ticker": "MSFT", "alarm_type": "price", "upper_limit": "500",
        "lower_limit": "", "email": "a@b.com", "timezone": "", "enabled": "on",
    })
    saved = json.loads(alarms_file.read_text())
    assert len(saved) == 1
    assert "created_at" in saved[0]
    assert saved[0]["initial_price"] == 123.45
    assert saved[0]["history"] == []


def test_alarm_creation_initial_price_null_on_fetch_failure(client, tmp_path, monkeypatch):
    import app as app_module
    alarms_file = tmp_path / "alarms_meta2.json"
    alarms_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    def raise_error(t):
        raise ValueError("no price")
    monkeypatch.setattr("checker.get_price", raise_error)
    login(client)
    client.post("/alarm/new", data={
        "ticker": "MSFT", "alarm_type": "price", "upper_limit": "500",
        "lower_limit": "", "email": "a@b.com", "timezone": "", "enabled": "on",
    })
    saved = json.loads(alarms_file.read_text())
    assert len(saved) == 1
    assert saved[0]["initial_price"] is None


def test_alarm_edit_preserves_created_at_and_initial_price(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "meta1", "ticker": "WDC", "enabled": True, "upper_limit": 280.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
                "created_at": "2026-04-01T00:00:00+00:00", "initial_price": 99.99, "history": []}]
    alarms_file = tmp_path / "alarms_meta3.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 200.0)
    login(client)
    client.post("/alarm/meta1/edit", data={
        "ticker": "WDC", "alarm_type": "price", "upper_limit": "300",
        "lower_limit": "", "email": "a@b.com", "timezone": "", "enabled": "on",
    })
    saved = json.loads(alarms_file.read_text())
    assert saved[0]["created_at"] == "2026-04-01T00:00:00+00:00"
    assert saved[0]["initial_price"] == 99.99
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_app.py::test_alarm_creation_sets_created_at_and_initial_price tests/test_app.py::test_alarm_creation_initial_price_null_on_fetch_failure tests/test_app.py::test_alarm_edit_preserves_created_at_and_initial_price -v
```

Expected: FAIL

- [ ] **Step 3: Add `datetime` import to `app.py`**

Add to the imports block at the top of `app.py`, after `from functools import wraps`:

```python
from datetime import datetime, timezone
```

- [ ] **Step 4: Update `_alarm_from_form` in `app.py`**

In `_alarm_from_form`, after the `alarm = { ... }` dict is created and before the `if alarm_type == "pct":` block, add:

```python
    if existing:
        alarm["created_at"] = existing.get("created_at")
        alarm["initial_price"] = existing.get("initial_price")
        alarm["history"] = existing.get("history", [])
    else:
        alarm["created_at"] = datetime.now(timezone.utc).isoformat()
        try:
            alarm["initial_price"] = checker.get_price(ticker)
        except Exception:
            alarm["initial_price"] = None
        alarm["history"] = []
```

- [ ] **Step 5: Run tests to confirm they pass**

```
pytest tests/test_app.py::test_alarm_creation_sets_created_at_and_initial_price tests/test_app.py::test_alarm_creation_initial_price_null_on_fetch_failure tests/test_app.py::test_alarm_edit_preserves_created_at_and_initial_price -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite**

```
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: capture created_at and initial_price on alarm creation"
```

---

## Task 4: Alert history in checker

**Files:**
- Modify: `checker.py` (append history after `send_email` in both alarm paths)
- Modify: `tests/test_checker.py` (add history tests)

- [ ] **Step 1: Write failing tests**

Add to the end of `tests/test_checker.py`:

```python
import checker


def test_history_appended_after_price_alarm_triggers(monkeypatch, tmp_path):
    alarm = {
        "id": "h1", "ticker": "WDC", "enabled": True,
        "upper_limit": 200.0, "lower_limit": None,
        "email": "a@b.com", "last_triggered": None, "timezone": None,
    }
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([alarm]))
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "from@test.com")
    monkeypatch.setattr(checker, "get_price", lambda t: 250.0)
    monkeypatch.setattr(checker, "send_email", lambda *a, **kw: None)
    checker.run(path=str(alarms_file))
    saved = json.loads(alarms_file.read_text())
    assert len(saved[0]["history"]) == 1
    entry = saved[0]["history"][0]
    assert entry["type"] == "upper"
    assert entry["price"] == 250.0
    assert entry["threshold"] == 200.0
    assert "triggered_at" in entry


def test_history_capped_at_10_entries(monkeypatch, tmp_path):
    existing_history = [
        {"triggered_at": f"2026-01-{i:02d}T00:00:00+00:00",
         "type": "upper", "price": 250.0, "threshold": 200.0}
        for i in range(1, 11)
    ]
    alarm = {
        "id": "h2", "ticker": "WDC", "enabled": True,
        "upper_limit": 200.0, "lower_limit": None,
        "email": "a@b.com", "last_triggered": None, "timezone": None,
        "history": existing_history,
    }
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([alarm]))
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "from@test.com")
    monkeypatch.setattr(checker, "get_price", lambda t: 250.0)
    monkeypatch.setattr(checker, "send_email", lambda *a, **kw: None)
    checker.run(path=str(alarms_file))
    saved = json.loads(alarms_file.read_text())
    assert len(saved[0]["history"]) == 10


def test_history_appended_after_pct_alarm_triggers(monkeypatch, tmp_path):
    alarm = {
        "id": "h3", "ticker": "WDC", "enabled": True,
        "upper_pct": 5.0, "lower_pct": None,
        "base_price": 100.0,
        "email": "a@b.com", "last_triggered": None, "timezone": None,
    }
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([alarm]))
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "from@test.com")
    monkeypatch.setattr(checker, "get_price", lambda t: 110.0)
    monkeypatch.setattr(checker, "send_email", lambda *a, **kw: None)
    checker.run(path=str(alarms_file))
    saved = json.loads(alarms_file.read_text())
    assert len(saved[0]["history"]) == 1
    entry = saved[0]["history"][0]
    assert entry["type"] == "upper_pct"
    assert entry["price"] == 110.0
    assert entry["threshold"] == 5.0
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_checker.py::test_history_appended_after_price_alarm_triggers tests/test_checker.py::test_history_capped_at_10_entries tests/test_checker.py::test_history_appended_after_pct_alarm_triggers -v
```

Expected: FAIL

- [ ] **Step 3: Update price alarm path in `checker.py`**

In `checker.run()`, find the block after the price alarm's `send_email` succeeds. It currently reads:

```python
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at ${price:.2f}")
```

Replace with:

```python
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        entry = {
                            "triggered_at": alarm["last_triggered"],
                            "type": limit_type,
                            "price": price,
                            "threshold": limit_value,
                        }
                        alarm.setdefault("history", []).append(entry)
                        alarm["history"] = alarm["history"][-10:]
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at ${price:.2f}")
```

- [ ] **Step 4: Update pct alarm path in `checker.py`**

Find the block after the pct alarm's `send_email` succeeds. It currently reads:

```python
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at {actual_pct:+.1f}%")
```

Replace with:

```python
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        entry = {
                            "triggered_at": alarm["last_triggered"],
                            "type": direction,
                            "price": price,
                            "threshold": pct_threshold,
                        }
                        alarm.setdefault("history", []).append(entry)
                        alarm["history"] = alarm["history"][-10:]
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at {actual_pct:+.1f}%")
```

- [ ] **Step 5: Run tests to confirm they pass**

```
pytest tests/test_checker.py::test_history_appended_after_price_alarm_triggers tests/test_checker.py::test_history_capped_at_10_entries tests/test_checker.py::test_history_appended_after_pct_alarm_triggers -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite**

```
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: append alert history to alarms after each email sent, cap at 10"
```

---

## Task 5: Dashboard card UI — metadata, history, and chart buttons

**Files:**
- Modify: `templates/dashboard.html` (add metadata row, history section, chart period buttons, refactor chart JS)
- Modify: `static/style.css` (add styles for new elements)

Note: this task is pure frontend — verify manually in the browser after deployment.

- [ ] **Step 1: Add CSS for new elements to `static/style.css`**

Add at the end of the file:

```css
/* ── Card metadata ───────────────────────────────── */
.card-meta {
    font-size: 0.78rem;
    color: #7a6a5a;
    grid-column: 1 / -1;
    margin-top: 0.1rem;
}

/* ── History ─────────────────────────────────────── */
.card-history {
    margin-bottom: 0.75rem;
    border-top: 1px solid #3a2e28;
    padding-top: 0.6rem;
}
.card-history summary {
    cursor: pointer;
    font-size: 0.82rem;
    color: #7a6a5a;
    user-select: none;
    list-style: none;
}
.card-history summary::-webkit-details-marker { display: none; }
.card-history summary::after { content: ' ▾'; }
.card-history[open] summary::after { content: ' ▴'; }
.history-list {
    list-style: none;
    margin-top: 0.5rem;
}
.history-list li {
    font-size: 0.8rem;
    color: #c8a07a;
    padding: 0.2rem 0;
    border-bottom: 1px solid #2a2420;
}
.history-empty {
    font-size: 0.8rem;
    color: #5a4a3a;
    margin-top: 0.4rem;
}

/* ── Chart period buttons ────────────────────────── */
.chart-controls {
    display: flex;
    gap: 0.35rem;
    margin-bottom: 0.4rem;
}
.chart-period-btn {
    padding: 0.2rem 0.55rem;
    font-size: 0.78rem;
    border-radius: 6px;
    font-weight: 700;
}
.chart-period-btn.active {
    background: #b5451b;
    border-color: #c0522a;
    color: #f5e6d3;
}
```

- [ ] **Step 2: Replace the full content of `templates/dashboard.html`**

Replace the entire file with:

```html
{% extends "base.html" %}
{% block content %}
<div class="toolbar">
    <h2>Alarms</h2>
    <a href="{{ url_for('alarm_new') }}" class="btn btn-primary">+ Add</a>
</div>

<div class="sort-controls">
    <a href="{{ url_for('dashboard', sort='newest') }}"
       class="btn {% if sort == 'newest' %}btn-primary{% endif %}">Newest</a>
    <a href="{{ url_for('dashboard', sort='oldest') }}"
       class="btn {% if sort == 'oldest' %}btn-primary{% endif %}">Oldest</a>
    <a href="{{ url_for('dashboard', sort='az') }}"
       class="btn {% if sort == 'az' %}btn-primary{% endif %}">A–Z</a>
</div>

{% for alarm in alarms %}
<div class="card {% if not alarm.enabled %}card-disabled{% endif %}">
    <div class="card-header">
        <span class="ticker">{{ alarm.ticker }}</span>
        <form method="post" action="/alarm/{{ alarm.id }}/toggle" style="display:inline">
            <button type="submit" class="toggle {{ 'toggle-on' if alarm.enabled else 'toggle-off' }}">
                {{ "ON" if alarm.enabled else "OFF" }}
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
                {% if alarm.get('upper_limit') %}↑ ${{ "%.2f"|format(alarm.upper_limit) }}{% endif %}
                {% if alarm.get('lower_limit') %}↓ ${{ "%.2f"|format(alarm.lower_limit) }}{% endif %}
            {% endif %}
        </div>
        <div class="price">
            {% if prices.get(alarm.ticker) is not none %}
                ${{ "%.2f"|format(prices[alarm.ticker]) }}
            {% else %}
                unavailable
            {% endif %}
        </div>
        <div class="last-triggered">
            Last alert: {{ alarm.last_triggered[:10] if alarm.last_triggered else "Never" }}
        </div>
        <div class="card-meta">
            Created: {% if alarm.get('created_at') %}{{ alarm.created_at[:10] }}{% else %}N/A{% endif %}
            &middot;
            Initial: {% if alarm.get('initial_price') is not none %}${{ "%.2f"|format(alarm.initial_price) }}{% else %}N/A{% endif %}
        </div>
    </div>
    <div class="chart-controls">
        <button class="btn chart-period-btn active" data-period="1mo" data-alarm="{{ alarm.id }}">1M</button>
        <button class="btn chart-period-btn" data-period="5d" data-alarm="{{ alarm.id }}">1W</button>
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
                    {{ entry.type.replace('_', ' ') }} ${{ "%.2f"|format(entry.threshold) }} hit at ${{ "%.2f"|format(entry.price) }}
                {% else %}
                    {{ entry.type.replace('_', ' ') }} {{ "%.1f"|format(entry.threshold) }}% at ${{ "%.2f"|format(entry.price) }}
                {% endif %}
            </li>
            {% endfor %}
        </ul>
        {% else %}
        <p class="history-empty">No alerts sent yet.</p>
        {% endif %}
    </details>
    <div class="card-actions">
        <a href="/alarm/{{ alarm.id }}/edit" class="btn">Edit</a>
        <form method="post" action="/alarm/{{ alarm.id }}/delete" style="display:inline"
              onsubmit="return confirm('Delete {{ alarm.ticker }} alarm?')">
            <button type="submit" class="btn btn-danger">Delete</button>
        </form>
    </div>
</div>
{% else %}
<p class="empty">No alarms yet. <a href="{{ url_for('alarm_new') }}">Add one</a>.</p>
{% endfor %}
{% endblock %}

{% block scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script>
const _charts = {};

function _renderChart(alarmId, period) {
    const periodLabel = {'5d': '1W', '1mo': '1M', '1y': '1Y'}[period] || '1M';
    fetch('/alarm/' + alarmId + '/chart-data?period=' + period)
        .then(r => r.json())
        .then(data => {
            if (data.error) return;
            const prices = data.prices;
            const high = Math.max(...prices);
            const low = Math.min(...prices);
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
                            ticks: {
                                maxTicksLimit: 4,
                                font: { size: 10 },
                                color: '#c8a07a',
                                callback: val => '$' + val.toFixed(0),
                            },
                            grid: { color: 'rgba(255,255,255,0.07)' },
                        }
                    },
                    animation: false,
                }
            });
        })
        .catch(() => {});
}

{% for alarm in alarms %}
_renderChart('{{ alarm.id }}', '1mo');
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
</script>
{% endblock %}
```

- [ ] **Step 3: Run the full test suite**

```
pytest tests/ -v
```

Expected: all pass (template changes don't affect backend tests)

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html static/style.css
git commit -m "feat: add card metadata, alert history, and chart period buttons to dashboard"
```

- [ ] **Step 5: Push to Railway and verify in browser**

```bash
git push
```

Open the deployed site and confirm:
- Sort buttons (Newest / Oldest / A–Z) appear and work
- Each card shows "Created: … · Initial: …" (N/A for existing alarms without the field)
- "History" expands/collapses on each card
- 1M / 1W / 1Y buttons switch the chart timeframe
