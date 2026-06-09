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
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_trade(trade, path=None):
    path = path or get_journal_path()
    trades = load_trades(path)
    trade = dict(trade)          # shallow copy before mutating
    if not trade.get("id"):
        trade["id"] = str(uuid.uuid4())
    trades.append(trade)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2)
    return trade


def clear_trades(path=None):
    path = path or get_journal_path()
    with open(path, "w", encoding="utf-8") as f:
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
        max_tokens=2048,
        system=_JOURNAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"REVIEW\n\nHere are all my trades:\n{trades_json}"}],
    )
    return response.content[0].text
