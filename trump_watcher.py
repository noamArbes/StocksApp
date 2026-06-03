import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta

# Trump's Truth Social account ID (Mastodon-compatible API)
_TRUMP_ACCOUNT_ID = "107780257626128497"
_API_URL = f"https://truthsocial.com/api/v1/accounts/{_TRUMP_ACCOUNT_ID}/statuses"

_RECIPIENT = "noamarbes1@gmail.com"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_recent_posts(minutes: int = 60) -> list[dict]:
    """Return Truth Social posts from the last `minutes` minutes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    req = urllib.request.Request(
        _API_URL,
        headers={"User-Agent": "StocksApp/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        posts = json.loads(resp.read().decode())

    result = []
    for post in posts:
        try:
            created = datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if created >= cutoff:
            stripped_post = post.copy()
            stripped_post["content"] = _strip_html(post.get("content", ""))
            result.append(stripped_post)
    return result
