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
