# Trade History, Savings P&L Coloring, Siemens Program, Favicon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add buy-record logging to the trade history tab, fix P&L coloring in the savings table, add a Siemens Matching Program card to the savings tab, and add a favicon.

**Architecture:** Four independent changes applied to a single feature branch. Tasks 1–3 touch the trade history flow (CSS, form, route, template). Tasks 4–6 build the Siemens section from the bottom up (checker helpers → app routes → templates). Each task commits on its own.

**Tech Stack:** Python/Flask, Jinja2, vanilla JS, pytest, CSS

---

## File Map

| File | Change |
|---|---|
| `static/style.css` | Add 2 specificity-fix rules + trade type badge styles + siemens card styles |
| `static/favicon.svg` | New — bell SVG favicon |
| `templates/base.html` | Add `<link rel="icon">` tag |
| `templates/trade_form.html` | Add type dropdown + JS show/hide sell fields |
| `templates/dashboard.html` | Rename tab label; add Type column to history table; add Siemens section to savings tab; add Siemens P&L breakdown row |
| `templates/siemens_form.html` | New — edit form for Siemens data |
| `app.py` | Update `_trade_from_form()`; update history route; add Siemens path/read/write/routes; update savings route |
| `checker.py` | Add Siemens path constants + `get_siemens_path()`, `load_siemens()`, `save_siemens()` |
| `tests/test_app.py` | New tests for buy type, Siemens routes, savings integration |

---

## Task 1: CSS fixes + favicon

**Files:**
- Modify: `static/style.css`
- Create: `static/favicon.svg`
- Modify: `templates/base.html`

No tests needed for these changes.

- [ ] **Step 1: Fix P&L coloring CSS specificity**

In `static/style.css`, find the two existing rules (around line 468):
```css
.value-positive { color: #22c55e; }
.value-negative { color: #ef4444; }
```

Add two more specific rules immediately after them:
```css
.value-positive { color: #22c55e; }
.value-negative { color: #ef4444; }
.savings-holdings-table td.value-positive { color: #22c55e; }
.savings-holdings-table td.value-negative { color: #ef4444; }
```

- [ ] **Step 2: Add trade type badge styles**

In `static/style.css`, find the `/* ── History table ─────────────────────────── */` comment (around line 471) and add these rules inside that section:

```css
.trade-type-badge {
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: 600;
}
.trade-type-buy  { background: #1a3a1a; color: #6fcf6f; }
.trade-type-sell { background: #3a1a1a; color: #e07070; }
```

- [ ] **Step 3: Create the favicon**

Create `static/favicon.svg` with this content:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#1e1a18"/>
  <text x="50%" y="52%" dominant-baseline="central" text-anchor="middle" font-size="20">🔔</text>
</svg>
```

- [ ] **Step 4: Wire up the favicon in base.html**

In `templates/base.html`, find the `<title>StockAlarm</title>` line and add the favicon link immediately after it:

```html
    <title>StockAlarm</title>
    <link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='favicon.svg') }}">
```

- [ ] **Step 5: Commit**

```bash
git add static/style.css static/favicon.svg templates/base.html
git commit -m "feat: fix savings P&L coloring, add trade type badge styles, add favicon"
```

---

## Task 2: Trade History — `_trade_from_form` + tests

**Files:**
- Modify: `app.py` (`_trade_from_form` function, around line 1027)
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py` after the existing `test_trade_from_form_*` tests:

```python
def test_trade_from_form_buy_type_skips_sell_validation():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("type", "buy"), ("ticker", "MSFT"), ("source", "yfinance"),
        ("shares", "5"), ("buy_price", "390.00"), ("buy_date", "2025-01-10"),
    ])
    trade, error = _trade_from_form(form)
    assert error is None
    assert trade["type"] == "buy"
    assert trade["sell_price"] is None
    assert trade["sell_date"] is None


def test_trade_from_form_sell_type_still_requires_sell_price():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("type", "sell"), ("ticker", "AAPL"), ("source", "yfinance"),
        ("shares", "10"), ("buy_price", "200.00"), ("buy_date", "2025-01-01"),
    ])
    trade, error = _trade_from_form(form)
    assert error is not None
    assert "sell price" in error.lower()


def test_trade_from_form_defaults_to_sell_when_type_missing():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "AAPL"), ("source", "yfinance"),
        ("shares", "10"), ("buy_price", "200.00"), ("buy_date", "2025-01-01"),
        ("sell_price", "240.00"), ("sell_date", "2025-01-20"),
    ])
    trade, error = _trade_from_form(form)
    assert error is None
    assert trade["type"] == "sell"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py::test_trade_from_form_buy_type_skips_sell_validation tests/test_app.py::test_trade_from_form_sell_type_still_requires_sell_price tests/test_app.py::test_trade_from_form_defaults_to_sell_when_type_missing -v
```

