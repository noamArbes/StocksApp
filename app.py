import os
import sys
import threading
from functools import wraps
from datetime import datetime, timezone

import json
import urllib.request
import urllib.parse
import urllib.error

from flask import Flask, redirect, render_template, request, session, url_for, jsonify

import checker
import cities_data
import tase

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
_TRADES_PATH = checker.get_trades_path()
_tase_cache = tase.load_securities_cache()


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


def _trades_path():
    return _TRADES_PATH


def read_trades():
    with _lock:
        path = _trades_path()
        return checker.load_trades(path)


def write_trades(trades):
    with _lock:
        path = _trades_path()
        checker.save_trades(trades, path)


def modify_trades(fn):
    """Read trades, apply fn(trades), write back — all under a single lock."""
    with _lock:
        path = _trades_path()
        trades = checker.load_trades(path)
        fn(trades)
        checker.save_trades(trades, path)


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
    tab = request.args.get("tab", "alarms")

    # --- History tab ---
    if tab == "history":
        trades = read_trades()
        trade_pcts = {}
        trade_pls = {}
        pl_values = []
        for t in trades:
            tid = t.get("id")
            if not tid:
                continue
            buy = t.get("buy_price") or 0
            sell = t.get("sell_price") or 0
            pct = (sell - buy) / buy * 100 if buy else 0.0
            trade_pcts[tid] = pct
            if t.get("shares"):
                pl = (sell - buy) * t["shares"]
                trade_pls[tid] = pl
                pl_values.append(pl)
            else:
                trade_pls[tid] = None
        pct_list = list(trade_pcts.values())
        avg_pct = sum(pct_list) / len(pct_list) if pct_list else None
        best = max(trade_pcts, key=trade_pcts.get, default=None)
        best_trade = next((t for t in trades if t.get("id") == best), None) if best else None
        summary = {
            "count": len(trades),
            "total_pl": sum(pl_values) if pl_values else None,
            "avg_pct": avg_pct,
            "best_ticker": best_trade["ticker"] if best_trade else None,
            "best_pct": trade_pcts[best] if best else None,
        }
        return render_template("dashboard.html", tab=tab, trades=trades,
                               summary=summary, trade_pcts=trade_pcts,
                               trade_pls=trade_pls)

    # --- Alarms tab ---
    alarms = read_alarms()
    sort = request.args.get("sort", "newest")
    if sort == "oldest":
        alarms.sort(key=lambda a: a.get("created_at") or "")
    elif sort == "az":
        alarms.sort(key=lambda a: a.get("ticker", ""))
    else:
        alarms.sort(key=lambda a: a.get("created_at") or "", reverse=True)

    owned_filter = request.args.get("owned", "all")
    if owned_filter == "owned":
        alarms = [a for a in alarms if a.get("owned", False)]
    elif owned_filter == "watching":
        alarms = [a for a in alarms if not a.get("owned", False)]

    prices = {}
    for alarm in alarms:
        ticker = alarm.get("ticker")
        if not ticker or ticker in prices:
            continue
        try:
            if alarm.get("source") == "tase":
                prices[ticker] = tase.get_price(alarm["tase_id"], alarm["tase_type"])
            else:
                prices[ticker] = checker.get_price(ticker)
        except Exception:
            prices[ticker] = None

    triggered = {}
    distances = {}
    price_changes = {}
    for alarm in alarms:
        alarm_id = alarm.get("id")
        ticker = alarm.get("ticker")
        price = prices.get(ticker)
        initial = alarm.get("initial_price")
        price_changes[alarm_id] = (price - initial) / initial * 100 if (price and initial) else None
        if price is None:
            triggered[alarm_id] = False
            distances[alarm_id] = None
            continue
        is_pct = alarm.get("upper_pct") is not None or alarm.get("lower_pct") is not None
        if is_pct:
            base = alarm.get("base_price")
            if base is None:
                triggered[alarm_id] = False
                distances[alarm_id] = None
            else:
                t, _, actual_pct = checker.condition_met_pct(alarm, price)
                triggered[alarm_id] = t
                parts = []
                if alarm.get("upper_pct") is not None:
                    rem = alarm["upper_pct"] - actual_pct
                    parts.append(f"↑ triggered" if rem <= 0 else f"↑ {rem:.1f}% to go")
                if alarm.get("lower_pct") is not None:
                    rem = alarm["lower_pct"] + actual_pct
                    parts.append(f"↓ triggered" if rem <= 0 else f"↓ {rem:.1f}% to go")
                distances[alarm_id] = " · ".join(parts) or None
        else:
            t, _, _ = checker.condition_met(alarm, price)
            triggered[alarm_id] = t
            curr = "₪" if alarm.get("source") == "tase" else "$"
            parts = []
            if alarm.get("upper_limit") is not None:
                diff = alarm["upper_limit"] - price
                parts.append("↑ triggered" if diff <= 0 else f"↑ {curr}{diff:.2f} ({diff/price*100:.1f}%) to go")
            if alarm.get("lower_limit") is not None:
                diff = price - alarm["lower_limit"]
                parts.append("↓ triggered" if diff <= 0 else f"↓ {curr}{diff:.2f} ({diff/price*100:.1f}%) to go")
            distances[alarm_id] = " · ".join(parts) or None

    return render_template("dashboard.html", tab=tab, alarms=alarms, prices=prices,
                           sort=sort, triggered=triggered, distances=distances,
                           price_changes=price_changes, owned_filter=owned_filter)


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
    sort = request.args.get("sort", "")
    owned_filter = request.args.get("owned", "")
    back_params = {}
    if sort:
        back_params["sort"] = sort
    if owned_filter:
        back_params["owned"] = owned_filter
    if request.method == "POST":
        updated, error = _alarm_from_form(request.form, existing=alarm)
        if error:
            return render_template("alarm_form.html", error=error, form=request.form, alarm=alarm,
                                   title="Edit Alarm", sort=sort, owned_filter=owned_filter)
        def do_update(alarms):
            for i, a in enumerate(alarms):
                if a.get("id") == alarm_id:
                    alarms[i] = updated
                    break
        modify_alarms(do_update)
        return redirect(url_for("dashboard", **back_params))
    form_data = dict(alarm)
    if isinstance(form_data.get("email"), list):
        form_data["email"] = ", ".join(form_data["email"])
    return render_template("alarm_form.html", form=form_data, alarm=alarm, title="Edit Alarm",
                           sort=sort, owned_filter=owned_filter)


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


