from datetime import datetime, timezone, timedelta
import checker
from checker import condition_met, should_alert


# --- condition_met tests ---

def test_price_above_upper_limit():
    alarm = {"upper_limit": 200.0, "lower_limit": None}
    triggered, limit_type, limit_value = condition_met(alarm, 201.0)
    assert triggered is True
    assert limit_type == "upper"
    assert limit_value == 200.0

def test_price_equal_to_upper_limit():
    alarm = {"upper_limit": 200.0, "lower_limit": None}
    triggered, limit_type, limit_value = condition_met(alarm, 200.0)
    assert triggered is True
    assert limit_type == "upper"

def test_price_below_upper_limit():
    alarm = {"upper_limit": 200.0, "lower_limit": None}
    triggered, _, _ = condition_met(alarm, 199.0)
    assert triggered is False

def test_price_below_lower_limit():
    alarm = {"upper_limit": None, "lower_limit": 100.0}
    triggered, limit_type, limit_value = condition_met(alarm, 99.0)
    assert triggered is True
    assert limit_type == "lower"
    assert limit_value == 100.0

def test_price_equal_to_lower_limit():
    alarm = {"upper_limit": None, "lower_limit": 100.0}
    triggered, limit_type, _ = condition_met(alarm, 100.0)
    assert triggered is True
    assert limit_type == "lower"

def test_price_above_lower_limit():
    alarm = {"upper_limit": None, "lower_limit": 100.0}
    triggered, _, _ = condition_met(alarm, 101.0)
    assert triggered is False

def test_no_limits_set():
    alarm = {"upper_limit": None, "lower_limit": None}
    triggered, limit_type, limit_value = condition_met(alarm, 150.0)
    assert triggered is False
    assert limit_type is None
    assert limit_value is None

def test_both_limits_set_upper_triggered():
    alarm = {"upper_limit": 200.0, "lower_limit": 100.0}
    triggered, limit_type, _ = condition_met(alarm, 205.0)
    assert triggered is True
    assert limit_type == "upper"

def test_both_limits_set_lower_triggered():
    alarm = {"upper_limit": 200.0, "lower_limit": 100.0}
    triggered, limit_type, _ = condition_met(alarm, 95.0)
    assert triggered is True
    assert limit_type == "lower"

def test_both_limits_set_no_trigger():
    alarm = {"upper_limit": 200.0, "lower_limit": 100.0}
    triggered, _, _ = condition_met(alarm, 150.0)
    assert triggered is False


# --- should_alert tests ---

def test_should_alert_when_never_triggered():
    alarm = {"last_triggered": None}
    assert should_alert(alarm) is True

def test_should_alert_when_triggered_four_days_ago():
    four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    alarm = {"last_triggered": four_days_ago}
    assert should_alert(alarm) is True

def test_should_not_alert_when_triggered_two_days_ago():
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    alarm = {"last_triggered": two_days_ago}
    assert should_alert(alarm) is False

def test_should_alert_when_triggered_exactly_three_days_ago():
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    alarm = {"last_triggered": three_days_ago}
    assert should_alert(alarm) is True


from checker import format_subject, format_body


# --- format_subject tests ---

def test_format_subject_upper_limit():
    subject = format_subject("AAPL", 231.50, "upper", 230.00)
    assert subject == "Stock Alert: AAPL hit $231.50 (upper limit: $230.00)"

def test_format_subject_lower_limit():
    subject = format_subject("TSLA", 98.75, "lower", 100.00)
    assert subject == "Stock Alert: TSLA hit $98.75 (lower limit: $100.00)"


# --- format_body tests ---

def test_format_body_contains_ticker():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "AAPL" in body

def test_format_body_contains_price():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "$231.50" in body

def test_format_body_contains_limit_value():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "$230.00" in body

def test_format_body_contains_limit_type():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "upper" in body

def test_format_body_lower_limit():
    body = format_body("TSLA", 98.75, "lower", 100.00)
    assert "lower" in body
    assert "$98.75" in body


import json
import os
import tempfile
from checker import load_alarms, save_alarms


# --- load_alarms / save_alarms tests ---

