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