@app.route("/alarm/<alarm_id>/toggle-owned", methods=["POST"])
@login_required
def alarm_toggle_owned(alarm_id):
    def do_toggle(alarms):
        for alarm in alarms:
            if alarm.get("id") == alarm_id:
                alarm["owned"] = not alarm.get("owned", False)
                break
    modify_alarms(do_toggle)
    sort = request.args.get("sort", "")
    owned = request.args.get("owned", "")
    params = {}
    if sort:
        params["sort"] = sort
    if owned:
        params["owned"] = owned
    return redirect(url_for("dashboard", **params))


# --- Trade CRUD ---

@app.route("/trade/new", methods=["GET", "POST"])
@login_required
def trade_new():
    if request.method == "POST":
        trade, error = _trade_from_form(request.form)
        if error:
            return render_template("trade_form.html", error=error, form=request.form, title="Add Trade")
        def do_append(trades):
            trades.append(trade)
        modify_trades(do_append)
        return redirect(url_for("dashboard", tab="history"))
    return render_template("trade_form.html", form={}, title="Add Trade")


@app.route("/trade/<trade_id>/edit", methods=["GET", "POST"])
@login_required
def trade_edit(trade_id):
    trades = read_trades()
    trade = next((t for t in trades if t.get("id") == trade_id), None)
    if trade is None:
        return redirect(url_for("dashboard", tab="history"))
    if request.method == "POST":
        updated, error = _trade_from_form(request.form, existing=trade)
        if error:
            return render_template("trade_form.html", error=error, form=request.form,
                                   trade=trade, title="Edit Trade")
        def do_update(trades):
            for i, t in enumerate(trades):
                if t.get("id") == trade_id:
                    trades[i] = updated
                    break
        modify_trades(do_update)
        return redirect(url_for("dashboard", tab="history"))
    return render_template("trade_form.html", form=dict(trade), trade=trade, title="Edit Trade")


@app.route("/trade/<trade_id>/delete", methods=["POST"])
@login_required
def trade_delete(trade_id):
    def do_delete(trades):
        trades[:] = [t for t in trades if t.get("id") != trade_id]
    modify_trades(do_delete)
    return redirect(url_for("dashboard", tab="history"))


