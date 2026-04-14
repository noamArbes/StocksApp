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


def test_alarm_from_form_owned_on():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "AAPL"), ("alarm_type", "price"),
        ("upper_limit", "200"), ("lower_limit", ""),
        ("email", "a@b.com"), ("timezone", "America/New_York"),
        ("enabled", "on"), ("owned", "on"),
    ])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["owned"] is True


def test_alarm_from_form_owned_off():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "AAPL"), ("alarm_type", "price"),
        ("upper_limit", "200"), ("lower_limit", ""),
        ("email", "a@b.com"), ("timezone", "America/New_York"),
        ("enabled", "on"),
        # "owned" checkbox not submitted = False
    ])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["owned"] is False


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


def test_chart_data_accepts_valid_period(client, tmp_path, monkeypatch):
    import app as app_module
    import pandas as pd
    alarms = [{"id": "cp1", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_cp1.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    captured = {}
    import yfinance as yf
    class FakeTicker:
        def history(self, period):
            captured["period"] = period
            dates = pd.date_range("2026-01-01", periods=3, tz="UTC")
            return pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=dates)
    monkeypatch.setattr(yf, "Ticker", lambda t: FakeTicker())
    login(client)
    resp = client.get("/alarm/cp1/chart-data?period=1y")
    assert resp.status_code == 200
    assert captured["period"] == "1y"


def test_chart_data_invalid_period_falls_back_to_default(client, tmp_path, monkeypatch):
    import app as app_module
    import pandas as pd
    alarms = [{"id": "cp2", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_cp2.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    captured = {}
    import yfinance as yf
    class FakeTicker:
        def history(self, period):
            captured["period"] = period
            dates = pd.date_range("2026-01-01", periods=3, tz="UTC")
            return pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=dates)
    monkeypatch.setattr(yf, "Ticker", lambda t: FakeTicker())
    login(client)
    resp = client.get("/alarm/cp2/chart-data?period=badvalue")
    assert resp.status_code == 200
    assert captured["period"] == "1mo"


def test_dashboard_sort_az(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [
        {"id": "s1", "ticker": "TSLA", "enabled": True, "upper_limit": 100.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-01T00:00:00+00:00"},
        {"id": "s2", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-02T00:00:00+00:00"},
    ]
    alarms_file = tmp_path / "alarms_sort.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard?sort=az")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert body.index("AAPL") < body.index("TSLA")


def test_dashboard_sort_oldest(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [
        {"id": "s3", "ticker": "TSLA", "enabled": True, "upper_limit": 100.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-02T00:00:00+00:00"},
        {"id": "s4", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "created_at": "2026-04-01T00:00:00+00:00"},
    ]
    alarms_file = tmp_path / "alarms_sort2.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard?sort=oldest")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert body.index("AAPL") < body.index("TSLA")


def test_alarm_creation_sets_created_at_and_initial_price(client, tmp_path, monkeypatch):
    import app as app_module
    alarms_file = tmp_path / "alarms_meta.json"
    alarms_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 123.45)
    login(client)
    client.post("/alarm/new", data={
        "ticker": "MSFT", "alarm_type": "price", "upper_limit": "500",
        "lower_limit": "", "email": "a@b.com", "timezone": "", "enabled": "on",
    })
    saved = json.loads(alarms_file.read_text())
    assert len(saved) == 1
    assert "created_at" in saved[0]
    assert saved[0]["initial_price"] == 123.45
    assert saved[0]["history"] == []


def test_alarm_creation_initial_price_null_on_fetch_failure(client, tmp_path, monkeypatch):
    import app as app_module
    alarms_file = tmp_path / "alarms_meta2.json"
    alarms_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    def raise_error(t):
        raise ValueError("no price")
    monkeypatch.setattr("checker.get_price", raise_error)
    login(client)
    client.post("/alarm/new", data={
        "ticker": "MSFT", "alarm_type": "price", "upper_limit": "500",
        "lower_limit": "", "email": "a@b.com", "timezone": "", "enabled": "on",
    })
    saved = json.loads(alarms_file.read_text())
    assert len(saved) == 1
    assert saved[0]["initial_price"] is None


def test_alarm_edit_preserves_created_at_and_initial_price(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "meta1", "ticker": "WDC", "enabled": True, "upper_limit": 280.0,
                "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
                "created_at": "2026-04-01T00:00:00+00:00", "initial_price": 99.99, "history": []}]
    alarms_file = tmp_path / "alarms_meta3.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 200.0)
    login(client)
    client.post("/alarm/meta1/edit", data={
        "ticker": "WDC", "alarm_type": "price", "upper_limit": "300",
        "lower_limit": "", "email": "a@b.com", "timezone": "", "enabled": "on",
    })
    saved = json.loads(alarms_file.read_text())
    assert saved[0]["created_at"] == "2026-04-01T00:00:00+00:00"
    assert saved[0]["initial_price"] == 99.99


from unittest.mock import patch


def test_tase_search_returns_results(client):
    login(client)
    sample_cache = [
        {"id": "1175819", "name": "Eltra Corp", "ticker": "ELTR", "type": "security"},
        {"id": "5118393", "name": "Migdal Bonds Fund", "ticker": None, "type": "fund"},
    ]
    with patch.object(app_module, "_tase_cache", sample_cache):
        resp = client.get("/api/tase-search?q=eltra")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data) == 1
    assert data[0]["id"] == "1175819"


def test_tase_search_requires_login(client):
    resp = client.get("/api/tase-search?q=eltra")
    assert resp.status_code in (302, 401)


def test_tase_search_short_query_returns_empty(client):
    login(client)
    resp = client.get("/api/tase-search?q=e")
    assert resp.status_code == 200
    assert json.loads(resp.data) == []


def test_duplicate_route_removed(client):
    login(client)
    resp = client.post("/alarm/nonexistent/duplicate")
    assert resp.status_code == 404


def test_create_tase_alarm(client):
    login(client)
    with patch("tase.get_price", return_value=185.30):
        resp = client.post("/alarm/new", data={
            "ticker": "Eltra Corp",
            "source": "tase",
            "tase_id": "1175819",
            "tase_type": "security",
            "alarm_type": "price",
            "upper_limit": "200",
            "email": "test@example.com",
            "timezone": "Asia/Jerusalem",
            "snooze_hours": "72",
            "enabled": "on",
        }, follow_redirects=True)
    assert resp.status_code == 200
    alarms = json.loads(open(app_module._alarms_path()).read())
    assert len(alarms) == 1
    assert alarms[0]["source"] == "tase"
    assert alarms[0]["tase_id"] == "1175819"
    assert alarms[0]["initial_price"] == 185.30
    assert alarms[0]["ticker"] == "Eltra Corp"  # preserves case for TASE


def test_create_alarm_with_manual_reference_price(client):
    login(client)
    with patch("checker.get_price", return_value=155.0):
        resp = client.post("/alarm/new", data={
            "ticker": "AAPL",
            "alarm_type": "price",
            "upper_limit": "200",
            "email": "test@example.com",
            "timezone": "America/New_York",
            "snooze_hours": "72",
            "enabled": "on",
            "reference_price": "130.00",
        }, follow_redirects=True)
    assert resp.status_code == 200
    alarms = json.loads(open(app_module._alarms_path()).read())
    assert alarms[0]["initial_price"] == 130.0  # manual price used, not live fetch


def test_create_pct_alarm_with_manual_reference_price(client):
    login(client)
    with patch("checker.get_price", return_value=155.0):
        resp = client.post("/alarm/new", data={
            "ticker": "AAPL",
            "alarm_type": "pct",
            "upper_pct": "5",
            "email": "test@example.com",
            "timezone": "America/New_York",
            "snooze_hours": "72",
            "enabled": "on",
            "reference_price": "130.00",
        }, follow_redirects=True)
    assert resp.status_code == 200
    alarms = json.loads(open(app_module._alarms_path()).read())
    assert alarms[0]["base_price"] == 130.0
    assert alarms[0]["initial_price"] == 130.0


def test_create_tase_alarm_missing_tase_id_returns_error(client):
    login(client)
    resp = client.post("/alarm/new", data={
        "ticker": "Some Fund",
        "source": "tase",
        "tase_id": "",
        "tase_type": "fund",
        "alarm_type": "price",
        "upper_limit": "200",
        "email": "test@example.com",
        "timezone": "Asia/Jerusalem",
        "snooze_hours": "72",
        "enabled": "on",
    })
    assert resp.status_code == 200
    assert b"select a security" in resp.data


def test_toggle_owned_flips_false_to_true(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "own1", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
               "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
               "owned": False}]
    alarms_file = tmp_path / "alarms_own1.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.post("/alarm/own1/toggle-owned")
    assert resp.status_code == 302
    saved = json.loads(alarms_file.read_text())
    assert saved[0]["owned"] is True


def test_toggle_owned_flips_true_to_false(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "own2", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
               "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
               "owned": True}]
    alarms_file = tmp_path / "alarms_own2.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.post("/alarm/own2/toggle-owned")
    assert resp.status_code == 302
    saved = json.loads(alarms_file.read_text())
    assert saved[0]["owned"] is False


def test_toggle_owned_defaults_missing_field_to_true(client, tmp_path, monkeypatch):
    import app as app_module
    # Alarm with no 'owned' field at all (legacy alarm)
    alarms = [{"id": "own3", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
               "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_own3.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.post("/alarm/own3/toggle-owned")
    assert resp.status_code == 302
    saved = json.loads(alarms_file.read_text())
    # Missing owned defaults to False, so flipping gives True
    assert saved[0]["owned"] is True


def test_toggle_owned_preserves_query_params(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "own4", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
               "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
               "owned": False}]
    alarms_file = tmp_path / "alarms_own4.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.post("/alarm/own4/toggle-owned?sort=az&owned=owned")
    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert "sort=az" in location
    assert "owned=owned" in location


def test_toggle_owned_requires_login(client):
    resp = client.post("/alarm/any/toggle-owned")
    assert resp.status_code == 302
    assert "dashboard" not in resp.headers["Location"]
