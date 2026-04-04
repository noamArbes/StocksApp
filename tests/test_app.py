import json
import os
import tempfile
import pytest

os.environ.setdefault("UI_PASSWORD", "testpass")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("BREVO_API_KEY", "test")
os.environ.setdefault("BREVO_SENDER_EMAIL", "test@test.com")

import app as app_module
from app import app as flask_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def login(client):
    return client.post("/login", data={"password": "testpass"}, follow_redirects=True)


def test_index_redirects_when_not_logged_in(client):
    resp = client.get("/")
    # Should show login page (200) or redirect to login (302)
    assert resp.status_code in (200, 302)


def test_login_correct_password_redirects_to_dashboard(client):
    resp = client.post("/login", data={"password": "testpass"})
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]


def test_login_wrong_password_shows_error(client):
    resp = client.post("/login", data={"password": "wrong"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Incorrect" in resp.data or b"incorrect" in resp.data


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 302


def test_logout_clears_session(client):
    login(client)
    client.get("/logout")
    resp = client.get("/dashboard")
    assert resp.status_code == 302


def test_dashboard_shows_alarms(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "abc1", "ticker": "WDC", "enabled": True, "upper_limit": 280.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms2.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"WDC" in resp.data


def test_alarm_from_form_valid_price():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "aapl"), ("alarm_type", "price"),
        ("upper_limit", "200"), ("lower_limit", ""),
        ("email", "a@b.com"), ("timezone", ""), ("enabled", "on"),
    ])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["ticker"] == "AAPL"
    assert alarm["upper_limit"] == 200.0
    assert alarm["lower_limit"] is None
    assert alarm["email"] == "a@b.com"
    assert alarm["enabled"] is True


def test_alarm_from_form_missing_ticker():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", ""), ("alarm_type", "price"),
                               ("upper_limit", "200"), ("email", "a@b.com")])
    _, error = _alarm_from_form(form)
    assert error == "Ticker is required"


def test_alarm_from_form_no_condition():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", "WDC"), ("alarm_type", "price"),
                               ("upper_limit", ""), ("lower_limit", ""), ("email", "a@b.com")])
    _, error = _alarm_from_form(form)
    assert error == "At least one price limit is required"


def test_alarm_from_form_bad_number():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", "WDC"), ("alarm_type", "price"),
                               ("upper_limit", "abc"), ("email", "a@b.com")])
    _, error = _alarm_from_form(form)
    assert error == "Price limits must be numbers"


def test_alarm_from_form_multiple_emails():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", "WDC"), ("alarm_type", "price"),
                               ("upper_limit", "200"), ("email", "a@b.com, c@d.com")])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["email"] == ["a@b.com", "c@d.com"]


def test_alarm_from_form_pct():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", "WDC"), ("alarm_type", "pct"),
                               ("upper_pct", "5"), ("lower_pct", "3"), ("email", "a@b.com")])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["upper_pct"] == 5.0
    assert alarm["lower_pct"] == 3.0
    assert alarm.get("base_price") is None


def test_create_alarm_via_post(client, tmp_path, monkeypatch):
    import app as app_module
    alarms_file = tmp_path / "alarms3.json"
    alarms_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.post("/alarm/new", data={
        "ticker": "AAPL", "alarm_type": "price", "upper_limit": "200",
        "lower_limit": "", "email": "a@b.com", "timezone": "", "enabled": "on",
    })
    assert resp.status_code == 302
    saved = json.loads(alarms_file.read_text())
    assert len(saved) == 1
    assert saved[0]["ticker"] == "AAPL"


def test_delete_alarm(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "del1", "ticker": "WDC", "enabled": True, "upper_limit": 280.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms4.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.post("/alarm/del1/delete")
    assert resp.status_code == 302
    saved = json.loads(alarms_file.read_text())
    assert saved == []


def test_toggle_alarm(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "tog1", "ticker": "WDC", "enabled": True, "upper_limit": 280.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms5.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    client.post("/alarm/tog1/toggle")
    saved = json.loads(alarms_file.read_text())
    assert saved[0]["enabled"] is False


def test_chart_data_returns_json(client, tmp_path, monkeypatch):
    import app as app_module
    import pandas as pd
    alarms = [{"id": "ch1", "ticker": "WDC", "enabled": True, "upper_limit": 280.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms6.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))

    import yfinance as yf
    class FakeTicker:
        def history(self, period):
            dates = pd.date_range("2026-03-01", periods=5, tz="UTC")
            return pd.DataFrame({"Close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=dates)
    monkeypatch.setattr(yf, "Ticker", lambda t: FakeTicker())

    login(client)
    resp = client.get("/alarm/ch1/chart-data")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "labels" in data
    assert "prices" in data
    assert len(data["prices"]) == 5
