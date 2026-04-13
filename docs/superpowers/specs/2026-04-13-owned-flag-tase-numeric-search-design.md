# Owned Flag + TASE Numeric ID Search — Design Spec

**Date:** 2026-04-13

## Overview

Two small independent features:
1. **Owned flag** — mark each alarm as "I own this security" or "Watching". Toggle on dashboard card, checkbox in alarm form, filter buttons to show All / Owned / Watching alarms.
2. **TASE numeric ID search** — allow searching Israeli securities by their numeric TASE ID (e.g., `5131081`) in addition to searching by name or ticker.

---

## Feature 1: Owned Flag

### Data Model

New field on each alarm:

| Field | Type | Default | Notes |
|---|---|---|---|
| `owned` | boolean | `False` | Existing alarms without this field treated as `False` — no migration needed |

### Dashboard Filter

Three filter buttons added to the existing sort controls row (alongside Newest / Oldest / A–Z):

- **All** (default)
- **Owned**
- **Watching**

Controlled via `?owned=` query param:
- No param or `?owned=all` → show all alarms
- `?owned=owned` → show only alarms where `owned == True`
- `?owned=watching` → show only alarms where `owned == False`

Filtering is applied server-side in the `/dashboard` route before passing the list to the template, the same way `sort` is handled. The `owned` param is preserved when navigating between sort options.

### Dashboard Card Toggle

A button on each alarm card — displayed next to the existing ON/OFF toggle — showing:
- **"Owned"** if `alarm.owned == True`
- **"Watching"** if `alarm.owned == False`

Clicking submits a POST to `/alarm/<id>/toggle-owned`. The route flips the `owned` field and redirects back to the dashboard, preserving the current `?sort=` and `?owned=` query params.

### Alarm Form Checkbox

A single **"I own this security"** checkbox added below the existing "Enabled" checkbox. Pre-checked based on `alarm.get("owned", False)` when editing. Submitted as a standard form field — `_alarm_from_form()` reads `form.get("owned") == "on"` and sets `alarm["owned"]` accordingly.

### New Route

```
POST /alarm/<alarm_id>/toggle-owned
```
Login required. Flips `alarm["owned"]` (defaults to `False` if missing). Redirects back to dashboard preserving query params.

---

## Feature 2: TASE Numeric ID Search

### Change

Update `tase.search(query, cache)` to also match items by `id` field when the query contains only digits.

**New logic:**
```python
id_match = query.isdigit() and query in item["id"]
if name_match or ticker_match or id_match:
    results.append(item)
```

The existing `/api/tase-search` endpoint and autocomplete JS are unchanged — they work automatically with the updated `search()` function.

### Behaviour

- Typing `5131081` → returns the item with `id == "5131081"` (exact substring match)
- Typing `513` → returns all items whose `id` contains `"513"`
- Non-digit queries → existing name/ticker matching only (no change)

---

## What Is Not Changing

- Alarm condition checking, email alerts, price fetching — unchanged
- Sort controls layout — owned filter buttons are added alongside, not replacing
- US stock alarms — `owned` field works identically for both US and TASE alarms
