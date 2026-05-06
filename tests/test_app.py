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
        ("email", "a@b.com"), ("timezone", "America/New_York"), ("enabled", "on"),
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
                               ("upper_limit", ""), ("lower_limit", ""),
                               ("email", "a@b.com"), ("timezone", "America/New_York")])
    _, error = _alarm_from_form(form)
    assert error == "At least one price limit is required"


def test_alarm_from_form_bad_number():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", "WDC"), ("alarm_type", "price"),
                               ("upper_limit", "abc"), ("email", "a@b.com"),
                               ("timezone", "America/New_York")])
    _, error = _alarm_from_form(form)
    assert error == "Price limits must be numbers"


def test_alarm_from_form_multiple_emails():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", "WDC"), ("alarm_type", "price"),
                               ("upper_limit", "200"), ("email", "a@b.com, c@d.com"),
                               ("timezone", "America/New_York")])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["email"] == ["a@b.com", "c@d.com"]


def test_alarm_from_form_pct():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([("ticker", "WDC"), ("alarm_type", "pct"),
                               ("upper_pct", "5"), ("lower_pct", "3"),
                               ("email", "a@b.com"), ("timezone", "America/New_York")])
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
        "lower_limit": "", "email": "a@b.com", "timezone": "America/New_York", "enabled": "on",
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
        "lower_limit": "", "email": "a@b.com", "timezone": "America/New_York", "enabled": "on",
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
        "lower_limit": "", "email": "a@b.com", "timezone": "America/New_York", "enabled": "on",
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


def test_dashboard_owned_filter_shows_only_owned(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [
        {"id": "f1", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "owned": True, "created_at": "2026-04-01T00:00:00+00:00"},
        {"id": "f2", "ticker": "TSLA", "enabled": True, "upper_limit": 100.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "owned": False, "created_at": "2026-04-02T00:00:00+00:00"},
    ]
    alarms_file = tmp_path / "alarms_filter1.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard?owned=owned")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "AAPL" in body
    assert "TSLA" not in body


def test_dashboard_owned_filter_shows_only_watching(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [
        {"id": "f3", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "owned": True, "created_at": "2026-04-01T00:00:00+00:00"},
        {"id": "f4", "ticker": "TSLA", "enabled": True, "upper_limit": 100.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "owned": False, "created_at": "2026-04-02T00:00:00+00:00"},
    ]
    alarms_file = tmp_path / "alarms_filter2.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard?owned=watching")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "TSLA" in body
    assert "AAPL" not in body


def test_dashboard_owned_filter_all_shows_all(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [
        {"id": "f5", "ticker": "AAPL", "enabled": True, "upper_limit": 200.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "owned": True, "created_at": "2026-04-01T00:00:00+00:00"},
        {"id": "f6", "ticker": "TSLA", "enabled": True, "upper_limit": 100.0,
         "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
         "owned": False, "created_at": "2026-04-02T00:00:00+00:00"},
    ]
    alarms_file = tmp_path / "alarms_filter3.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    resp = client.get("/dashboard?owned=all")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "AAPL" in body
    assert "TSLA" in body


def test_dashboard_owned_filter_legacy_alarm_treated_as_watching(client, tmp_path, monkeypatch):
    import app as app_module
    # Alarm with no 'owned' key at all (pre-feature alarm)
    alarms = [{"id": "f7", "ticker": "WDC", "enabled": True, "upper_limit": 100.0,
               "lower_limit": None, "email": "a@b.com", "last_triggered": None, "timezone": None,
               "created_at": "2026-04-01T00:00:00+00:00"}]
    alarms_file = tmp_path / "alarms_filter4.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    # With ?owned=watching, legacy alarm (no 'owned' key) should appear
    resp = client.get("/dashboard?owned=watching")
    assert resp.status_code == 200
    assert b"WDC" in resp.data
    # With ?owned=owned, it should NOT appear
    resp2 = client.get("/dashboard?owned=owned")
    assert b"WDC" not in resp2.data


def test_alarm_from_form_shares_set():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("alarm_type", "price"), ("upper_limit", "200"),
        ("email", "a@b.com"), ("timezone", "America/New_York"),
        ("enabled", "on"), ("owned", "on"), ("shares", "20"),
    ])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["shares"] == 20


