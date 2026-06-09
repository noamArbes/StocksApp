# Trading Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Trading Journal tab to StocksApp where users describe trades in plain language, Claude parses them into structured cards and flags rule violations, and data is persisted server-side for multi-device access.

**Architecture:** New `journal.py` module handles storage (journal.json), R calculation, response parsing, and the Anthropic API client (lazy-init, same pattern as `trump_watcher.py`). Six new Flask routes in `app.py` handle CRUD and AI proxying, using the same `_lock` / path-function pattern as existing routes. A two-panel `templates/journal.html` (chat 40% left, cards 60% right) drives the UI with inline vanilla JS.

**Tech Stack:** Python/Flask, anthropic SDK, Jinja2, vanilla JS, JSON file storage

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `journal.py` | Create | Storage helpers, R calculation, response parsing, AI client, system prompt |
| `tests/test_journal.py` | Create | Unit tests for all journal.py functions |
| `app.py` | Modify | Import journal, add `_JOURNAL_PATH`, `_journal_path()`, 3 read/write helpers, 6 routes |
| `tests/test_app.py` | Modify | Add journal route tests |
| `templates/journal.html` | Create | Two-panel UI: chat left, cards right, all JS inline |
| `templates/dashboard.html` | Modify | Add "Journal" tab to tab bar |

---

## Task 1: Storage and parsing module

**Files:**
- Create: `journal.py`
- Create: `tests/test_journal.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_journal.py`:

```python
import json
import os
import pytest
import journal


# ─── Storage ───────────────────────────────────────────────────────────────

def test_load_trades_returns_empty_list_when_file_missing(tmp_path):
    result = journal.load_trades(str(tmp_path / "journal.json"))
    assert result == []


def test_save_trade_assigns_uuid(tmp_path):
    path = str(tmp_path / "journal.json")
    saved = journal.save_trade({"ticker": "NVDA"}, path)
    assert "id" in saved
    assert len(saved["id"]) == 36


def test_save_trade_appends_in_order(tmp_path):
    path = str(tmp_path / "journal.json")
    journal.save_trade({"ticker": "NVDA"}, path)
    journal.save_trade({"ticker": "AAPL"}, path)
    trades = journal.load_trades(path)
    assert len(trades) == 2
    assert trades[0]["ticker"] == "NVDA"
    assert trades[1]["ticker"] == "AAPL"


def test_save_trade_preserves_existing_id(tmp_path):
    path = str(tmp_path / "journal.json")
    saved = journal.save_trade({"ticker": "NVDA", "id": "fixed-id"}, path)
    assert saved["id"] == "fixed-id"


def test_clear_trades_empties_file(tmp_path):
    path = str(tmp_path / "journal.json")
    journal.save_trade({"ticker": "NVDA"}, path)
    journal.clear_trades(path)
    assert journal.load_trades(path) == []


# ─── R multiple calculation ────────────────────────────────────────────────

def test_calculate_r_multiple_basic():
    # risk = 138.50 - 134.00 = 4.50; reward = 148.00 - 138.50 = 9.50
    result = journal.calculate_r_multiple(138.50, 134.00, 148.00)
    assert result == round(9.50 / 4.50, 2)


def test_calculate_r_multiple_stop_above_entry_returns_none():
    result = journal.calculate_r_multiple(130.00, 135.00, 148.00)
    assert result is None


def test_calculate_r_multiple_none_inputs_returns_none():
    assert journal.calculate_r_multiple(None, 134.00, 148.00) is None
    assert journal.calculate_r_multiple(138.50, None, 148.00) is None
    assert journal.calculate_r_multiple(138.50, 134.00, None) is None


# ─── Response parsing ──────────────────────────────────────────────────────

def test_parse_claude_response_extracts_text_and_json():
    text = 'PART 1: No rule violations detected.\n\nPART 2: {"ticker": "NVDA", "result": "Win"}'
    reply, trade = journal.parse_claude_response(text)
    assert reply == "No rule violations detected."
    assert trade == {"ticker": "NVDA", "result": "Win"}


def test_parse_claude_response_no_part2_returns_none_trade():
    text = "PART 1: Tell me more about the setup."
    reply, trade = journal.parse_claude_response(text)
    assert "Tell me more" in reply
    assert trade is None


def test_parse_claude_response_malformed_json_returns_none_trade():
    text = "PART 1: Good trade.\n\nPART 2: {bad json}"
    reply, trade = journal.parse_claude_response(text)
    assert reply == "Good trade."
    assert trade is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_journal.py -v
```

