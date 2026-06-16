# Savings Geographic Allocation Indicator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `region` field to each savings holding and display a Geographic Allocation donut card on the Savings tab summary row.

**Architecture:** `region` is stored as a string field on each holding in `savings.json`. The savings() route computes `geo_data` and `geo_pie` in parallel to the existing `cat_data` / `pie` dicts. The dashboard template renders a new Geography donut card using the same SVG circle pattern as the existing Allocation card. Today's Change card gets a compact CSS modifier to make room.

**Tech Stack:** Python/Flask, Jinja2, SVG donut charts, CSS grid

---

## File Map

| File | Change |
|------|--------|
| `app.py` | `_holding_from_form` reads `region`; `savings()` computes `geo_data` + `geo_pie` |
| `templates/savings_form.html` | Add region `<select>` dropdown |
| `templates/dashboard.html` | Compact Today's Change card; add Geography donut card |
| `static/style.css` | Update grid to 5 columns; add `.savings-today-compact` |
| `tests/test_app.py` | Tests for region in form parsing; geo data in savings route |

---

## Task 1: Parse `region` from holding form

**Files:**
- Modify: `app.py:266-278` (`_holding_from_form` return dict)
- Test: `tests/test_app.py` (append to end of file)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:

```python
def test_holding_from_form_includes_region():
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "MSFT"), ("name", "Microsoft"),
        ("category", "stocks"), ("shares", "4"), ("cost_basis", "1000"),
        ("currency", "USD"), ("region", "us"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    assert holding["region"] == "us"


def test_holding_from_form_region_defaults_to_none_when_missing():
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "MSFT"), ("name", "Microsoft"),
        ("category", "stocks"), ("shares", "4"), ("cost_basis", "1000"),
        ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    assert holding.get("region") is None


def test_holding_from_form_rejects_invalid_region():
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "MSFT"), ("name", "Microsoft"),
        ("category", "stocks"), ("shares", "4"), ("cost_basis", "1000"),
        ("currency", "USD"), ("region", "mars"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "region" in error.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_app.py::test_holding_from_form_includes_region tests/test_app.py::test_holding_from_form_region_defaults_to_none_when_missing tests/test_app.py::test_holding_from_form_rejects_invalid_region -v
```

Expected: 3 FAILs — `region` key not in holding dict yet.

- [ ] **Step 3: Update `_holding_from_form` in `app.py`**

Find the `return {` block (around line 266) and add region parsing before it, plus add `"region"` to the returned dict:

```python
    # After the currency line (line 264), add:
    VALID_REGIONS = ("us", "israel", "europe", "china", "developing")
    region_raw = form.get("region", "").strip() or None
    if region_raw is not None and region_raw not in VALID_REGIONS:
        return None, "Invalid region — must be one of: US, Israel, Europe, China, Developing Markets"

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
        "region": region_raw,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }, None
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_app.py::test_holding_from_form_includes_region tests/test_app.py::test_holding_from_form_region_defaults_to_none_when_missing tests/test_app.py::test_holding_from_form_rejects_invalid_region -v
```

Expected: 3 PASSes.

- [ ] **Step 5: Run full test suite to check for regressions**

```
pytest tests/test_app.py -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```
git add app.py tests/test_app.py
git commit -m "feat: add region field to holding form parsing"
```

---

## Task 2: Add region dropdown to savings form

**Files:**
- Modify: `templates/savings_form.html:29-33` (after market toggle block)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:

```python
def test_savings_form_contains_region_select(savings_client):
    c, _ = savings_client
    login(c)
    resp = c.get("/savings/new?category=stocks")
    assert resp.status_code == 200
    assert b'name="region"' in resp.data
    assert b"Israel" in resp.data
    assert b"Europe" in resp.data
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_app.py::test_savings_form_contains_region_select -v
```

Expected: FAIL — region select not in template yet.

- [ ] **Step 3: Add region select to `templates/savings_form.html`**

Insert after the closing `{% endif %}` of the market toggle block (after line 29, before the `<input type="hidden" name="source"...>` line):

```html
        <label>Region (geographic exposure)
            <select name="region">
                <option value="" disabled {% if not form.get('region') and not holding %}selected{% endif %}>— select region —</option>
                <option value="us" {% if (holding and holding.get('region') == 'us') or form.get('region') == 'us' %}selected{% endif %}>US</option>
                <option value="israel" {% if (holding and holding.get('region') == 'israel') or form.get('region') == 'israel' %}selected{% endif %}>Israel</option>
                <option value="europe" {% if (holding and holding.get('region') == 'europe') or form.get('region') == 'europe' %}selected{% endif %}>Europe</option>
                <option value="china" {% if (holding and holding.get('region') == 'china') or form.get('region') == 'china' %}selected{% endif %}>China</option>
                <option value="developing" {% if (holding and holding.get('region') == 'developing') or form.get('region') == 'developing' %}selected{% endif %}>Developing Markets</option>
            </select>
        </label>
