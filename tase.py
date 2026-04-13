import json
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
    """Case-insensitive substring search on name and ticker. Returns top 10 matches."""
    q = query.lower()
    results = []
    for item in cache:
        name_match = q in item["name"].lower()
        ticker_match = item["ticker"] is not None and q in item["ticker"].lower()
        if name_match or ticker_match:
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
