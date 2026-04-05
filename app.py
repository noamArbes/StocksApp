import os
import sys
import threading
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for, jsonify

import checker

# --- Startup validation ---
_UI_PASSWORD = os.environ.get("UI_PASSWORD")
_SECRET_KEY = os.environ.get("SECRET_KEY")

if not _UI_PASSWORD or not _SECRET_KEY:
    print("[ERROR] Missing required env vars: UI_PASSWORD and SECRET_KEY")
    sys.exit(1)

app = Flask(__name__)
app.secret_key = _SECRET_KEY

_lock = threading.Lock()
_ALARMS_PATH = checker.get_alarms_path()  # sync local→volume once at startup


def _alarms_path():
    return _ALARMS_PATH


def read_alarms():
    with _lock:
        path = _alarms_path()
        return checker.load_alarms(path)


def write_alarms(alarms):
    with _lock:
        path = _alarms_path()
        checker.save_alarms(alarms, path)


def modify_alarms(fn):
    """Read alarms, apply fn(alarms), write back — all under a single lock."""
    with _lock:
        path = _alarms_path()
        alarms = checker.load_alarms(path)
        fn(alarms)
        checker.save_alarms(alarms, path)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


# --- Auth routes ---

@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password") == _UI_PASSWORD:
        session["logged_in"] = True
        return redirect(url_for("dashboard"))
    return render_template("login.html", error="Incorrect password")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# --- Dashboard ---

@app.route("/dashboard")
@login_required
def dashboard():
    alarms = read_alarms()
    sort = request.args.get("sort", "newest")
    if sort == "oldest":
        alarms.sort(key=lambda a: a.get("created_at") or "")
    elif sort == "az":
        alarms.sort(key=lambda a: a.get("ticker", ""))
    else:
        alarms.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    prices = {}
    for alarm in alarms:
        ticker = alarm.get("ticker")
        if ticker and ticker not in prices:
            try:
                prices[ticker] = checker.get_price(ticker)
            except Exception:
                prices[ticker] = None
    return render_template("dashboard.html", alarms=alarms, prices=prices, sort=sort)


# --- Alarm CRUD ---

@app.route("/alarm/new", methods=["GET", "POST"])
@login_required
def alarm_new():
    if request.method == "POST":
        alarm, error = _alarm_from_form(request.form)
        if error:
            return render_template("alarm_form.html", error=error, form=request.form, title="Add Alarm")
        def do_append(alarms):
            alarms.append(alarm)
        modify_alarms(do_append)
        return redirect(url_for("dashboard"))
    return render_template("alarm_form.html", form={}, title="Add Alarm")


@app.route("/alarm/<alarm_id>/edit", methods=["GET", "POST"])
@login_required
def alarm_edit(alarm_id):
    alarms = read_alarms()
    alarm = next((a for a in alarms if a.get("id") == alarm_id), None)
    if alarm is None:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        updated, error = _alarm_from_form(request.form, existing=alarm)
        if error:
            return render_template("alarm_form.html", error=error, form=request.form, alarm=alarm, title="Edit Alarm")
        def do_update(alarms):
            for i, a in enumerate(alarms):
                if a.get("id") == alarm_id:
                    alarms[i] = updated
                    break
        modify_alarms(do_update)
        return redirect(url_for("dashboard"))
    form_data = dict(alarm)
    if isinstance(form_data.get("email"), list):
        form_data["email"] = ", ".join(form_data["email"])
    return render_template("alarm_form.html", form=form_data, alarm=alarm, title="Edit Alarm")


@app.route("/alarm/<alarm_id>/delete", methods=["POST"])
@login_required
def alarm_delete(alarm_id):
    def do_delete(alarms):
        alarms[:] = [a for a in alarms if a.get("id") != alarm_id]
    modify_alarms(do_delete)
    return redirect(url_for("dashboard"))


@app.route("/alarm/<alarm_id>/toggle", methods=["POST"])
@login_required
def alarm_toggle(alarm_id):
    def do_toggle(alarms):
        for alarm in alarms:
            if alarm.get("id") == alarm_id:
                alarm["enabled"] = not alarm.get("enabled", False)
                break
    modify_alarms(do_toggle)
    return redirect(url_for("dashboard"))


# --- Chart data ---

@app.route("/alarm/<alarm_id>/chart-data")
@login_required
def chart_data(alarm_id):
    alarms = read_alarms()
    alarm = next((a for a in alarms if a.get("id") == alarm_id), None)
    if alarm is None:
        return jsonify({"error": "not found"}), 404
    ticker = alarm.get("ticker")
    period = request.args.get("period", "1mo")
    if period not in ("5d", "1mo", "1y"):
        period = "1mo"
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=period)
        labels = [str(d.date()) for d in hist.index]
        prices = [round(float(p), 2) for p in hist["Close"]]
        return jsonify({"labels": labels, "prices": prices})
    except Exception as e:
        app.logger.error(f"Chart data fetch failed for {ticker}: {e}")
        return jsonify({"error": "Could not fetch chart data"}), 500


# --- Form helper ---

def _alarm_from_form(form, existing=None):
    """Parse and validate form data. Returns (alarm_dict, error_str_or_None)."""
    import uuid

    ticker = form.get("ticker", "").strip().upper()
    if not ticker:
        return None, "Ticker is required"

    email_raw = form.get("email", "").strip()
    emails = [e.strip() for e in email_raw.split(",") if e.strip()]
    if not emails:
        return None, "At least one email is required"

    alarm_type = form.get("alarm_type", "price")

    alarm = {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "ticker": ticker,
        "enabled": form.get("enabled") == "on",
        "timezone": form.get("timezone", "").strip() or None,
        "last_triggered": existing.get("last_triggered") if existing else None,
        "email": emails if len(emails) > 1 else emails[0],
    }

    if alarm_type == "pct":
        upper_pct = form.get("upper_pct", "").strip()
        lower_pct = form.get("lower_pct", "").strip()
        try:
            alarm["upper_pct"] = float(upper_pct) if upper_pct else None
            alarm["lower_pct"] = float(lower_pct) if lower_pct else None
        except ValueError:
            return None, "Percentage values must be numbers"
        if alarm["upper_pct"] is None and alarm["lower_pct"] is None:
            return None, "At least one percentage threshold is required"
        alarm["base_price"] = existing.get("base_price") if existing else None
    else:
        upper = form.get("upper_limit", "").strip()
        lower = form.get("lower_limit", "").strip()
        try:
            alarm["upper_limit"] = float(upper) if upper else None
            alarm["lower_limit"] = float(lower) if lower else None
        except ValueError:
            return None, "Price limits must be numbers"
        if alarm["upper_limit"] is None and alarm["lower_limit"] is None:
            return None, "At least one price limit is required"

    return alarm, None


if __name__ == "__main__":
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(checker.run, "interval", minutes=15, kwargs={"path": _ALARMS_PATH})
    scheduler.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
