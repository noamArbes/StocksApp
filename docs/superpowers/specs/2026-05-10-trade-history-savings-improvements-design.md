# Design Spec: Trade History, Savings P&L Coloring, Siemens Program, Favicon

**Date:** 2026-05-10
**Status:** Approved

---

## Overview

Four independent improvements to the StocksApp:

1. **Trade History** — extend the Sell History tab to also log buy records
2. **P&L coloring fix** — fix CSS specificity bug hiding green/red colors in Savings holdings table
3. **Siemens Matching Program** — a manually-updated summary card at the bottom of the Savings tab
4. **Favicon** — add a bell icon to the browser tab

---

## Feature 1 — Trade History

### Goal
The "Sell History" tab currently only tracks completed sell trades. The user wants to also log buy trades as a reference log (no live price calculation).

### Tab rename
- "Sell History" → **"Trade History"** everywhere (tab label, page title, route redirects)

### Data model
- Add `type` field to the trade dict: `"buy"` or `"sell"`
- Existing records without `type` default to `"sell"` (backward-compatible)
- Buy records omit `sell_price` and `sell_date` (both `None`)
- Sell records remain unchanged

Trade dict shape:
```json
{
  "id": "abc12345",
  "type": "sell",
  "ticker": "AAPL",
  "source": "yfinance",
  "shares": 10,
  "buy_price": 210.0,
  "buy_date": "2025-01-05",
  "sell_price": 240.0,
  "sell_date": "2025-01-20",
  "created_at": "2025-01-20T10:00:00+00:00"
}
```

Buy record:
```json
{
  "id": "def67890",
  "type": "buy",
  "ticker": "MSFT",
  "source": "yfinance",
  "shares": 5,
  "buy_price": 390.0,
  "buy_date": "2025-01-10",
  "sell_price": null,
  "sell_date": null,
  "created_at": "2025-01-10T10:00:00+00:00"
}
```

### Form (`trade_form.html`)
- New **Trade Type** dropdown at the top: "Buy" / "Sell"
- When type = "Buy": sell price and sell date fields are hidden (via JS)
- When type = "Sell": form is unchanged from today
- `_trade_from_form()` in `app.py`: sell_price and sell_date become optional when `type == "buy"`; validation only requires them for sell records

### Table (`dashboard.html` history section)
- New **Type** column (first column) showing a badge: green "Buy" or red "Sell"
- Buy rows show: type, ticker, shares, buy price, buy date, `—` for sell price, `—` for sell date, `—` for P&L
- Sell rows unchanged
- Summary cards (count, total P&L, avg return, best trade) count **sell records only** — buy records excluded

### Tests
- `_trade_from_form` with `type=buy` accepts missing sell fields
- `_trade_from_form` with `type=sell` still requires sell fields
- Dashboard history tab renders buy and sell rows correctly

---

## Feature 2 — P&L Coloring Fix (Savings tab)

### Root cause
`.savings-holdings-table td { color: #2d2a24; }` has CSS specificity `0,1,1` which overrides `.value-positive { color: #22c55e; }` (specificity `0,1,0`).

### Fix
Add two rules to `style.css` after the existing `.value-positive` / `.value-negative` rules:

```css
.savings-holdings-table td.value-positive { color: #22c55e; }
.savings-holdings-table td.value-negative { color: #ef4444; }
```

No Python or template changes needed.

---

## Feature 3 — Siemens Matching Program

### Goal
A manually-updated summary card at the bottom of the Savings tab tracking the user's Siemens Employee Share Program. The user updates it periodically by copying figures from the Siemens portal.

### Data model (`siemens.json`)
```json
{
  "shares": 24.83,
  "total_value_ils": 42500,
  "gain_ils": 3200,
  "gain_pct": 8.1,
  "last_updated": "2026-05-07T10:00:00+00:00"
}
```
- File lives alongside `savings.json` (same directory, Railway volume)
- If file doesn't exist, the section renders an empty state with an "Add details" button

### Portal URL
Hard-coded constant in `app.py`:
```python
SIEMENS_PORTAL_URL = "https://samlparticipant.equateplus.com/EquatePlusParticipant2/start"
```

### Display (bottom of Savings tab)
- Section heading: **"Siemens Matching Program"** (same visual style as category headings)
- Compact card showing 4 stats in a row: Shares · Value (₪) · Gain (₪) · Gain %
- Gain values colored green/red using existing `value-positive` / `value-negative` classes (inline style on the element, not table td — no specificity conflict)
- **Open Portal** button (links to `SIEMENS_PORTAL_URL`, opens in new tab)
- **Edit** button → `/siemens/edit` form
- "Updated X days/hours ago" timestamp (relative, computed in Python)

### Portfolio summary integration
- `total_value_ils` added to `summary.total_value_ils`
- `gain_ils` added to `total_pl_ils`
- Cost basis derived as `total_value_ils - gain_ils`, added to `total_cost_ils` (used for `total_pl_pct` denominator)
- Siemens contributes **0** to `total_today_ils` (no daily change — manually updated)
- Siemens is shown as its own row in the P&L breakdown in the summary cards (label: "Siemens Program")

### Routes
| Route | Method | Purpose |
|---|---|---|
| `/siemens/edit` | GET | Render edit form pre-filled with current values |
| `/siemens/edit` | POST | Validate, save, redirect to `savings` |

### Edit form fields
- Shares (number, required)
- Total Value ₪ (number, required)
- Gain ₪ (number, required — can be negative)
- Gain % (number, required — can be negative)

### Tests
- Savings route includes Siemens value in portfolio total
- `/siemens/edit` GET returns 200
- `/siemens/edit` POST saves correctly and redirects
- Missing `siemens.json` renders empty state without error

---

## Feature 4 — Favicon

### Goal
Show a bell icon on the browser tab.

### Implementation
- Create `static/favicon.svg`: a simple SVG with a 🔔 bell character on a dark background matching the app's color scheme (`#1e1a18` background, `#f0b840` bell)
- Add to `<head>` in `base.html`:
  ```html
  <link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='favicon.svg') }}">
  ```

No backend changes needed.

---

## What's NOT in scope
- Live price fetching for Siemens (all values manually entered)
- Matching event history log (the 4-year match hasn't happened yet; the edit form handles it when it does — user just updates shares and gain)
- Sorting savings holdings by % of category (removed from scope per user request)
- Unrealized P&L on buy records in Trade History
