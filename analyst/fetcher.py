import sys
import os
import time
import requests

_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_path  = os.path.join(_root_path, "src")
sys.path.insert(0, _root_path)

import types as _types
_pkg = _types.ModuleType("src")
_pkg.__path__ = [_src_path]
_pkg.__package__ = "src"
sys.modules.setdefault("src", _pkg)

from src.auth import get_headers as get_auth_headers

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

SPORT_SERIES = {
    # Tennis
    "tennis_atp":   "KXATPMATCH",
    "tennis_wta":   "KXWTAMATCH",
    # Basketball (no NBA)
    "ncaab_men":    "KXNCAAMBGAME",
    "ncaab_women":  "KXNCAAWBGAME",
    "ncaab_bigeast":"KXNCAAMBIGEAST",
    "ncaab_bigten": "KXNCAAMBIGTEN",
    "nbl":          "KXNBLGAME",
    "cba":          "KXCBAGAME",
    "kbl":          "KXKBLGAME",
    "aba":          "KXABAGAME",
    "acb":          "KXACBGAME",
    "bbl":          "KXBBLGAME",
    "vtb":          "KXVTBGAME",
    "fiba":         "KXFIBAGAME",
    # Hockey (no NHL)
    "ahl":          "KXAHLGAME",
    "shl":          "KXSHLGAME",
    "liiga":        "KXLIIGAGAME",
    # Baseball
    "mlb":          "KXMLBGAME",
}

# Minimum candles threshold — skip markets with fewer than this
MIN_CANDLES = 50

session = requests.Session()


def _get(path: str, params: dict = None):
    url = f"{BASE_URL}{path}"
    headers = get_auth_headers("GET", f"/trade-api/v2{path}")
    r = session.get(url, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _ts(val):
    if not val:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    try:
        from datetime import datetime, timezone
        return int(datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0


def fetch_settled_markets(series_ticker: str, sport: str, limit: int = 1000) -> list:
    """Fetch as many settled markets as possible for a series, paging backwards."""
    markets = []
    seen = set()
    cursor = None
    attempts = 0
    max_attempts = 50

    while len(markets) < limit and attempts < max_attempts:
        params = {
            "series_ticker": series_ticker,
            "status": "settled",
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            data = _get("/markets", params)
        except Exception as e:
            print(f"  [warn] Fetch failed: {e}")
            break

        batch = data.get("markets", [])
        if not batch:
            break

        added = 0
        for m in batch:
            t = m.get("ticker", "")
            if t.startswith(series_ticker + "-") and t not in seen:
                seen.add(t)
                markets.append(_normalize_market(m, sport))
                added += 1
                if len(markets) >= limit:
                    break

        cursor = data.get("cursor")
        attempts += 1

        if added > 0:
            print(f"    Page {attempts}: +{added} (total: {len(markets)})", flush=True)

        if not cursor or not batch:
            break

        time.sleep(0.15)

    return markets


def _normalize_market(m: dict, sport: str) -> dict:
    return {
        "ticker":      m.get("ticker", ""),
        "title":       m.get("title", "") or m.get("subtitle", ""),
        "sport":       sport,
        "status":      m.get("status", ""),
        "result":      m.get("result", "") or m.get("market_result", ""),
        "open_time":   _ts(m.get("open_time") or m.get("open_date")),
        "close_time":  _ts(m.get("close_time") or m.get("close_date")),
        "settle_time": _ts(m.get("expiration_time") or m.get("close_time")),
        "fetched_at":  int(time.time()),
    }


def fetch_candlesticks(ticker: str, open_time: int, close_time: int, period_interval: int = 1) -> list:
    parts = ticker.split("-")
    series_ticker = parts[0] if parts else ""

    start_ts = max(0, open_time - 1800) if open_time else None
    end_ts   = (close_time + 7200) if close_time else None

    if not start_ts or not end_ts:
        return []

    # Try live endpoint first
    try:
        path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
        data = _get(path, {
            "period_interval": period_interval,
            "start_ts": start_ts,
            "end_ts": end_ts,
        })
        candles = data.get("candlesticks", [])
        if candles:
            return candles
    except Exception:
        pass

    # Fall back to historical
    try:
        path = f"/historical/markets/{ticker}/candlesticks"
        data = _get(path, {
            "period_interval": period_interval,
            "start_ts": start_ts,
            "end_ts": end_ts,
        })
        return data.get("candlesticks", [])
    except Exception as e:
        print(f"  [warn] Candlestick fetch failed for {ticker}: {e}")
        return []


def fetch_all_sports(sports: list = None, limit_per_sport: int = 1000) -> dict:
    """Fetch all sports or a subset. Returns {sport: [markets]}."""
    to_fetch = {k: v for k, v in SPORT_SERIES.items() if not sports or k in sports}
    result = {}
    for sport, series in to_fetch.items():
        print(f"\nFetching {sport} ({series})...")
        markets = fetch_settled_markets(series, sport, limit=limit_per_sport)
        result[sport] = markets
        print(f"  → {len(markets)} total markets for {sport}")
        time.sleep(0.3)
    return result