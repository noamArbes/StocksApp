# Stock Alarm App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python script that runs every 15 minutes on Railway, checks stock prices against user-defined limits, and sends Gmail alerts when a limit is hit.

**Architecture:** A single `checker.py` script with clearly separated functions for price fetching, condition checking, email formatting, email sending, and alarm file I/O. Credentials come from environment variables; alarms are stored in a JSON file on a Railway persistent volume at `/data/alarms.json` (falls back to local `alarms.json` when running locally).

**Tech Stack:** Python 3, `yfinance` (stock prices), `smtplib` (Gmail SMTP), `pytest` (tests), Railway (deployment + cron scheduling)

---

## File Map

| File | Purpose |
|---|---|
| `checker.py` | All application logic + `if __name__ == "__main__"` entry point |
| `alarms.json` | Template alarm file committed to git; copied to `/data/alarms.json` on first Railway deploy |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes `__pycache__`, `.env`, `config.json` |
| `railway.toml` | Railway cron schedule and start command |
| `tests/test_checker.py` | All unit tests |

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `alarms.json`
- Create: `railway.toml`

- [ ] **Step 1: Create `requirements.txt`**

```
yfinance>=0.2.36
pytest>=8.0.0
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
config.json
```

- [ ] **Step 3: Create `alarms.json` template**

```json
[
  {
    "id": "example_alarm",
    "ticker": "AAPL",
    "upper_limit": 230.00,
    "lower_limit": 180.00,
    "email": "you@gmail.com",
    "enabled": false,
    "last_triggered": null
  }
]
```

Note: `enabled` is `false` so this example alarm never fires. The user will add real alarms with `"enabled": true`.

- [ ] **Step 4: Create `railway.toml`**

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python checker.py"
cronSchedule = "*/15 * * * *"
```

- [ ] **Step 5: Create `tests/` directory**

```bash
mkdir tests
```

- [ ] **Step 6: Install dependencies locally**

Run: `pip install -r requirements.txt`

Expected: packages install without errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore alarms.json railway.toml
git commit -m "feat: project scaffold"
```

---

## Task 2: Alarm Condition and Timing Logic

**Files:**
- Create: `checker.py` (condition and timing functions only)
- Create: `tests/test_checker.py`

- [ ] **Step 1: Write failing tests for `condition_met`**

Create `tests/test_checker.py`:

```python
from datetime import datetime, timezone, timedelta
from checker import condition_met, should_alert


# --- condition_met tests ---

def test_price_above_upper_limit():
    alarm = {"upper_limit": 200.0, "lower_limit": None}
    triggered, limit_type, limit_value = condition_met(alarm, 201.0)
    assert triggered is True
    assert limit_type == "upper"
    assert limit_value == 200.0

def test_price_equal_to_upper_limit():
    alarm = {"upper_limit": 200.0, "lower_limit": None}
    triggered, limit_type, limit_value = condition_met(alarm, 200.0)
    assert triggered is True
    assert limit_type == "upper"

def test_price_below_upper_limit():
    alarm = {"upper_limit": 200.0, "lower_limit": None}
    triggered, _, _ = condition_met(alarm, 199.0)
    assert triggered is False

def test_price_below_lower_limit():
    alarm = {"upper_limit": None, "lower_limit": 100.0}
    triggered, limit_type, limit_value = condition_met(alarm, 99.0)
    assert triggered is True
    assert limit_type == "lower"
    assert limit_value == 100.0

def test_price_equal_to_lower_limit():
    alarm = {"upper_limit": None, "lower_limit": 100.0}
    triggered, limit_type, _ = condition_met(alarm, 100.0)
    assert triggered is True
    assert limit_type == "lower"

def test_price_above_lower_limit():
    alarm = {"upper_limit": None, "lower_limit": 100.0}
    triggered, _, _ = condition_met(alarm, 101.0)
    assert triggered is False

def test_no_limits_set():
    alarm = {"upper_limit": None, "lower_limit": None}
    triggered, limit_type, limit_value = condition_met(alarm, 150.0)
    assert triggered is False
    assert limit_type is None
    assert limit_value is None

def test_both_limits_set_upper_triggered():
    alarm = {"upper_limit": 200.0, "lower_limit": 100.0}
    triggered, limit_type, _ = condition_met(alarm, 205.0)
    assert triggered is True
    assert limit_type == "upper"

def test_both_limits_set_lower_triggered():
    alarm = {"upper_limit": 200.0, "lower_limit": 100.0}
    triggered, limit_type, _ = condition_met(alarm, 95.0)
    assert triggered is True
    assert limit_type == "lower"

def test_both_limits_set_no_trigger():
    alarm = {"upper_limit": 200.0, "lower_limit": 100.0}
    triggered, _, _ = condition_met(alarm, 150.0)
    assert triggered is False


# --- should_alert tests ---

def test_should_alert_when_never_triggered():
    alarm = {"last_triggered": None}
    assert should_alert(alarm) is True

def test_should_alert_when_triggered_four_days_ago():
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    alarm = {"last_triggered": four_days_ago}
    assert should_alert(alarm) is True

def test_should_not_alert_when_triggered_two_days_ago():
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    alarm = {"last_triggered": two_days_ago}
    assert should_alert(alarm) is False

def test_should_alert_when_triggered_exactly_three_days_ago():
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    alarm = {"last_triggered": three_days_ago}
    assert should_alert(alarm) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_checker.py -v`