def test_load_alarms_returns_list():
    alarms = [{"id": "a1", "ticker": "AAPL", "enabled": True, "last_triggered": None}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(alarms, f)
        path = f.name
    try:
        result = load_alarms(path)
        assert isinstance(result, list)
        assert result[0]["ticker"] == "AAPL"
    finally:
        os.unlink(path)

def test_save_and_reload_alarms():
    alarms = [{"id": "a1", "ticker": "TSLA", "enabled": False, "last_triggered": "2026-01-01T00:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_alarms(alarms, path)
        result = load_alarms(path)
        assert result[0]["ticker"] == "TSLA"
        assert result[0]["enabled"] is False
        assert result[0]["last_triggered"] == "2026-01-01T00:00:00+00:00"
    finally:
        os.unlink(path)

def test_save_alarms_writes_valid_json():
    alarms = [{"id": "a1", "ticker": "GOOG", "enabled": True, "last_triggered": None}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_alarms(alarms, path)
        with open(path) as f:
            data = json.load(f)
        assert data[0]["ticker"] == "GOOG"
    finally:
        os.unlink(path)


def test_volume_sync_preserves_base_price(monkeypatch, tmp_path):
    import json as _json
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    volume_path = data_dir / "alarms.json"

    local_alarms = [{"id": "a1", "ticker": "WDC", "upper_pct": 5.0, "base_price": None, "last_triggered": None}]
    volume_alarms = [{"id": "a1", "ticker": "WDC", "upper_pct": 5.0, "base_price": 280.0, "last_triggered": None}]

    local_file = tmp_path / "alarms.json"
    local_file.write_text(_json.dumps(local_alarms))
    volume_path.write_text(_json.dumps(volume_alarms))

    monkeypatch.setattr("checker.LOCAL_PATH", str(local_file))
    monkeypatch.setattr("checker.VOLUME_PATH", str(volume_path))

    import os
    original_isdir = os.path.isdir
    monkeypatch.setattr("os.path.isdir", lambda p: True if p == "/data" else original_isdir(p))
    monkeypatch.setattr("checker.get_alarms_path.__globals__['os'].path.isdir", lambda p: True if p == "/data" else original_isdir(p), raising=False)

    # Patch os.path.isdir inside checker module specifically
    import checker
    monkeypatch.setattr(checker.os.path, "isdir", lambda p: True if p == "/data" else original_isdir(p))

    checker.get_alarms_path()

    result = _json.loads(volume_path.read_text())
    assert result[0]["base_price"] == 280.0


def test_format_body_shows_local_timezone():
    body = format_body("AAPL", 231.50, "upper", 230.00, tz_name="Asia/Jerusalem")
    # Jerusalem is UTC+2 or UTC+3 — IST or IDT should appear
    assert "IST" in body or "IDT" in body or "+03" in body or "+02" in body

def test_format_body_falls_back_to_utc_on_invalid_timezone():
    body = format_body("AAPL", 231.50, "upper", 230.00, tz_name="Invalid/Zone")
    assert "UTC" in body

def test_format_body_defaults_to_utc_when_no_timezone():
    body = format_body("AAPL", 231.50, "upper", 230.00)
    assert "UTC" in body


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


def test_history_appended_after_price_alarm_triggers(monkeypatch, tmp_path):
    alarm = {
        "id": "h1", "ticker": "WDC", "enabled": True,
        "upper_limit": 200.0, "lower_limit": None,
        "email": "a@b.com", "last_triggered": None, "timezone": None,
    }
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([alarm]))
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "from@test.com")
    monkeypatch.setattr(checker, "get_price", lambda t: 250.0)
    monkeypatch.setattr(checker, "send_email", lambda *a, **kw: None)
    checker.run(path=str(alarms_file))
    saved = json.loads(alarms_file.read_text())
    assert len(saved[0]["history"]) == 1
    entry = saved[0]["history"][0]
    assert entry["type"] == "upper"
    assert entry["price"] == 250.0
    assert entry["threshold"] == 200.0
    assert "triggered_at" in entry


def test_history_capped_at_10_entries(monkeypatch, tmp_path):
    existing_history = [
        {"triggered_at": f"2026-01-{i:02d}T00:00:00+00:00",
         "type": "upper", "price": 250.0, "threshold": 200.0}
        for i in range(1, 11)
    ]
    alarm = {
        "id": "h2", "ticker": "WDC", "enabled": True,
        "upper_limit": 200.0, "lower_limit": None,
        "email": "a@b.com", "last_triggered": None, "timezone": None,
        "history": existing_history,
    }
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([alarm]))
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "from@test.com")
    monkeypatch.setattr(checker, "get_price", lambda t: 250.0)
    monkeypatch.setattr(checker, "send_email", lambda *a, **kw: None)
    checker.run(path=str(alarms_file))
    saved = json.loads(alarms_file.read_text())
    assert len(saved[0]["history"]) == 10


