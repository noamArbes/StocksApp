import json
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