Expected: `ModuleNotFoundError: No module named 'checker'`

- [ ] **Step 3: Create `checker.py` with `condition_met` and `should_alert`**

```python
from datetime import datetime, timezone, timedelta


def condition_met(alarm: dict, price: float) -> tuple:
    """Returns (triggered: bool, limit_type: str | None, limit_value: float | None)"""
    upper = alarm.get("upper_limit")
    lower = alarm.get("lower_limit")

    if upper is not None and price >= upper:
        return True, "upper", upper
    if lower is not None and price <= lower:
        return True, "lower", lower
    return False, None, None


def should_alert(alarm: dict) -> bool:
    """Returns True if enough time has passed since the last alert (or never alerted)."""
    last = alarm.get("last_triggered")
    if last is None:
        return True
    last_dt = datetime.fromisoformat(last)
    return datetime.now(timezone.utc) - last_dt >= timedelta(days=3)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_checker.py -v`

Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: alarm condition and timing logic with tests"
```

---

## Task 3: Email Formatting

**Files:**
- Modify: `checker.py` (add `format_subject`, `format_body`)
- Modify: `tests/test_checker.py` (add formatting tests)

- [ ] **Step 1: Write failing tests for `format_subject` and `format_body`**

Append to `tests/test_checker.py`:

```python
from checker import format_subject, format_body


# --- format_subject tests ---

def test_format_subject_upper_limit():
    subject = format_subject("AAPL", 231.50, "upper", 230.00)
    assert subject == "Stock Alert: AAPL hit $231.50 (upper limit: $230.00)"

def test_format_subject_lower_limit():
    subject = format_subject("TSLA", 98.75, "lower", 100.00)
    assert subject == "Stock Alert: TSLA hit $98.75 (lower limit: $100.00)"


# --- format_body tests ---

def test_format_body_contains_ticker():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "AAPL" in body

def test_format_body_contains_price():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "$231.50" in body

def test_format_body_contains_limit_value():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "$230.00" in body

def test_format_body_contains_limit_type():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "upper" in body

def test_format_body_lower_limit():
    body = format_body("TSLA", 98.75, "lower", 100.00)
    assert "lower" in body
    assert "$98.75" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_checker.py -v -k "format"`

Expected: `ImportError: cannot import name 'format_subject'`

- [ ] **Step 3: Add `format_subject` and `format_body` to `checker.py`**

Append to `checker.py` (after `should_alert`):

```python
def format_subject(ticker: str, price: float, limit_type: str, limit_value: float) -> str:
    return f"Stock Alert: {ticker} hit ${price:.2f} ({limit_type} limit: ${limit_value:.2f})"


