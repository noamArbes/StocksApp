# ETF P&L % Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Total cost basis" field with a "Total gain/loss %" field for ETF holdings; derive and store cost basis automatically from the live price.

**Architecture:** Two changes — (1) `_holding_from_form()` in `app.py` branches on `category == "etf"` to read `pl_pct`, fetch the live price, and compute cost basis; (2) `savings_form.html` conditionally shows the P&L % field for ETFs and the cost basis field for stocks/MMFs. Data model unchanged.

**Tech Stack:** Python/Flask, Jinja2, yfinance (`checker.get_price_with_change`), TASE API (`tase.get_price`), pytest

---

## File Map

| File | Change |
|------|--------|
| `app.py` | Modify `_holding_from_form()` lines 186–192: branch on ETF to derive cost basis from P&L % + live price |
| `templates/savings_form.html` | Replace cost basis field with P&L % field when category is ETF |
| `tests/test_app.py` | New tests for ETF P&L derivation, validation errors, price fetch failure |

---

## Task 1: Backend — ETF P&L % derivation in `_holding_from_form`

**Files:**
- Modify: `app.py` (lines 186–192 — the cost basis parsing block)
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_app.py` (after the existing `test_holding_from_form_invalid_category` test):

```python
def test_holding_from_form_etf_derives_cost_basis_from_pnl(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "25"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    # cost_basis = (100.0 * 10) / (1 + 25/100) = 1000 / 1.25 = 800.0
    assert abs(holding["cost_basis"] - 800.0) < 0.01


def test_holding_from_form_etf_negative_pnl(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (90.0, 91.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "QQQ"), ("name", "Invesco"),
        ("category", "etf"), ("shares", "5"), ("pl_pct", "-10"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    # cost_basis = (90.0 * 5) / (1 + (-10)/100) = 450 / 0.9 = 500.0
    assert abs(holding["cost_basis"] - 500.0) < 0.01


def test_holding_from_form_etf_pnl_missing(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "gain/loss" in error.lower() or "%" in error


def test_holding_from_form_etf_pnl_minus_100(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "-100"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "-100" in error or "cannot be" in error.lower()


def test_holding_from_form_etf_price_fetch_fails(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (None, None))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "15"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "price" in error.lower()


def test_holding_from_form_stocks_still_uses_cost_basis(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "AAPL"), ("name", "Apple"),
        ("category", "stocks"), ("shares", "10"), ("cost_basis", "1500"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    assert holding["cost_basis"] == 1500.0


def test_holding_from_form_mmf_still_uses_cost_basis():
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VMFXX"), ("name", "Vanguard MMF"),
        ("category", "mmf"), ("shares", "1000"), ("cost_basis", "1000"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    assert holding["cost_basis"] == 1000.0
```

- [ ] **Step 2: Run tests to confirm they fail**

```
py -m pytest tests/test_app.py::test_holding_from_form_etf_derives_cost_basis_from_pnl tests/test_app.py::test_holding_from_form_etf_negative_pnl tests/test_app.py::test_holding_from_form_etf_pnl_missing tests/test_app.py::test_holding_from_form_etf_pnl_minus_100 tests/test_app.py::test_holding_from_form_etf_price_fetch_fails tests/test_app.py::test_holding_from_form_stocks_still_uses_cost_basis tests/test_app.py::test_holding_from_form_mmf_still_uses_cost_basis -v
```

Expected: first 5 FAILED, last 2 PASSED (stocks/MMF already work).

- [ ] **Step 3: Replace the cost basis parsing block in `_holding_from_form`**

In `app.py`, find this block (lines 186–192):

```python
    cost_raw = form.get("cost_basis", "").strip()
    if not cost_raw:
        return None, "Cost basis is required"
    try:
        cost_basis = float(cost_raw)
    except ValueError:
        return None, "Cost basis must be a number"
```

Replace with:

```python
    if category == "etf":
        pl_pct_raw = form.get("pl_pct", "").strip()
        if not pl_pct_raw:
            return None, "Total gain/loss % is required and must be a number"
        try:
            pl_pct = float(pl_pct_raw)
        except ValueError:
            return None, "Total gain/loss % is required and must be a number"
        if pl_pct == -100:
            return None, "Gain/loss % cannot be -100%"
        try:
            if is_tase:
                current_price = tase.get_price(tase_id, tase_type)
            else:
                current_price, _ = checker.get_price_with_change(ticker)
            if current_price is None:
                raise ValueError("no price")
        except Exception:
            return None, "Could not fetch current price — please try again"
        cost_basis = (current_price * shares) / (1 + pl_pct / 100)
    else:
        cost_raw = form.get("cost_basis", "").strip()
        if not cost_raw:
            return None, "Cost basis is required"
        try:
            cost_basis = float(cost_raw)
        except ValueError:
            return None, "Cost basis must be a number"
```

- [ ] **Step 4: Run the tests — expect all 7 to pass**

```
py -m pytest tests/test_app.py::test_holding_from_form_etf_derives_cost_basis_from_pnl tests/test_app.py::test_holding_from_form_etf_negative_pnl tests/test_app.py::test_holding_from_form_etf_pnl_missing tests/test_app.py::test_holding_from_form_etf_pnl_minus_100 tests/test_app.py::test_holding_from_form_etf_price_fetch_fails tests/test_app.py::test_holding_from_form_stocks_still_uses_cost_basis tests/test_app.py::test_holding_from_form_mmf_still_uses_cost_basis -v
```

Expected: all 7 PASS.

- [ ] **Step 5: Run the full test suite to check for regressions**

```
py -m pytest tests/ -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: derive ETF cost basis from P&L % and live price"
```

---

## Task 2: Template — show P&L % field for ETFs, cost basis for stocks/MMFs

**Files:**
- Modify: `templates/savings_form.html` (lines 59–63 — the cost basis label)

- [ ] **Step 1: Replace the cost basis field with a conditional block**

In `templates/savings_form.html`, find:

```html
        <label>Total cost basis (what you paid in total)
            <input type="number" step="0.01" min="0" name="cost_basis"
                value="{{ form.get('cost_basis', '') }}"
                placeholder="e.g. 8200.00" required>
        </label>
```

Replace with:

```html
        {% if category == 'etf' %}
        <label>Total gain/loss % since purchase
            <input type="number" step="any" name="pl_pct"
                value="{{ form.get('pl_pct', '') }}"
                placeholder="e.g. 15 for +15%, -8 for -8%" required>
        </label>
        {% else %}
        <label>Total cost basis (what you paid in total)
            <input type="number" step="0.01" min="0" name="cost_basis"
                value="{{ form.get('cost_basis', '') }}"
                placeholder="e.g. 8200.00" required>
        </label>
        {% endif %}
```

- [ ] **Step 2: Verify manually**

Start the server and open `/savings/new?category=etf`. Confirm:
- "Total gain/loss % since purchase" field is shown (no cost basis field)
- Open `/savings/new?category=stocks` — cost basis field shown, no P&L % field
- Open `/savings/new?category=mmf` — cost basis field shown, no P&L % field

- [ ] **Step 3: Run the full test suite**

```
py -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add templates/savings_form.html
git commit -m "feat: show P&L % input for ETF form, cost basis for stocks/MMF"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] ETF form shows P&L % field ✓ (Task 2)
- [x] Stocks/MMF form unchanged ✓ (Task 2 + Task 1 tests)
- [x] Validation: missing P&L % → error ✓ (Task 1 Step 3)
- [x] Validation: P&L % = -100 → error ✓ (Task 1 Step 3)
- [x] Validation: price fetch fails → error ✓ (Task 1 Step 3)
- [x] TASE ETFs use `tase.get_price()` for price fetch ✓ (Task 1 Step 3)
- [x] cost_basis stored as normal in holding dict ✓ (Task 1 Step 3)
- [x] No data model changes ✓
