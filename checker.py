from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request

import yfinance as yf
import tase


def _local_time_str(tz_name: str | None) -> str:
    """Returns current time formatted for the given timezone. Falls back to UTC if invalid."""
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
            return datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
        except ZoneInfoNotFoundError:
            print(f"[WARN] Invalid timezone '{tz_name}', defaulting to UTC")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def condition_met(alarm: dict, price: float) -> tuple:
    """Returns (triggered: bool, limit_type: str | None, limit_value: float | None)"""
    upper = alarm.get("upper_limit")
    lower = alarm.get("lower_limit")

    if upper is not None and price >= upper:
        return True, "upper", upper
    if lower is not None and price <= lower:
        return True, "lower", lower
    return False, None, None


def condition_met_pct(alarm: dict, price: float) -> tuple:
    """Returns (triggered: bool, direction: str | None, actual_pct: float | None).

    Checks upper_pct and lower_pct thresholds against base_price.
    Assumes base_price is already set (not None).
    actual_pct is positive for price increases, negative for decreases.
    """
    base = alarm["base_price"]
    actual_pct = (price - base) / base * 100

    upper_pct = alarm.get("upper_pct")
    lower_pct = alarm.get("lower_pct")

    if upper_pct is not None and actual_pct >= upper_pct:
        return True, "upper_pct", actual_pct
    if lower_pct is not None and actual_pct <= -lower_pct:
        return True, "lower_pct", actual_pct
    return False, None, actual_pct


def should_alert(alarm: dict) -> bool:
    """Returns True if enough time has passed since the last alert (or never alerted)."""
    last = alarm.get("last_triggered")
    if last is None:
        return True
    last_dt = datetime.fromisoformat(last)
    snooze_hours = alarm.get("snooze_hours", 72)
    return datetime.now(timezone.utc) - last_dt >= timedelta(hours=snooze_hours)


def format_subject(ticker: str, price: float, limit_type: str, limit_value: float, currency: str = "$") -> str:
    return f"Stock Alert: {ticker} hit {currency}{price:.2f} ({limit_type} limit: {currency}{limit_value:.2f})"


def format_body(ticker: str, price: float, limit_type: str, limit_value: float, tz_name: str | None = None, currency: str = "$") -> str:
    now = _local_time_str(tz_name)
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: {currency}{price:.2f}\n"
        f"Limit Triggered: {limit_type} limit ({currency}{limit_value:.2f})\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )


def format_subject_pct(ticker: str, price: float, direction: str, pct_threshold: float, actual_pct: float, currency: str = "$") -> str:
    sign = "+" if actual_pct >= 0 else ""
    return f"Stock Alert: {ticker} moved {sign}{actual_pct:.1f}% (threshold: {pct_threshold:.1f}%)"


def format_body_pct(ticker: str, price: float, direction: str, pct_threshold: float, base_price: float, actual_pct: float, tz_name: str | None = None, currency: str = "$") -> str:
    now = _local_time_str(tz_name)
    sign = "+" if actual_pct >= 0 else ""
    direction_label = "risen" if direction == "upper_pct" else "fallen"
    return (
        f"Stock Alert\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: {currency}{price:.2f}\n"
        f"Base Price: {currency}{base_price:.2f}\n"
        f"Change: {sign}{actual_pct:.2f}% ({direction_label})\n"
        f"Threshold: {pct_threshold:.1f}%\n"
        f"Time: {now}\n\n"
        f"To disable this alarm, set \"enabled\": false in alarms.json and push to GitHub."
    )


VOLUME_PATH = "/data/alarms.json"
LOCAL_PATH = "alarms.json"
TRADES_LOCAL_PATH = "trades.json"
TRADES_VOLUME_PATH = "/data/trades.json"
SAVINGS_LOCAL_PATH = "savings.json"
SAVINGS_VOLUME_PATH = "/data/savings.json"
SNAPSHOTS_LOCAL_PATH = "savings_snapshots.json"
SNAPSHOTS_VOLUME_PATH = "/data/savings_snapshots.json"
SIEMENS_LOCAL_PATH = "siemens.json"
SIEMENS_VOLUME_PATH = "/data/siemens.json"
ANALYSIS_LOCAL_PATH = "ai_portfolio_analysis.json"
ANALYSIS_VOLUME_PATH = "/data/ai_portfolio_analysis.json"


def get_alarms_path() -> str:
    """Returns the path to alarms.json — volume path on Railway, local path otherwise.
    If the volume file already exists it is used as-is (the UI is the source of truth).
    Only seeds from the local file on the very first deploy when no volume file exists yet."""
    data_dir = "/data"
    if os.path.isdir(data_dir):
        volume_path = os.path.join(data_dir, "alarms.json")
        if not os.path.exists(volume_path) and os.path.exists(LOCAL_PATH):
            with open(LOCAL_PATH) as f:
                local_alarms = json.load(f)
            save_alarms(local_alarms, volume_path)
            print(f"[SEED] Volume initialised from local file ({len(local_alarms)} alarms)")
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


def get_trades_path() -> str:
    """Returns the path to trades.json — volume path on Railway, local path otherwise."""
    if os.path.isdir("/data"):
        return TRADES_VOLUME_PATH
    return TRADES_LOCAL_PATH


def get_savings_path() -> str:
    """Returns the path to savings.json — volume path on Railway, local path otherwise."""
    if os.path.isdir("/data"):
        return SAVINGS_VOLUME_PATH
    return SAVINGS_LOCAL_PATH


def get_snapshots_path() -> str:
    """Returns the path to savings_snapshots.json — volume path on Railway, local path otherwise."""
    if os.path.isdir("/data"):
        return SNAPSHOTS_VOLUME_PATH
    return SNAPSHOTS_LOCAL_PATH


