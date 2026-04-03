from datetime import datetime, timezone, timedelta
import json
import os
import shutil
import smtplib
from email.mime.text import MIMEText

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
    Copies the local template to the volume on first deploy."""
    data_dir = "/data"
    if os.path.isdir(data_dir):
        volume_path = os.path.join(data_dir, "alarms.json")
        if not os.path.exists(volume_path) and os.path.exists(LOCAL_PATH):
            shutil.copy(LOCAL_PATH, volume_path)
        return volume_path
    return LOCAL_PATH


def load_alarms(path: str) -> list:
    with open(path, "r") as f:
        return json.load(f)


def save_alarms(alarms: list, path: str) -> None:
    with open(path, "w") as f:
        json.dump(alarms, f, indent=2)


def get_price(ticker: str) -> float:
    """Fetches the latest price for a ticker from Yahoo Finance.
    Raises ValueError if the price cannot be retrieved."""
    info = yf.Ticker(ticker).fast_info
    price = info.last_price
    if price is None:
        raise ValueError(f"Could not fetch price for ticker: {ticker}")
    return float(price)


def send_email(subject: str, body: str, to: str, sender: str, password: str) -> None:
    """Sends an email via Gmail SMTP SSL."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)


def run() -> None:
    sender = os.environ.get("GMAIL_SENDER")
    password = os.environ.get("GMAIL_APP_PASSWORD")

    if not sender or not password:
        raise EnvironmentError(
            "Missing required environment variables: GMAIL_SENDER and GMAIL_APP_PASSWORD"
        )

    path = get_alarms_path()
    alarms = load_alarms(path)
    changed = False

    for alarm in alarms:
        if not alarm.get("enabled", False):
            print(f"[SKIP] {alarm.get('id', alarm.get('ticker'))} is disabled")
            continue

        ticker = alarm["ticker"]

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
                    send_email(subject, body, alarm["email"], sender, password)
                    alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                    changed = True
                    print(f"[ALERT] Email sent for {ticker} at ${price:.2f}")
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
