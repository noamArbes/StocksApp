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
import research
import journal as journal_module
import portfolio_analysis

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
_ANALYSIS_PATH = checker.get_portfolio_analysis_path()
_JOURNAL_PATH = journal_module.get_journal_path()
_SIEMENS_PORTAL_URL = "https://samlparticipant.equateplus.com/EquatePlusParticipant2/start"
_tase_cache = tase.load_securities_cache()
_PRESETS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets.json")

VALID_REGIONS = ("us", "israel", "europe", "china", "developing")


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


def _journal_path():
    return _JOURNAL_PATH


def _analysis_path():
    return _ANALYSIS_PATH


def read_portfolio_analysis():
    with _lock:
        return checker.load_portfolio_analysis(_analysis_path())


def read_journal_trades():
    with _lock:
        return journal_module.load_trades(_journal_path())


def write_journal_trade(trade):
    with _lock:
        return journal_module.save_trade(trade, _journal_path())


def clear_journal_trades():
    with _lock:
        journal_module.clear_trades(_journal_path())


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


# --- Auto trade-history logging for savings changes ---

AUTO_TRADE_CATEGORIES = ("stocks", "etf")
_SHARE_EPSILON = 1e-9


def _parse_txn_date(form) -> str:
    """Parses an optional txn_date form field (YYYY-MM-DD), falling back to today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = (form.get("txn_date") or "").strip()
    if not raw:
        return today
    try:
        datetime.strptime(raw, "%Y-%m-%d")
        return raw
    except ValueError:
        return today


def _current_market_price(holding: dict):
    """Best-effort live price for a single holding. Never raises."""
    try:
        if holding.get("source") == "tase":
            return tase.get_price(holding["tase_id"], holding["tase_type"])
        price, _ = checker.get_price_with_change(holding["ticker"])
        return price
    except Exception:
        return None


def _avg_cost_per_share(holding: dict):
    shares = holding.get("shares") or 0
    cost = holding.get("cost_basis")
    if shares and cost is not None:
        return cost / shares
    return None


def _auto_trade(holding: dict, trade_type: str, shares: float, price: float,
                 buy_price=None, txn_date=None) -> dict:
    """Builds a trade dict for a buy/sell inferred from a savings holding change."""
    d = txn_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    is_buy = trade_type == "buy"
    return {
        "id": str(uuid.uuid4())[:8],
        "type": trade_type,
        "ticker": holding.get("ticker"),
        "name": holding.get("name"),
        "source": holding.get("source", "yfinance"),
        "shares": round(shares, 6),
        "buy_price": round(price, 4) if is_buy else (round(buy_price, 4) if buy_price is not None else None),
        "buy_date": d if is_buy else None,
        "sell_price": None if is_buy else round(price, 4),
        "sell_date": None if is_buy else d,
        "buy_amount_ils": None,
        "sell_amount_ils": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _log_auto_trade_for_shares_delta(before_holding, after_holding, delta_shares,
                                      delta_cost, txn_date):
    """Appends a buy/sell trade for a shares delta on an existing stocks/etf holding."""
    if after_holding.get("category") not in AUTO_TRADE_CATEGORIES:
        return
    if delta_shares > _SHARE_EPSILON:
        if delta_cost > 0:
            price = delta_cost / delta_shares
        else:
            price = _current_market_price(after_holding)
            if price is None:
                price = _avg_cost_per_share(before_holding)
        if price is not None:
            trade = _auto_trade(after_holding, "buy", delta_shares, price, txn_date=txn_date)
            modify_trades(lambda trades: trades.append(trade))
    elif delta_shares < -_SHARE_EPSILON:
        sold = -delta_shares
        sell_price = _current_market_price(after_holding)
        if sell_price is None:
            sell_price = _avg_cost_per_share(before_holding)
        buy_price = _avg_cost_per_share(before_holding)
        if sell_price is not None:
            trade = _auto_trade(after_holding, "sell", sold, sell_price,
                                 buy_price=buy_price, txn_date=txn_date)
            modify_trades(lambda trades: trades.append(trade))


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

    if category == "etf" and existing is None:
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

    region_raw = form.get("region", "").strip() or None
    if region_raw is not None and region_raw not in VALID_REGIONS:
        return None, "Invalid region — must be one of: US, Israel, Europe, China, Developing Markets"

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
        "region": region_raw,
        "order": existing.get("order") if existing else None,
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
        trades = list(reversed(read_trades()))
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
            gain_pct = float(request.form.get("gain_pct", "").strip())
        except ValueError:
            return render_template("siemens_form.html",
                                   error="All fields must be numbers",
                                   form=request.form)
        if gain_pct <= -100:
            return render_template("siemens_form.html",
                                   error="Percentage Gained cannot be -100% or lower",
                                   form=request.form)
        cost_basis = total_value_ils / (1 + gain_pct / 100)
        gain_ils = total_value_ils - cost_basis
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

_SECTOR_PALETTE = ["#4fc3f7", "#e57373", "#aed581", "#ffb74d", "#ce93d8",
                    "#81c784", "#f06292", "#9575cd", "#4db6ac", "#dce775"]


def _build_sector_pie(sector_pct: dict) -> list[dict]:
    circ = 251.33
    items = sorted(sector_pct.items(), key=lambda kv: kv[1], reverse=True)
    slices, offset = [], 0.0
    for i, (name, pct) in enumerate(items):
        dash = round(pct / 100 * circ, 2)
        slices.append({
            "name": name, "pct": pct,
            "color": _SECTOR_PALETTE[i % len(_SECTOR_PALETTE)],
            "dash": dash, "gap": round(circ - dash, 2), "offset": round(-offset, 2),
        })
        offset += dash
    return slices


@app.route("/savings")
@login_required
def savings():
    holdings = read_savings()
    holdings = [h for _, h in sorted(
        enumerate(holdings),
        key=lambda pair: pair[1].get("order") if pair[1].get("order") is not None else pair[0],
    )]
    prices = _fetch_savings_prices(holdings)
    usd_to_ils = checker.get_usd_to_ils()

    _maybe_record_snapshot(holdings, prices, usd_to_ils)

    CATEGORIES = ("etf", "stocks", "mmf")
    REGIONS = VALID_REGIONS
    REGION_LABELS = {
        "us": "US",
        "israel": "Israel",
        "europe": "Europe",
        "china": "China",
        "developing": "Dev. Markets",
    }

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

    # Geographic breakdown
    geo_data = {}
    for region in REGIONS:
        region_holdings = [h for h in holdings if h.get("region") == region]
        value_ils = sum(holding_data[h["id"]]["current_value_ils"] or 0 for h in region_holdings)
        geo_data[region] = {"value_ils": value_ils, "pct_of_portfolio": 0.0}

    # Siemens is always Europe
    if siemens:
        geo_data["europe"]["value_ils"] += siemens.get("total_value_ils") or 0

    # Unclassified holdings (region is null/missing)
    unclassified_ils = sum(
        holding_data[h["id"]]["current_value_ils"] or 0
        for h in holdings if not h.get("region")
    )

    for region in REGIONS:
        geo_data[region]["pct_of_portfolio"] = (
            geo_data[region]["value_ils"] / total_value_ils * 100 if total_value_ils else 0.0
        )

    geo_pie = {}
    geo_offset = 0.0
    for region in REGIONS:
        pct = geo_data[region]["pct_of_portfolio"]
        dash = round(pct / 100 * 251.33, 2)
        gap = round(251.33 - dash, 2)
        geo_pie[region] = {"dash": dash, "gap": gap, "offset": round(-geo_offset, 2)}
        geo_offset += dash

    if unclassified_ils and total_value_ils:
        pct = unclassified_ils / total_value_ils * 100
        dash = round(pct / 100 * 251.33, 2)
        geo_pie["unclassified"] = {
            "dash": dash,
            "gap": round(251.33 - dash, 2),
            "offset": round(-geo_offset, 2),
        }

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

    analysis = read_portfolio_analysis()
    us_sector_pie = _build_sector_pie((analysis or {}).get("sector_by_region", {}).get("us", {}))
    il_sector_pie = _build_sector_pie((analysis or {}).get("sector_by_region", {}).get("israel", {}))
    stock_exposure = (analysis or {}).get("stock_exposure", [])
    analysis_computed_rel = _relative_time(analysis["computed_at"]) if analysis else None

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
        geo_data=geo_data, geo_pie=geo_pie,
        regions=REGIONS, region_labels=REGION_LABELS,
        unclassified_ils=unclassified_ils,
        us_sector_pie=us_sector_pie, il_sector_pie=il_sector_pie,
        stock_exposure=stock_exposure, analysis_computed_rel=analysis_computed_rel,
    )


@app.route("/savings/new", methods=["GET", "POST"])
@login_required
def savings_new():
    category = request.args.get("category", "stocks")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if request.method == "POST":
        holding, error = _holding_from_form(request.form)
        if error:
            return render_template("savings_form.html", error=error,
                                   form=request.form, title="Add Holding",
                                   category=request.form.get("category", category),
                                   today=today)
        def do_append(holdings):
            same_cat = [h for h in holdings if h.get("category") == holding["category"]]
            max_order = max(
                (h.get("order") if h.get("order") is not None else i
                 for i, h in enumerate(same_cat)),
                default=-1,
            )
            holding["order"] = max_order + 1
            holdings.append(holding)
        modify_savings(do_append)
        if holding["category"] in AUTO_TRADE_CATEGORIES and holding["shares"] > _SHARE_EPSILON:
            price = holding["cost_basis"] / holding["shares"]
            txn_date = _parse_txn_date(request.form)
            trade = _auto_trade(holding, "buy", holding["shares"], price, txn_date=txn_date)
            modify_trades(lambda trades: trades.append(trade))
        return redirect(url_for("savings"))
    return render_template("savings_form.html", form={"category": category},
                           title="Add Holding", category=category, today=today)


@app.route("/savings/<hid>/edit", methods=["GET", "POST"])
@login_required
def savings_edit(hid):
    holdings = read_savings()
    holding = next((h for h in holdings if h.get("id") == hid), None)
    if holding is None:
        return redirect(url_for("savings"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if request.method == "POST":
        updated, error = _holding_from_form(request.form, existing=holding)
        if error:
            return render_template("savings_form.html", error=error,
                                   form=request.form, holding=holding,
                                   title="Edit Holding",
                                   category=holding["category"], today=today)
        before_shares = holding.get("shares") or 0
        before_cost = holding.get("cost_basis") or 0
        def do_update(holdings):
            for i, h in enumerate(holdings):
                if h.get("id") == hid:
                    holdings[i] = updated
                    break
        modify_savings(do_update)
        delta_shares = updated["shares"] - before_shares
        delta_cost = updated["cost_basis"] - before_cost
        txn_date = _parse_txn_date(request.form)
        _log_auto_trade_for_shares_delta(holding, updated, delta_shares, delta_cost, txn_date)
        return redirect(url_for("savings"))
    return render_template("savings_form.html", form=dict(holding),
                           holding=holding, title="Edit Holding",
                           category=holding["category"], today=today)


@app.route("/savings/<hid>/delete", methods=["POST"])
@login_required
def savings_delete(hid):
    holdings_before = read_savings()
    before = next((h for h in holdings_before if h.get("id") == hid), None)
    def do_delete(holdings):
        holdings[:] = [h for h in holdings if h.get("id") != hid]
    modify_savings(do_delete)
    if before and before.get("category") in AUTO_TRADE_CATEGORIES:
        shares = before.get("shares") or 0
        if shares > _SHARE_EPSILON:
            sell_price = _current_market_price(before)
            if sell_price is None:
                sell_price = _avg_cost_per_share(before)
            buy_price = _avg_cost_per_share(before)
            if sell_price is not None:
                txn_date = _parse_txn_date(request.form)
                trade = _auto_trade(before, "sell", shares, sell_price,
                                     buy_price=buy_price, txn_date=txn_date)
                modify_trades(lambda trades: trades.append(trade))
    return redirect(url_for("savings"))


@app.route("/savings/<hid>/shares", methods=["POST"])
@login_required
def savings_update_shares(hid):
    shares_raw = request.form.get("shares", "").strip()
    try:
        shares = float(shares_raw)
    except ValueError:
        return jsonify({"error": "Invalid shares value"}), 400
    holdings_before = read_savings()
    before = next((h for h in holdings_before if h.get("id") == hid), None)
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
    if before and before.get("category") in AUTO_TRADE_CATEGORIES:
        delta_shares = shares - (before.get("shares") or 0)
        after = dict(before, shares=shares)
        txn_date = _parse_txn_date(request.form)
        _log_auto_trade_for_shares_delta(before, after, delta_shares, 0, txn_date)
    return jsonify({"ok": True, "shares": shares,
                    "last_updated_rel": _relative_time(updated_ts)})


@app.route("/savings/<hid>/move", methods=["POST"])
@login_required
def savings_move(hid):
    direction = request.form.get("direction", "")
    if direction not in ("up", "down"):
        return redirect(url_for("savings"))

    def do_move(holdings):
        holding = next((h for h in holdings if h.get("id") == hid), None)
        if holding is None:
            return
        cat = holding.get("category")
        indices = [i for i, h in enumerate(holdings) if h.get("category") == cat]

        def order_key(i):
            o = holdings[i].get("order")
            return o if o is not None else i
        ordered = sorted(indices, key=order_key)
        pos = next(p for p, i in enumerate(ordered) if holdings[i]["id"] == hid)
        swap_pos = pos - 1 if direction == "up" else pos + 1
        if swap_pos < 0 or swap_pos >= len(ordered):
            return

        ordered_ids = [holdings[i]["id"] for i in ordered]
        ordered_ids[pos], ordered_ids[swap_pos] = ordered_ids[swap_pos], ordered_ids[pos]
        id_to_order = {hid_: i for i, hid_ in enumerate(ordered_ids)}
        for h in holdings:
            if h.get("id") in id_to_order:
                h["order"] = id_to_order[h["id"]]

    modify_savings(do_move)
    return redirect(url_for("savings"))


@app.route("/savings/refresh-analysis", methods=["POST"])
@login_required
def savings_refresh_analysis():
    try:
        portfolio_analysis.run(savings_path=_savings_path(), analysis_path=_analysis_path())
    except Exception as e:
        print(f"[WARN] Portfolio analysis refresh failed: {e}")
    return redirect(url_for("savings"))


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

    name = form.get("name", "").strip()
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
        "name": name,
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


# --- Research routes ---

@app.route("/research")
@login_required
def research_tab():
    return render_template("research.html")


@app.route("/api/research/analyze")
@login_required
def research_analyze():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    if research.is_tase_ticker(ticker):
        return jsonify({"error": "TASE analysis not yet supported"}), 400
    quote = research.get_quote(ticker)
    if not quote:
        return jsonify({"error": f"Could not fetch data for {ticker}"}), 404
    analyst = research.get_analyst_data(ticker, quote["price"])
    profile = research.get_company_profile(ticker)
    technicals = research.get_technicals(ticker)
    fundamentals = research.get_fundamentals(ticker)
    news = research.get_news(ticker)
    return jsonify({
        "ticker": ticker,
        "quote": quote,
        "analyst": analyst,
        "profile": profile,
        "technicals": technicals,
        "fundamentals": fundamentals,
        "news": news,
    })


@app.route("/api/research/ai-summary")
@login_required
def research_ai_summary():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "ticker required"}), 400
    quote = research.get_quote(ticker)
    analyst = research.get_analyst_data(ticker, quote["price"]) if quote else None
    fundamentals = research.get_fundamentals(ticker)
    news = research.get_news(ticker)
    summary = research.get_ai_summary(ticker, {
        "quote": quote, "analyst": analyst,
        "fundamentals": fundamentals, "news": news,
    })
    return jsonify({"summary": summary})


@app.route("/api/research/find-tickers")
@login_required
def research_find_tickers():
    market = request.args.get("market", "us")
    security_type = request.args.get("security_type") or None
    sector = request.args.get("sector") or None
    momentum = request.args.get("momentum") or None
    market_cap = request.args.get("market_cap") or None
    sort_by = request.args.get("sort_by", "upside")
    offset = int(request.args.get("offset", 0))
    limit = 10
    results = research.find_tickers(
        market=market, security_type=security_type, sector=sector,
        momentum=momentum, market_cap=market_cap, limit=offset + limit,
        tase_cache=_tase_cache,
    )
    sorted_results = research.sort_ticker_results(results, sort_by)
    page = sorted_results[offset:offset + limit]
    return jsonify({"results": page, "has_more": len(sorted_results) > offset + limit})


@app.route("/api/research/presets", methods=["GET"])
@login_required
def research_presets_list():
    return jsonify(research.load_presets(_PRESETS_PATH))


@app.route("/api/research/presets", methods=["POST"])
@login_required
def research_presets_save():
    body = request.get_json()
    if not body or not body.get("name"):
        return jsonify({"error": "name required"}), 400
    preset = research.save_preset(_PRESETS_PATH, body["name"], body.get("filters", {}))
    return jsonify(preset)


@app.route("/api/research/presets/<preset_id>", methods=["DELETE"])
@login_required
def research_presets_delete(preset_id):
    research.delete_preset(_PRESETS_PATH, preset_id)
    return jsonify({"ok": True})


@app.route("/journal")
@login_required
def journal_tab():
    return render_template("journal.html")


@app.route("/api/journal/trades", methods=["GET"])
@login_required
def api_journal_trades_get():
    return jsonify(read_journal_trades())


@app.route("/api/journal/trades", methods=["POST"])
@login_required
def api_journal_trade_post():
    trade = request.get_json()
    if not trade:
        return jsonify({"error": "bad request"}), 400
    r = journal_module.calculate_r_multiple(
        trade.get("entry_price"), trade.get("stop_price"), trade.get("target_price")
    )
    if r is not None:
        trade["r_multiple_entry"] = r
    saved = write_journal_trade(trade)
    return jsonify(saved), 201


@app.route("/api/journal/trades", methods=["DELETE"])
@login_required
def api_journal_trades_delete():
    clear_journal_trades()
    return jsonify({"ok": True})


@app.route("/api/journal/chat", methods=["POST"])
@login_required
def api_journal_chat():
    body = request.get_json()
    messages = body.get("messages", [])
    user_message = body.get("message", "")
    messages = messages + [{"role": "user", "content": user_message}]
    try:
        raw = journal_module.call_claude_chat(messages)
    except Exception:
        return jsonify({"error": "AI unavailable"}), 503
    reply, trade = journal_module.parse_claude_response(raw)
    return jsonify({"reply": reply, "trade": trade})


@app.route("/api/journal/review", methods=["POST"])
@login_required
def api_journal_review():
    trades = read_journal_trades()
    try:
        reply = journal_module.call_claude_review(trades)
    except Exception:
        return jsonify({"error": "AI unavailable"}), 503
    return jsonify({"reply": reply})


if __name__ == "__main__":
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(checker.run, "interval", minutes=15, kwargs={"path": _ALARMS_PATH})
    scheduler.add_job(portfolio_analysis.run, "interval", hours=24, id="portfolio_analysis")
    scheduler.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
