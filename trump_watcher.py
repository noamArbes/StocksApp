import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta
import anthropic
from checker import send_email

# Trump's Truth Social account ID (Mastodon-compatible API)
_TRUMP_ACCOUNT_ID = "107780257626128497"
_API_URL = f"https://truthsocial.com/api/v1/accounts/{_TRUMP_ACCOUNT_ID}/statuses"

_RECIPIENT = "noamarbes1@gmail.com"

_claude_client = None


def _get_claude_client():
    global _claude_client
    if _claude_client is None:
        _claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _claude_client

_SYSTEM_PROMPT = """You are a financial analyst monitoring political social media for market-moving content.

Analyze the given Truth Social post. FLAG it if it contains ANY of:
- A specific company name or stock ticker
- A specific industry or sector (steel, semiconductors, oil, pharma, banks, etc.)
- Trade or tariff language (tariff, deal, trade, import, export, tax)
- Market sentiment language (great time, buy, winning, strong, tremendous, beautiful deal)
- Policy announcements that would directly affect publicly traded companies
- Mentions of a major trading partner country (China, Canada, Mexico, EU, Japan)

If the post should be FLAGGED, respond ONLY with this exact format (fill in the brackets):
---
🚨 TRUMP TRADE ALERT
📅 Date & Time: [ISO timestamp of the post]
📝 Post Summary: [one sentence summary]
🎯 Tickers Likely Affected: [comma-separated tickers, or most likely affected if none mentioned]
📈 Direction: [Bullish / Bearish / Mixed]
🏭 Sector: [most affected sector]
⚡ Confidence: [High / Medium / Low]
💡 Why It Matters: [one sentence on why this could move markets]
---

If the post should NOT be flagged, respond with exactly: NO_ALERT"""


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


def analyze_posts(posts: list[dict]) -> list[str]:
    """Analyze posts with Claude. Returns a list of formatted alert strings for flagged posts."""
    alerts = []
    for post in posts:
        content = post.get("content", "").strip()
        if not content:
            continue
        timestamp = post.get("created_at", "")
        user_msg = f"Post timestamp: {timestamp}\nPost content: {content}"
        try:
            response = _get_claude_client().messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            if not response.content:
                continue
            text = response.content[0].text.strip()
        except Exception as e:
            print(f"[TrumpWatcher] Claude API error for post {post.get('id', '?')}: {e}")
            continue
        if text.upper() != "NO_ALERT":
            alerts.append(text)
    return alerts


def run() -> None:
    """Main entry point: fetch, analyze, and email alerts if any posts are flagged."""
    api_key = os.environ.get("BREVO_API_KEY")
    sender = os.environ.get("BREVO_SENDER_EMAIL")
    if not api_key or not sender:
        print("[TrumpWatcher] Missing BREVO_API_KEY or BREVO_SENDER_EMAIL — skipping email")
        return

    try:
        posts = fetch_recent_posts(minutes=60)
    except Exception as e:
        print(f"[TrumpWatcher] Failed to fetch posts: {e}")
        return

    if not posts:
        print("[TrumpWatcher] No recent posts found")
        return

    try:
        alerts = analyze_posts(posts)
    except Exception as e:
        print(f"[TrumpWatcher] Failed to analyze posts: {e}")
        return

    if not alerts:
        print("[TrumpWatcher] No posts flagged")
        return

    n = len(alerts)
    subject = f"🚨 Trump Trade Alert — {n} post{'s' if n > 1 else ''} flagged"
    body = "\n\n".join(alerts)
    send_email(subject, body, _RECIPIENT, api_key, sender)
    print(f"[TrumpWatcher] Alert email sent — {n} post(s) flagged")