Expected: all 3 FAILED

- [ ] **Step 3: Update `_trade_from_form()` in `app.py`**

Replace the entire `_trade_from_form` function (starting at `def _trade_from_form(form, existing=None):`) with:

```python
def _trade_from_form(form, existing=None):
    """Parse and validate trade form data. Returns (trade_dict, error_str_or_None)."""
    import uuid

    ticker = form.get("ticker", "").strip()
    if not ticker:
        return None, "Ticker is required"

    source = form.get("source", "yfinance")
    trade_type = form.get("type", "sell")
    if trade_type not in ("buy", "sell"):
        trade_type = "sell"

    shares_raw = form.get("shares", "").strip()
    if shares_raw:
        try:
            shares = float(shares_raw)
        except ValueError:
            return None, "Shares must be a number"
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
    if trade_type == "sell" and sell_price is None:
        return None, "Sell price is required"

    buy_date = form.get("buy_date", "").strip()
    sell_date = form.get("sell_date", "").strip()
    if not buy_date:
        return None, "Buy date is required"
    if trade_type == "sell" and not sell_date:
        return None, "Sell date is required"

    return {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "type": trade_type,
        "ticker": ticker,
        "source": source,
        "shares": shares,
        "buy_price": buy_price,
        "buy_date": buy_date,
        "sell_price": sell_price,
        "sell_date": sell_date if trade_type == "sell" else None,
        "created_at": existing["created_at"] if existing else datetime.now(timezone.utc).isoformat(),
    }, None
```

- [ ] **Step 4: Run tests — expect all 3 to pass**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py::test_trade_from_form_buy_type_skips_sell_validation tests/test_app.py::test_trade_from_form_sell_type_still_requires_sell_price tests/test_app.py::test_trade_from_form_defaults_to_sell_when_type_missing -v
```

Expected: all 3 PASS

- [ ] **Step 5: Run the full trade test suite to check for regressions**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py -k "trade" -v
```

