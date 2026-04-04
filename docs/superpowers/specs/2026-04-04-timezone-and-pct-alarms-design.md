# Spec: Timezone-Aware Emails & Percentage-Based Alarms

## Overview

Two enhancements to the stock alarm system:
1. Each alarm displays the alert time in the recipient's local timezone.
2. Alarms can trigger based on a percentage change from a captured base price, with separate thresholds for upward and downward moves.

---

## Feature 1: Per-Alarm Timezone

### Behavior
- Each alarm in `alarms.json` has an optional `timezone` field (e.g. `"Asia/Jerusalem"`, `"America/New_York"`).
- The time shown in alert emails is converted from UTC to that timezone.
- If `timezone` is missing or invalid, the system falls back to UTC and logs `[WARN] Invalid or missing timezone for <id>, defaulting to UTC`.

### Implementation
- Use Python's built-in `zoneinfo` module (available since Python 3.9 — no new dependencies).
- `format_body()` accepts a `timezone` string and converts `datetime.now(timezone.utc)` to local time before formatting.
- `run()` reads `alarm.get("timezone")` and passes it to `format_body()`.

---

## Feature 2: Percentage-Based Alarms

### Behavior
- An alarm uses percentage thresholds instead of fixed price limits by setting `upper_pct`, `lower_pct`, or both.
- `upper_pct`: alert if price rises X% above `base_price`.
- `lower_pct`: alert if price falls X% below `base_price`.
- `base_price` starts as `null`. On the first run, the current price is captured and saved as `base_price` — no alert is sent on that run.
- To reset the measurement window, manually set `base_price` back to `null` in `alarms.json`.
- Existing price-limit alarms (`upper_limit`/`lower_limit`) are unaffected.

### Alarm types are mutually exclusive
An alarm uses either price limits or percentage thresholds, not both. If an alarm has both, percentage fields take precedence.

### Implementation
- `condition_met()` is updated to check for `upper_pct`/`lower_pct`. If `base_price` is null, it sets it and returns not-triggered.
- New `format_subject_pct()` and `format_body_pct()` functions handle percentage alert messaging, showing the % change and base price.
- `run()` saves the alarm back to disk when `base_price` is first captured (`changed = True`).

---

## Data Format

```json
[
  {
    "id": "WDC_price_alarm",
    "ticker": "WDC",
    "upper_limit": 300.00,
    "lower_limit": null,
    "timezone": "Asia/Jerusalem",
    "email": "someone@gmail.com",
    "enabled": true,
    "last_triggered": null
  },
  {
    "id": "WDC_pct_alarm",
    "ticker": "WDC",
    "upper_pct": 5.0,
    "lower_pct": 3.0,
    "base_price": null,
    "timezone": "Asia/Jerusalem",
    "email": "someone@gmail.com",
    "enabled": true,
    "last_triggered": null
  }
]
```

---

## Error Handling

| Situation | Behavior |
|-----------|----------|
| Invalid/missing `timezone` | Fall back to UTC, log `[WARN]` |
| `base_price` is null on first run | Capture price, save to disk, do not alert |
| Price fetch fails after `base_price` set | Skip alarm, keep existing `base_price` |
| Alarm has no limit or pct fields | Log `[SKIP] <id>: no condition defined` |

---

## Out of Scope

- Auto-detecting timezone from recipient location (not possible server-side)
- Multiple percentage thresholds per alarm
- Resetting `base_price` automatically after an alert
