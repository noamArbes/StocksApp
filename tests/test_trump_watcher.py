import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import tempfile
import pathlib
import trump_watcher


def _make_post(minutes_ago: int, content: str) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"id": "1", "created_at": ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "content": content}


def test_fetch_recent_posts_returns_posts_within_window():
    recent = _make_post(30, "Big tariffs on China coming!")
    old = _make_post(90, "Have a great day!")
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps([recent, old]).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        posts = trump_watcher.fetch_recent_posts(minutes=60)

    assert len(posts) == 1
    assert "tariffs" in posts[0]["content"]


def test_fetch_recent_posts_returns_empty_when_none_recent():
    old = _make_post(90, "Hello world")
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps([old]).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        posts = trump_watcher.fetch_recent_posts(minutes=60)

    assert posts == []


def test_fetch_recent_posts_strips_html_from_content():
    recent = _make_post(30, "Trade <b>China</b> tariffs!")
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps([recent]).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        posts = trump_watcher.fetch_recent_posts(minutes=60)

    assert posts[0]["content"] == "Trade China tariffs!"


def test_analyze_posts_returns_formatted_alerts():
    posts = [_make_post(10, "We are putting massive tariffs on China steel!")]
    fake_alert = (
        "---\n"
        "🚨 TRUMP TRADE ALERT\n"
        "📅 Date & Time: 2026-06-03 10:00 UTC\n"
        "📝 Post Summary: Trump announced massive tariffs on Chinese steel.\n"
        "🎯 Tickers Likely Affected: X, NUE, STLD\n"
        "📈 Direction: Bearish\n"
        "🏭 Sector: Steel / Materials\n"
        "⚡ Confidence: High\n"
        "💡 Why It Matters: Tariffs on China steel directly hit domestic steel producers.\n"
        "---"
    )
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=fake_alert)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("trump_watcher._get_claude_client", return_value=mock_client):
        alerts = trump_watcher.analyze_posts(posts)

    assert len(alerts) == 1
    assert "🚨 TRUMP TRADE ALERT" in alerts[0]


def test_analyze_posts_returns_empty_for_non_market_post():
    posts = [_make_post(10, "Happy Sunday everyone! God bless America.")]
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="NO_ALERT")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("trump_watcher._get_claude_client", return_value=mock_client):
        alerts = trump_watcher.analyze_posts(posts)

    assert alerts == []


def test_run_sends_email_when_alerts_found():
    posts = [_make_post(10, "Tariffs on China!")]
    alert_text = "---\n🚨 TRUMP TRADE ALERT\n...\n---"

    with patch("trump_watcher.fetch_recent_posts", return_value=posts), \
         patch("trump_watcher.analyze_posts", return_value=[alert_text]), \
         patch("trump_watcher.send_email") as mock_send, \
         patch.dict("os.environ", {"BREVO_API_KEY": "test-key", "BREVO_SENDER_EMAIL": "from@test.com"}):
        trump_watcher.run()

    mock_send.assert_called_once_with(
        "🚨 Trump Trade Alert — 1 post flagged",
        alert_text,
        "noamarbes1@gmail.com",
        "test-key",
        "from@test.com",
    )


def test_run_does_not_send_email_when_no_alerts():
    with patch.dict("os.environ", {"BREVO_API_KEY": "test_key", "BREVO_SENDER_EMAIL": "sender@example.com"}), \
         patch("trump_watcher.fetch_recent_posts", return_value=[]), \
         patch("trump_watcher.analyze_posts", return_value=[]), \
         patch("trump_watcher.send_email") as mock_send:
        trump_watcher.run()

    mock_send.assert_not_called()


def test_run_does_not_send_email_on_fetch_error():
    with patch("trump_watcher.fetch_recent_posts", side_effect=Exception("network error")), \
         patch("trump_watcher.send_email") as mock_send, \
         patch.dict("os.environ", {"BREVO_API_KEY": "test-key", "BREVO_SENDER_EMAIL": "from@test.com"}):
        trump_watcher.run()

    mock_send.assert_not_called()


def test_run_does_not_send_email_on_analyze_error():
    posts = [_make_post(10, "Tariffs on China!")]
    with patch("trump_watcher.fetch_recent_posts", return_value=posts), \
         patch("trump_watcher.analyze_posts", side_effect=Exception("API error")), \
         patch("trump_watcher.send_email") as mock_send, \
         patch.dict("os.environ", {"BREVO_API_KEY": "test-key", "BREVO_SENDER_EMAIL": "from@test.com"}):
        trump_watcher.run()

    mock_send.assert_not_called()


def test_parse_alert_extracts_fields():
    raw = (
        "---\n"
        "🚨 TRUMP TRADE ALERT\n"
        "📅 Date & Time: 2026-06-03T14:32:00Z\n"
        "📝 Post Summary: Trump announced massive tariffs on Chinese steel.\n"
        "🎯 Tickers Likely Affected: X, NUE, STLD\n"
        "📈 Direction: Bearish\n"
        "🏭 Sector: Steel / Materials\n"
        "⚡ Confidence: High\n"
        "💡 Why It Matters: Tariffs on China steel directly hit domestic steel producers.\n"
        "---"
    )
    post = {"content": "We are putting massive tariffs on China steel!", "created_at": "2026-06-03T14:32:00Z"}
    result = trump_watcher.parse_alert(raw, post)

    assert result["summary"] == "Trump announced massive tariffs on Chinese steel."
    assert result["tickers"] == ["X", "NUE", "STLD"]
    assert result["direction"] == "Bearish"
    assert result["sector"] == "Steel / Materials"
    assert result["confidence"] == "High"
    assert result["why_it_matters"] == "Tariffs on China steel directly hit domestic steel producers."
    assert result["raw_post"] == "We are putting massive tariffs on China steel!"
    assert result["timestamp"] == "2026-06-03T14:32:00Z"
    assert "id" in result


def test_save_alert_writes_to_file():
    alert = {
        "id": "test-id",
        "timestamp": "2026-06-03T14:32:00Z",
        "summary": "Test alert",
        "tickers": ["AAPL"],
        "direction": "Bullish",
        "sector": "Technology",
        "confidence": "High",
        "why_it_matters": "Test reason.",
        "raw_post": "Test post",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(pathlib.Path(tmpdir) / "trump_alerts.json")
        trump_watcher.save_alert(alert, path=path)
        with open(path) as f:
            data = json.load(f)
    assert len(data) == 1
    assert data[0]["id"] == "test-id"


def test_save_alert_prepends_and_caps_at_100():
    alerts = [{"id": str(i), "timestamp": "", "summary": "", "tickers": [],
                "direction": "", "sector": "", "confidence": "",
                "why_it_matters": "", "raw_post": ""} for i in range(100)]
    new_alert = {**alerts[0], "id": "new"}
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(pathlib.Path(tmpdir) / "trump_alerts.json")
        with open(path, "w") as f:
            json.dump(alerts, f)
        trump_watcher.save_alert(new_alert, path=path)
        with open(path) as f:
            data = json.load(f)
    assert len(data) == 100
    assert data[0]["id"] == "new"
