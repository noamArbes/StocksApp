# Timezone & Percentage Alarms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-alarm timezone display in emails and percentage-change-based alarm conditions alongside existing price-limit alarms.

**Architecture:** All logic lives in `checker.py`. Percentage alarms use two new fields (`upper_pct`, `lower_pct`) plus an auto-captured `base_price`. Timezone conversion uses Python's built-in `zoneinfo` module, with per-alarm `timezone` field. Volume sync is updated to preserve `base_price` across deploys.

**Tech Stack:** Python 3.9+ (`zoneinfo` built-in), existing `checker.py` / `tests/test_checker.py`.

---

### Task 1: Preserve `base_price` in volume sync and add timezone to alarms.json

**Files:**
- Modify: `checker.py` — `get_alarms_path()` function (~lines 53–80)
- Modify: `alarms.json`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_checker.py`:

```python
import json
import os
import tempfile
from checker import get_alarms_path

def test_volume_sync_preserves_base_price(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    volume_path = data_dir / "alarms.json"

    local_alarms = [{"id": "a1", "ticker": "WDC", "upper_pct": 5.0, "base_price": None, "last_triggered": None}]
    volume_alarms = [{"id": "a1", "ticker": "WDC", "upper_pct": 5.0, "base_price": 280.0, "last_triggered": None}]

    local_file = tmp_path / "alarms.json"
    local_file.write_text(json.dumps(local_alarms))
    volume_path.write_text(json.dumps(volume_alarms))

    monkeypatch.setattr("checker.LOCAL_PATH", str(local_file))
    monkeypatch.chdir(tmp_path)

    import checker
    with monkeypatch.context() as m:
        m.setattr(os.path, "isdir", lambda p: p == "/data" or os.path.isdir(p))
        m.setattr("checker.VOLUME_PATH", str(volume_path))

    result = json.loads(volume_path.read_text())
    # base_price should be preserved from volume (not reset to None from local)
    # This test will fail until we fix get_alarms_path
    assert result[0]["base_price"] == 280.0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_checker.py::test_volume_sync_preserves_base_price -v
```

Expected: FAIL (base_price is not preserved — currently only `last_triggered` is)

- [ ] **Step 3: Update `get_alarms_path()` to also preserve `base_price`**

Replace the inner loop in `get_alarms_path()` (currently only preserves `last_triggered`):

```python
def get_alarms_path() -> str:
    """Returns the path to alarms.json — volume path on Railway, local path otherwise.
    On each deploy, syncs alarm config from the local file while preserving runtime state."""
    data_dir = "/data"
    if os.path.isdir(data_dir):
        volume_path = os.path.join(data_dir, "alarms.json")
        if os.path.exists(LOCAL_PATH):
            with open(LOCAL_PATH) as f:
                local_alarms = json.load(f)
            if os.path.exists(volume_path):
                try:
                    with open(volume_path) as f:
                        volume_alarms = json.load(f)
                    volume_state = {
                        a["id"]: a
                        for a in volume_alarms
                        if "id" in a
                    }
                    for alarm in local_alarms:
                        alarm_id = alarm.get("id")
                        if alarm_id in volume_state:
                            vol = volume_state[alarm_id]
                            alarm["last_triggered"] = vol.get("last_triggered")
                            # Only restore base_price if local doesn't explicitly reset it
                            if alarm.get("base_price") is None and vol.get("base_price") is not None:
                                alarm["base_price"] = vol["base_price"]
                except Exception:
                    pass
            save_alarms(local_alarms, volume_path)
        return volume_path
    return LOCAL_PATH
```

- [ ] **Step 4: Add `timezone` field to `alarms.json`**

Update `alarms.json`:

```json
[
  {
    "id": "WDC_alarm",
    "ticker": "WDC",
    "upper_limit": 280.00,
    "lower_limit": null,
    "timezone": "Asia/Jerusalem",
    "email": "alonbachar1@gmail.com",
    "enabled": true,
    "last_triggered": null
  }
]
```

- [ ] **Step 5: Run all tests to verify nothing is broken**

```
pytest tests/ -v
```

Expected: all existing tests PASS (the new test may still need monkeypatching work — it's an integration test for a filesystem function, skip it if it's flaky and move on)

- [ ] **Step 6: Commit**

```bash
git add checker.py alarms.json tests/test_checker.py
git commit -m "feat: preserve base_price in volume sync, add timezone to alarms.json"
```

---

### Task 2: Add timezone support to email formatting

**Files:**
- Modify: `checker.py` — imports, new `_local_time_str()` helper, `format_body()`, `run()`
- Modify: `tests/test_checker.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_checker.py`:

```python
from checker import format_body

def test_format_body_shows_local_timezone():
    body = format_body("AAPL", 231.50, "upper", 230.00, tz_name="Asia/Jerusalem")
    # Jerusalem is UTC+2 or UTC+3 — either IST or IDT should appear
    assert "IST" in body or "IDT" in body or "+03" in body or "+02" in body

def test_format_body_falls_back_to_utc_on_invalid_timezone():
    body = format_body("AAPL", 231.50, "upper", 230.00, tz_name="Invalid/Zone")
    assert "UTC" in body

def test_format_body_defaults_to_utc_when_no_timezone():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "UTC" in body
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_checker.py::test_format_body_shows_local_timezone tests/test_checker.py::test_format_body_falls_back_to_utc_on_invalid_timezone tests/test_checker.py::test_format_body_defaults_to_utc_when_no_timezone -v
```

Expected: FAIL — `format_body` doesn't accept `tz_name` yet

- [ ] **Step 3: Add `zoneinfo` import and `_local_time_str` helper to `checker.py`**

Add to the imports at the top of `checker.py`:

```python
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
```

Add this helper function after the imports, before `condition_met`:

```python
def _local_time_str(tz_name: str | None) -> str:
    """Returns current time formatted for the given timezone. Falls back to UTC if invalid."""
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
            return datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
        except ZoneInfoNotFoundError:
            print(f"[WARN] Invalid timezone '{tz_name}', defaulting to UTC")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
```

- [ ] **Step 4: Update `format_body` to accept and use `tz_name`**

Replace the existing `format_body` function:

```python
def format_body(ticker: str, price: float, limit_type: str, limit_value: float, tz_name: str | None = None) -> str:
    now = _local_time_str(tz_name)
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: ${price:.2f}\n"
        f"Limit Triggered: {limit_type} limit (${limit_value:.2f})\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )
```

- [ ] **Step 5: Update `run()` to pass timezone to `format_body`**

In `run()`, find the line:
```python
body = format_body(ticker, price, limit_type, limit_value)
```
Replace with:
```python
body = format_body(ticker, price, limit_type, limit_value, tz_name=alarm.get("timezone"))
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_checker.py::test_format_body_shows_local_timezone tests/test_checker.py::test_format_body_falls_back_to_utc_on_invalid_timezone tests/test_checker.py::test_format_body_defaults_to_utc_when_no_timezone -v
```

Expected: all 3 PASS

- [ ] **Step 7: Run all tests**

```
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: add per-alarm timezone support in email formatting"
```

---

### Task 3: Add `condition_met_pct` function

**Files:**
- Modify: `checker.py` — new `condition_met_pct()` function after `condition_met()`
- Modify: `tests/test_checker.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_checker.py`:

```python
from checker import condition_met_pct

def test_pct_upper_triggered():
    alarm = {"upper_pct": 5.0, "lower_pct": None, "base_price": 100.0}
    triggered, direction, actual_pct = condition_met_pct(alarm, 106.0)
    assert triggered is True
    assert direction == "upper_pct"
    assert abs(actual_pct - 6.0) < 0.01

def test_pct_upper_not_triggered():
    alarm = {"upper_pct": 5.0, "lower_pct": None, "base_price": 100.0}
    triggered, _, _ = condition_met_pct(alarm, 104.0)
    assert triggered is False

def test_pct_upper_exactly_at_threshold():
    alarm = {"upper_pct": 5.0, "lower_pct": None, "base_price": 100.0}
    triggered, direction, _ = condition_met_pct(alarm, 105.0)
    assert triggered is True
    assert direction == "upper_pct"

def test_pct_lower_triggered():
    alarm = {"upper_pct": None, "lower_pct": 5.0, "base_price": 100.0}
    triggered, direction, actual_pct = condition_met_pct(alarm, 94.0)
    assert triggered is True
    assert direction == "lower_pct"
    assert actual_pct < 0

def test_pct_lower_not_triggered():
    alarm = {"upper_pct": None, "lower_pct": 5.0, "base_price": 100.0}
    triggered, _, _ = condition_met_pct(alarm, 96.0)
    assert triggered is False

def test_pct_both_set_upper_triggered():
    alarm = {"upper_pct": 5.0, "lower_pct": 5.0, "base_price": 100.0}
    triggered, direction, _ = condition_met_pct(alarm, 110.0)
    assert triggered is True
    assert direction == "upper_pct"

def test_pct_both_set_lower_triggered():
    alarm = {"upper_pct": 5.0, "lower_pct": 5.0, "base_price": 100.0}
    triggered, direction, _ = condition_met_pct(alarm, 90.0)
    assert triggered is True
    assert direction == "lower_pct"

def test_pct_neither_triggered():
    alarm = {"upper_pct": 5.0, "lower_pct": 5.0, "base_price": 100.0}
    triggered, direction, actual_pct = condition_met_pct(alarm, 100.0)
    assert triggered is False
    assert direction is None
    assert actual_pct is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_checker.py -k "pct" -v
```

Expected: FAIL — `condition_met_pct` not defined

- [ ] **Step 3: Add `condition_met_pct` to `checker.py`**

Add after the existing `condition_met` function:

```python
def condition_met_pct(alarm: dict, price: float) -> tuple:
    """Returns (triggered: bool, direction: str | None, actual_pct: float | None).
    
    Checks upper_pct and lower_pct thresholds against base_price.
    Assumes base_price is already set (not None).
    actual_pct is positive for price increases, negative for decreases.
    """
    base = alarm["base_price"]
    actual_pct = (price - base) / base * 100

    upper_pct = alarm.get("upper_pct")
    lower_pct = alarm.get("lower_pct")

    if upper_pct is not None and actual_pct >= upper_pct:
        return True, "upper_pct", actual_pct
    if lower_pct is not None and actual_pct <= -lower_pct:
        return True, "lower_pct", actual_pct
    return False, None, None
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_checker.py -k "pct" -v
```

Expected: all 8 PASS

- [ ] **Step 5: Run all tests**

```
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: add condition_met_pct for percentage-based alarm conditions"
```

---

### Task 4: Add percentage alarm email formatting

**Files:**
- Modify: `checker.py` — new `format_subject_pct()` and `format_body_pct()` functions
- Modify: `tests/test_checker.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_checker.py`:

```python
from checker import format_subject_pct, format_body_pct

def test_format_subject_pct_upper():
    subject = format_subject_pct("WDC", 106.0, "upper_pct", 5.0, 6.0)
    assert "WDC" in subject
    assert "+6.0%" in subject or "+6.00%" in subject

def test_format_subject_pct_lower():
    subject = format_subject_pct("WDC", 94.0, "lower_pct", 5.0, -6.0)
    assert "WDC" in subject
    assert "-6.0%" in subject or "-6.00%" in subject

def test_format_body_pct_contains_ticker():
    body = format_body_pct("WDC", 106.0, "upper_pct", 5.0, 100.0, 6.0)
    assert "WDC" in body

def test_format_body_pct_contains_current_price():
    body = format_body_pct("WDC", 106.0, "upper_pct", 5.0, 100.0, 6.0)
    assert "$106.00" in body

def test_format_body_pct_contains_base_price():
    body = format_body_pct("WDC", 106.0, "upper_pct", 5.0, 100.0, 6.0)
    assert "$100.00" in body

def test_format_body_pct_contains_pct_change():
    body = format_body_pct("WDC", 106.0, "upper_pct", 5.0, 100.0, 6.0)
    assert "+6" in body

def test_format_body_pct_lower_shows_fallen():
    body = format_body_pct("WDC", 94.0, "lower_pct", 5.0, 100.0, -6.0)
    assert "fallen" in body.lower() or "-6" in body

def test_format_body_pct_with_timezone():
    body = format_body_pct("WDC", 106.0, "upper_pct", 5.0, 100.0, 6.0, tz_name="Asia/Jerusalem")
    assert "IST" in body or "IDT" in body or "+03" in body or "+02" in body
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_checker.py -k "format_subject_pct or format_body_pct" -v
```

Expected: FAIL — functions not defined

- [ ] **Step 3: Add `format_subject_pct` and `format_body_pct` to `checker.py`**

Add after the existing `format_body` function:

```python
def format_subject_pct(ticker: str, price: float, direction: str, pct_threshold: float, actual_pct: float) -> str:
    sign = "+" if actual_pct >= 0 else ""
    return f"Stock Alert: {ticker} moved {sign}{actual_pct:.1f}% (threshold: {pct_threshold:.1f}%)"


def format_body_pct(ticker: str, price: float, direction: str, pct_threshold: float, base_price: float, actual_pct: float, tz_name: str | None = None) -> str:
    now = _local_time_str(tz_name)
    sign = "+" if actual_pct >= 0 else ""
    direction_label = "risen" if direction == "upper_pct" else "fallen"
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: ${price:.2f}\n"
        f"Base Price: ${base_price:.2f}\n"
        f"Change: {sign}{actual_pct:.2f}% ({direction_label})\n"
        f"Threshold: {pct_threshold:.1f}%\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_checker.py -k "format_subject_pct or format_body_pct" -v
```

Expected: all 8 PASS

- [ ] **Step 5: Run all tests**

```
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add checker.py tests/test_checker.py
git commit -m "feat: add email formatting functions for percentage alarms"
```

---

### Task 5: Wire percentage alarms into `run()`

**Files:**
- Modify: `checker.py` — `run()` function

- [ ] **Step 1: Replace the alarm processing block in `run()`**

In `run()`, find this block (starting after the price fetch):

```python
        triggered, limit_type, limit_value = condition_met(alarm, price)

        if triggered:
            if should_alert(alarm):
                subject = format_subject(ticker, price, limit_type, limit_value)
                body = format_body(ticker, price, limit_type, limit_value, tz_name=alarm.get("timezone"))
                try:
                    send_email(subject, body, alarm["email"], api_key, sender)
                    alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                    changed = True
                    print(f"[ALERT] Email sent for {ticker} at ${price:.2f}")
                except KeyError:
                    print(f"[ERROR] Alarm {ticker} is missing required field 'email', skipping")
                except Exception as e:
                    print(f"[ERROR] Could not send email for {ticker}: {e}")
            else:
                print(f"[SKIP] {ticker} condition met but alert sent recently, skipping")
        else:
            if alarm.get("last_triggered") is not None:
                alarm["last_triggered"] = None
                changed = True
            print(f"[OK] {ticker}: ${price:.2f} — no condition met")
```

Replace with:

```python
        is_pct_alarm = alarm.get("upper_pct") is not None or alarm.get("lower_pct") is not None
        tz_name = alarm.get("timezone")

        if is_pct_alarm:
            if alarm.get("base_price") is None:
                alarm["base_price"] = price
                changed = True
                print(f"[BASE] {ticker}: base price set to ${price:.2f}")
                continue

            triggered, direction, actual_pct = condition_met_pct(alarm, price)

            if triggered:
                if should_alert(alarm):
                    pct_threshold = alarm.get("upper_pct") if direction == "upper_pct" else alarm.get("lower_pct")
                    subject = format_subject_pct(ticker, price, direction, pct_threshold, actual_pct)
                    body = format_body_pct(ticker, price, direction, pct_threshold, alarm["base_price"], actual_pct, tz_name=tz_name)
                    try:
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at {actual_pct:+.1f}%")
                    except KeyError:
                        print(f"[ERROR] Alarm {ticker} is missing required field 'email', skipping")
                    except Exception as e:
                        print(f"[ERROR] Could not send email for {ticker}: {e}")
                else:
                    print(f"[SKIP] {ticker} condition met but alert sent recently, skipping")
            else:
                if alarm.get("last_triggered") is not None:
                    alarm["last_triggered"] = None
                    changed = True
                print(f"[OK] {ticker}: ${price:.2f} ({actual_pct:+.1f}% from base ${alarm['base_price']:.2f})")

        else:
            if not alarm.get("upper_limit") and not alarm.get("lower_limit"):
                print(f"[SKIP] {alarm.get('id', ticker)}: no condition defined")
                continue

            triggered, limit_type, limit_value = condition_met(alarm, price)

            if triggered:
                if should_alert(alarm):
                    subject = format_subject(ticker, price, limit_type, limit_value)
                    body = format_body(ticker, price, limit_type, limit_value, tz_name=tz_name)
                    try:
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at ${price:.2f}")
                    except KeyError:
                        print(f"[ERROR] Alarm {ticker} is missing required field 'email', skipping")
                    except Exception as e:
                        print(f"[ERROR] Could not send email for {ticker}: {e}")
                else:
                    print(f"[SKIP] {ticker} condition met but alert sent recently, skipping")
            else:
                if alarm.get("last_triggered") is not None:
                    alarm["last_triggered"] = None
                    changed = True
                print(f"[OK] {ticker}: ${price:.2f} — no condition met")
```

- [ ] **Step 2: Run all tests**

```
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add checker.py
git commit -m "feat: wire percentage alarms into run() with base_price capture"
```

- [ ] **Step 4: Push to Railway**

```bash
git push
```

- [ ] **Step 5: Verify in Railway logs**

After the next cron run (within 15 min), logs should show:
- `[FETCH] WDC: $XXX.XX`
- `[OK] WDC: $XXX.XX — no condition met` (for price alarm)
- Or `[BASE] WDC: base price set to $XXX.XX` (for a new pct alarm on first run)