Expected: all existing trade tests still pass (the `test_trade_from_form_missing_sell_price` test still passes because it doesn't submit a `type` field, so it defaults to "sell" and sell_price is still required).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add type field to trade data model, buy trades skip sell validation"
```

---

## Task 3: Trade History — form template + dashboard route + table

**Files:**
- Modify: `templates/trade_form.html`
- Modify: `app.py` (history section of `dashboard()` route, lines ~308–340)
- Modify: `templates/dashboard.html` (tab label + history table)

- [ ] **Step 1: Update `trade_form.html` — add type dropdown and show/hide JS**

Replace the entire content of `templates/trade_form.html` with:

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

        {% if not is_record_sale %}
        <label>Trade Type *
            <select name="type" id="trade-type" onchange="updateTradeType()">
                <option value="sell" {% if form.get('type', 'sell') == 'sell' %}selected{% endif %}>Sell</option>
                <option value="buy" {% if form.get('type') == 'buy' %}selected{% endif %}>Buy</option>
            </select>
        </label>
        {% else %}
        <input type="hidden" name="type" value="sell">
        {% endif %}

        <label>Number of shares — optional
            <input type="number" step="any" min="0" name="shares"
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
        </div>

        <div id="sell-fields" {% if form.get('type') == 'buy' %}style="display:none"{% endif %}>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.75rem;margin-top:0.75rem">
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
<script>
function updateTradeType() {
    var type = document.getElementById('trade-type').value;
    document.getElementById('sell-fields').style.display = type === 'sell' ? '' : 'none';
}
</script>
{% endblock %}
```

- [ ] **Step 2: Update the history route in `app.py` to filter sell-only for summary stats**

Find the `# --- History tab ---` block in `dashboard()` (around line 307). Replace it with:

```python
    # --- History tab ---
    if tab == "history":
        trades = read_trades()
        sell_trades = [t for t in trades if t.get("type", "sell") == "sell"]
        trade_pcts = {}
        trade_pls = {}
        pl_values = []
        for t in sell_trades:
            tid = t.get("id")
            if not tid:
                continue
            buy = t.get("buy_price") or 0
            sell = t.get("sell_price") or 0
            pct = (sell - buy) / buy * 100 if buy else 0.0
            trade_pcts[tid] = pct
            if t.get("shares"):
                pl = (sell - buy) * t["shares"]
                trade_pls[tid] = pl
                pl_values.append(pl)
            else:
                trade_pls[tid] = None
        pct_list = list(trade_pcts.values())
        avg_pct = sum(pct_list) / len(pct_list) if pct_list else None
        best = max(trade_pcts, key=trade_pcts.get, default=None)
        best_trade = next((t for t in sell_trades if t.get("id") == best), None) if best else None
        summary = {
            "count": len(sell_trades),
            "total_pl": sum(pl_values) if pl_values else None,
            "avg_pct": avg_pct,
            "best_ticker": best_trade["ticker"] if best_trade else None,
            "best_pct": trade_pcts[best] if best else None,
        }
        return render_template("dashboard.html", tab=tab, trades=trades,
                               summary=summary, trade_pcts=trade_pcts,
                               trade_pls=trade_pls)
```

- [ ] **Step 3: Update `dashboard.html` — rename tab + update history table**

**3a.** Find this line (around line 15):
```html
       class="tab {% if tab == 'history' %}tab-active{% endif %}">Sell History</a>
```
Change `Sell History` to `Trade History`.

**3b.** Find this comment (around line 25):
```
   SELL HISTORY TAB
```
Change it to `TRADE HISTORY TAB`.

**3c.** Find the table header row in the history table (around line 70):
```html
        <tr>
```
followed by `<th>` tags for Ticker, Shares, Buy Price, etc. Replace the entire `<tr>` header with:
```html
        <tr>
            <th>Type</th>
            <th style="text-align:left">Ticker</th>
            <th>Shares</th>
            <th>Buy Price</th>
            <th>Buy Date</th>
            <th>Sell Price</th>
            <th>Sell Date</th>
            <th>% Change</th>
            <th>Total P&amp;L</th>
            <th></th>
        </tr>
```

**3d.** Find the `<tr>` that starts each trade row (around line 87):
```html
    <tr>
        <td class="trade-ticker">{{ trade.ticker }}</td>
```
Add a Type badge cell before the ticker cell, and add null guards on sell_price and sell_date:

```html
    <tr>
        {% set ttype = trade.get('type', 'sell') %}
        <td><span class="trade-type-badge trade-type-{{ ttype }}">{{ ttype|title }}</span></td>
        <td class="trade-ticker">{{ trade.ticker }}</td>
        <td>{{ trade.shares if trade.shares else '—' }}</td>
        <td>{{ curr }}{{ "%.2f"|format(trade.buy_price) }}</td>
        <td>{{ trade.buy_date }}</td>
        <td>{% if trade.sell_price is not none %}{{ curr }}{{ "%.2f"|format(trade.sell_price) }}{% else %}—{% endif %}</td>
        <td>{{ trade.sell_date or '—' }}</td>
```

(Leave the `% Change`, `Total P&L`, and actions cells unchanged — buy records will show `—` naturally since their ids are not in `trade_pcts`/`trade_pls`.)

- [ ] **Step 4: Run the full test suite**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add templates/trade_form.html app.py templates/dashboard.html
git commit -m "feat: Trade History tab — type dropdown, combined buy/sell table, sell-only summary stats"
```

---

## Task 4: Siemens — `checker.py` helpers

**Files:**
- Modify: `checker.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py`:

```python
def test_load_siemens_returns_none_when_file_missing():
    import checker
    assert checker.load_siemens("/nonexistent/path/siemens.json") is None


def test_load_siemens_returns_dict_when_file_exists(tmp_path):
    import checker
    data = {"shares": 10.0, "total_value_ils": 5000, "gain_ils": 200, "gain_pct": 4.2,
            "last_updated": "2026-05-10T10:00:00+00:00"}
    f = tmp_path / "siemens.json"
    f.write_text(json.dumps(data))
    result = checker.load_siemens(str(f))
    assert result["shares"] == 10.0
    assert result["gain_pct"] == 4.2


def test_save_siemens_writes_file(tmp_path):
    import checker
    data = {"shares": 24.83, "total_value_ils": 42500, "gain_ils": 3200, "gain_pct": 8.1,
            "last_updated": "2026-05-10T10:00:00+00:00"}
    path = str(tmp_path / "siemens.json")
    checker.save_siemens(data, path)
    saved = json.loads(open(path).read())
    assert saved["shares"] == 24.83
```

- [ ] **Step 2: Run to confirm they fail**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py::test_load_siemens_returns_none_when_file_missing tests/test_app.py::test_load_siemens_returns_dict_when_file_exists tests/test_app.py::test_save_siemens_writes_file -v
```

Expected: all 3 FAILED

- [ ] **Step 3: Add Siemens helpers to `checker.py`**

In `checker.py`, find the path constants block (around line 104):
```python
SNAPSHOTS_LOCAL_PATH = "savings_snapshots.json"
SNAPSHOTS_VOLUME_PATH = "/data/savings_snapshots.json"
```

Add immediately after:
```python
SIEMENS_LOCAL_PATH = "siemens.json"
SIEMENS_VOLUME_PATH = "/data/siemens.json"
```

Then find `get_snapshots_path()` and add a new function immediately after it:
```python
def get_siemens_path() -> str:
    """Returns the path to siemens.json — volume path on Railway, local path otherwise."""
    if os.path.isdir("\data"):
        return SIEMENS_VOLUME_PATH
    return SIEMENS_LOCAL_PATH


def load_siemens(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_siemens(data: dict, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)
```

- [ ] **Step 4: Run tests — expect all 3 to pass**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py::test_load_siemens_returns_none_when_file_missing tests/test_app.py::test_load_siemens_returns_dict_when_file_exists tests/test_app.py::test_save_siemens_writes_file -v
```

Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
git add checker.py tests/test_app.py
git commit -m "feat: add Siemens path constants and load/save helpers to checker.py"
```

---

## Task 5: Siemens — `app.py` routes + savings integration

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py`:

```python
def test_siemens_edit_get_empty_state(tmp_path, monkeypatch):
    """GET /siemens/edit works when no siemens.json exists yet."""
    monkeypatch.setattr(app_module, "_SIEMENS_PATH", str(tmp_path / "siemens.json"))
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        login(c)
        resp = c.get("/siemens/edit")
    assert resp.status_code == 200


def test_siemens_edit_post_saves_and_redirects(tmp_path, monkeypatch):
    siemens_file = tmp_path / "siemens.json"
    monkeypatch.setattr(app_module, "_SIEMENS_PATH", str(siemens_file))
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        login(c)
        resp = c.post("/siemens/edit", data={
            "shares": "24.83",
            "total_value_ils": "42500",
            "gain_ils": "3200",
            "gain_pct": "8.1",
        })
    assert resp.status_code == 302
    saved = json.loads(siemens_file.read_text())
    assert saved["shares"] == 24.83
    assert saved["gain_pct"] == 8.1
    assert "last_updated" in saved


def test_savings_includes_siemens_in_total(savings_client, tmp_path, monkeypatch):
    c, savings_file = savings_client
    siemens_file = tmp_path / "siemens.json"
    siemens_file.write_text(json.dumps({
        "shares": 10.0, "total_value_ils": 5000, "gain_ils": 500, "gain_pct": 11.1,
        "last_updated": "2026-05-10T10:00:00+00:00"
    }))
    monkeypatch.setattr(app_module, "_SIEMENS_PATH", str(siemens_file))
    login(c)
    resp = c.get("/savings")
    assert resp.status_code == 200
    assert b"5,000" in resp.data or b"5000" in resp.data


def test_savings_works_without_siemens_file(savings_client, tmp_path, monkeypatch):
    c, _ = savings_client
    monkeypatch.setattr(app_module, "_SIEMENS_PATH", str(tmp_path / "no_siemens.json"))
    login(c)
    resp = c.get("/savings")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to confirm they fail**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py::test_siemens_edit_get_empty_state tests/test_app.py::test_siemens_edit_post_saves_and_redirects tests/test_app.py::test_savings_includes_siemens_in_total tests/test_app.py::test_savings_works_without_siemens_file -v
```

Expected: all 4 FAILED

- [ ] **Step 3: Add Siemens path/read/write to `app.py`**

In `app.py`, find:
```python
_SNAPSHOTS_PATH = checker.get_snapshots_path()
```

Add immediately after:
```python
_SIEMENS_PATH = checker.get_siemens_path()
SIEMENS_PORTAL_URL = "https://samlparticipant.equateplus.com/EquatePlusParticipant2/start"
```

Then find the `read_snapshots()` function and add after it:

```python
def read_siemens():
    with _lock:
        return checker.load_siemens(_SIEMENS_PATH)


def write_siemens(data):
    with _lock:
        checker.save_siemens(data, _SIEMENS_PATH)
```

- [ ] **Step 4: Add Siemens to the savings route in `app.py`**

In the `savings()` route, find these lines (around line 655):
```python
    total_value_ils = sum(d["value_ils"] for d in cat_data.values())
    total_pl_ils = sum(d["pl_ils"] for d in cat_data.values())
    total_today_ils = sum(d["today_ils"] for d in cat_data.values())
    total_cost_ils = sum(d["cost_ils"] for d in cat_data.values())
    total_pl_pct = (total_pl_ils / total_cost_ils * 100) if total_cost_ils else None
    prev_total = total_value_ils - total_today_ils
    total_today_pct = (total_today_ils / prev_total * 100) if prev_total else None
```

Replace with:
```python
    total_value_ils = sum(d["value_ils"] for d in cat_data.values())
    total_pl_ils = sum(d["pl_ils"] for d in cat_data.values())
    total_today_ils = sum(d["today_ils"] for d in cat_data.values())
    total_cost_ils = sum(d["cost_ils"] for d in cat_data.values())

    siemens = read_siemens()
    if siemens:
        sie_value = siemens.get("total_value_ils") or 0
        sie_gain = siemens.get("gain_ils") or 0
        total_value_ils += sie_value
        total_pl_ils += sie_gain
        total_cost_ils += sie_value - sie_gain

    total_pl_pct = (total_pl_ils / total_cost_ils * 100) if total_cost_ils else None
    prev_total = total_value_ils - total_today_ils
    total_today_pct = (total_today_ils / prev_total * 100) if prev_total else None
```

Then find the `return render_template(` call at the end of the savings route (around line 693) and add `siemens`, `siemens_updated_rel`, and `siemens_portal_url` to it:

```python
    return render_template(
        "dashboard.html", tab="savings",
        holdings=holdings, holding_data=holding_data,
        cat_data=cat_data, summary=summary,
        pie=pie, snapshots=snapshots,
        usd_to_ils=usd_to_ils,
        categories=("etf", "stocks", "mmf"),
        category_labels={"etf": "ETFs", "stocks": "Stocks", "mmf": "Money Market Funds (MMF)"},
        siemens=siemens,
        siemens_updated_rel=_relative_time(siemens.get("last_updated")) if siemens else None,
        siemens_portal_url=SIEMENS_PORTAL_URL,
    )
```

- [ ] **Step 5: Add the `/siemens/edit` routes to `app.py`**

In `app.py`, find the `# --- Savings ---` comment (around line 592) and add a new route section before it:

```python
# --- Siemens ---

@app.route("/siemens/edit", methods=["GET", "POST"])
@login_required
def siemens_edit():
    if request.method == "POST":
        try:
            shares = float(request.form.get("shares", "").strip())
            total_value_ils = float(request.form.get("total_value_ils", "").strip())
            gain_ils = float(request.form.get("gain_ils", "").strip())
            gain_pct = float(request.form.get("gain_pct", "").strip())
        except ValueError:
            return render_template("siemens_form.html",
                                   error="All fields must be numbers",
                                   form=request.form)
        write_siemens({
            "shares": shares,
            "total_value_ils": total_value_ils,
            "gain_ils": gain_ils,
            "gain_pct": gain_pct,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        return redirect(url_for("savings"))
    siemens = read_siemens() or {}
    return render_template("siemens_form.html", form=siemens)
```

- [ ] **Step 6: Run the Siemens tests — expect all 4 to pass**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py::test_siemens_edit_get_empty_state tests/test_app.py::test_siemens_edit_post_saves_and_redirects tests/test_app.py::test_savings_includes_siemens_in_total tests/test_app.py::test_savings_works_without_siemens_file -v
```

Expected: all 4 PASS

- [ ] **Step 7: Run the full test suite**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py -v
```

Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add Siemens routes and integrate Siemens value into savings portfolio summary"
```

---

## Task 6: Siemens — templates + CSS

**Files:**
- Create: `templates/siemens_form.html`
- Modify: `templates/dashboard.html` (savings tab — Siemens section + P&L breakdown row)
- Modify: `static/style.css` (Siemens card styles)

No new tests — route tests in Task 5 verify data flow; UI verified by visual inspection.

- [ ] **Step 1: Create `templates/siemens_form.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="form-card">
    <h2>Siemens Matching Program</h2>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post">
        <label>Shares *
            <input type="number" step="any" name="shares"
                value="{{ form.get('shares') or '' }}"
                placeholder="e.g. 24.83" required>
        </label>
        <label>Total Value (₪) *
            <input type="number" step="any" name="total_value_ils"
                value="{{ form.get('total_value_ils') or '' }}"
                placeholder="e.g. 42500" required>
        </label>
        <label>Gain (₪) *
            <input type="number" step="any" name="gain_ils"
                value="{{ form.get('gain_ils') or '' }}"
                placeholder="e.g. 3200 (negative if loss)" required>
        </label>
        <label>Gain % *
            <input type="number" step="any" name="gain_pct"
                value="{{ form.get('gain_pct') or '' }}"
                placeholder="e.g. 8.1 (negative if loss)" required>
        </label>
        <div class="form-actions">
            <button type="submit" class="btn btn-primary">Save</button>
            <a href="{{ url_for('savings') }}" class="btn">Cancel</a>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 2: Add Siemens CSS to `static/style.css`**

At the end of `style.css`, add:

```css
/* ── Siemens Matching Program ────────────────── */
.siemens-card {
    margin: 0.5rem 0 1rem;
    background: #242018;
    border: 1px solid #3a3028;
    border-radius: 8px;
    padding: 1rem 1.25rem;
}

.siemens-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.75rem;
    text-align: center;
}

.siemens-stat-label {
    color: #7a6a5a;
    font-size: 0.68rem;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
}

.siemens-stat-value {
    font-weight: 700;
    font-size: 1rem;
    color: #f5e6d3;
}

.siemens-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 0.75rem;
    padding-top: 0.6rem;
    border-top: 1px solid #3a3028;
}

.siemens-empty {
    color: #7a6a5a;
    font-size: 0.9rem;
    text-align: center;
    padding: 1.5rem;
}
```

- [ ] **Step 3: Add Siemens section to `dashboard.html` (savings tab)**

In `dashboard.html`, find the line that ends the category loop (around line 634):
```html
{% endfor %}
```
followed by `<script>` for the savings tab JS. Add the Siemens section between that `{% endfor %}` and the `<script>` tag:

```html
{% endfor %}

{# ══ Siemens Matching Program ══ #}
<div class="savings-category">
    <div class="savings-category-header" style="cursor:default">
        <span class="savings-cat-dot" style="background:#7b68ee"></span>
        <span class="savings-cat-title">Siemens Matching Program</span>
    </div>
    {% if siemens %}
    <div class="siemens-card">
        <div class="siemens-stats">
            <div>
                <div class="siemens-stat-label">Shares</div>
                <div class="siemens-stat-value">{{ "%.2f"|format(siemens.shares) }}</div>
            </div>
            <div>
                <div class="siemens-stat-label">Value (₪)</div>
                <div class="siemens-stat-value">₪{{ "{:,.0f}".format(siemens.total_value_ils) }}</div>
            </div>
            <div>
                <div class="siemens-stat-label">Gain (₪)</div>
                <div class="siemens-stat-value {% if siemens.gain_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
                    {{ "{:+,.0f}".format(siemens.gain_ils) }} ₪
                </div>
            </div>
            <div>
                <div class="siemens-stat-label">Gain %</div>
                <div class="siemens-stat-value {% if siemens.gain_pct >= 0 %}value-positive{% else %}value-negative{% endif %}">
                    {{ "%+.1f"|format(siemens.gain_pct) }}%
                </div>
            </div>
        </div>
        <div class="siemens-footer">
            <span class="savings-updated">Updated {{ siemens_updated_rel }}</span>
            <div class="savings-actions">
                <a href="{{ siemens_portal_url }}" target="_blank" rel="noopener" class="btn-xs">🔗 Open Portal</a>
                <a href="{{ url_for('siemens_edit') }}" class="btn-xs">Edit</a>
            </div>
        </div>
    </div>
    {% else %}
    <div class="siemens-card siemens-empty">
        No data yet. <a href="{{ url_for('siemens_edit') }}">Add details</a>
    </div>
    {% endif %}
</div>
```

- [ ] **Step 4: Add Siemens row to the P&L breakdown in `dashboard.html`**

In `dashboard.html`, find the P&L breakdown loop in the summary cards section (around line 455):
```html
        {% for cat in categories %}
        <div class="savings-breakdown-row">
            <span>{{ category_labels[cat] }}</span>
            <span class="{% if cat_data[cat].pl_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
                {{ "{:+,.0f}".format(cat_data[cat].pl_ils) }} ₪
            </span>
        </div>
        {% endfor %}
```

Add a Siemens row immediately after the `{% endfor %}`:
```html
        {% if siemens %}
        <div class="savings-breakdown-row">
            <span>Siemens Program</span>
            <span class="{% if siemens.gain_ils >= 0 %}value-positive{% else %}value-negative{% endif %}">
                {{ "{:+,.0f}".format(siemens.gain_ils) }} ₪
            </span>
        </div>
        {% endif %}
```

- [ ] **Step 5: Run the full test suite**

```
cd C:\Projects\StocksApp
py -m pytest tests/test_app.py -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add templates/siemens_form.html templates/dashboard.html static/style.css
git commit -m "feat: add Siemens Matching Program card and edit form to savings tab"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] P&L coloring fix — CSS specificity rules added (Task 1)
- [x] Favicon — SVG file + base.html link (Task 1)
- [x] Trade History — `type` field in data model (Task 2)
- [x] Buy records skip sell validation (Task 2)
- [x] Type dropdown in form with JS show/hide (Task 3)
- [x] Tab renamed "Trade History" (Task 3)
- [x] Type badge column in table (Task 3)
- [x] Summary stats count sells only (Task 3)
- [x] Null guards on sell_price/sell_date in table (Task 3)
- [x] `is_record_sale` locks type to sell (Task 3)
- [x] Siemens checker helpers (Task 4)
- [x] Siemens app paths + read/write (Task 5)
- [x] `/siemens/edit` GET + POST (Task 5)
- [x] Siemens integrated into portfolio total (Task 5)
- [x] Siemens cost basis derived as value − gain for `total_pl_pct` (Task 5)
- [x] Siemens contributes 0 to today's change (Task 5 — value not added to `total_today_ils`)
- [x] `siemens_form.html` template (Task 6)
- [x] Siemens card in savings tab (Task 6)
- [x] Siemens empty state with "Add details" link (Task 6)
- [x] Siemens P&L breakdown row in summary (Task 6)
- [x] Portal link opens in new tab (Task 6)
- [x] "Updated X ago" timestamp (Task 6)

**No placeholders found.**

**Type consistency:** All references to `siemens.gain_ils`, `siemens.gain_pct`, `siemens.total_value_ils`, `siemens.shares` match the dict keys defined in Task 5. `_SIEMENS_PATH` monkeypatched in tests matches the module-level constant added in Task 5.
