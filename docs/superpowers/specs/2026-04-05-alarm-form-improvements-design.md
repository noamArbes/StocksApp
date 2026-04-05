# Alarm Form Improvements Design

**Date:** 2026-04-05
**Status:** Approved

## Overview

Improve the alarm creation/edit form with ticker autocomplete (live Yahoo Finance search), city-based timezone autocomplete (bundled dataset), required timezone validation, and visual field validation feedback.

## Backend Changes

### New endpoint: `/ticker-search`

```
GET /ticker-search?q=<query>
```

- Requires login
- Only responds if `q` is 2+ characters
- Proxies to Yahoo Finance search API: `https://query1.finance.yahoo.com/v1/finance/search?q=<query>&quotesCount=6&newsCount=0`
- Returns JSON array of up to 6 matches:

```json
[
  {"symbol": "AAPL", "name": "Apple Inc."},
  {"symbol": "AAPL.BA", "name": "Apple Inc. (Buenos Aires)"}
]
```

- Returns `[]` on any error (Yahoo Finance is an unofficial API, must not crash the app)
- Implemented in `app.py`

### New endpoint: `/city-search`

```
GET /city-search?q=<query>
```

- Requires login
- Only responds if `q` is 2+ characters
- Searches `cities_data.py` (bundled dataset, case-insensitive prefix/substring match on city name)
- Returns up to 8 matches:

```json
[
  {"city": "Tel Aviv", "country": "Israel", "timezone": "Asia/Jerusalem"},
  {"city": "New York", "country": "United States", "timezone": "America/New_York"}
]
```

- Implemented in `app.py`

### New file: `cities_data.py`

A Python module containing a list of ~2000 major world cities:

```python
CITIES = [
    {"city": "Tel Aviv", "country": "Israel", "timezone": "Asia/Jerusalem"},
    {"city": "Jerusalem", "country": "Israel", "timezone": "Asia/Jerusalem"},
    {"city": "New York", "country": "United States", "timezone": "America/New_York"},
    # ...
]
```

- All timezones are valid IANA timezone strings (compatible with `zoneinfo`)
- Covers all countries, skewed toward major/capital cities
- No external dependencies — plain Python list

### Validation change: timezone now required

In `_alarm_from_form`, add validation after the timezone field is read:

```python
timezone = form.get("timezone", "").strip() or None
if not timezone:
    return None, "Timezone (city) is required"
```

## Frontend Changes (`templates/alarm_form.html`)

### Ticker autocomplete

- The existing ticker `<input>` gains a `<div class="autocomplete-dropdown">` below it
- JS listens for `input` events with 300ms debounce
- At 2+ characters: fetches `/ticker-search?q=<value>`
- Renders results as clickable items: `AAPL — Apple Inc.`
- Clicking an item: fills the input with the symbol, closes dropdown
- Pressing Escape or clicking outside: closes dropdown

### City/timezone field

The existing timezone free-text input is replaced with:

```html
<label>City (for timezone) *
    <input type="text" id="city-input" autocomplete="off" placeholder="e.g. Tel Aviv">
    <div class="autocomplete-dropdown" id="city-dropdown"></div>
</label>
<input type="hidden" name="timezone" id="timezone-hidden">
```

- JS fetches `/city-search?q=<value>` with 300ms debounce at 2+ characters
- Results shown as: `Tel Aviv — Israel`
- On selection: fills city input with `Tel Aviv — Israel`, fills hidden `timezone` field with `Asia/Jerusalem`
- On edit (existing alarm): city input pre-filled with `{city} — {country}` derived from existing `timezone` value (reverse lookup against `CITIES` dataset served via a new `/timezone-to-city?tz=` endpoint)

### Visual validation

On form submit, JS checks:
- Ticker input is not empty
- At least one of upper_limit / lower_limit (or upper_pct / lower_pct for pct alarms) is filled
- Email input is not empty
- Hidden timezone field is not empty

For each failing field: add class `field-error` to the parent `<label>`, show a `<span class="field-error-msg">` with a short message. Block form submission. Clear errors on next input event.

### CSS additions (`static/style.css`)

```css
.autocomplete-dropdown  — positioned below input, dark background, border
.autocomplete-item      — hover highlight
.field-error input      — red border
.field-error-msg        — small red error text below field
```

## Edit Form Pre-population

When editing an alarm that already has a timezone (e.g. `Asia/Jerusalem`):
- A new endpoint `GET /timezone-to-city?tz=<timezone>` returns the best matching city from `CITIES`
- JS calls this on page load if a timezone value exists, and pre-fills the city input
- Falls back to showing the raw timezone string if no city match found

## Out of Scope

- Ticker autocomplete on the edit form — ticker field remains a plain text input when editing
- Fuzzy city matching (prefix/substring is sufficient)
- Autocomplete keyboard navigation (arrow keys) — mouse/tap only for now