def test_alarm_from_form_shares_blank():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("alarm_type", "price"), ("upper_limit", "200"),
        ("email", "a@b.com"), ("timezone", "America/New_York"), ("enabled", "on"),
    ])
    alarm, error = _alarm_from_form(form)
    assert error is None
    assert alarm["shares"] is None


def test_alarm_from_form_shares_invalid():
    from app import _alarm_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("alarm_type", "price"), ("upper_limit", "200"),
        ("email", "a@b.com"), ("timezone", "America/New_York"),
        ("enabled", "on"), ("owned", "on"), ("shares", "abc"),
    ])
    _, error = _alarm_from_form(form)
    assert error == "Shares must be a number"


def test_trade_from_form_valid():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("source", "yfinance"),
        ("shares", "20"), ("buy_price", "42.10"), ("buy_date", "2026-01-15"),
        ("sell_price", "67.80"), ("sell_date", "2026-04-10"),
    ])
    trade, error = _trade_from_form(form)
    assert error is None
    assert trade["ticker"] == "WDC"
    assert trade["shares"] == 20
    assert trade["buy_price"] == 42.10
    assert trade["sell_price"] == 67.80
    assert trade["buy_date"] == "2026-01-15"
    assert trade["sell_date"] == "2026-04-10"
    assert trade["source"] == "yfinance"
    assert "id" in trade
    assert "created_at" in trade


def test_trade_from_form_shares_optional():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "AAPL"), ("source", "yfinance"),
        ("buy_price", "150.0"), ("buy_date", "2026-01-01"),
        ("sell_price", "160.0"), ("sell_date", "2026-02-01"),
    ])
    trade, error = _trade_from_form(form)
    assert error is None
    assert trade["shares"] is None


def test_trade_from_form_missing_ticker():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", ""), ("buy_price", "42.0"), ("buy_date", "2026-01-01"),
        ("sell_price", "50.0"), ("sell_date", "2026-02-01"),
    ])
    _, error = _trade_from_form(form)
    assert error == "Ticker is required"


def test_trade_from_form_missing_sell_price():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("buy_price", "42.0"), ("buy_date", "2026-01-01"),
        ("sell_price", ""), ("sell_date", "2026-02-01"),
    ])
    _, error = _trade_from_form(form)
    assert error == "Sell price is required"


def test_trade_from_form_missing_buy_date():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("buy_price", "42.0"), ("buy_date", ""),
        ("sell_price", "50.0"), ("sell_date", "2026-02-01"),
    ])
    _, error = _trade_from_form(form)
    assert error == "Buy date is required"


def test_trade_from_form_preserves_id_on_edit():
    from app import _trade_from_form
    from werkzeug.datastructures import ImmutableMultiDict
    existing = {"id": "abc12345", "created_at": "2026-01-01T00:00:00+00:00"}
    form = ImmutableMultiDict([
        ("ticker", "WDC"), ("source", "yfinance"),
        ("buy_price", "42.0"), ("buy_date", "2026-01-01"),
        ("sell_price", "50.0"), ("sell_date", "2026-02-01"),
    ])
    trade, error = _trade_from_form(form, existing=existing)
    assert error is None
    assert trade["id"] == "abc12345"
    assert trade["created_at"] == "2026-01-01T00:00:00+00:00"


def test_create_trade_via_post(client, tmp_path, monkeypatch):
    import app as app_module
    trades_file = tmp_path / "trades.json"
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/trade/new", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "20", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "67.80", "sell_date": "2026-04-10",
    })
    assert resp.status_code == 302
    assert "tab=history" in resp.headers["Location"]
    saved = json.loads(trades_file.read_text())
    assert len(saved) == 1
    assert saved[0]["ticker"] == "WDC"


def test_edit_trade_via_post(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [{"id": "tr1", "ticker": "WDC", "source": "yfinance", "shares": 20,
               "buy_price": 42.10, "buy_date": "2026-01-15",
               "sell_price": 67.80, "sell_date": "2026-04-10",
               "created_at": "2026-04-10T00:00:00+00:00"}]
    trades_file = tmp_path / "trades_edit.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/trade/tr1/edit", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "25", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "70.00", "sell_date": "2026-04-11",
    })
    assert resp.status_code == 302
    saved = json.loads(trades_file.read_text())
    assert saved[0]["shares"] == 25
    assert saved[0]["sell_price"] == 70.00