@app.route("/alarm/<alarm_id>/record-sale", methods=["GET", "POST"])
@login_required
def alarm_record_sale(alarm_id):
    alarms = read_alarms()
    alarm = next((a for a in alarms if a.get("id") == alarm_id), None)
    if alarm is None:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        trade, error = _trade_from_form(request.form)
        if error:
            return render_template("trade_form.html", error=error, form=request.form,
                                   title="Record Sale", is_record_sale=True, trade=alarm)
        def do_append(trades):
            trades.append(trade)
        modify_trades(do_append)
        if request.form.get("delete_alarm") == "on":
            # Note: trade write and alarm delete are separate operations;
            # if the process dies between them, the trade is saved but the alarm survives.
            def do_delete(alarms):
                alarms[:] = [a for a in alarms if a.get("id") != alarm_id]
            modify_alarms(do_delete)
        return redirect(url_for("dashboard", tab="history"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    buy_date = (alarm.get("created_at") or "")[:10] or today
    form_data = {
        "ticker": alarm.get("ticker", ""),
        "source": alarm.get("source", "yfinance"),
        "shares": alarm.get("shares") or "",
        "buy_price": alarm.get("initial_price") or "",
        "buy_date": buy_date,
        "sell_price": "",
        "sell_date": today,
    }
    return render_template("trade_form.html", form=form_data, title="Record Sale",
                           is_record_sale=True, trade=alarm)


# --- Test email ---

@app.route("/alarm/<alarm_id>/test-email", methods=["POST"])
@login_required
def alarm_test_email(alarm_id):
    api_key = os.environ.get("BREVO_API_KEY")
    sender = os.environ.get("BREVO_SENDER_EMAIL")
    if not api_key or not sender:
        return jsonify({"error": "Email not configured on server"}), 500
    alarms = read_alarms()
    alarm = next((a for a in alarms if a.get("id") == alarm_id), None)
    if alarm is None:
        return jsonify({"error": "Alarm not found"}), 404
    ticker = alarm.get("ticker", "?")
    try:
        if alarm.get("source") == "tase":
            price = tase.get_price(alarm["tase_id"], alarm["tase_type"])
        else:
            price = checker.get_price(ticker)
    except Exception:
        price = None
    price_str = f"${price:.2f}" if price is not None else "unavailable"
    subject = f"Test Alert: {ticker} is currently at {price_str}"
    body = (
        f"This is a test email from StockAlarm.\n\n"
        f"Ticker: {ticker}\n"
        f"Current Price: {price_str}\n\n"
        f"Your alarm is set up correctly."
    )
    to = alarm.get("email")
    try:
        checker.send_email(subject, body, to, api_key, sender)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Chart data ---

@app.route("/alarm/<alarm_id>/chart-data")
@login_required
def chart_data(alarm_id):
    alarms = read_alarms()
    alarm = next((a for a in alarms if a.get("id") == alarm_id), None)
    if alarm is None:
        return jsonify({"error": "not found"}), 404
    tase_id = alarm.get("tase_id")
    period = request.args.get("period", "1mo")
    if period not in ("5d", "1mo", "1y"):
        period = "1mo"
    try:
        if tase_id:
            history = tase.get_history(tase_id, alarm.get("tase_type", "security"), period)
            labels = [h["date"] for h in history]
            prices = [h["price"] for h in history]
        else:
            import yfinance as yf
            ticker = alarm.get("ticker")
            hist = yf.Ticker(ticker).history(period=period)
            labels = [str(d.date()) for d in hist.index]
            prices = [round(float(p), 2) for p in hist["Close"]]
        return jsonify({"labels": labels, "prices": prices})
    except Exception as e:
        label = tase_id or alarm.get("ticker")
        app.logger.error(f"Chart data fetch failed for {label}: {e}")
        return jsonify({"error": "Could not fetch chart data"}), 500


# --- Autocomplete endpoints ---

@app.route("/ticker-search")
@login_required
def ticker_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search?" + urllib.parse.urlencode({
            "q": q, "quotesCount": 6, "newsCount": 0
        })
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        results = [
            {"symbol": item["symbol"], "name": item.get("shortname") or item.get("longname") or ""}
            for item in data.get("quotes", [])
            if item.get("symbol")
        ]
        return jsonify(results[:6])
    except Exception:
        return jsonify([])


@app.route("/city-search")
@login_required
def city_search():
    q = request.args.get("q", "").strip().lower()
    if len(q) < 2:
        return jsonify([])
    matches = [
        c for c in cities_data.CITIES
        if q in c["city"].lower() or c["city"].lower().startswith(q)
    ]
    # Prioritize prefix matches
    matches.sort(key=lambda c: (not c["city"].lower().startswith(q), c["city"]))
    return jsonify(matches[:8])


@app.route("/api/tase-search")
@login_required
def tase_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    return jsonify(tase.search(q, _tase_cache))


@app.route("/timezone-to-city")
@login_required
def timezone_to_city():
    tz = request.args.get("tz", "").strip()
    for c in cities_data.CITIES:
        if c["timezone"] == tz:
            return jsonify(c)
    return jsonify(None)


