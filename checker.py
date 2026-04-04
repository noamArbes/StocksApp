from datetime import datetime, timezone, timedelta
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request

import yfinance as yf


def condition_met(alarm: dict, price: float) -> tuple:
    """Returns (triggered: bool, limit_type: str | None, limit_value: float | None)"""
    upper = alarm.get("upper_limit")
    lower = alarm.get("lower_limit")

    if upper is not None and price >= upper:
        return True, "upper", upper
    if lower is not None and price <= lower:
        return True, "lower", lower
    return False, None, None


def should_alert(alarm: dict) -> bool:
    """Returns True if enough time has passed since the last alert (or never alerted)."""
    last = alarm.get("last_triggered")
    if last is None:
        return True
    last_dt = datetime.fromisoformat(last)
    return datetime.now(timezone.utc) - last_dt >= timedelta(days=3)


def format_subject(ticker: str, price: float, limit_type: str, limit_value: float) -> str:
    return f"Stock Alert: {ticker} hit ${price:.2f} ({limit_type} limit: ${limit_value:.2f})"


def format_body(ticker: str, price: float, limit_type: str, limit_value: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: ${price:.2f}\n"
        f"Limit Triggered: {limit_type} limit (${limit_value:.2f})\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )


VOLUME_PATH = "/data/alarms.json"
LOCAL_PATH = "alarms.json"


def get_alarms_path() -> str:
    """Returns the path to alarms.json — volume path on Railway, local path otherwise.
    On each deploy, syncs alarm config from the local file while preserving runtime state."""
    data_dir = "/data"
    if os.path.isdir(data_dir):
        volume_path = os.path.join(data_dir, "alarms.json")
        if os.path.exists(LOCAL_PATH):
            with open(LOCAL_PATH) as f:
                local_alarms = json.load(f)
            if os.path.exists(volume_path):
                try:
                    with open(volume_path) as f:
                        volume_alarms = json.load(f)
                    volume_state = {
                        a["id"]: a
                        for a in volume_alarms
                        if "id" in a
                    }
                    for alarm in local_alarms:
                        alarm_id = alarm.get("id")
                        if alarm_id in volume_state:
                            vol = volume_state[alarm_id]
                            alarm["last_triggered"] = vol.get("last_triggered")
                            # Only restore base_price if local doesn't explicitly reset it
                            if alarm.get("base_price") is None and vol.get("base_price") is not None:
                                alarm["base_price"] = vol["base_price"]
                except Exception as e:
                    print(f"[WARN] Could not read volume alarms file, using local: {e}")
            save_alarms(local_alarms, volume_path)
        return volume_path
    return LOCAL_PATH


def load_alarms(path: str) -> list:
    with open(path, "r") as f:
        return json.load(f)


def save_alarms(alarms: list, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(alarms, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)


def get_price(ticker: str) -> float:
    """Fetches the latest price for a ticker from Yahoo Finance.
    Raises ValueError if the price cannot be retrieved."""
    info = yf.Ticker(ticker).fast_info
    price = info.last_price
    if price is None:
        raise ValueError(f"Could not fetch price for ticker: {ticker}")
    return float(price)


def send_email(subject: str, body: str, to: str, api_key: str, sender: str) -> None:
    """Sends an email via Brevo API."""
    data = json.dumps({
        "sender": {"name": "StocksApp", "email": sender},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }).encode()
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=data,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.read().decode()}") from e


def run() -> None:
    api_key = os.environ.get("BREVO_API_KEY")
    sender = os.environ.get("BREVO_SENDER_EMAIL")

    if not api_key or not sender:
        raise EnvironmentError(
            "Missing required environment variables: BREVO_API_KEY and BREVO_SENDER_EMAIL"
        )

    path = get_alarms_path()
    alarms = load_alarms(path)
    changed = False

    for alarm in alarms:
        if not alarm.get("enabled", False):
            print(f"[SKIP] {alarm.get('id', alarm.get('ticker'))} is disabled")
            continue

        try:
            ticker = alarm["ticker"]
        except KeyError:
            print(f"[ERROR] Alarm {alarm.get('id', '?')} is missing required field 'ticker', skipping")
            continue

        try:
            price = get_price(ticker)
            print(f"[FETCH] {ticker}: ${price:.2f}")
        except Exception as e:
            print(f"[ERROR] Could not fetch price for {ticker}: {e}")
            continue

        triggered, limit_type, limit_value = condition_met(alarm, price)

        if triggered:
            if should_alert(alarm):
                subject = format_subject(ticker, price, limit_type, limit_value)
                body = format_body(ticker, price, limit_type, limit_value)
                try:
                    send_email(subject, body, alarm["email"], api_key, sender)
                    alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                    changed = True
                    print(f"[ALERT] Email sent for {ticker} at ${price:.2f}")
                except KeyError:
                    print(f"[ERROR] Alarm {ticker} is missing required field 'email', skipping")
                except Exception as e:
                    print(f"[ERROR] Could not send email for {ticker}: {e}")
            else:
                print(f"[SKIP] {ticker} condition met but alert sent recently, skipping")
        else:
            if alarm.get("last_triggered") is not None:
                alarm["last_triggered"] = None
                changed = True
            print(f"[OK] {ticker}: ${price:.2f} — no condition met")

    if changed:
        save_alarms(alarms, path)
        print(f"[SAVED] Updated alarms saved to {path}")


if __name__ == "__main__":
    run()
