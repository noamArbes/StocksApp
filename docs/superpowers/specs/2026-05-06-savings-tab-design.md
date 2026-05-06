# Savings Tab — Design Spec
**Date:** 2026-05-06  
**Status:** Approved

---

## Overview

Add a new "Savings" tab to the existing dashboard alongside Alarms and Sell History. The tab tracks the user's investment portfolio across three categories: Stocks, ETFs, and Money Market Funds (MMF). It shows live prices, P&L since cost basis, today's change, allocation breakdown, and a 30-day growth chart. Holdings can be added, edited, and deleted. The user updates their holdings daily.

---

## Data Model

### `savings.json`
A JSON array of holding objects, stored at the project root (same pattern as `alarms.json` and `trades.json`).

```json
[
  {
    "id": "uuid4",
    "name": "Vanguard S&P 500",
    "category": "etf",
    "source": "yfinance",
    "ticker": "VOO",
    "tase_id": "",
    "tase_type": "",
    "shares": 23.5,
    "cost_basis": 8200.00,
    "currency": "USD",
    "last_updated": "2026-05-06T10:30:00+03:00"
  }
]
```

**Field notes:**
- `category`: one of `"stocks"`, `"etf"`, `"mmf"`
- `source`: `"yfinance"` for US securities, `"tase"` for Israeli securities
- `cost_basis`: total amount paid across all purchases (user calculates their own average), in the holding's native currency
- `shares`: total shares owned (fractional allowed)
- `currency`: `"USD"` or `"ILS"`

### `savings_snapshots.json`
A JSON array of daily portfolio total snapshots for the 30-day growth chart.

```json
[
  { "date": "2026-04-06", "total_ils": 445200.0 },
  { "date": "2026-05-06", "total_ils": 487340.0 }
]
```

One record per day, appended on the first page load after midnight. Only the last 90 days are kept.

---

## Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/savings` | Main savings tab |
| GET | `/savings/new` | Add holding form (accepts `?category=etf\|stocks\|mmf`) |
| POST | `/savings/new` | Submit new holding |
| GET | `/savings/<id>/edit` | Edit holding form |
| POST | `/savings/<id>/edit` | Submit holding update |
| POST | `/savings/<id>/delete` | Delete holding |
| POST | `/savings/<id>/shares` | Inline shares update (AJAX, returns JSON) |

---

## Live Prices & Currency Conversion

- **US stocks/ETFs** (`source: yfinance`): fetched via `yfinance` on page load, same pattern as alarm price checks
- **Israeli securities/MMF** (`source: tase`): fetched via TASE API, same pattern as existing TASE alarms
- **USD → ILS exchange rate**: fetched from `yfinance` using ticker `ILS=X` once per page load
- Each holding is displayed in its **own native currency** (USD or ILS)
- Category subtotals and portfolio totals are shown in **ILS** (converted using live rate)
- Today's change = `(current_price - previous_close) × shares`, converted to ILS for totals

---

## Savings Tab Page Layout

### 1. Tab Bar
```
Alarms | Sell History | Savings ←
```
Added as a third tab in `dashboard.html`.

### 2. Summary Row (4 cards)

| Card | Content |
|------|---------|
| **Total Portfolio (ILS)** | Large number (2rem). Sub-line: "across all categories". Below: 30-day growth sparkline chart |
| **Total P&L (ILS)** | Amount (1.4rem, colored). Percentage below (1.05rem, same color). Below: breakdown by category |
| **Today's Change (ILS)** | Amount (1.4rem, colored). Percentage below (1.05rem). Below: breakdown by category |
| **Allocation** | Donut pie chart showing % split across ETFs / Stocks / MMF with color-coded legend |

### 3. Category Sections (one each for ETFs, Stocks, MMF)
Each section is collapsible. Header shows:
- Colored dot matching pie chart color
- Category name
- Total value in ILS
- Total P&L in ILS
- Today's change in ILS
- % of total portfolio

Expanded section shows a holdings table:

| Column | Notes |
|--------|-------|
| Name / Ticker | Ticker bold, full name smaller below |
| Shares | Inline-editable (click pencil icon → input → save via AJAX) |
| Cost Basis | In native currency |
| Price | Live price in native currency |
| Value | `shares × price` in native currency |
| P&L | Amount + % since cost basis, colored green/red |
| Today | Day's change in native currency, colored |
| % of Category | Small horizontal bar + percentage |
| Updated | Relative time ("now", "2h ago") |
| Actions | Edit button (full form) + Delete (×) button |

Each category section has a "+ Add [Category]" button at the bottom.

### 4. Add/Edit Holding Form (`savings_form.html`)
Fields:
- Category (pre-selected, read-only on edit)
- Market toggle: US / Israeli (same as alarm form)
- Ticker / TASE search (same autocomplete as alarm form)
- Name (auto-filled from ticker lookup, editable)
- Shares (number, fractional allowed)
- Cost Basis (number, in native currency)
- Currency (auto-set from market: USD for US, ILS for Israeli)

---

## Daily Snapshot Logic

On every `/savings` page load:
1. Check the last entry in `savings_snapshots.json`
2. If it's from a previous calendar day (or file is empty), compute current total ILS and append a new record
3. Trim records older than 90 days
4. Pass the last 30 days of records to the template for the sparkline chart

---

## Alert Form Changes (small, independent)

In `alarm_form.html`:
- Email field: pre-filled with `noamarbes1@gmail.com` when creating a new alarm (editable). On edit, shows the stored value as usual.
- City field: pre-filled with `Tel Aviv` when creating a new alarm (editable, still triggers timezone autocomplete as normal)
- Both defaults only apply when `alarm` is `None` (new alarm, not edit)

---

## Typography (Summary Cards)

- Total Portfolio amount: `font-size: 2rem`, `font-weight: 700`
- P&L / Today's Change amount: `font-size: 1.4rem`, `font-weight: 700`
- P&L / Today's Change percentage: `font-size: 1.05rem`, `font-weight: 600` (secondary but prominent)
- All colored green (`#2e7d32`) for positive, red (`#c62828`) for negative

---

## File Changes Summary

| File | Change |
|------|--------|
| `app.py` | Add savings routes, price fetch logic, snapshot logic |
| `checker.py` | Add `load_savings`, `save_savings`, `load_snapshots`, `save_snapshots` |
| `templates/dashboard.html` | Add Savings tab to tab bar + savings tab content |
| `templates/savings_form.html` | New file — add/edit holding form |
| `templates/alarm_form.html` | Pre-fill email and city defaults |
| `static/style.css` | Add savings tab styles (summary cards, pie, category sections, holdings table) |
| `savings.json` | New data file (created on first use) |
| `savings_snapshots.json` | New data file (created on first use) |
