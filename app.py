import os
import sys
import threading
import uuid
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
_SAVINGS_PATH = checker.get_savings_path()
_SNAPSHOTS_PATH = checker.get_snapshots_path()
_SIEMENS_PATH = checker.get_siemens_path()
_SIEMENS_PORTAL_URL = "https://samlparticipant.equateplus.com/EquatePlusParticipant2/start"
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


def _savings_path():
    return _SAVINGS_PATH


def _snapshots_path():
    return _SNAPSHOTS_PATH


def read_savings():
    with _lock:
        return checker.load_savings(_savings_path())


def write_savings(holdings):
    with _lock:
        checker.save_savings(holdings, _savings_path())


def modify_savings(fn):
    with _lock:
        path = _savings_path()
        holdings = checker.load_savings(path)
        fn(holdings)
        checker.save_savings(holdings, path)


def read_snapshots():
    with _lock:
        return checker.load_snapshots(_snapshots_path())


def read_siemens():
    with _lock:
        return checker.load_siemens(_SIEMENS_PATH)


def write_siemens(data):
    with _lock:
        checker.save_siemens(data, _SIEMENS_PATH)


def _relative_time(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        diff = datetime.now(timezone.utc) - dt
        secs = diff.total_seconds()
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{int(secs / 60)}m ago"
        if secs < 86400:
            return f"{int(secs / 3600)}h ago"
        return f"{int(secs / 86400)}d ago"
    except Exception:
        return "—"


def _fetch_savings_prices(holdings: list) -> dict:
    """Returns {ticker: {"price": float|None, "prev_close": float|None}}.
    TASE holdings get prev_close=None (not available from TASE API)."""
    prices = {}
    for h in holdings:
        ticker = h.get("ticker")
        if not ticker or ticker in prices:
            continue
        try:
            if h.get("source") == "tase":
                price = tase.get_price(h["tase_id"], h["tase_type"])
                prices[ticker] = {"price": price, "prev_close": None}
            else:
                price, prev = checker.get_price_with_change(ticker)
                prices[ticker] = {"price": price, "prev_close": prev}
        except Exception:
            prices[ticker] = {"price": None, "prev_close": None}
    return prices


def _holding_from_form(form, existing=None):
    """Parse and validate holding form data. Returns (holding_dict, error_str|None)."""
    source = form.get("source", "yfinance")
    is_tase = source == "tase"

    ticker_raw = form.get("ticker", "").strip()
    if not ticker_raw:
        return None, "Ticker is required"
    ticker = ticker_raw if is_tase else ticker_raw.upper()

    tase_id = form.get("tase_id", "").strip() if is_tase else ""
    tase_type = form.get("tase_type", "").strip() if is_tase else ""
    if is_tase and not tase_id:
        return None, "Please select a security from the dropdown"

    name = form.get("name", "").strip() or ticker

    category = form.get("category", "").strip()
    if category not in ("stocks", "etf", "mmf"):
        return None, "Invalid category"

    if category == "etf":
        current_value_raw = form.get("current_value", "").strip()
        if not current_value_raw:
            return None, "Current value is required"
        try:
            current_value = float(current_value_raw)
        except ValueError:
            return None, "Current value must be a number"
        if current_value <= 0:
            return None, "Current value must be greater than zero"

        total_change_raw = form.get("total_change", "").strip()
        if not total_change_raw:
            return None, "Total change is required"
        try:
            total_change = float(total_change_raw)
        except ValueError:
            return None, "Total change must be a number"

        cost_basis = current_value - total_change
        if cost_basis <= 0:
            return None, "Total change cannot be equal to or greater than current value"

        try:
            if is_tase:
                current_price = tase.get_price(tase_id, tase_type)
            else:
                current_price, _ = checker.get_price_with_change(ticker)
            if current_price is None:
                raise ValueError("no price")
        except Exception:
            return None, "Could not fetch current price — please try again"
        shares = round(current_value / current_price, 2)
    else:
        shares_raw = form.get("shares", "").strip()
        if not shares_raw:
            return None, "Shares is required"
        try:
            shares = float(shares_raw)
        except ValueError:
            return None, "Shares must be a number"

        cost_raw = form.get("cost_basis", "").strip()
        if not cost_raw:
            return None, "Cost basis is required"
        try:
            cost_basis = float(cost_raw)
        except ValueError:
            return None, "Cost basis must be a number"

    currency = "ILS" if is_tase else form.get("currency", "USD")

    return {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "name": name,
        "category": category,
        "source": source,
        "ticker": ticker,
        "tase_id": tase_id,
        "tase_type": tase_type,
        "shares": shares,
        "cost_basis": cost_basis,
        "currency": currency,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }, None


def _maybe_record_snapshot(holdings: list, prices: dict, usd_to_ils: float) -> None:
    """Appends a daily total-ILS snapshot if today's entry is not yet recorded."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _lock:
        path = _snapshots_path()
        snapshots = checker.load_snapshots(path)
        if snapshots and snapshots[-1].get("date") == today_str:
            return
        total_ils = 0.0
        for h in holdings:
            ticker = h.get("ticker")
            pinfo = prices.get(ticker, {})
            price = pinfo.get("price")
            if price is None:
                continue
            shares = h.get("shares") or 0
            rate = usd_to_ils if h.get("currency") == "USD" else 1.0
            total_ils += price * shares * rate
        snapshots.append({"date": today_str, "total_ils": round(total_ils, 2)})
        snapshots = snapshots[-90:]
        checker.save_snapshots(snapshots, path)


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
        sell_trades = [t for t in trades if t.get("type", "sell") == "sell"]
        trade_pcts = {}
        trade_pls = {}
        pl_values = []
        for t in sell_trades:
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
        best_trade = next((t for t in sell_trades if t.get("id") == best), None) if best else None
        summary = {
            "count": len(sell_trades),
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


# --- Siemens ---

@app.route("/siemens/edit", methods=["GET", "POST"])
@login_required
def siemens_edit():
    if request.method == "POST":
        try:
            shares = float(request.form.get("shares", "").strip())
            total_value_ils = float(request.form.get("total_value_ils", "").strip())
            gain_ils = float(request.form.get("gain_ils", "").strip())
            gain_pct = float(request.form.get("gain_pct", "").strip())
        except ValueError:
            return render_template("siemens_form.html",
                                   error="All fields must be numbers",
                                   form=request.form)
        write_siemens({
            "shares": shares,
            "total_value_ils": total_value_ils,
            "gain_ils": gain_ils,
            "gain_pct": gain_pct,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })
        return redirect(url_for("savings"))
    siemens = read_siemens() or {}
    return render_template("siemens_form.html", form=siemens)


# --- Savings ---

@app.route("/savings")
@login_required
def savings():
    holdings = read_savings()
    prices = _fetch_savings_prices(holdings)
    usd_to_ils = checker.get_usd_to_ils()

    _maybe_record_snapshot(holdings, prices, usd_to_ils)

    CATEGORIES = ("etf", "stocks", "mmf")

    holding_data = {}
    for h in holdings:
        hid = h["id"]
        ticker = h.get("ticker")
        pinfo = prices.get(ticker, {})
        price = pinfo.get("price")
        prev_close = pinfo.get("prev_close")
        shares = h.get("shares") or 0
        cost_basis = h.get("cost_basis") or 0
        currency = h.get("currency", "ILS")
        rate = usd_to_ils if currency == "USD" else 1.0

        current_value = price * shares if price is not None else None
        current_value_ils = current_value * rate if current_value is not None else None
        cost_ils = cost_basis * rate
        pl_ils = (current_value_ils - cost_ils) if current_value_ils is not None else None
        pl_pct = (pl_ils / cost_ils * 100) if (pl_ils is not None and cost_ils) else None

        today_change = ((price - prev_close) * shares
                        if price is not None and prev_close is not None else None)
        today_change_ils = today_change * rate if today_change is not None else None

        holding_data[hid] = {
            "price": price,
            "current_value": current_value,
            "current_value_ils": current_value_ils,
            "cost_ils": cost_ils,
            "pl_ils": pl_ils,
            "pl_pct": pl_pct,
            "today_change": today_change,
            "today_change_ils": today_change_ils,
            "last_updated_rel": _relative_time(h.get("last_updated")),
            "pct_of_cat": 0.0,
        }

    cat_data = {}
    for cat in CATEGORIES:
        cat_holdings = [h for h in holdings if h.get("category") == cat]
        value_ils = sum(holding_data[h["id"]]["current_value_ils"] or 0 for h in cat_holdings)
        pl_ils = sum(holding_data[h["id"]]["pl_ils"] or 0 for h in cat_holdings)
        today_ils = sum(holding_data[h["id"]]["today_change_ils"] or 0 for h in cat_holdings)
        cost_ils = sum(holding_data[h["id"]]["cost_ils"] for h in cat_holdings)
        cat_data[cat] = {
            "value_ils": value_ils,
            "pl_ils": pl_ils,
            "today_ils": today_ils,
            "cost_ils": cost_ils,
            "pct_of_portfolio": 0.0,
        }

    total_value_ils = sum(d["value_ils"] for d in cat_data.values())
    total_pl_ils = sum(d["pl_ils"] for d in cat_data.values())
    total_today_ils = sum(d["today_ils"] for d in cat_data.values())
    total_cost_ils = sum(d["cost_ils"] for d in cat_data.values())

    siemens = read_siemens()
    if siemens:
        sie_value = siemens.get("total_value_ils") or 0
        sie_gain = siemens.get("gain_ils") or 0
        total_value_ils += sie_value
        total_pl_ils += sie_gain
        total_cost_ils += sie_value - sie_gain

    total_pl_pct = (total_pl_ils / total_cost_ils * 100) if total_cost_ils else None
    prev_total = total_value_ils - total_today_ils
    total_today_pct = (total_today_ils / prev_total * 100) if prev_total else None

    for cat in CATEGORIES:
        cat_data[cat]["pct_of_portfolio"] = (
            cat_data[cat]["value_ils"] / total_value_ils * 100 if total_value_ils else 0.0)
        cat_value = cat_data[cat]["value_ils"]
        for h in holdings:
            if h.get("category") == cat:
                hval = holding_data[h["id"]]["current_value_ils"] or 0
                holding_data[h["id"]]["pct_of_cat"] = (
                    hval / cat_value * 100 if cat_value else 0.0)

    circ = 251.33
    pie = {}
    offset = 0.0
    for cat in CATEGORIES:
        pct = cat_data[cat]["pct_of_portfolio"]
        dash = round(pct / 100 * circ, 2)
        gap = round(circ - dash, 2)
        pie[cat] = {"dash": dash, "gap": gap, "offset": round(-offset, 2)}
        offset += dash
    if siemens and total_value_ils:
        sie_pct = (siemens.get("total_value_ils") or 0) / total_value_ils * 100
        dash = round(sie_pct / 100 * circ, 2)
        pie["siemens"] = {"dash": dash, "gap": round(circ - dash, 2), "offset": round(-offset, 2)}

    snapshots = read_snapshots()[-30:]

    summary = {
        "total_value_ils": total_value_ils,
        "total_pl_ils": total_pl_ils,
        "total_pl_pct": total_pl_pct,
        "total_today_ils": total_today_ils,
        "total_today_pct": total_today_pct,
    }

    return render_template(
        "dashboard.html", tab="savings",
        holdings=holdings, holding_data=holding_data,
        cat_data=cat_data, summary=summary,
        pie=pie, snapshots=snapshots,
        usd_to_ils=usd_to_ils,
        categories=("etf", "stocks", "mmf"),
        category_labels={"etf": "ETFs", "stocks": "Stocks", "mmf": "Money Market Funds (MMF)"},
        siemens=siemens,
        siemens_updated_rel=_relative_time(siemens.get("last_updated")) if siemens else None,
        siemens_portal_url=_SIEMENS_PORTAL_URL,
    )


@app.route("/savings/new", methods=["GET", "POST"])
@login_required
def savings_new():
    category = request.args.get("category", "stocks")
    if request.method == "POST":
        holding, error = _holding_from_form(request.form)
        if error:
            return render_template("savings_form.html", error=error,
                                   form=request.form, title="Add Holding",
                                   category=request.form.get("category", category))
        def do_append(holdings):
            holdings.append(holding)
        modify_savings(do_append)
        return redirect(url_for("savings"))
    return render_template("savings_form.html", form={"category": category},
                           title="Add Holding", category=category)


@app.route("/savings/<hid>/edit", methods=["GET", "POST"])
@login_required
def savings_edit(hid):
    holdings = read_savings()
    holding = next((h for h in holdings if h.get("id") == hid), None)
    if holding is None:
        return redirect(url_for("savings"))
    if request.method == "POST":
        updated, error = _holding_from_form(request.form, existing=holding)
        if error:
            return render_template("savings_form.html", error=error,
                                   form=request.form, holding=holding,
                                   title="Edit Holding",
                                   category=holding["category"])
        def do_update(holdings):
            for i, h in enumerate(holdings):
                if h.get("id") == hid:
                    holdings[i] = updated
                    break
        modify_savings(do_update)
        return redirect(url_for("savings"))
    return render_template("savings_form.html", form=dict(holding),
                           holding=holding, title="Edit Holding",
                           category=holding["category"])


@app.route("/savings/<hid>/delete", methods=["POST"])
@login_required
def savings_delete(hid):
    def do_delete(holdings):
        holdings[:] = [h for h in holdings if h.get("id") != hid]
    modify_savings(do_delete)
    return redirect(url_for("savings"))


@app.route("/savings/<hid>/shares", methods=["POST"])
@login_required
def savings_update_shares(hid):
    shares_raw = request.form.get("shares", "").strip()
    try:
        shares = float(shares_raw)
    except ValueError:
        return jsonify({"error": "Invalid shares value"}), 400
    updated_ts = datetime.now(timezone.utc).isoformat()
    found = [False]
    def do_update(holdings):
        for h in holdings:
            if h.get("id") == hid:
                h["shares"] = shares
                h["last_updated"] = updated_ts
                found[0] = True
                break
    modify_savings(do_update)
    if not found[0]:
        return jsonify({"error": "Holding not found"}), 404
    return jsonify({"ok": True, "shares": shares,
                    "last_updated_rel": _relative_time(updated_ts)})


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
            shares = float(shares_raw)
        except ValueError:
            return None, "Shares must be a number"
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
    trade_type = form.get("type", "sell")
    if trade_type not in ("buy", "sell"):
        trade_type = "sell"

    ils_mode = form.get("ils_mode") == "1"

    if ils_mode:
        shares = None
        buy_price = None
        sell_price = None
        try:
            buy_amount_raw = form.get("buy_amount_ils", "").strip()
            sell_amount_raw = form.get("sell_amount_ils", "").strip()
            buy_amount_ils = float(buy_amount_raw) if buy_amount_raw else None
            sell_amount_ils = float(sell_amount_raw) if sell_amount_raw else None
        except ValueError:
            return None, "Amounts must be numbers"
        buy_date = form.get("buy_date", "").strip() if trade_type == "buy" else None
        sell_date = form.get("sell_date", "").strip() if trade_type == "sell" else None
        if trade_type == "buy":
            if buy_amount_ils is None:
                return None, "Buy amount is required"
            if not buy_date:
                return None, "Buy date is required"
        else:
            if sell_amount_ils is None:
                return None, "Sell amount is required"
            if not sell_date:
                return None, "Sell date is required"
    else:
        buy_amount_ils = None
        sell_amount_ils = None
        shares_raw = form.get("shares", "").strip()
        if shares_raw:
            try:
                shares = float(shares_raw)
            except ValueError:
                return None, "Shares must be a number"
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
        if trade_type == "sell" and sell_price is None:
            return None, "Sell price is required"
        buy_date = form.get("buy_date", "").strip()
        sell_date = form.get("sell_date", "").strip()
        if not buy_date:
            return None, "Buy date is required"
        if trade_type == "sell" and not sell_date:
            return None, "Sell date is required"

    return {
        "id": existing["id"] if existing else str(uuid.uuid4())[:8],
        "type": trade_type,
        "ticker": ticker,
        "source": source,
        "shares": shares,
        "buy_price": buy_price,
        "buy_date": buy_date,
        "sell_price": sell_price,
        "sell_date": sell_date if trade_type == "sell" else None,
        "buy_amount_ils": buy_amount_ils,
        "sell_amount_ils": sell_amount_ils,
        "created_at": existing["created_at"] if existing else datetime.now(timezone.utc).isoformat(),
    }, None


if __name__ == "__main__":
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(checker.run, "interval", minutes=15, kwargs={"path": _ALARMS_PATH})
    scheduler.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
