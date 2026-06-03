# Trump Alerts UI — Design Spec

**Date:** 2026-06-03  
**Status:** Approved

## Overview

Add a "Trump Alerts" sub-tab to the Research page that displays a persistent, scrollable history of all flagged Trump Trade Alerts. Alerts are saved to a JSON file on disk (same pattern as `alarms.json`) and survive restarts.

## Data Storage

**File:** `trump_alerts.json` at the project root (same location as `alarms.json`)

Each alert entry:
```json
{
  "id": "<uuid>",
  "timestamp": "2026-06-03T14:32:00Z",
  "summary": "Trump announced massive tariffs on Chinese steel.",
  "tickers": ["X", "NUE", "STLD"],
  "direction": "Bearish",
  "sector": "Steel / Materials",
  "confidence": "High",
  "why_it_matters": "Tariffs on China steel directly hit domestic steel producers.",
  "raw_post": "We are putting massive tariffs on China steel!"
}
```

- Stored as a JSON array, newest first
- Capped at 100 entries (oldest pruned when cap exceeded)
- File created automatically on first alert

## Backend Changes

### `trump_watcher.py`

New helpers:
- `get_alerts_path()` — returns path to `trump_alerts.json` (mirrors `checker.get_alarms_path()`)
- `save_alert(alert: dict)` — loads existing alerts, prepends new entry, prunes to 100, writes back atomically (write to temp file + rename, same pattern as `checker.py`)
- `parse_alert(raw: str, post: dict) -> dict` — parses Claude's formatted alert string into a structured dict with `id`, `timestamp`, `summary`, `tickers`, `direction`, `sector`, `confidence`, `why_it_matters`, `raw_post`

`run()` updated to call `save_alert(parse_alert(alert, post))` for each flagged alert before sending email.

### `app.py`

One new route:
```
GET /api/trump-alerts
```
Returns `{"alerts": [...]}` — reads from `trump_alerts.json` via `trump_watcher.get_alerts_path()`. Login required.

## Frontend Changes

### `templates/research.html`

1. Add "Trump Alerts" button to the Research sub-tab bar (alongside "Find Tickers" and "Analyze Stock")
2. Add a new panel `#panel-trump` that shows:
   - A list of alert cards (one per entry), newest first
   - Each card shows: date/time, summary, tickers (as chips), direction badge (colored: green=Bullish, red=Bearish, yellow=Mixed), sector, confidence badge, "Why it matters" text
   - Empty state: "No alerts recorded yet. Alerts appear here when Trump posts market-moving content."
3. Panel fetches `/api/trump-alerts` on tab activation (lazy load, same pattern as other panels)

## File Structure

| File | Change |
|------|--------|
| `trump_watcher.py` | Add `get_alerts_path()`, `save_alert()`, `parse_alert()`; update `run()` |
| `app.py` | Add `GET /api/trump-alerts` route |
| `templates/research.html` | Add sub-tab button + panel |
| `trump_alerts.json` | Created automatically on first alert |
| `tests/test_trump_watcher.py` | Add tests for `parse_alert()` and `save_alert()` |

## Error Handling

- If `trump_alerts.json` doesn't exist, `/api/trump-alerts` returns `{"alerts": []}` 
- If `parse_alert()` fails to parse a field, it falls back to the raw string
- `save_alert()` failures are logged but do not interrupt the email flow