```

- [ ] **Step 4: Run test to confirm it passes**

```
pytest tests/test_app.py::test_savings_form_contains_region_select -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add templates/savings_form.html tests/test_app.py
git commit -m "feat: add region dropdown to savings add/edit form"
```

---

## Task 3: Compute geographic breakdown in `savings()` route

**Files:**
- Modify: `app.py:667-780` (`savings()` route body)
- Test: `tests/test_app.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_app.py`:

```python
def test_savings_page_loads_with_region_tagged_holdings(savings_client):
    c, savings_file = savings_client
    savings_file.write_text(json.dumps([
        {"id": "h1", "ticker": "MSFT", "category": "stocks", "source": "yfinance",
         "name": "Microsoft", "tase_id": "", "tase_type": "", "shares": 1,
         "cost_basis": 100, "currency": "USD", "region": "us",
         "last_updated": "2026-06-16T10:00:00+00:00"},
        {"id": "h2", "ticker": "IL1", "category": "mmf", "source": "tase",
         "name": "Local MMF", "tase_id": "999", "tase_type": "fund", "shares": 100,
         "cost_basis": 100, "currency": "ILS", "region": "israel",
         "last_updated": "2026-06-16T10:00:00+00:00"},
        {"id": "h3", "ticker": "EU1", "category": "etf", "source": "tase",
         "name": "EU ETF", "tase_id": "1159094", "tase_type": "etf", "shares": 50,
         "cost_basis": 500, "currency": "ILS", "region": "europe",
         "last_updated": "2026-06-16T10:00:00+00:00"},
    ]))
    login(c)
    resp = c.get("/savings")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_app.py::test_savings_page_loads_with_region_tagged_holdings -v
```

Expected: FAIL — `savings()` crashes because `geo_data` and `geo_pie` aren't computed yet (Jinja2 will get an undefined variable error).

- [ ] **Step 3: Add geo computation to `savings()` in `app.py`**

Add these constants near the top of the `savings()` function body (after the `CATEGORIES = ...` line):

```python
    REGIONS = ("us", "israel", "europe", "china", "developing")
    REGION_LABELS = {
        "us": "US",
        "israel": "Israel",
        "europe": "Europe",
        "china": "China",
        "developing": "Dev. Markets",
    }
```

Then, after the existing `cat_data` / `total_value_ils` / `siemens` block (after line 731, before `total_pl_pct = ...`), add:

```python
    # Geographic breakdown
    geo_data = {}
    for region in REGIONS:
        region_holdings = [h for h in holdings if h.get("region") == region]
        value_ils = sum(holding_data[h["id"]]["current_value_ils"] or 0 for h in region_holdings)
        geo_data[region] = {"value_ils": value_ils, "pct_of_portfolio": 0.0}

    # Siemens is always Europe
    if siemens:
        geo_data["europe"]["value_ils"] += siemens.get("total_value_ils") or 0

    # Unclassified holdings (region is null/missing)
    unclassified_ils = sum(
        holding_data[h["id"]]["current_value_ils"] or 0
        for h in holdings if not h.get("region")
    )

    for region in REGIONS:
        geo_data[region]["pct_of_portfolio"] = (
            geo_data[region]["value_ils"] / total_value_ils * 100 if total_value_ils else 0.0
        )

    geo_pie = {}
    geo_offset = 0.0
    for region in REGIONS:
        pct = geo_data[region]["pct_of_portfolio"]
        dash = round(pct / 100 * 251.33, 2)
        gap = round(251.33 - dash, 2)
        geo_pie[region] = {"dash": dash, "gap": gap, "offset": round(-geo_offset, 2)}
        geo_offset += dash

    if unclassified_ils and total_value_ils:
        pct = unclassified_ils / total_value_ils * 100
        dash = round(pct / 100 * 251.33, 2)
        geo_pie["unclassified"] = {
            "dash": dash,
            "gap": round(251.33 - dash, 2),
            "offset": round(-geo_offset, 2),
        }
