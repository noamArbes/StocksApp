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