Expected: `ERROR — ModuleNotFoundError: No module named 'journal'`

- [ ] **Step 3: Implement journal.py**

Create `journal.py`:

```python
import json
import os
import re
import uuid

import anthropic

_JOURNAL_SYSTEM_PROMPT = (
    "You are a trading journal AI. When a user describes a trade, respond in TWO parts:\n"
    "PART 1: One sentence. Flag rule violations: no impulse trades, stop always predefined, never average down.\n"
    "PART 2: Extract to JSON:\n"
    '{"date":null,"ticker":"","setup_type":"breakout|pullback_ema|range|vcp|other",'
    '"entry_price":null,"stop_price":null,"target_price":null,"r_multiple_entry":null,'
    '"execution_quality":null,"emotional_state":"calm|anxious|FOMO|revenge|disciplined",'
    '"result":"Win|Loss|Breakeven|Open","actual_r":null,"did_right":"","would_change":""}\n'
    "Use null for missing fields.\n"
    "On REVIEW: win rate, avg R won/lost, common setup, execution mistakes, emotion/result correlation, one fix.\n"
    "Start with: Tell me about your last trade."
)

_claude_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _claude_client


def get_journal_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal.json")


def load_trades(path=None):
    path = path or get_journal_path()
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_trade(trade, path=None):
    path = path or get_journal_path()
    trades = load_trades(path)
    if not trade.get("id"):
        trade["id"] = str(uuid.uuid4())
    trades.append(trade)
    with open(path, "w") as f:
        json.dump(trades, f, indent=2)
    return trade


def clear_trades(path=None):
    path = path or get_journal_path()
    with open(path, "w") as f:
        json.dump([], f)


def calculate_r_multiple(entry, stop, target):
    try:
        risk = float(entry) - float(stop)
        if risk <= 0:
            return None
        return round((float(target) - float(entry)) / risk, 2)
    except (TypeError, ValueError):
        return None


def parse_claude_response(text):
    parts = text.split("PART 2:")
    if len(parts) < 2:
        reply = text.replace("PART 1:", "").strip()
        return reply, None

    reply = parts[0].replace("PART 1:", "").strip()
    json_part = parts[1].strip()

    match = re.search(r"\{.*\}", json_part, re.DOTALL)
    if not match:
        return reply, None

    try:
        trade = json.loads(match.group())
        return reply, trade
    except json.JSONDecodeError:
        return reply, None


def call_claude_chat(messages):
    client = _get_claude_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_JOURNAL_SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text


def call_claude_review(trades):
    client = _get_claude_client()
    trades_json = json.dumps(trades, indent=2)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_JOURNAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"REVIEW\n\nHere are all my trades:\n{trades_json}"}],
    )
    return response.content[0].text
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_journal.py -v
```

Expected: all 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add journal.py tests/test_journal.py
git commit -m "feat: add journal storage module with parsing and R calculation"
```

---

## Task 2: Flask routes

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing route tests**

Append to `tests/test_app.py`:

```python
# ─── Journal fixtures and tests ────────────────────────────────────────────

@pytest.fixture
def journal_client(tmp_path, monkeypatch):
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([]))
    journal_file = tmp_path / "journal.json"
    journal_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr(app_module, "_journal_path", lambda: str(journal_file))
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        c.post("/login", data={"password": "testpass"})
        yield c, str(journal_file)


def test_journal_page_requires_login(client):
    resp = client.get("/journal")
    assert resp.status_code == 302


def test_get_journal_trades_empty(journal_client):
    c, _ = journal_client
    resp = c.get("/api/journal/trades")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_post_journal_trade_saves_and_calculates_r(journal_client):
    c, path = journal_client
    trade = {
        "ticker": "NVDA",
        "date": "2024-12-03",
        "result": "Win",
        "entry_price": 138.50,
        "stop_price": 134.00,
        "target_price": 148.00,
    }
    resp = c.post("/api/journal/trades", json=trade)
    assert resp.status_code == 201
    saved = resp.get_json()
    assert saved["ticker"] == "NVDA"
    assert "id" in saved
    assert saved["r_multiple_entry"] == round(9.50 / 4.50, 2)


