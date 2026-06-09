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