def get_siemens_path() -> str:
    """Returns the path to siemens.json — volume path on Railway, local path otherwise."""
    if os.path.isdir("/data"):
        return SIEMENS_VOLUME_PATH
    return SIEMENS_LOCAL_PATH


def get_portfolio_analysis_path() -> str:
    """Returns the path to ai_portfolio_analysis.json — volume path on Railway, local path otherwise."""
    if os.path.isdir("/data"):
        return ANALYSIS_VOLUME_PATH
    return ANALYSIS_LOCAL_PATH


def load_portfolio_analysis(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_portfolio_analysis(data: dict, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)


def load_siemens(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def save_siemens(data: dict, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)


def load_trades(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_trades(trades: list, path: str) -> None:
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(trades, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)


def load_savings(path: str) -> list:
    """Loads savings data from a JSON file. Returns empty list if file missing."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_savings(holdings: list, path: str) -> None:
    """Saves savings data to a JSON file atomically."""
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(holdings, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, path)


def load_snapshots(path: str) -> list:
    """Loads snapshot data from a JSON file. Returns empty list if file missing."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_snapshots(snapshots: list, path: str) -> None:
    """Saves snapshot data to a JSON file atomically."""
    dir_name = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".tmp") as f:
        json.dump(snapshots, f, indent=2)
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


def get_price_with_change(ticker: str) -> tuple:
    """Returns (last_price, previous_close) for a yfinance ticker.
    Returns (None, None) on any failure."""
    try:
        info = yf.Ticker(ticker).fast_info
        price = float(info.last_price) if info.last_price is not None else None
        prev = float(info.previous_close) if info.previous_close is not None else None
        return price, prev
    except Exception:
        return None, None


def get_usd_to_ils() -> float:
    """Returns the current USD→ILS exchange rate from yfinance. Falls back to 3.7."""
    try:
        info = yf.Ticker("USDILS=X").fast_info
        rate = info.last_price
        return float(rate) if rate else 3.7
    except Exception:
        return 3.7


def send_email(subject: str, body: str, to: str | list, api_key: str, sender: str) -> None:
    """Sends an email via Brevo API. `to` can be a single address or a list."""
    recipients = to if isinstance(to, list) else [to]
    data = json.dumps({
        "sender": {"name": "StocksApp", "email": sender},
        "to": [{"email": addr} for addr in recipients],
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


def run(path: str = None) -> None:
    api_key = os.environ.get("BREVO_API_KEY")
    sender = os.environ.get("BREVO_SENDER_EMAIL")

    if not api_key or not sender:
        raise EnvironmentError(
            "Missing required environment variables: BREVO_API_KEY and BREVO_SENDER_EMAIL"
        )

    if path is None:
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

        currency = "₪" if alarm.get("source") == "tase" else "$"
        try:
            if alarm.get("source") == "tase":
                price = tase.get_price(alarm["tase_id"], alarm["tase_type"])
            else:
                price = get_price(ticker)
            print(f"[FETCH] {ticker}: {currency}{price:.2f}")
        except Exception as e:
            print(f"[ERROR] Could not fetch price for {ticker}: {e}")
            continue

        is_pct_alarm = alarm.get("upper_pct") is not None or alarm.get("lower_pct") is not None
        tz_name = alarm.get("timezone")

        if is_pct_alarm:
            if alarm.get("base_price") is None:
                alarm["base_price"] = price
                changed = True
                print(f"[BASE] {ticker}: base price set to {currency}{price:.2f}")
                continue

            triggered, direction, actual_pct = condition_met_pct(alarm, price)

            if triggered:
                if should_alert(alarm):
                    pct_threshold = alarm.get("upper_pct") if direction == "upper_pct" else alarm.get("lower_pct")
                    subject = format_subject_pct(ticker, price, direction, pct_threshold, actual_pct, currency=currency)
                    body = format_body_pct(ticker, price, direction, pct_threshold, alarm["base_price"], actual_pct, tz_name=tz_name, currency=currency)
                    try:
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        entry = {
                            "triggered_at": alarm["last_triggered"],
                            "type": direction,
                            "price": price,
                            "threshold": pct_threshold,
                        }
                        alarm.setdefault("history", []).append(entry)
                        alarm["history"] = alarm["history"][-10:]
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at {actual_pct:+.1f}%")
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
                print(f"[OK] {ticker}: {currency}{price:.2f} ({actual_pct:+.1f}% from base {currency}{alarm['base_price']:.2f})")

        else:
            if not alarm.get("upper_limit") and not alarm.get("lower_limit"):
                print(f"[SKIP] {alarm.get('id', ticker)}: no condition defined")
                continue

            triggered, limit_type, limit_value = condition_met(alarm, price)

            if triggered:
                if should_alert(alarm):
                    subject = format_subject(ticker, price, limit_type, limit_value, currency=currency)
                    body = format_body(ticker, price, limit_type, limit_value, tz_name=tz_name, currency=currency)
                    try:
                        send_email(subject, body, alarm["email"], api_key, sender)
                        alarm["last_triggered"] = datetime.now(timezone.utc).isoformat()
                        entry = {
                            "triggered_at": alarm["last_triggered"],
                            "type": limit_type,
                            "price": price,
                            "threshold": limit_value,
                        }
                        alarm.setdefault("history", []).append(entry)
                        alarm["history"] = alarm["history"][-10:]
                        changed = True
                        print(f"[ALERT] Email sent for {ticker} at {currency}{price:.2f}")
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
                print(f"[OK] {ticker}: {currency}{price:.2f} — no condition met")

    if changed:
        save_alarms(alarms, path)
        print(f"[SAVED] Updated alarms saved to {path}")


if __name__ == "__main__":
    run()
