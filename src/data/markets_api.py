"""
markets_api.py — Fetches and normalizes raw market data from the Kalshi API.

Single responsibility: HTTP fetching and price normalization.
Caching is delegated to cache.py. Filtering/parsing is in market_filter.py
and market_parser.py.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.auth import get_headers
from src.config import BASE_URL, REQUEST_TIMEOUT
from src.data import cache

# Shared session with connection pooling — reused across all requests
_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20,
    max_retries=1,
))


def _normalize(m: dict) -> dict:
    """
    Kalshi returns prices as dollar strings (e.g. "0.41") in some endpoints.
    Normalize everything to integer cents so downstream code is consistent.
    """
    def to_cents(val) -> int:
        try:
            return round(float(val) * 100)
        except (TypeError, ValueError):
            return 0

    if m.get("yes_ask") is None:
        m["yes_ask"] = to_cents(m.get("yes_ask_dollars"))
    if m.get("no_ask") is None:
        m["no_ask"] = to_cents(m.get("no_ask_dollars"))
    if m.get("yes_bid") is None:
        m["yes_bid"] = to_cents(m.get("yes_bid_dollars"))
    if m.get("no_bid") is None:
        m["no_bid"] = to_cents(m.get("no_bid_dollars"))
    if m.get("last_price") is None:
        m["last_price"] = to_cents(m.get("last_price_dollars"))
    if m.get("volume") is None:
        try:
            m["volume"] = int(float(m["volume_fp"])) if m.get("volume_fp") else 0
        except (TypeError, ValueError):
            m["volume"] = 0
    return m


def fetch_series(series_ticker: str, stale_ok: bool = False) -> list:
    """
    Fetch all open markets for one series ticker.
    Returns disk-cached data immediately if stale_ok=True (used for fast
    initial render before the network response arrives).
    Always writes fresh data back to the cache.
    """
    cached = cache.get(series_ticker, stale_ok=stale_ok)
    if cached is not None:
        return cached

    path = "/trade-api/v2/markets"
    r = _session.get(
        f"{BASE_URL}/markets",
        headers=get_headers("GET", path),
        params={"status": "open", "limit": 100, "series_ticker": series_ticker},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    markets = [_normalize(m) for m in r.json().get("markets", [])]
    cache.set(series_ticker, markets)
    return markets


def fetch_series_concurrent(series_list: list) -> list:
    """
    Fetch multiple series in parallel. Wall time = slowest single request.
    Used by data_manager to load all series for a sport at once.
    """
    if not series_list:
        return []
    if len(series_list) == 1:
        try:
            return fetch_series(series_list[0])
        except Exception:
            return []

    all_markets = []
    with ThreadPoolExecutor(max_workers=len(series_list)) as ex:
        futures = {ex.submit(fetch_series, s): s for s in series_list}
        for f in as_completed(futures):
            try:
                all_markets.extend(f.result())
            except Exception:
                pass
    return all_markets


def warmup_cache():
    """
    Background refresh of all previously-cached series.
    Called on import so data is fresh by the time the user opens markets.
    """
    import threading
    def _warm():
        for ticker in cache.cached_tickers():
            try:
                fetch_series(ticker)
            except Exception:
                pass
    threading.Thread(target=_warm, daemon=True).start()


# Fire warmup the moment this module is imported
warmup_cache()