def test_history_appended_after_pct_alarm_triggers(monkeypatch, tmp_path):
    alarm = {
        "id": "h3", "ticker": "WDC", "enabled": True,
        "upper_pct": 5.0, "lower_pct": None,
        "base_price": 100.0,
        "email": "a@b.com", "last_triggered": None, "timezone": None,
    }
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([alarm]))
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "from@test.com")
    monkeypatch.setattr(checker, "get_price", lambda t: 110.0)
    monkeypatch.setattr(checker, "send_email", lambda *a, **kw: None)
    checker.run(path=str(alarms_file))
    saved = json.loads(alarms_file.read_text())
    assert len(saved[0]["history"]) == 1
    entry = saved[0]["history"][0]
    assert entry["type"] == "upper_pct"
    assert entry["price"] == 110.0
    assert entry["threshold"] == 5.0


from checker import format_subject, format_body, format_subject_pct, format_body_pct


def test_format_subject_default_currency():
    result = format_subject("AAPL", 150.00, "upper", 149.00)
    assert "$150.00" in result
    assert "$149.00" in result


def test_format_subject_shekel_currency():
    result = format_subject("ELTR", 185.30, "upper", 180.00, currency="₪")
    assert "₪185.30" in result
    assert "₪180.00" in result
    assert "$" not in result


def test_format_body_default_currency():
    result = format_body("AAPL", 150.00, "upper", 149.00)
    assert "$150.00" in result
    assert "$149.00" in result


def test_format_body_shekel_currency():
    result = format_body("ELTR", 185.30, "upper", 180.00, currency="₪")
    assert "₪185.30" in result
    assert "₪180.00" in result
    assert "$" not in result


def test_format_body_pct_default_currency():
    result = format_body_pct("AAPL", 155.0, "upper_pct", 5.0, 150.0, 3.33)
    assert "$155.00" in result
    assert "$150.00" in result


def test_format_body_pct_shekel_currency():
    result = format_body_pct("ELTR", 190.0, "upper_pct", 5.0, 180.0, 5.56, currency="₪")
    assert "₪190.00" in result
    assert "₪180.00" in result
    assert "$" not in result


# --- load_trades / save_trades tests ---

def test_load_trades_returns_empty_list_when_file_missing():
    result = checker.load_trades("/tmp/nonexistent_trades_abc123.json")
    assert result == []


def test_load_trades_returns_list():
    trades = [{"id": "t1", "ticker": "WDC", "buy_price": 42.10, "sell_price": 67.80,
               "buy_date": "2026-01-15", "sell_date": "2026-04-10", "shares": 20,
               "source": "yfinance", "created_at": "2026-04-10T14:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(trades, f)
        path = f.name
    try:
        result = checker.load_trades(path)
        assert isinstance(result, list)
        assert result[0]["ticker"] == "WDC"
        assert result[0]["shares"] == 20
    finally:
        os.unlink(path)


def test_save_and_reload_trades():
    trades = [{"id": "t2", "ticker": "AAPL", "buy_price": 150.0, "sell_price": 160.0,
               "buy_date": "2026-01-01", "sell_date": "2026-02-01", "shares": None,
               "source": "yfinance", "created_at": "2026-02-01T00:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        checker.save_trades(trades, path)
        result = checker.load_trades(path)
        assert result[0]["ticker"] == "AAPL"
        assert result[0]["shares"] is None
    finally:
        os.unlink(path)


def test_save_trades_writes_valid_json():
    trades = [{"id": "t3", "ticker": "TSLA", "buy_price": 200.0, "sell_price": 250.0,
               "buy_date": "2026-01-01", "sell_date": "2026-03-01", "shares": 5,
               "source": "yfinance", "created_at": "2026-03-01T00:00:00+00:00"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        checker.save_trades(trades, path)
        with open(path) as f:
            data = json.load(f)
        assert data[0]["ticker"] == "TSLA"
    finally:
        os.unlink(path)
