# Spec: Web UI for Stock Alarm App

## Overview

A mobile-first, password-protected web UI hosted on Railway alongside the existing stock alarm checker. Users can view, add, edit, and delete alarms through the browser instead of editing JSON manually. Each alarm card shows the current price and a 30-day mini chart.

---

## Architecture

Single Railway service running Flask continuously. APScheduler replaces the Railway cron — the checker logic runs every 15 minutes inside the app process. `checker.py` is unchanged and imported by `app.py`.

```
app.py              — Flask web server + APScheduler
checker.py          — unchanged, imported by app.py
templates/
  base.html         — shared mobile-first layout, session gate
  dashboard.html    — alarm list with status cards and mini charts
  alarm_form.html   — add/edit alarm form
static/
  style.css         — mobile-first styles
railway.toml        — startCommand → "python app.py", cronSchedule removed
requirements.txt    — adds flask, apscheduler
```

---

## Routes

| Route | Method | Description |
|---|---|---|
| `/` | GET | Redirect to dashboard if logged in, else login page |
| `/login` | POST | Verify password, set session, redirect to dashboard |
| `/logout` | GET | Clear session, redirect to login |
| `/dashboard` | GET | All alarms as cards with price, status, mini chart |
| `/alarm/new` | GET | Add alarm form |
| `/alarm/new` | POST | Save new alarm to alarms.json |
| `/alarm/<id>/edit` | GET | Edit alarm form (pre-filled) |
| `/alarm/<id>/edit` | POST | Save changes to alarms.json |
| `/alarm/<id>/delete` | POST | Delete alarm from alarms.json |
| `/alarm/<id>/toggle` | POST | Toggle enabled/disabled, redirect to dashboard |
| `/alarm/<id>/chart-data` | GET | 30-day price history as JSON for Chart.js |

---

## Pages

### Login
Simple centered form with a password field. Shows an error message on wrong password. No lockout (personal tool).

### Dashboard
One card per alarm showing:
- Ticker name and enabled/disabled toggle
- Condition: price alarm (e.g. "↑ $280.00") or percentage alarm (e.g. "±5%")
- Current price (fetched live from yfinance)
- Last triggered date (or "Never")
- 30-day mini price chart (Chart.js, loaded via CDN)
- Edit and Delete buttons
- Enabled toggle — clicking it immediately POSTs to `/alarm/<id>/toggle` and refreshes the page

"Add Alarm" button at the top.

### Add/Edit Alarm Form
Fields:
- Ticker (text, required)
- Alarm type: Price Limits or Percentage Change (radio, switches visible fields)
- If Price Limits: Upper Limit (number, optional), Lower Limit (number, optional)
- If Percentage Change: Rise % (number, optional), Drop % (number, optional)
- Email(s) (text, comma-separated for multiple — app converts to/from JSON array on save/load)
- Timezone (text, e.g. "Asia/Jerusalem", optional — defaults to UTC)
- Enabled (checkbox)

---

## Data & State

- Alarms read/written from the same `alarms.json` / Railway volume path as the checker
- A threading lock (`threading.Lock`) protects all file reads and writes
- Flask sessions use signed cookies with `SECRET_KEY` env var
- Chart data fetched live from yfinance on demand (no caching)
- `base_price` and `last_triggered` fields are read-only in the UI — managed by the checker

### New Environment Variables (add in Railway)
- `UI_PASSWORD` — password to access the UI
- `SECRET_KEY` — random string for Flask session signing (e.g. generate with `python -c "import secrets; print(secrets.token_hex())"`)

---

## Scheduling

APScheduler runs `checker.run()` every 15 minutes inside the Flask process. The Railway `cronSchedule` is removed from `railway.toml`. The start command changes from `python checker.py` to `python app.py`.

---

## Error Handling

| Situation | Behavior |
|---|---|
| Wrong password | Show error on login page, no lockout |
| Missing `UI_PASSWORD` or `SECRET_KEY` | App refuses to start with a clear error message |
| File locked during concurrent access | Retry once, return "try again" response if still locked |
| yfinance fetch fails (price or chart) | Show "unavailable" gracefully in the card |
| Invalid form input (bad ticker, non-numeric value) | Inline error on form, do not save |

---

## Out of Scope

- User accounts / per-user alarms
- Push notifications
- Price alerts history log
- Chart date range controls
- Dark mode
