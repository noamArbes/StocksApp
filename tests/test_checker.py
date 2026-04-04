from datetime import datetime, timezone, timedelta
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
