import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
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

    with patch("trump_watcher._claude_client") as mock_client:
        mock_client.messages.create.return_value = mock_message
        alerts = trump_watcher.analyze_posts(posts)

    assert len(alerts) == 1
    assert "🚨 TRUMP TRADE ALERT" in alerts[0]


def test_analyze_posts_returns_empty_for_non_market_post():
    posts = [_make_post(10, "Happy Sunday everyone! God bless America.")]
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="NO_ALERT")]

    with patch("trump_watcher._claude_client") as mock_client:
        mock_client.messages.create.return_value = mock_message
        alerts = trump_watcher.analyze_posts(posts)

    assert alerts == []


def test_run_sends_email_when_alerts_found():
    posts = [_make_post(10, "Tariffs on China!")]
    alert_text = "---\n🚨 TRUMP TRADE ALERT\n...\n---"

    with patch.dict("os.environ", {"BREVO_API_KEY": "test_key", "BREVO_SENDER_EMAIL": "sender@example.com"}), \
         patch("trump_watcher.fetch_recent_posts", return_value=posts), \
         patch("trump_watcher.analyze_posts", return_value=[alert_text]), \
         patch("trump_watcher.send_email") as mock_send:
        trump_watcher.run()

    mock_send.assert_called_once()
    args = mock_send.call_args[0]
    assert "Trump Trade Alert" in args[0]
    assert alert_text in args[1]
    assert args[2] == "noamarbes1@gmail.com"


def test_run_does_not_send_email_when_no_alerts():
    with patch.dict("os.environ", {"BREVO_API_KEY": "test_key", "BREVO_SENDER_EMAIL": "sender@example.com"}), \
         patch("trump_watcher.fetch_recent_posts", return_value=[]), \
         patch("trump_watcher.analyze_posts", return_value=[]), \
         patch("trump_watcher.send_email") as mock_send:
        trump_watcher.run()

    mock_send.assert_not_called()
