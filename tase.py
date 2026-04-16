import json
import urllib.parse
import urllib.request
import urllib.error

_BASE_HEADERS = {
    "User-Agent": "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; FSL 7.0.6.01001)",
    "Referer": "https://www.tase.co.il/",
    "Cache-Control": "no-cache",
}

_MAYA_HEADERS = {
    **_BASE_HEADERS,
    "X-Maya-With": "allow",
    "Accept-Language": "en-US",
}


def load_securities_cache() -> list[dict]:
    """Fetch all TASE securities. Filters to stocks/ETFs (type 1) and mutual funds (type 4).
    Returns [] on any failure — app starts normally without Israeli search."""
    url = "https://api.tase.co.il/api/content/searchentities?lang=1"
    req = urllib.request.Request(url, headers=_BASE_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[WARN] TASE securities cache load failed: {e}")
        return []

    results = []
    for item in data:
        t = item.get("Type")
        if t not in (1, 4):
            continue
        item_id = item.get("Id")
        if item_id is None:
            continue
        results.append({
            "id": str(item_id),
            "name": item.get("Name") or "",
            "ticker": item.get("Smb"),
            "type": "fund" if t == 4 else "security",
        })
    return results


def search(query: str, cache: list[dict]) -> list[dict]:
    """Case-insensitive substring search on name, ticker, and (if all-digit) numeric ID.
    Returns top 10 matches."""
    q = query.lower()
    results = []
    for item in cache:
        name_match = q in item["name"].lower()
        ticker_match = item["ticker"] is not None and q in item["ticker"].lower()
        id_match = query.isdigit() and query in item["id"]
        if name_match or ticker_match or id_match:
            results.append(item)
            if len(results) == 10:
                break
    return results


def get_price(tase_id: str, tase_type: str) -> float:
    """Fetch current price from TASE API.
    Raises ValueError if price is unavailable or request fails."""
    if tase_type == "fund":
        url = f"https://mayaapi.tase.co.il/api/fund/details?fundId={tase_id}"
        req = urllib.request.Request(url, headers=_MAYA_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ValueError(f"Could not fetch fund price for {tase_id}: {e}") from e
        price = data.get("UnitValuePrice")
    else:
        url = f"https://api.tase.co.il/api/company/securitydata?securityId={tase_id}&lang=1"
        req = urllib.request.Request(url, headers=_BASE_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ValueError(f"Could not fetch security price for {tase_id}: {e}") from e
        price = data.get("LastRate")

    if price is None:
        raise ValueError(f"Price not available for TASE id {tase_id}")
    return float(price)


def get_history(tase_id: str, tase_type: str, period: str) -> list[dict]:
    """Fetch historical daily closing prices from TASE API.
    Returns list of {"date": "YYYY-MM-DD", "price": float}, oldest first.
    Raises ValueError on failure."""
    from datetime import date, timedelta
    today = date.today()
    days_back = {"5d": 10, "1mo": 35, "1y": 370}
    date_from = today - timedelta(days=days_back.get(period, 35))

    if tase_type == "fund":
        return _get_fund_history(tase_id, date_from, today)
    return _get_security_history(tase_id, date_from, today)


def _get_security_history(tase_id: str, date_from, date_to) -> list[dict]:
    url = "https://api.tase.co.il/api/security/historyeod"
    results = []
    page = 1
    while True:
        body = json.dumps({
            "dFrom": date_from.strftime("%Y-%m-%d"),
            "dTo": date_to.strftime("%Y-%m-%d"),
            "oId": tase_id,
            "pageNum": page,
            "pType": "8",
            "TotalRec": 1,
            "lang": "1",
        }).encode()
        req = urllib.request.Request(url, data=body, headers={
            **_BASE_HEADERS,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ValueError(f"Could not fetch security history for {tase_id}: {e}") from e
        items = data.get("Items", [])
        if not items:
            break
        for item in items:
            day, month, year = item["TradeDate"].split("/")
            results.append({"date": f"{year}-{month}-{day}", "price": float(item["CloseRate"])})
        if len(items) < 30:
            break
        page += 1
    results.reverse()
    return results


def _get_fund_history(tase_id: str, date_from, date_to) -> list[dict]:
    url = "https://mayaapi.tase.co.il/api/fund/history"
    results = []
    page = 1
    while True:
        body = urllib.parse.urlencode({
            "DateFrom": date_from.strftime("%Y-%m-%d"),
            "DateTo": date_to.strftime("%Y-%m-%d"),
            "FundId": tase_id,
            "Page": page,
            "Period": "0",
        }).encode()
        req = urllib.request.Request(url, data=body, headers={
            **_MAYA_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise ValueError(f"Could not fetch fund history for {tase_id}: {e}") from e
        items = data.get("Table", [])
        if not items:
            break
        for item in items:
            results.append({"date": item["TradeDate"][:10], "price": float(item["SellPrice"])})
        if len(items) < 30:
            break
        page += 1
    results.reverse()
    return results