def test_delete_journal_trades_clears_all(journal_client):
    import journal as j
    c, path = journal_client
    j.save_trade({"ticker": "NVDA"}, path)
    resp = c.delete("/api/journal/trades")
    assert resp.status_code == 200
    assert j.load_trades(path) == []


def test_journal_chat_returns_reply_and_trade(journal_client, monkeypatch):
    import journal as j
    c, _ = journal_client
    monkeypatch.setattr(
        j, "call_claude_chat",
        lambda msgs: 'PART 1: No violations.\n\nPART 2: {"ticker": "NVDA", "result": "Win"}'
    )
    resp = c.post("/api/journal/chat", json={"messages": [], "message": "Bought NVDA"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reply"] == "No violations."
    assert data["trade"]["ticker"] == "NVDA"


def test_journal_review_returns_reply(journal_client, monkeypatch):
    import journal as j
    c, _ = journal_client
    monkeypatch.setattr(j, "call_claude_review", lambda trades: "Win rate: 75%")
    resp = c.post("/api/journal/review")
    assert resp.status_code == 200
    assert resp.get_json()["reply"] == "Win rate: 75%"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_app.py -k "journal" -v
```

Expected: `FAILED — AttributeError: module 'app' has no attribute '_journal_path'`

- [ ] **Step 3: Add journal import and path to app.py**

At the top of `app.py`, after the existing module imports (`import trump_watcher`), add:

```python
import journal as journal_module
```

After the line `_SIEMENS_PATH = checker.get_siemens_path()` (around line 38), add:

```python
_JOURNAL_PATH = journal_module.get_journal_path()
```

- [ ] **Step 4: Add journal path function and helpers to app.py**

After the `_snapshots_path()` function (around line 98), add:

```python
def _journal_path():
    return _JOURNAL_PATH


def read_journal_trades():
    with _lock:
        return journal_module.load_trades(_journal_path())


def write_journal_trade(trade):
    with _lock:
        return journal_module.save_trade(trade, _journal_path())


def clear_journal_trades():
    with _lock:
        journal_module.clear_trades(_journal_path())
```

- [ ] **Step 5: Add the six journal routes to app.py**

Add after the last existing route definition:

```python
@app.route("/journal")
def journal_tab():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("journal.html")


@app.route("/api/journal/trades", methods=["GET"])
def api_journal_trades_get():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(read_journal_trades())


@app.route("/api/journal/trades", methods=["POST"])
def api_journal_trade_post():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    trade = request.get_json()
    r = journal_module.calculate_r_multiple(
        trade.get("entry_price"), trade.get("stop_price"), trade.get("target_price")
    )
    if r is not None:
        trade["r_multiple_entry"] = r
    saved = write_journal_trade(trade)
    return jsonify(saved), 201


@app.route("/api/journal/trades", methods=["DELETE"])
def api_journal_trades_delete():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    clear_journal_trades()
    return jsonify({"ok": True})


@app.route("/api/journal/chat", methods=["POST"])
def api_journal_chat():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json()
    messages = body.get("messages", [])
    user_message = body.get("message", "")
    messages = messages + [{"role": "user", "content": user_message}]
    try:
        raw = journal_module.call_claude_chat(messages)
    except Exception:
        return jsonify({"error": "AI unavailable"}), 503
    reply, trade = journal_module.parse_claude_response(raw)
    return jsonify({"reply": reply, "trade": trade})


@app.route("/api/journal/review", methods=["POST"])
def api_journal_review():
    if not session.get("logged_in"):
        return jsonify({"error": "unauthorized"}), 401
    trades = read_journal_trades()
    try:
        reply = journal_module.call_claude_review(trades)
    except Exception:
        return jsonify({"error": "AI unavailable"}), 503
    return jsonify({"reply": reply})
```

- [ ] **Step 6: Run journal route tests to verify they pass**

```bash
python -m pytest tests/test_app.py -k "journal" -v
```

Expected: all 6 journal tests pass.

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add journal Flask routes"
```

---

## Task 3: Journal HTML template

**Files:**
- Create: `templates/journal.html`

- [ ] **Step 1: Create templates/journal.html**

```html
{% extends "base.html" %}
{% block content %}
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap');

  .journal-wrap {
    display: flex;
    gap: 0;
    height: calc(100vh - 80px);
    overflow: hidden;
  }

  /* ── Chat panel ── */
  .journal-chat {
    width: 40%;
    display: flex;
    flex-direction: column;
    border-right: 1px solid #1e1e1e;
    padding: 16px;
    gap: 12px;
    min-width: 0;
  }
  .chat-messages {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .chat-msg {
    max-width: 90%;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.5;
    font-family: 'IBM Plex Mono', monospace;
    white-space: pre-wrap;
  }
  .chat-msg.user {
    align-self: flex-end;
    background: #1a1a1a;
    color: #ccc;
  }
  .chat-msg.ai {
    align-self: flex-start;
    background: #111;
    color: #eee;
    border: 1px solid #222;
  }
  .chat-input-area {
    display: flex;
    gap: 8px;
    align-items: flex-end;
  }
  .chat-input-area textarea {
    flex: 1;
    background: #111;
    border: 1px solid #333;
    color: #eee;
    border-radius: 6px;
    padding: 10px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    resize: none;
    height: 72px;
  }
  .chat-input-area textarea:focus { outline: none; border-color: #444; }
  .btn-send {
    background: #2CC84A;
    color: #000;
    border: none;
    border-radius: 6px;
    padding: 0 16px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    height: 36px;
    flex-shrink: 0;
  }
  .btn-send:hover { background: #25a83e; }
  .btn-send:disabled { opacity: 0.5; cursor: default; }

  /* ── Cards panel ── */
  .journal-cards {
    width: 60%;
    display: flex;
    flex-direction: column;
    padding: 16px;
    min-width: 0;
    overflow: hidden;
  }
  .cards-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
    flex-shrink: 0;
  }
  .trade-count {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #555;
    flex: 1;
  }
  .btn-review {
    background: transparent;
    border: 1px solid #444;
    color: #ccc;
    border-radius: 4px;
    padding: 5px 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    cursor: pointer;
  }
  .btn-review:hover { border-color: #666; color: #eee; }
  .btn-clear {
    background: transparent;
    border: 1px solid #333;
    color: #666;
    border-radius: 4px;
    padding: 5px 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    cursor: pointer;
  }
  .btn-clear:hover { border-color: #c0392b; color: #e74c3c; }
  .cards-list {
    overflow-y: auto;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  /* ── Trade card ── */
  .trade-card {
    background: #0f0f0f;
    border: 1px solid #1e1e1e;
    border-radius: 8px;
    padding: 14px 16px;
    font-family: 'IBM Plex Mono', monospace;
    animation: slideIn 0.25s ease-out;
  }
  @keyframes slideIn {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .card-top {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }
  .card-ticker { font-size: 16px; font-weight: 700; color: #eee; }
  .card-date   { font-size: 11px; color: #444; margin-left: auto; }
  .badge {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .badge-Win       { background: #0d3b1a; color: #2CC84A; }
  .badge-Loss      { background: #3b0d0d; color: #e74c3c; }
  .badge-Breakeven { background: #1a1a1a; color: #777; }
  .badge-Open      { background: #0d1f2e; color: #4a9ede; }
  .card-setup { font-size: 11px; color: #555; margin-bottom: 8px; }
  .card-prices {
    font-size: 12px;
    color: #999;
    margin-bottom: 8px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }
  .card-prices .lbl { color: #444; font-size: 10px; margin-right: 3px; }
  .card-r-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }
  .r-entry  { font-size: 11px; color: #e6a817; white-space: nowrap; }
  .r-actual { font-size: 11px; color: #888;    white-space: nowrap; }
  .r-bar-wrap {
    flex: 1;
    height: 4px;
    background: #1a1a1a;
    border-radius: 2px;
    overflow: hidden;
  }
  .r-bar-fill          { height: 100%; border-radius: 2px; }
  .r-bar-fill.win      { background: #2CC84A; }
  .r-bar-fill.loss     { background: #e74c3c; }
  .r-bar-fill.neutral  { background: #555; }
  .card-meta {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 11px;
    color: #555;
    margin-bottom: 6px;
  }
  .exec-dots { letter-spacing: 2px; }
  .dot-on  { color: #2CC84A; }
  .dot-off { color: #2a2a2a; }
  .emotion-tag {
    background: #161616;
    border: 1px solid #222;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 10px;
    color: #666;
  }
  .card-note { font-size: 11px; margin-top: 4px; line-height: 1.4; }
  .card-note.did-right    { color: #1a6b2e; }
  .card-note.would-change { color: #444; }
</style>

<div class="journal-wrap">

  <!-- Left: AI Chat -->
  <div class="journal-chat">
    <div class="chat-messages" id="chatMessages"></div>
    <div class="chat-input-area">
      <textarea id="chatInput"
        placeholder="e.g. Bought NVDA on 12/3, breakout at $138.50, stop $134, target $148, execution 4/5, calm. Won at $146.20."
        onkeydown="handleKey(event)"></textarea>
      <button class="btn-send" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <!-- Right: Trade Cards -->
  <div class="journal-cards">
    <div class="cards-header">
      <span class="trade-count" id="tradeCount">0 trades</span>
      <button class="btn-review" onclick="requestReview()">REQUEST REVIEW</button>
      <button class="btn-clear"  onclick="clearAll()">CLEAR ALL</button>
    </div>
    <div class="cards-list" id="cardsList"></div>
  </div>

</div>
{% endblock %}

{% block scripts %}
<script>
  let conversationHistory = [];

  const SETUP_LABELS = {
    breakout: 'Breakout', pullback_ema: 'Pullback EMA',
    range: 'Range', vcp: 'VCP', other: 'Other'
  };

  function fmtSetup(s)  { return SETUP_LABELS[s] || s || '—'; }
  function fmtVal(v, p) { return v != null ? `${p || ''}${v}` : '—'; }

  function execDots(q) {
    const n = parseInt(q) || 0;
    let s = '';
    for (let i = 1; i <= 5; i++)
      s += `<span class="${i <= n ? 'dot-on' : 'dot-off'}">${i <= n ? '●' : '○'}</span>`;
    return `<span class="exec-dots">${s}</span>`;
  }

  function rBarPct(actual_r) {
    if (actual_r == null) return 0;
    return Math.min(Math.abs(parseFloat(actual_r)) * 20, 100);
  }

  function rBarClass(result) {
    if (result === 'Win') return 'win';
    if (result === 'Loss') return 'loss';
    return 'neutral';
  }

  function renderCard(t) {
    const result = t.result || 'Open';
    const pct    = rBarPct(t.actual_r);
    return `
      <div class="trade-card" id="card-${t.id}">
        <div class="card-top">
          <span class="card-ticker">${t.ticker || '—'}</span>
          <span class="badge badge-${result}">${result}</span>
          <span class="card-date">${t.date || ''}</span>
        </div>
        <div class="card-setup">${fmtSetup(t.setup_type)}</div>
        <div class="card-prices">
          <span><span class="lbl">Entry</span>${fmtVal(t.entry_price, '$')}</span>
          <span><span class="lbl">Stop</span>${fmtVal(t.stop_price, '$')}</span>
          <span><span class="lbl">Target</span>${fmtVal(t.target_price, '$')}</span>
        </div>
        <div class="card-r-row">
          <span class="r-entry">R ${fmtVal(t.r_multiple_entry)}</span>
          <div class="r-bar-wrap">
            <div class="r-bar-fill ${rBarClass(result)}" style="width:${pct}%"></div>
          </div>
          <span class="r-actual">Actual ${fmtVal(t.actual_r)}</span>
        </div>
        <div class="card-meta">
          ${execDots(t.execution_quality)}
          <span class="emotion-tag">${t.emotional_state || '—'}</span>
        </div>
        ${t.did_right    ? `<div class="card-note did-right">✓ ${t.did_right}</div>`       : ''}
        ${t.would_change ? `<div class="card-note would-change">△ ${t.would_change}</div>` : ''}
      </div>`;
  }

  function addMsg(role, text) {
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.textContent = text;
    document.getElementById('chatMessages').appendChild(div);
    div.scrollIntoView({ behavior: 'smooth' });
  }

  function updateCount() {
    const n = document.getElementById('cardsList').querySelectorAll('.trade-card').length;
    document.getElementById('tradeCount').textContent = `${n} trade${n !== 1 ? 's' : ''}`;
  }

  function prependCard(trade) {
    const list = document.getElementById('cardsList');
    const tmp  = document.createElement('div');
    tmp.innerHTML = renderCard(trade);
    list.insertBefore(tmp.firstElementChild, list.firstChild);
    updateCount();
  }

  async function sendMessage() {
    const input = document.getElementById('chatInput');
    const text  = input.value.trim();
    if (!text) return;

    input.value = '';
    document.getElementById('sendBtn').disabled = true;
    addMsg('user', text);
    conversationHistory.push({ role: 'user', content: text });

    try {
      const resp = await fetch('/api/journal/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: conversationHistory.slice(0, -1),
          message: text
        }),
      });
      const data = await resp.json();
      if (data.error) { addMsg('ai', 'Something went wrong, try again.'); return; }

      addMsg('ai', data.reply);
      conversationHistory.push({ role: 'assistant', content: data.reply });

      if (data.trade && data.trade.ticker) {
        const saveResp = await fetch('/api/journal/trades', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data.trade),
        });
        if (saveResp.ok) prependCard(await saveResp.json());
      }
    } catch (e) {
      addMsg('ai', 'Something went wrong, try again.');
    } finally {
      document.getElementById('sendBtn').disabled = false;
    }
  }

  async function requestReview() {
    addMsg('user', '[REQUEST REVIEW]');
    try {
      const resp = await fetch('/api/journal/review', { method: 'POST' });
      const data = await resp.json();
      addMsg('ai', data.error ? 'Something went wrong, try again.' : data.reply);
    } catch (e) {
      addMsg('ai', 'Something went wrong, try again.');
    }
  }

  async function clearAll() {
    if (!confirm('Delete all trade cards? This cannot be undone.')) return;
    await fetch('/api/journal/trades', { method: 'DELETE' });
    document.getElementById('cardsList').innerHTML = '';
    updateCount();
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }

  // Init: load opening message + persisted trades
  (async () => {
    addMsg('ai', 'Tell me about your last trade.');
    conversationHistory.push({ role: 'assistant', content: 'Tell me about your last trade.' });
    try {
      const trades = await (await fetch('/api/journal/trades')).json();
      trades.forEach(t => {
        const list = document.getElementById('cardsList');
        const tmp  = document.createElement('div');
        tmp.innerHTML = renderCard(t);
        list.appendChild(tmp.firstElementChild);
      });
      updateCount();
    } catch (e) {}
  })();
</script>
{% endblock %}
```

- [ ] **Step 2: Verify the template renders via test**

```bash
python -m pytest tests/test_app.py::test_journal_page_requires_login -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add templates/journal.html
git commit -m "feat: add journal two-panel HTML template"
```

---

## Task 4: Add Journal tab to dashboard

**Files:**
- Modify: `templates/dashboard.html`

- [ ] **Step 1: Add the Journal tab**

In `templates/dashboard.html`, find:

```html
    <a href="{{ url_for('research_tab') }}"
       class="tab">Research</a>
```

Replace with:

```html
    <a href="{{ url_for('research_tab') }}"
       class="tab">Research</a>
    <a href="{{ url_for('journal_tab') }}"
       class="tab">Journal</a>
```

- [ ] **Step 2: Run the full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat: add Journal tab to dashboard nav"
```

---

## Self-Review

**Spec coverage:**
- ✅ Two-panel layout — chat 40% left, cards 60% right
- ✅ Claude conversation with history sent per request
- ✅ Trade cards: ticker, date, result badge, setup, entry/stop/target, R at entry (amber), actual R with bar, execution dots, emotion tag, did-right / would-change notes
- ✅ Server-side persistence in journal.json (multi-device via Railway)
- ✅ REQUEST REVIEW button → plain-text analysis in chat
- ✅ CLEAR ALL with confirmation dialog
- ✅ Trade count in cards header
- ✅ Input placeholder with example
- ✅ Opening message "Tell me about your last trade."
- ✅ Rule violation flagging (impulse, no stop, averaging down)
- ✅ Dark theme, IBM Plex Mono, green #2CC84A wins, red losses, amber R-at-entry
- ✅ Card animate-in (slideIn keyframe)
- ✅ API key in Railway env var (ANTHROPIC_API_KEY), never exposed to browser
- ✅ `direction` field removed (always Long)
- ✅ `position_size` field removed

**Type consistency check:**
- `journal_module.get_journal_path` → defined Task 1, used Task 2 ✅
- `journal_module.load_trades` / `save_trade` / `clear_trades` → defined Task 1, used Task 2 ✅
- `journal_module.calculate_r_multiple` → defined Task 1, used Task 2 ✅
- `journal_module.parse_claude_response` → defined Task 1, used Task 2 ✅
- `journal_module.call_claude_chat` / `call_claude_review` → defined Task 1, used Task 2 ✅
- `_journal_path()` → defined and used in Task 2 only ✅
- Card field names in JS match data model exactly ✅