```

Add `geo_data`, `geo_pie`, `regions=REGIONS`, `region_labels=REGION_LABELS`, `unclassified_ils=unclassified_ils` to the `render_template(...)` call.

- [ ] **Step 4: Run test to confirm it passes**

```
pytest tests/test_app.py::test_savings_page_loads_with_region_tagged_holdings -v
```

Expected: PASS — route no longer crashes with region-tagged holdings.

- [ ] **Step 4b: Run full test suite**

```
pytest tests/test_app.py -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 5: Commit**

```
git add app.py
git commit -m "feat: compute geographic breakdown in savings route"
```

---

## Task 4: CSS — compact Today's Change card + 5-column grid

**Files:**
- Modify: `static/style.css:543-548` (`.savings-summary` grid) and end of savings section

- [ ] **Step 1: Update `.savings-summary` grid columns**

In `static/style.css`, change the `.savings-summary` rule from:

```css
.savings-summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr) auto;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
    align-items: start;
}
```

to:

```css
.savings-summary {
    display: grid;
    grid-template-columns: 1.4fr 1.4fr 0.5fr auto auto;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
    align-items: start;
}
```

- [ ] **Step 2: Add `.savings-today-compact` modifier**

Append after the `.savings-pie-legend` block (after line 640 in `static/style.css`):

```css
.savings-today-compact .savings-stat-value-large,
.savings-today-compact .savings-stat-amount {
    font-size: 1rem;
}
.savings-today-compact .savings-stat-pct {
    font-size: 0.85rem;
}
.savings-today-compact .savings-stat-breakdown {
    display: none;
}
```

- [ ] **Step 3: Update mobile breakpoints**

Find the `@media (max-width: 900px)` block that overrides `.savings-summary` and update it:

```css
@media (max-width: 900px) {
    .savings-summary {
        grid-template-columns: 1fr 1fr;
    }
```

(No change needed here — `1fr 1fr` already handles both pie cards wrapping. The `600px` breakpoint with `1fr` also stays the same.)

- [ ] **Step 4: Commit**

```
git add static/style.css
git commit -m "feat: 5-column savings grid and compact today card CSS"
```

---

## Task 5: Add Geography donut card to dashboard template

**Files:**
- Modify: `templates/dashboard.html` — savings tab summary section (around line 486-555)

- [ ] **Step 1: Make Today's Change card compact**

Find the Today's Change card div (the one with `savings-stat-label` containing "Today's Change"). Add `savings-today-compact` to its outer div class:

Change:
```html
    <div class="savings-stat-card">
        <div class="savings-stat-label">Today's Change (ILS)</div>
```

To:
```html
    <div class="savings-stat-card savings-today-compact">
        <div class="savings-stat-label">Today's Change (ILS)</div>
```

- [ ] **Step 2: Add Geography donut card after the existing Allocation card**

After the closing `</div>` of the Allocation (pie) card (after line 554, inside `.savings-summary`), add:

