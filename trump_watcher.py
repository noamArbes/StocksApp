import json
import os
import re
import urllib.request
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
import anthropic
from checker import send_email

# Trump's Truth Social account ID (Mastodon-compatible API)
_TRUMP_ACCOUNT_ID = "107780257626128497"
_API_URL = f"https://truthsocial.com/api/v1/accounts/{_TRUMP_ACCOUNT_ID}/statuses"

_RECIPIENT = "noamarbes1@gmail.com"
_ALERTS_MAX = 100

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


def get_alerts_path() -> str:
    """Returns the path to trump_alerts.json, next to alarms.json."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "trump_alerts.json")


def parse_alert(raw: str, post: dict) -> dict:
    """Parse Claude's formatted alert string into a structured dict."""
    def _extract(label: str) -> str:
        pattern = re.escape(label) + r"[ \t]*(.*)"
        match = re.search(pattern, raw)
        return match.group(1).strip() if match else ""

    tickers_raw = _extract("🎯 Tickers Likely Affected:")
    tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]

    return {
        "id": str(uuid.uuid4()),
        "timestamp": post.get("created_at", ""),
        "summary": _extract("📝 Post Summary:"),
        "tickers": tickers,
        "direction": _extract("📈 Direction:"),
        "sector": _extract("🏭 Sector:"),
        "confidence": _extract("⚡ Confidence:"),
        "why_it_matters": _extract("💡 Why It Matters:"),
        "raw_post": post.get("content", ""),
    }


def save_alert(alert: dict, path: str | None = None) -> None:
    """Prepend alert to trump_alerts.json, cap at _ALERTS_MAX entries. Atomic write."""
    if path is None:
        path = get_alerts_path()
    try:
        with open(path) as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = []

    existing.insert(0, alert)
    existing = existing[:_ALERTS_MAX]

    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(existing, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


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


def analyze_posts(posts: list[dict]) -> list[tuple[str, dict]]:
    """Analyze posts with Claude. Returns (alert_string, source_post) pairs for flagged posts."""
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
            alerts.append((text, post))
    return alerts


def run() -> None:
    """Main entry point: fetch, analyze, save, and email alerts if any posts are flagged."""
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
        alert_pairs = analyze_posts(posts)
    except Exception as e:
        print(f"[TrumpWatcher] Failed to analyze posts: {e}")
        return

    if not alert_pairs:
        print("[TrumpWatcher] No posts flagged")
        return

    # Save each alert to disk (correctly paired with its source post)
    for raw, post in alert_pairs:
        try:
            alert = parse_alert(raw, post)
            save_alert(alert)
        except Exception as e:
            print(f"[TrumpWatcher] Failed to save alert: {e}")

    n = len(alert_pairs)
    subject = f"🚨 Trump Trade Alert — {n} post{'s' if n > 1 else ''} flagged"
    body = "\n\n".join(raw for raw, _ in alert_pairs)
    send_email(subject, body, _RECIPIENT, api_key, sender)
    print(f"[TrumpWatcher] Alert email sent — {n} post(s) flagged")