# --- Form helpers ---

def _alarm_from_form(form, existing=None):
    """Parse and validate form data. Returns (alarm_dict, error_str_or_None)."""
    import uuid

    source = form.get("source", "yfinance")
    is_tase = source == "tase"

    ticker_raw = form.get("ticker", "").strip()
    if not ticker_raw:
        return None, "Ticker is required"
    ticker = ticker_raw if is_tase else ticker_raw.upper()

    tase_id = form.get("tase_id", "").strip() if is_tase else None
    tase_type = form.get("tase_type", "").strip() if is_tase else None
    if is_tase and not tase_id:
        return None, "Please select a security from the dropdown"

    email_raw = form.get("email", "").strip()
    emails = [e.strip() for e in email_raw.split(",") if e.strip()]
    if not emails:
        return None, "At least one email is required"

    alarm_type = form.get("alarm_type", "price")
    tz = form.get("timezone", "").strip() or None
    if not tz:
        return None, "Timezone (city) is required"

    try:
        snooze_hours = int(form.get("snooze_hours", 72))
    except ValueError:
        snooze_hours = 72
    notes = form.get("notes", "").strip()

    shares_raw = form.get("shares", "").strip()
    if shares_raw:
        try:
            shares = int(shares_raw)
        except ValueError:
            return None, "Shares must be a whole number"
    else:
        shares = None

    # Manual reference price (overrides live fetch for initial_price / base_price)
    ref_price_raw = form.get("reference_price", "").strip()
    manual_ref = None
    if ref_price_raw:
        try:
            manual_ref = float(ref_price_raw)
        except ValueError:
            return None, "Reference price must be a number"

    alarm = {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "ticker": ticker,
        "enabled": form.get("enabled") == "on",
        "owned": form.get("owned") == "on",
        "shares": shares,
        "timezone": tz,
        "snooze_hours": snooze_hours,
        "notes": notes or None,
        "last_triggered": existing.get("last_triggered") if existing else None,
        "email": emails if len(emails) > 1 else emails[0],
    }

    if is_tase:
        alarm["source"] = "tase"
        alarm["tase_id"] = tase_id
        alarm["tase_type"] = tase_type

    if existing:
        alarm["created_at"] = existing.get("created_at")
        alarm["initial_price"] = existing.get("initial_price")
        alarm["history"] = existing.get("history", [])
    else:
        alarm["created_at"] = datetime.now(timezone.utc).isoformat()
        alarm["history"] = []
        if manual_ref is not None:
            alarm["initial_price"] = manual_ref
        else:
            try:
                if is_tase:
                    alarm["initial_price"] = tase.get_price(tase_id, tase_type)
                else:
                    alarm["initial_price"] = checker.get_price(ticker)
            except Exception:
                alarm["initial_price"] = None

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
        if existing:
            alarm["base_price"] = existing.get("base_price")
        elif manual_ref is not None:
            alarm["base_price"] = manual_ref
        else:
            alarm["base_price"] = None
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


def _trade_from_form(form, existing=None):
    """Parse and validate trade form data. Returns (trade_dict, error_str_or_None)."""
    import uuid

    ticker = form.get("ticker", "").strip()
    if not ticker:
        return None, "Ticker is required"

    source = form.get("source", "yfinance")

    shares_raw = form.get("shares", "").strip()
    if shares_raw:
        try:
            shares = int(shares_raw)
        except ValueError:
            return None, "Shares must be a whole number"
    else:
        shares = None

    buy_price_raw = form.get("buy_price", "").strip()
    sell_price_raw = form.get("sell_price", "").strip()
    try:
        buy_price = float(buy_price_raw) if buy_price_raw else None
        sell_price = float(sell_price_raw) if sell_price_raw else None
    except ValueError:
        return None, "Prices must be numbers"
    if buy_price is None:
        return None, "Buy price is required"
    if sell_price is None:
        return None, "Sell price is required"

    buy_date = form.get("buy_date", "").strip()
    sell_date = form.get("sell_date", "").strip()
    if not buy_date:
        return None, "Buy date is required"
    if not sell_date:
        return None, "Sell date is required"

    return {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "ticker": ticker,
        "source": source,
        "shares": shares,
        "buy_price": buy_price,
        "buy_date": buy_date,
        "sell_price": sell_price,
        "sell_date": sell_date,
        "created_at": existing["created_at"] if existing else datetime.now(timezone.utc).isoformat(),
    }, None


if __name__ == "__main__":
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(checker.run, "interval", minutes=15, kwargs={"path": _ALARMS_PATH})
    scheduler.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