def format_body(ticker: str, price: float, limit_type: str, limit_value: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: ${price:.2f}\n"
        f"Limit Triggered: {limit_type} limit (${limit_value:.2f})\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `pytest tests/test_checker.py -v`

Expected: all 21 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: email subject and body formatting with tests"
```

---

## Task 4: Alarm File I/O

**Files:**
- Modify: `checker.py` (add `get_alarms_path`, `load_alarms`, `save_alarms`)
- Modify: `tests/test_checker.py` (add I/O tests)

- [ ] **Step 1: Write failing tests for `load_alarms` and `save_alarms`**

Append to `tests/test_checker.py`:

```python
import json
import os
import tempfile
from checker import load_alarms, save_alarms


# --- load_alarms / save_alarms tests ---

def test_load_alarms_returns_list():
    alarms = [{"id": "a1", "ticker": "AAPL", "enabled": True, "last_triggered": None}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(alarms, f)
        path = f.name
    try:
        result = load_alarms(path)
        assert isinstance(result, list)
        assert result[0]["ticker"] == "AAPL"
    finally:
        os.unlink(path)

def test_save_and_reload_alarms():
    alarms = [{"id": "a1", "ticker": "TSLA", "enabled": False, "last_triggered": "2026-01-01T00:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_alarms(alarms, path)
        result = load_alarms(path)
        assert result[0]["ticker"] == "TSLA"
        assert result[0]["enabled"] is False
        assert result[0]["last_triggered"] == "2026-01-01T00:00:00+00:00"
    finally:
        os.unlink(path)

def test_save_alarms_writes_valid_json():
    alarms = [{"id": "a1", "ticker": "GOOG", "enabled": True, "last_triggered": None}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_alarms(alarms, path)
        with open(path) as f:
            data = json.load(f)
        assert data[0]["ticker"] == "GOOG"
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_checker.py -v -k "alarms"`

Expected: `ImportError: cannot import name 'load_alarms'`

- [ ] **Step 3: Add I/O functions to `checker.py`**

First, add these imports at the **top** of `checker.py` (after the existing `from datetime import ...` line):

```python
import json
import os
import shutil
```

Then append the following constants and functions after `format_body`:

```python
VOLUME_PATH = "/data/alarms.json"
LOCAL_PATH = "alarms.json"


def get_alarms_path() -> str:
    """Returns the path to alarms.json — volume path on Railway, local path otherwise.
    Copies the local template to the volume on first deploy."""
    data_dir = "/data"
    if os.path.isdir(data_dir):
        volume_path = os.path.join(data_dir, "alarms.json")
        if not os.path.exists(volume_path) and os.path.exists(LOCAL_PATH):
            shutil.copy(LOCAL_PATH, volume_path)
        return volume_path
    return LOCAL_PATH


def load_alarms(path: str) -> list:
    with open(path, "r") as f:
        return json.load(f)


def save_alarms(alarms: list, path: str) -> None:
    with open(path, "w") as f:
        json.dump(alarms, f, indent=2)
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `pytest tests/test_checker.py -v`

Expected: all 24 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: alarm file I/O with tests"
```

---

## Task 5: Price Fetching

**Files:**
- Modify: `checker.py` (add `get_price`)

No unit tests for this function — it makes a live network call to Yahoo Finance. It will be exercised in the integration smoke test in Task 7.

- [ ] **Step 1: Add `get_price` to `checker.py`**

Add `import yfinance as yf` at the **top** of `checker.py` (with the other imports).

Then append the function after `save_alarms`:

```python


def get_price(ticker: str) -> float:
    """Fetches the latest price for a ticker from Yahoo Finance.
    Raises ValueError if the price cannot be retrieved."""
    info = yf.Ticker(ticker).fast_info
    price = info.last_price
    if price is None:
        raise ValueError(f"Could not fetch price for ticker: {ticker}")
    return float(price)
```

- [ ] **Step 2: Run existing tests to confirm nothing broke**

Run: `pytest tests/test_checker.py -v`

Expected: all 24 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add checker.py
git commit -m "feat: price fetching via yfinance"
```

---

## Task 6: Email Sending

**Files:**
- Modify: `checker.py` (add `send_email`)

No unit tests for this function — it makes a live SMTP connection. It will be tested manually in Task 7.

- [ ] **Step 1: Add `send_email` to `checker.py`**

Add these imports at the **top** of `checker.py` (with the other imports):

```python
import smtplib
from email.mime.text import MIMEText
```

Then append the function after `get_price`:

```python


def send_email(subject: str, body: str, to: str, sender: str, password: str) -> None:
    """Sends an email via Gmail SMTP SSL."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)
```

- [ ] **Step 2: Run existing tests to confirm nothing broke**

Run: `pytest tests/test_checker.py -v`

Expected: all 24 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add checker.py
git commit -m "feat: email sending via Gmail SMTP"
```

---

## Task 7: Main Orchestration + Smoke Test

**Files:**
- Modify: `checker.py` (add `run` function and `__main__` block)

- [ ] **Step 1: Add `run()` and `__main__` to `checker.py`**

Append to `checker.py` (at the bottom):

```python
def run() -> None:
    sender = os.environ.get("GMAIL_SENDER")
    password = os.environ.get("GMAIL_APP_PASSWORD")

    if not sender or not password:
        raise EnvironmentError(
            "Missing required environment variables: GMAIL_SENDER and GMAIL_APP_PASSWORD"
        )

    path = get_alarms_path()
    alarms = load_alarms(path)
    changed = False

    for alarm in alarms:
        if not alarm.get("enabled", False):
            print(f"[SKIP] {alarm.get('id', alarm.get('ticker'))} is disabled")
            continue

        ticker = alarm["ticker"]

        try:
            price = get_price(ticker)
            print(f"[FETCH] {ticker}: ${price:.2f}")
        except Exception as e:
            print(f"[ERROR] Could not fetch price for {ticker}: {e}")
            continue

        triggered, limit_type, limit_value = condition_met(alarm, price)

        if triggered:
            if should_alert(alarm):
                subject = format_subject(ticker, price, limit_type, limit_value)
                body = format_body(ticker, price, limit_type, limit_value)
                try:
                    send_email(subject, body, alarm["email"], sender, password)
                    alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                    changed = True
                    print(f"[ALERT] Email sent for {ticker} at ${price:.2f}")
                except Exception as e:
                    print(f"[ERROR] Could not send email for {ticker}: {e}")
            else:
                print(f"[SKIP] {ticker} condition met but alert sent recently, skipping")
        else:
            if alarm.get("last_triggered") is not None:
                alarm["last_triggered"] = None
                changed = True
            print(f"[OK] {ticker}: ${price:.2f} — no condition met")

    if changed:
        save_alarms(alarms, path)
        print(f"[SAVED] Updated alarms saved to {path}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run all tests to confirm nothing broke**

Run: `pytest tests/test_checker.py -v`

Expected: all 24 tests PASS.

- [ ] **Step 3: Smoke test — run the script locally with a real ticker**

First, temporarily edit `alarms.json` to set `"enabled": true` on the example alarm and set a price limit you know will NOT be hit (e.g., upper_limit of 99999). Set env vars:

On Windows (PowerShell):
```powershell
$env:GMAIL_SENDER="your_bot@gmail.com"
$env:GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
python checker.py
```

On Mac/Linux:
```bash
GMAIL_SENDER="your_bot@gmail.com" GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" python checker.py
```

Expected output (example):
```
[FETCH] AAPL: $225.43
[OK] AAPL: $225.43 — no condition met
```

Then test a trigger: set `upper_limit` to a value below the current price, run again.

Expected output:
```
[FETCH] AAPL: $225.43
[ALERT] Email sent for AAPL at $225.43
[SAVED] Updated alarms saved to alarms.json
```

Check your inbox for the email. Verify `alarms.json` now has a `last_triggered` timestamp.

Revert `alarms.json` to `"enabled": false` after the smoke test.

- [ ] **Step 4: Commit**

```bash
git add checker.py
git commit -m "feat: main orchestration and entry point"
```

---

## Task 8: Railway Deployment

**Files:**
- No code changes — deployment configuration only

- [ ] **Step 1: Push the repo to GitHub**

1. Go to [github.com](https://github.com) and create a new repository called `StocksApp`
2. Run:
```bash
git remote add origin https://github.com/<your-username>/StocksApp.git
git push -u origin master
```

- [ ] **Step 2: Create a Railway project**

1. Go to [railway.app](https://railway.app) and sign up / log in
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `StocksApp` repository
4. Railway will detect the Python project automatically via `railway.toml`

- [ ] **Step 3: Add a persistent volume**

1. In your Railway project, click **Add Service** → **Volume**
2. Set the mount path to `/data`
3. Attach it to your `StocksApp` service

- [ ] **Step 4: Set up Gmail app password**

1. Go to your Google account at [myaccount.google.com](https://myaccount.google.com)
2. Go to **Security** → enable **2-Step Verification** (required before the next step)
3. Go to **Security** → **App Passwords** (search for "App Passwords" in the search bar if you can't find it)
4. Select app: **Mail**, select device: **Other** → name it "StocksApp" → click **Generate**
5. Copy the 16-character password shown (you'll only see it once)

- [ ] **Step 5: Set environment variables**

In your Railway project → your service → **Variables** tab, add:

| Variable | Value |
|---|---|
| `GMAIL_SENDER` | your Gmail address |
| `GMAIL_APP_PASSWORD` | your 16-character app password |

- [ ] **Step 6: Verify the cron schedule**

In Railway → your service → **Settings**, confirm the cron schedule shows `*/15 * * * *` (set by `railway.toml`). If not, enter it manually there.

- [ ] **Step 7: Trigger a manual run and check logs**

In Railway → your service → **Deployments**, click **Run** to trigger the script manually.

Then go to **Logs** and verify output like:
```
[SKIP] example_alarm is disabled
```

This confirms the script runs successfully on Railway.

- [ ] **Step 8: Add your first real alarm**

Edit `alarms.json` locally:

```json
[
  {
    "id": "my_first_alarm",
    "ticker": "AAPL",
    "upper_limit": 300.00,
    "lower_limit": 150.00,
    "email": "your-real-email@gmail.com",
    "enabled": true,
    "last_triggered": null
  }
]
```

Commit and push:
```bash
git add alarms.json
git commit -m "chore: add first real alarm"
git push
```

Railway will auto-redeploy. Your alarm is now live.