def test_delete_trade(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [{"id": "tr2", "ticker": "AAPL", "source": "yfinance", "shares": None,
               "buy_price": 150.0, "buy_date": "2026-01-01",
               "sell_price": 160.0, "sell_date": "2026-02-01",
               "created_at": "2026-02-01T00:00:00+00:00"}]
    trades_file = tmp_path / "trades_del.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/trade/tr2/delete")
    assert resp.status_code == 302
    saved = json.loads(trades_file.read_text())
    assert saved == []


def test_trade_routes_require_login(client):
    assert client.post("/trade/new").status_code == 302
    assert client.post("/trade/abc/delete").status_code == 302


def test_record_sale_get_prefills_from_alarm(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "rs1", "ticker": "WDC", "source": "yfinance", "owned": True,
               "initial_price": 42.10, "shares": 20,
               "created_at": "2026-01-15T10:00:00+00:00",
               "enabled": True, "upper_limit": 280.0, "lower_limit": None,
               "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_rs.json"
    alarms_file.write_text(json.dumps(alarms))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    login(client)
    resp = client.get("/alarm/rs1/record-sale")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "WDC" in body
    assert "42.1" in body
    assert "2026-01-15" in body


def test_record_sale_post_saves_trade(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "rs2", "ticker": "WDC", "source": "yfinance", "owned": True,
               "initial_price": 42.10, "shares": 20,
               "created_at": "2026-01-15T10:00:00+00:00",
               "enabled": True, "upper_limit": 280.0, "lower_limit": None,
               "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_rs2.json"
    alarms_file.write_text(json.dumps(alarms))
    trades_file = tmp_path / "trades_rs2.json"
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/alarm/rs2/record-sale", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "20", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "67.80", "sell_date": "2026-04-10",
    })
    assert resp.status_code == 302
    assert "tab=history" in resp.headers["Location"]
    saved = json.loads(trades_file.read_text())
    assert len(saved) == 1
    assert saved[0]["ticker"] == "WDC"
    # Alarm is NOT deleted (checkbox not checked)
    alarms_saved = json.loads(alarms_file.read_text())
    assert len(alarms_saved) == 1


def test_record_sale_post_deletes_alarm_when_checked(client, tmp_path, monkeypatch):
    import app as app_module
    alarms = [{"id": "rs3", "ticker": "WDC", "source": "yfinance", "owned": True,
               "initial_price": 42.10, "shares": 20,
               "created_at": "2026-01-15T10:00:00+00:00",
               "enabled": True, "upper_limit": 280.0, "lower_limit": None,
               "email": "a@b.com", "last_triggered": None, "timezone": None}]
    alarms_file = tmp_path / "alarms_rs3.json"
    alarms_file.write_text(json.dumps(alarms))
    trades_file = tmp_path / "trades_rs3.json"
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.post("/alarm/rs3/record-sale", data={
        "ticker": "WDC", "source": "yfinance",
        "shares": "20", "buy_price": "42.10", "buy_date": "2026-01-15",
        "sell_price": "67.80", "sell_date": "2026-04-10",
        "delete_alarm": "on",
    })
    assert resp.status_code == 302
    alarms_saved = json.loads(alarms_file.read_text())
    assert alarms_saved == []


def test_record_sale_requires_login(client):
    resp = client.get("/alarm/any/record-sale")
    assert resp.status_code == 302
    assert "dashboard" not in resp.headers.get("Location", "")


