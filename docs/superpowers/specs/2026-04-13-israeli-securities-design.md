# Israeli Securities Support — Design Spec

**Date:** 2026-04-13

## Overview

Add support for Israeli funds and securities (TASE stocks, ETFs, and mutual funds) alongside the existing US stock alarms. Users can create alarms for Israeli securities using a market toggle in the alarm form. Israeli prices are fetched from the TASE public API. Additionally, remove the copy-alarm feature and add a manual reference price field to all alarm types.

---

## Data Model

Two new optional fields added to each alarm object:

| Field | Type | Values | Notes |
|---|---|---|---|
| `source` | string | `"yfinance"` or `"tase"` | Omitted/absent means `"yfinance"` (all existing alarms unaffected) |
| `tase_id` | string | e.g. `"1175819"` | Numeric TASE security ID; only set when `source == "tase"` |
| `tase_type` | string | `"security"` or `"fund"` | Routes to correct TASE endpoint; only set when `source == "tase"` |

The existing `ticker` field remains the display label:
- TASE stocks/ETFs: Hebrew ticker symbol (e.g. `"ELTR"`)
- TASE mutual funds: fund short name (e.g. `"Migdal Bonds"`)

Prices for Israeli securities are in ILS (₪). Currency is derived from `source` at display time — no currency field stored on the alarm.

No migration needed. Existing alarms without `source` continue to use yfinance.

---

## New Module: `tase.py`

Handles all TASE API interaction. Three responsibilities:

### 1. `load_securities_cache() -> list[dict]`

Calls `GET https://api.tase.co.il/api/content/searchentities?lang=1` with required headers:
```
User-Agent: Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; FSL 7.0.6.01001)
Referer: https://www.tase.co.il/
Cache-Control: no-cache
```
Filters to type 1 (stocks/ETFs) and type 4 (mutual funds) only. Returns a flat list of dicts:
```python
{"id": "1175819", "name": "Eltra", "ticker": "ELTR", "type": "security"}  # stock or ETF
{"id": "5118393", "name": "Migdal Bonds Fund", "ticker": None, "type": "fund"}
```
Called once at app startup. If unreachable, logs a warning and returns `[]`.

### 2. `search(query: str, cache: list[dict]) -> list[dict]`

Case-insensitive substring match on `name` and `ticker` fields. Returns top 10 results. No external calls — runs entirely against the in-memory cache.

### 3. `get_price(tase_id: str, tase_type: str) -> float`

Routes by `tase_type`:
- `"fund"` → `GET https://mayaapi.tase.co.il/api/fund/details?fundId=<tase_id>` (requires additional header `X-Maya-With: allow`) → returns `UnitValuePrice`
- `"security"` → `GET https://api.tase.co.il/api/company/securitydata?securityId=<tase_id>&lang=1` → returns `LastRate`

Raises `ValueError` if price is `None` or unreachable — same contract as the existing `get_price` in `checker.py`.

---

## `checker.py` Changes

### Price routing in `run()`

Per alarm, before fetching price:
```python
if alarm.get("source") == "tase":
    price = tase.get_price(alarm["tase_id"], alarm["tase_type"])
else:
    price = get_price(alarm["ticker"])  # existing yfinance path
```

### Currency in email alerts

`format_subject`, `format_body`, `format_subject_pct`, `format_body_pct` get an optional `currency` parameter defaulting to `"$"`. TASE alarms pass `"₪"`. All existing call sites are unaffected (default applies).

---

## `app.py` Changes

### TASE cache at startup

After existing startup validation:
```python
_tase_cache = tase.load_securities_cache()
```
If the TASE API is unreachable, `_tase_cache = []` and app starts normally.

### New endpoint: `GET /api/tase-search`

Login required. Reads `q` query param, calls `tase.search(q, _tase_cache)`, returns JSON list. Used by the alarm form autocomplete.

### `_alarm_from_form()` updates

- When `source=tase` is submitted: read `tase_id` and `tase_type` from hidden form fields; include them in the alarm dict.
- `initial_price` fetch routes via `tase.get_price()` for TASE alarms.
- If the user provides a manual reference price (see below), skip the auto-fetch for `initial_price` and `base_price`.

### Dashboard price routing

The `/dashboard` route's per-alarm `get_price` calls get the same source-based routing as `checker.py`.

### Remove copy-alarm

- Delete the `/alarm/<alarm_id>/duplicate` route and `alarm_duplicate` function.
- Remove the duplicate button from `dashboard.html`.

---

## `alarm_form.html` Changes

### Market toggle

Above the ticker/search field: two pill buttons — **"US (Yahoo Finance)"** (default) and **"Israeli (TASE)"**.

When Israeli is selected:
- Field label changes from "Ticker" to "Search Israeli Security"
- Placeholder changes to `e.g. מגדל or Migdal`
- Autocomplete fetches from `/api/tase-search` instead of the existing ticker endpoint
- Each dropdown result shows: security name + type badge (Stock / ETF / Fund) + ticker symbol if available
- On selection: visible input shows the name; hidden fields `tase_id`, `tase_type`, `source` are populated

When editing an existing TASE alarm: market toggle is locked to "Israeli", search field shows the security name (readonly, same as ticker today).

### Manual reference price

Below the alarm type radio buttons (Price Limits / Percentage Change), add an optional **"Reference Price"** field (number input, `step=0.01`). Label shows the appropriate currency symbol based on the active market toggle. Help text: `"Leave blank to use the current market price at creation time."` 

Behaviour:
- If filled: stored as `initial_price` (price alarms) and/or `base_price` (percentage alarms) at creation time; auto-fetch is skipped.
- If blank: existing auto-fetch behaviour applies.
- Shown for both alarm types.

### Currency label

Price limit fields show **₪** instead of **$** when Israeli mode is active.

---

## `dashboard.html` Changes

### Currency symbol

Wherever a price is displayed (current price, upper/lower limits, distance-to-trigger string), use **₪** for `source == "tase"` alarms, **$** otherwise.

### Security label

The ticker badge on each alarm card:
- TASE stocks/ETFs: show ticker symbol as today
- TASE mutual funds: show fund short name (the `ticker` field stores it)

### Remove duplicate button

Remove the copy/duplicate action button from each alarm card.

---

## What Is Not Changing

- Alarm enable/disable, snooze, notes, test email, triggered badge, alert history — all unchanged.
- Condition checking logic (`condition_met`, `condition_met_pct`) — unchanged.
- Email sending via Brevo — unchanged.
- US stock alarms — fully unaffected; no migration required.
