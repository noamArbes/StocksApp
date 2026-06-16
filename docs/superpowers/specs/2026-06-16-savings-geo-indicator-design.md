# Savings Tab — Geographic Allocation Indicator

## Overview

Add a "Geography" donut card to the Savings tab summary row showing what percentage of the portfolio is invested in each geographic region (US, Israel, Europe, China, Developing Markets). Region is an explicit field on each holding, set when adding or editing.

---

## Data Model

Add a `region` field to each holding object in `savings.json`.

**Allowed values:** `"us"` | `"israel"` | `"europe"` | `"china"` | `"developing"`

**Nullable:** Yes — existing holdings default to `null` (unclassified) until manually edited. Unclassified value is grouped under an "Unclassified" slice in the donut (shown only if any holdings are unclassified).

**Example holding after change:**
```json
{
  "id": "7cee3e8d",
  "name": "Microsoft Corporation",
  "source": "yfinance",
  "ticker": "MSFT",
  "region": "us",
  ...
}
```

**Why explicit, not inferred:** `source = "tase"` does not imply Israel — TASE-listed ETFs can track US indices (e.g. S&P 500 copies), European indices, or other markets. Geography must be set intentionally by the user.

**Siemens:** Already stored separately (not in `savings.json`). Hardcode its region as `"europe"` in the backend calculation.

---

## Form Changes (`templates/savings_form.html`)

Add a region `<select>` below the market toggle (US / Israeli buttons).

- Label: "Region (geographic exposure)"
- Options: `— select region —` (disabled placeholder), US, Israel, Europe, China, Developing Markets
- Required field on both add and edit
- Pre-selected to the holding's current `region` value on edit

---

## Backend (`app.py` — `savings()` route)

Compute `geo_data` dict in parallel to the existing `cat_data` computation.

```python
REGIONS = ("us", "israel", "europe", "china", "developing")
REGION_LABELS = {
    "us": "US",
    "israel": "Israel",
    "europe": "Europe",
    "china": "China",
    "developing": "Dev. Markets",
}

geo_data = {}
for region in REGIONS:
    region_holdings = [h for h in holdings if h.get("region") == region]
    value_ils = sum(holding_data[h["id"]]["current_value_ils"] or 0 for h in region_holdings)
    geo_data[region] = {
        "value_ils": value_ils,
        "pct_of_portfolio": 0.0,
    }

# Add Siemens to europe
if siemens:
    geo_data["europe"]["value_ils"] += siemens.get("total_value_ils") or 0

# Unclassified (region is null/missing)
unclassified_ils = sum(
    holding_data[h["id"]]["current_value_ils"] or 0
    for h in holdings if not h.get("region")
)

# Compute percentages
for region in REGIONS:
    geo_data[region]["pct_of_portfolio"] = (
        geo_data[region]["value_ils"] / total_value_ils * 100 if total_value_ils else 0.0
    )

# Build donut offsets (same SVG pattern as existing pie)
geo_pie = {}
offset = 0.0
for region in REGIONS:
    pct = geo_data[region]["pct_of_portfolio"]
    dash = round(pct / 100 * 251.33, 2)
    gap = round(251.33 - dash, 2)
    geo_pie[region] = {"dash": dash, "gap": gap, "offset": round(-offset, 2)}
    offset += dash

if unclassified_ils and total_value_ils:
    pct = unclassified_ils / total_value_ils * 100
    dash = round(pct / 100 * 251.33, 2)
    geo_pie["unclassified"] = {"dash": dash, "gap": round(251.33 - dash, 2), "offset": round(-offset, 2)}
```

Pass `geo_data`, `geo_pie`, `region_labels=REGION_LABELS`, `regions=REGIONS` to `render_template`.

---

## Template Changes (`templates/dashboard.html`)

### Today's Change card — compact

Add `savings-today-compact` to the Today's Change card's outer `<div class="savings-stat-card">` element. This hides the per-category breakdown rows and reduces font sizes so the card takes less horizontal space in the grid.

### New Geography card

Add after the existing Allocation (pie) card, using the same `savings-stat-card savings-pie-card` classes.

**Region colors:**
| Region | Color |
|---|---|
| US | `#4fc3f7` |
| Israel | `#e57373` |
| Europe | `#aed581` |
| China | `#ffb74d` |
| Developing Markets | `#ce93d8` |
| Unclassified | `#888888` |

**Donut:** Same SVG circle pattern as existing Allocation card (r=40, stroke-width=24, circumference=251.33).

**Legend:** Region label + percentage, one row per region. Omit rows where `value_ils == 0`.

---

## CSS

Add `.savings-today-compact` modifier:
```css
.savings-today-compact .savings-stat-value-large,
.savings-today-compact .savings-stat-amount { font-size: 1rem; }
.savings-today-compact .savings-stat-breakdown { display: none; }
```

No new classes needed for the Geography card — reuses existing `savings-stat-card`, `savings-pie-card`, `savings-legend-item`, `savings-legend-dot`.

---

## Migration

No automatic migration script. Existing holdings keep `region: null`. The user manually edits each holding to set its region. Unclassified holdings appear as a grey slice in the Geography donut until tagged.

---

## Out of Scope

- Filtering holdings by region
- Per-region P&L
- Historic geographic allocation snapshots