```html
    {# Geography donut card #}
    {% set geo_colors = {'us': '#4fc3f7', 'israel': '#e57373', 'europe': '#aed581', 'china': '#ffb74d', 'developing': '#ce93d8'} %}
    <div class="savings-stat-card savings-pie-card">
        <div class="savings-stat-label">Geography</div>
        <svg viewBox="0 0 120 120" width="130" height="130">
            {% for region in regions %}
            {% if geo_data[region].value_ils > 0 %}
            <circle cx="60" cy="60" r="40"
                fill="none"
                stroke="{{ geo_colors[region] }}"
                stroke-width="24"
                stroke-dasharray="{{ geo_pie[region].dash }} {{ geo_pie[region].gap }}"
                stroke-dashoffset="{{ geo_pie[region].offset }}"
                transform="rotate(-90 60 60)"/>
            {% endif %}
            {% endfor %}
            {% if geo_pie.unclassified is defined %}
            <circle cx="60" cy="60" r="40"
                fill="none"
                stroke="#888888"
                stroke-width="24"
                stroke-dasharray="{{ geo_pie.unclassified.dash }} {{ geo_pie.unclassified.gap }}"
                stroke-dashoffset="{{ geo_pie.unclassified.offset }}"
                transform="rotate(-90 60 60)"/>
            {% endif %}
            <circle cx="60" cy="60" r="28" fill="white"/>
            <text x="60" y="56" text-anchor="middle" font-size="9" fill="#7a6a5a">Geo</text>
            <text x="60" y="68" text-anchor="middle" font-size="10" fill="#2d2a24" font-weight="bold">
                ₪{{ "{:,.0f}".format(summary.total_value_ils / 1000) if summary.total_value_ils else '0' }}k
            </text>
        </svg>
        <div class="savings-pie-legend">
            {% for region in regions %}
            {% if geo_data[region].value_ils > 0 %}
            <div class="savings-legend-item">
                <span class="savings-legend-dot" style="background:{{ geo_colors[region] }}"></span>
                <span>{{ region_labels[region] }} — {{ "%.1f"|format(geo_data[region].pct_of_portfolio) }}%</span>
            </div>
            {% endif %}
            {% endfor %}
            {% if geo_pie.unclassified is defined %}
            <div class="savings-legend-item">
                <span class="savings-legend-dot" style="background:#888888"></span>
                <span>Unclassified — {{ "%.1f"|format(unclassified_ils / summary.total_value_ils * 100) if summary.total_value_ils else '0' }}%</span>
            </div>
            {% endif %}
        </div>
    </div>
```

- [ ] **Step 3: Write and run the end-to-end Geography card test**

Append to `tests/test_app.py`:

```python
def test_savings_geography_card_rendered(savings_client):
    c, savings_file = savings_client
    savings_file.write_text(json.dumps([
        {"id": "h1", "ticker": "MSFT", "category": "stocks", "source": "yfinance",
         "name": "Microsoft", "tase_id": "", "tase_type": "", "shares": 1,
         "cost_basis": 100, "currency": "USD", "region": "us",
         "last_updated": "2026-06-16T10:00:00+00:00"},
        {"id": "h2", "ticker": "IL1", "category": "mmf", "source": "tase",
         "name": "Local MMF", "tase_id": "999", "tase_type": "fund", "shares": 100,
         "cost_basis": 100, "currency": "ILS", "region": "israel",
         "last_updated": "2026-06-16T10:00:00+00:00"},
    ]))
    login(c)
    resp = c.get("/savings")
    assert resp.status_code == 200
    assert b"Geography" in resp.data
    assert b"Israel" in resp.data
    assert b"US" in resp.data
```

Run:

```
pytest tests/test_app.py::test_savings_geography_card_rendered -v
```

Expected: PASS.

- [ ] **Step 4: Run full test suite**

```
pytest tests/test_app.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add templates/dashboard.html tests/test_app.py
git commit -m "feat: add geography donut card to savings tab"
```

---

## Task 6: Manual smoke test

- [ ] **Step 1: Start the app**

```
python app.py
```

Open `http://localhost:5000/savings` in a browser (log in if needed).

- [ ] **Step 2: Verify layout**

Confirm the summary row shows 5 cards: Total Portfolio | Total P&L | Today (compact) | Allocation | Geography.

- [ ] **Step 3: Edit an existing holding and set its region**

Click edit on any holding → confirm the Region dropdown appears with the 5 options → save → return to savings page.

- [ ] **Step 4: Verify Geography donut updates**

After tagging at least one holding with a region, confirm its color slice appears in the Geography donut with the correct percentage. Holdings without a region should show a grey "Unclassified" slice.

- [ ] **Step 5: Tag TASE ID 1159094 as Europe**

Edit that ETF holding → select "Europe" → save. Confirm the Europe slice grows in the Geography donut (it already includes Siemens).
