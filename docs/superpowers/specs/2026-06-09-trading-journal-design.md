# Trading Journal — Design Spec

**Date:** 2026-06-09  
**Status:** Approved

## Overview

Add a Trading Journal tab to the existing StocksApp. Users describe trades in plain language; Claude parses them into structured cards and flags rule violations. All data is stored server-side so the journal works across devices (computer + phone) via the existing Railway deployment.

---

## Architecture

### New Files

- `templates/journal.html` — two-panel page (chat left, cards right), self-contained JS
- `journal.py` — storage helpers (load/save trades from `journal.json`)

### Flask Routes (added to `app.py`)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/journal` | Serve the journal page (behind existing auth) |
| GET | `/api/journal/trades` | Return all saved trades as JSON |
| POST | `/api/journal/chat` | Send user message to Claude, return AI response + parsed trade JSON |
| POST | `/api/journal/trades` | Save a parsed trade card |
| DELETE | `/api/journal/trades` | Clear all trades |
| POST | `/api/journal/review` | Send all trades to Claude, return performance review text |

### Storage

`journal.json` on the server — same pattern as `alarms.json`. Protected by the existing `_lock` threading lock.

### API Key

`ANTHROPIC_API_KEY` Railway env var — already used by `trump_watcher.py`, no new setup required.

---

## UI Layout

### Tab Bar

"Journal" added to the existing tab bar in `dashboard.html` alongside Alarms, Trade History, Savings, Research.

### Page Layout

Full-width two-panel split inside `base.html`:

**Left panel (40%) — AI Chat**
- Message history scrolls upward
- Input box pinned to bottom
- Placeholder: *"e.g. Bought NVDA on 12/3, breakout at $138.50, stop $134, target $148, execution 4/5, calm. Won at $146.20."*
- Claude opens with: *"Tell me about your last trade."*

**Right panel (60%) — Trade Cards**
- Newest card on top
- Header: trade count + REQUEST REVIEW button + CLEAR ALL button
- Cards animate in on creation

### Trade Card Fields

- Ticker + date (card header)
- Result badge: Win / Loss / Breakeven / Open
- Setup label: breakout, pullback EMA, range, VCP, other
- Entry / Stop / Target prices
- R at entry (amber) · Actual R with green/red bar
- Execution dots ●●●○○ (1–5)
- Emotion tag
- Did right / Would change notes

### Design

- Inherits dark theme from existing `style.css`
- Font: IBM Plex Mono
- Win / Long: `#2CC84A` green
- Loss: red
- R-at-entry: amber
- No gradients

---

## Data Model

Each trade in `journal.json` is an object in an array:

```json
{
  "id": "uuid",
  "date": "2024-12-03",
  "ticker": "NVDA",
  "setup_type": "breakout|pullback_ema|range|vcp|other",
  "entry_price": 138.50,
  "stop_price": 134.00,
  "target_price": 148.00,
  "r_multiple_entry": 2.0,
  "execution_quality": 4,
  "emotional_state": "calm|anxious|FOMO|revenge|disciplined",
  "result": "Win|Loss|Breakeven|Open",
  "actual_r": 1.8,
  "did_right": "Waited for breakout confirmation",
  "would_change": "Taken partial profits at 1R"
}
```

**Omitted from original spec:** `direction` (always Long), `position_size`.

`r_multiple_entry` is calculated server-side when entry, stop, and target are all present: `(target - entry) / (entry - stop)`.

---

## AI Integration

**Model:** `claude-sonnet-4-5-20251001`

**System Prompt:**

```
You are a trading journal AI. When a user describes a trade, respond in TWO parts:
PART 1: One sentence. Flag rule violations: no impulse trades, stop always predefined, never average down.
PART 2: Extract to JSON:
{"date":null,"ticker":"","setup_type":"breakout|pullback_ema|range|vcp|other","entry_price":null,"stop_price":null,"target_price":null,"r_multiple_entry":null,"execution_quality":null,"emotional_state":"calm|anxious|FOMO|revenge|disciplined","result":"Win|Loss|Breakeven|Open","actual_r":null,"did_right":"","would_change":""}
Use null for missing fields.
On REVIEW: win rate, avg R won/lost, common setup, execution mistakes, emotion/result correlation, one fix.
Start with: Tell me about your last trade.
```

**Chat Flow:**

1. User types in chat → `POST /api/journal/chat`
2. Flask sends full conversation history to Claude, receives response
3. Browser displays PART 1 as Claude's chat reply
4. If PART 2 JSON contains a ticker, browser calls `POST /api/journal/trades` to persist it and animates in a new card on the right
5. REQUEST REVIEW → `POST /api/journal/review` → all trades sent as context → Claude returns plain-text analysis → displayed in chat

**Conversation history** is kept client-side in JS and sent with each request so Claude has context across the session. It is not persisted server-side between sessions.

---

## Error Handling

- If Claude returns malformed JSON in PART 2, the chat reply still displays but no card is created; no error shown to the user
- If the Anthropic API call fails, return a user-friendly error message in the chat: *"Something went wrong, try again."*
- CLEAR ALL requires a confirmation dialog before deleting

---

## Out of Scope

- Editing existing trade cards
- Attaching charts or screenshots
- Cross-referencing with the existing Trade History tab
- Push notifications or reminders
