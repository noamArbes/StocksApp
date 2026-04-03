# Stock Alarm App — Design Spec
*Date: 2026-04-03*

## Overview

A Python script that runs on Railway (a beginner-friendly cloud platform) every 15 minutes, checks stock prices against user-defined limits, and sends email alerts via Gmail when a limit is hit. Alarms are managed by editing a JSON config file. The app runs 24/7 independently of the user's computer.

---

## Architecture

**Language:** Python 3  
**Deployment:** Railway (cloud platform, no command line needed)  
**Scheduling:** Railway cron job — triggers every 15 minutes  
**Stock data:** Yahoo Finance via `yfinance` library  
**Email:** Gmail SMTP with app password  

**Project structure:**
```
StocksApp/
├── checker.py         # main script
├── alarms.json        # alarm definitions template (committed to git)
└── requirements.txt   # Python dependencies
```

At runtime, `alarms.json` is read from and written to the Railway persistent volume at `/data/alarms.json`. The copy in the repo serves as the initial template and is copied to the volume on first deploy.

**Credentials** (Gmail sender, app password) are stored as environment variables in Railway's dashboard — never in files, never committed to git.

---

## Data Shapes

### `alarms.json`

A JSON array of alarm objects. The user edits this file to add, modify, or disable alarms.

```json
[
  {
    "id": "alarm_1",
    "ticker": "AAPL",
    "upper_limit": 230.00,
    "lower_limit": 180.00,
    "email": "you@gmail.com",
    "enabled": true,
    "last_triggered": null
  }
]
```

**Fields:**
- `id` — human-readable label for the alarm
- `ticker` — stock symbol (e.g., `"AAPL"`, `"TSLA"`)
- `upper_limit` — optional; alert if price >= this value
- `lower_limit` — optional; alert if price <= this value
- `email` — address to send the alert to
- `enabled` — set to `false` to manually disable the alarm
- `last_triggered` — UTC timestamp of the last sent alert, or `null` if never triggered

`alarms.json` is stored on a Railway persistent volume so changes survive restarts and redeployments.

---

## Core Logic (`checker.py`)

On each run (triggered by Railway cron every 15 minutes):

1. Load `alarms.json` from the persistent volume
2. Read Gmail credentials from environment variables
3. For each alarm where `"enabled": true`:
   - Fetch current price via `yfinance.Ticker(ticker).fast_info.last_price`
   - Check if a condition is met:
     - `upper_limit` is set and `price >= upper_limit`
     - `lower_limit` is set and `price <= lower_limit`
   - If a condition is met:
     - If `last_triggered` is `null` → send alert immediately
     - If `last_triggered` is set → send alert only if 3+ days have passed since then
     - On sending: update `last_triggered` to current UTC timestamp
   - If no condition is met:
     - Reset `last_triggered` to `null` (so next trigger sends an immediate alert)
4. Save updated `alarms.json` back to the persistent volume
5. Script exits — Railway cron picks it up again in 15 minutes

**Email format:**
- Subject: `Stock Alert: AAPL hit $231.50 (upper limit: $230.00)`
- Body: ticker, current price, which limit was hit, limit value, timestamp

---

## Error Handling

- **Bad ticker / network error fetching price:** Log the error, skip that alarm, continue with the rest. Do not crash.
- **Email sending failure:** Log the error, do NOT update `last_triggered` (alarm retries next cycle).
- All output is printed to stdout and visible in Railway's logs dashboard (no log file needed).

---

## Alarm Lifecycle

| State | Description |
|---|---|
| `enabled: true`, `last_triggered: null` | Active, never triggered |
| `enabled: true`, `last_triggered: <timestamp>` | Active, alert sent — resends after 3 days if condition still met |
| `enabled: false` | Manually disabled — will never trigger |

---

## Deployment (Step-by-Step, No Command Line Needed)

1. Create a free account at [railway.app](https://railway.app)
2. Connect your GitHub account and push this repo to GitHub
3. In Railway: create a new project → deploy from GitHub repo
4. Add a persistent volume in Railway and mount it at `/data`
5. Set environment variables in Railway's dashboard:
   - `GMAIL_SENDER` — your Gmail address
   - `GMAIL_APP_PASSWORD` — your 16-character Gmail app password
6. Set the cron schedule in Railway: `*/15 * * * *`
7. Edit `alarms.json` locally, commit, and push — Railway auto-redeploys

**To add/modify an alarm:** Edit `alarms.json`, commit, and push to GitHub.  
**To disable an alarm:** Set `"enabled": false` in `alarms.json`, commit, and push.  
**To check logs:** View them in Railway's web dashboard.

---

## Gmail Setup (One-Time)

1. Go to your Google account → Security → enable 2-Step Verification
2. Go to Security → App Passwords
3. Generate a new app password for "Mail"
4. Paste the 16-character password into Railway's environment variables as `GMAIL_APP_PASSWORD`

---

## Future Stages

- REST API for managing alarms (instead of editing JSON and pushing to GitHub)
- Web UI for adding/removing/disabling alarms without touching code
- Support for multiple notification channels (SMS, push notifications)
