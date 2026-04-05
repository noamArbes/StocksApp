# Visibility Improvements Design

**Date:** 2026-04-05
**Status:** Approved

## Overview

Add visibility features to the StocksApp dashboard: alert history per alarm, creation metadata, alarm sorting, and multi-timeframe charts. Personal-use app deployed on Railway.

## Data Model

Each alarm in `alarms.json` gains three new fields:

```json
{
  "created_at": "2026-04-05T10:00:00+00:00",
  "initial_price": 261.00,
  "history": [
    {
      "triggered_at": "2026-04-05T12:00:00+00:00",
      "type": "upper_limit",
      "price": 283.50,
      "threshold": 280.00
    }
  ]
}
```

- `created_at` — ISO timestamp (UTC) set once at alarm creation
- `initial_price` — stock price fetched live at creation; `null` if fetch fails
- `history` — list of up to 10 most recent alert entries, trimmed on each append

Existing alarms without these fields are handled gracefully: display "N/A" where missing. No migration script needed.

### History entry fields

| Field | Type | Description |
|---|---|---|
| `triggered_at` | ISO string | When the alert email was sent |
| `type` | string | `upper_limit`, `lower_limit`, `upper_pct`, `lower_pct` |
| `price` | float | Stock price at time of trigger |
| `threshold` | float | The limit or percentage that was breached |

## Backend Changes

### `app.py` — alarm creation

In `alarm_new` (POST handler), after form validation and before calling `modify_alarms`:

1. Set `alarm["created_at"] = datetime.now(timezone.utc).isoformat()`
2. Attempt `alarm["initial_price"] = checker.get_price(ticker)` — store `null` on failure, do not block alarm creation

### `checker.py` — alert history

After a successful `send_email` call (both price and percentage alarm paths):

1. Build a history entry dict from `triggered_at`, `type`, `price`, `threshold`
2. Append to `alarm["history"]` (initialising to `[]` if missing)
3. Trim to last 10 entries: `alarm["history"] = alarm["history"][-10:]`
4. Set `changed = True`

### `app.py` — chart endpoint

The `/alarm/<alarm_id>/chart-data` endpoint accepts an optional `?period=` query parameter:

- Allowed values: `5d`, `1mo`, `1y`
- Default: `1mo` (preserves current behaviour)
- Passed directly to `yf.Ticker(ticker).history(period=period)`

## Frontend Changes

### Sorting controls

A row of three buttons at the top of the dashboard, above the alarm list:

- **Newest** (default) — sort by `created_at` descending
- **Oldest** — sort by `created_at` ascending
- **A–Z** — sort alphabetically by `ticker`

Sorting is done server-side: the selected sort order is passed as a query parameter (`?sort=newest|oldest|az`), and the dashboard route sorts the `alarms` list before rendering. No JavaScript required.

Active sort button is visually highlighted using existing CSS conventions.

### Card metadata

Below the current price line on each card, add two small lines:

```
Created: Apr 3 2026 · Initial price: $261.00
```

If `created_at` or `initial_price` is missing, show "N/A" for that field.

### Alert history (collapsible)

A collapsible section at the bottom of each card, above the action buttons:

- Trigger: "History ▾" / "History ▴" toggle (pure HTML `<details>`/`<summary>`, no JS)
- Collapsed by default
- When expanded, shows a compact list of up to 10 entries:
  ```
  Apr 5 2026 — upper limit $280 hit at $283.50
  Mar 28 2026 — lower_pct 5% hit at −6.2%
  ```
- If `history` is empty or missing: "No alerts sent yet."

### Chart timeframe buttons

Above each alarm's chart canvas, add three small buttons: **1W · 1M · 1Y**

- Clicking a button fetches `/alarm/<id>/chart-data?period=<value>` and re-renders the chart
- Active button is highlighted
- Default selection is 1M on page load
- Implemented in the existing inline `<script>` block in `dashboard.html`