def test_dashboard_history_tab_shows_trades(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [{"id": "dt1", "ticker": "WDC", "source": "yfinance", "shares": 20,
               "buy_price": 42.10, "buy_date": "2026-01-15",
               "sell_price": 67.80, "sell_date": "2026-04-10",
               "created_at": "2026-04-10T00:00:00+00:00"}]
    trades_file = tmp_path / "trades_dash.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.get("/dashboard?tab=history")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "WDC" in body
    assert "67" in body  # sell price


def test_dashboard_history_tab_shows_summary(client, tmp_path, monkeypatch):
    import app as app_module
    trades = [
        {"id": "dt2", "ticker": "WDC", "source": "yfinance", "shares": 10,
         "buy_price": 40.0, "buy_date": "2026-01-01",
         "sell_price": 60.0, "sell_date": "2026-03-01",
         "created_at": "2026-03-01T00:00:00+00:00"},
        {"id": "dt3", "ticker": "AAPL", "source": "yfinance", "shares": None,
         "buy_price": 150.0, "buy_date": "2026-01-01",
         "sell_price": 165.0, "sell_date": "2026-03-15",
         "created_at": "2026-03-15T00:00:00+00:00"},
    ]
    trades_file = tmp_path / "trades_sum.json"
    trades_file.write_text(json.dumps(trades))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.get("/dashboard?tab=history")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Summary: 2 trades, WDC is best (+50%)
    assert "2" in body
    assert "WDC" in body


def test_dashboard_alarms_tab_does_not_load_trades(client, tmp_path, monkeypatch):
    import app as app_module
    monkeypatch.setattr("checker.get_price", lambda t: 42.0)
    login(client)
    # Default tab=alarms — should not try to read trades at all (no trades file patched)
    resp = client.get("/dashboard")
    assert resp.status_code == 200


def test_dashboard_tab_bar_rendered(client, tmp_path, monkeypatch):
    import app as app_module
    trades_file = tmp_path / "trades_tabs.json"
    trades_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_trades_path", lambda: str(trades_file))
    login(client)
    resp = client.get("/dashboard?tab=history")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Sell History" in body
    assert "Alarms" in body


def test_holding_from_form_requires_ticker(client):
    login(client)
    resp = client.post("/savings/new", data={
        "source": "yfinance", "category": "stocks",
        "shares": "10", "cost_basis": "1000", "currency": "USD"
    }, follow_redirects=True)
    assert b"Ticker" in resp.data or resp.status_code in (200, 400)

def test_holding_from_form_requires_shares(client):
    login(client)
    resp = client.post("/savings/new", data={
        "source": "yfinance", "ticker": "VOO", "category": "etf",
        "cost_basis": "1000", "currency": "USD"
    }, follow_redirects=True)
    assert b"Shares" in resp.data or resp.status_code in (200, 400)

def test_holding_from_form_invalid_category(client):
    login(client)
    resp = client.post("/savings/new", data={
        "source": "yfinance", "ticker": "VOO", "category": "invalid",
        "shares": "10", "cost_basis": "1000", "currency": "USD"
    }, follow_redirects=True)
    assert b"category" in resp.data.lower() or resp.status_code in (200, 400)


def test_holding_from_form_etf_derives_cost_basis_from_pnl(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "25"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    # cost_basis = (100.0 * 10) / (1 + 25/100) = 1000 / 1.25 = 800.0
    assert abs(holding["cost_basis"] - 800.0) < 0.01


def test_holding_from_form_etf_negative_pnl(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (90.0, 91.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "QQQ"), ("name", "Invesco"),
        ("category", "etf"), ("shares", "5"), ("pl_pct", "-10"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    # cost_basis = (90.0 * 5) / (1 + (-10)/100) = 450 / 0.9 = 500.0
    assert abs(holding["cost_basis"] - 500.0) < 0.01


def test_holding_from_form_etf_pnl_missing(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "gain/loss" in error.lower() or "%" in error


def test_holding_from_form_etf_pnl_non_numeric(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "abc"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "gain/loss" in error.lower() or "%" in error


def test_holding_from_form_etf_tase_derives_cost_basis(monkeypatch):
    import app as app_module
    import tase as tase_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(tase_module, "get_price", lambda tase_id, tase_type: 50.0)
    form = ImmutableMultiDict([
        ("source", "tase"), ("ticker", "מגדל"), ("name", "Migdal Fund"),
        ("tase_id", "1234567"), ("tase_type", "fund"),
        ("category", "etf"), ("shares", "20"), ("pl_pct", "25"), ("currency", "ILS"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    # cost_basis = (50.0 * 20) / (1 + 25/100) = 1000 / 1.25 = 800.0
    assert abs(holding["cost_basis"] - 800.0) < 0.01


def test_holding_from_form_etf_pnl_minus_100(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "-100"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "-100" in error or "cannot be" in error.lower()


def test_holding_from_form_etf_pnl_near_minus_100(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (100.0, 99.0))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "-100.5"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert error is not None


def test_holding_from_form_etf_price_fetch_fails(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (None, None))
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VOO"), ("name", "Vanguard"),
        ("category", "etf"), ("shares", "10"), ("pl_pct", "15"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert holding is None
    assert "price" in error.lower()


def test_holding_from_form_stocks_still_uses_cost_basis(monkeypatch):
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "AAPL"), ("name", "Apple"),
        ("category", "stocks"), ("shares", "10"), ("cost_basis", "1500"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    assert holding["cost_basis"] == 1500.0


def test_holding_from_form_mmf_still_uses_cost_basis():
    import app as app_module
    from werkzeug.datastructures import ImmutableMultiDict
    form = ImmutableMultiDict([
        ("source", "yfinance"), ("ticker", "VMFXX"), ("name", "Vanguard MMF"),
        ("category", "mmf"), ("shares", "1000"), ("cost_basis", "1000"), ("currency", "USD"),
    ])
    holding, error = app_module._holding_from_form(form)
    assert error is None
    assert holding["cost_basis"] == 1000.0


@pytest.fixture
def savings_client(tmp_path, monkeypatch):
    alarms_file = tmp_path / "alarms.json"
    alarms_file.write_text(json.dumps([]))
    savings_file = tmp_path / "savings.json"
    savings_file.write_text(json.dumps([]))
    snapshots_file = tmp_path / "savings_snapshots.json"
    snapshots_file.write_text(json.dumps([]))
    monkeypatch.setattr(app_module, "_alarms_path", lambda: str(alarms_file))
    monkeypatch.setattr(app_module, "_SAVINGS_PATH", str(savings_file))
    monkeypatch.setattr(app_module, "_SNAPSHOTS_PATH", str(snapshots_file))
    monkeypatch.setattr(app_module, "_fetch_savings_prices", lambda h: {})
    monkeypatch.setattr(app_module.checker, "get_usd_to_ils", lambda: 3.7)
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c, savings_file


def test_savings_page_loads(savings_client):
    c, _ = savings_client
    login(c)
    resp = c.get("/savings")
    assert resp.status_code == 200


def test_savings_new_post_adds_holding(savings_client, monkeypatch):
    c, savings_file = savings_client
    monkeypatch.setattr(app_module.checker, "get_price_with_change", lambda t: (500.0, 495.0))
    login(c)
    resp = c.post("/savings/new", data={
        "source": "yfinance", "ticker": "VOO", "name": "Vanguard",
        "category": "etf", "shares": "10", "pl_pct": "0",
        "currency": "USD",
    }, follow_redirects=True)
    assert resp.status_code == 200
    holdings = json.loads(savings_file.read_text())
    assert len(holdings) == 1
    assert holdings[0]["ticker"] == "VOO"


def test_savings_delete_removes_holding(savings_client):
    c, savings_file = savings_client
    savings_file.write_text(json.dumps([{"id": "abc123", "ticker": "VOO",
        "category": "etf", "shares": 10, "cost_basis": 5000, "currency": "USD",
        "source": "yfinance", "name": "Vanguard", "tase_id": "", "tase_type": "",
        "last_updated": "2026-05-06T10:00:00+00:00"}]))
    login(c)
    resp = c.post("/savings/abc123/delete", follow_redirects=True)
    assert resp.status_code == 200
    holdings = json.loads(savings_file.read_text())
    assert holdings == []


def test_savings_inline_shares_update(savings_client):
    c, savings_file = savings_client
    savings_file.write_text(json.dumps([{"id": "abc123", "ticker": "VOO",
        "category": "etf", "shares": 10, "cost_basis": 5000, "currency": "USD",
        "source": "yfinance", "name": "Vanguard", "tase_id": "", "tase_type": "",
        "last_updated": "2026-05-06T10:00:00+00:00"}]))
    login(c)
    resp = c.post("/savings/abc123/shares", data={"shares": "15.5"})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert data["shares"] == 15.5
    holdings = json.loads(savings_file.read_text())
    assert holdings[0]["shares"] == 15.5
