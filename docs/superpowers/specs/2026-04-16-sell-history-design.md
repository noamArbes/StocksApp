# Sell History Design

**Date:** 2026-04-16
**Status:** Approved

## Goal

Add a Sell History feature to track completed stock trades. Users can enter trades manually or create them from an existing alarm. The history is displayed as a tab on the dashboard with a summary card and a sortable table.

---

## User-Facing Features

### 1. Dashboard: Two Tabs

The dashboard gains a tab bar with two tabs: **Alarms** (default) and **Sell History**. Implemented via a `?tab=` query parameter on the existing `/dashboard` route. The sort/owned filter controls remain on the Alarms tab only.

### 2. Sell History Tab Layout

**Summary card** (top, always visible):
- Total trades count
- Total P&L (sum of all trades where shares is provided; blank trades excluded)
- Average % return across all trades
- Best trade (ticker + % gain)

**Table** (below summary card), columns:
| Stock | Shares | Buy Price | Buy Date | Sell Price | Sell Date | % Change | Total P&L | Actions |
|---|---|---|---|---|---|---|---|---|

- % Change = `(sell_price - buy_price) / buy_price * 100`, always computed (no shares needed)
- Total P&L = `(sell_price - buy_price) * shares` — shown as "—" when shares is blank
- Currency symbol ($ or ₪) matches the trade's `source` field (defaults to `$`)
- Positive values shown in green, negative in red
- Actions column: **Edit** | **Delete** buttons per row
- "+ Add Trade" button in the top-right of the tab header

### 3. Record Sale (from an alarm card)

A **"Record Sale"** button appears on alarm cards where `owned = true`. Clicking it opens a dedicated form page (`/alarm/<id>/record-sale`) pre-filled with:
- Stock ticker (from alarm, read-only display but stored as-is)
- Shares (from alarm's `shares` field, editable)
- Buy price (from alarm's `initial_price`, editable)
- Buy date (from alarm's `created_at` date portion, editable)
- Sell price (blank — user must fill in)
- Sell date (today's date pre-filled, editable)

All fields are editable inputs. Required fields: sell price, sell date. A checkbox **"Delete alarm after saving"** (unchecked by default) deletes the alarm when the trade is saved.

### 4. Manual Add Trade

"+ Add Trade" button opens `/trade/new` — same form as Record Sale but all fields blank. Required: ticker, buy price, buy date, sell price, sell date. Shares is optional.

### 5. Edit / Delete Trades

- **Edit**: `/trade/<id>/edit` — same form pre-filled with existing trade data
- **Delete**: `POST /trade/<id>/delete` — confirmation via `onsubmit` JS confirm dialog (same pattern as alarm delete)

### 6. Shares field on Owned Alarm

The alarm form gains an optional **"Number of shares"** field, visible only when the "I own this security" checkbox is checked. Stored as `shares` (integer or null) in the alarm dict. Pre-filled into the Record Sale form.

---

## Data Model

### `trades.json`

New file alongside `alarms.json`, using the same atomic load/save pattern (`load_trades` / `save_trades` in `checker.py`). On Railway, stored at `/data/trades.json`; locally at `trades.json`.

Each trade record:
```json
{
  "id": "a1b2c3d4",
  "ticker": "WDC",
  "source": "yfinance",
  "shares": 20,
  "buy_price": 42.10,
  "buy_date": "2026-01-15",
  "sell_price": 67.80,
  "sell_date": "2026-04-10",
  "created_at": "2026-04-10T14:32:00+00:00"
}
```

- `source`: `"yfinance"` (default) or `"tase"` — determines currency symbol
- `shares`: integer or `null`
- `% change` and `total P&L` are computed at render time, never stored
- `id`: first 8 chars of a UUID4 (same as alarms)

### Alarm dict additions

```json
{
  "shares": 20
}
```

`shares` is `null` when not set. Only meaningful when `owned = true`, but not enforced server-side.

---

## Routes

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard?tab=history` | Sell History tab |
| GET | `/dashboard?tab=alarms` | Alarms tab (default) |
| GET/POST | `/trade/new` | Manual add trade form |
| GET/POST | `/trade/<id>/edit` | Edit existing trade |
| POST | `/trade/<id>/delete` | Delete trade |
| GET/POST | `/alarm/<id>/record-sale` | Pre-filled trade form from alarm |

---

## Architecture

- `checker.py`: add `load_trades(path)`, `save_trades(trades, path)`, `get_trades_path()` — mirrors existing alarm functions exactly
- `app.py`:
  - `read_trades()` / `write_trades()` / `modify_trades()` — mirrors alarm helpers
  - `_trade_from_form(form, existing=None)` — parse and validate trade form data
  - `/dashboard` route: reads `?tab=` param, loads trades when tab is `history`, computes summary stats
  - New CRUD routes for trades
  - `/alarm/<id>/record-sale` route
- `templates/dashboard.html`: tab bar, history tab content (summary card + table) alongside existing alarms content
- `templates/trade_form.html`: new template for add/edit/record-sale (single template, title varies)
- `templates/alarm_form.html`: add optional shares field (shown when owned checkbox is checked)

---

## Out of Scope

- Sorting/filtering the trade table (add later if needed)
- Importing trades from a CSV
- Multiple currencies within a single trade (buy in one currency, sell in another)
- Profit after tax or fees
