import requests
import time
from .auth import get_headers
from .config import BASE_URL, TRADING_URL, REQUEST_TIMEOUT, MARKET_FETCH_LIMIT

def fetch_balance() -> dict:
    path = "/trade-api/v2/portfolio/balance"
    r = requests.get(f"{TRADING_URL}/portfolio/balance", headers=get_headers("GET", path), timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()

def fetch_positions() -> list:
    path = "/trade-api/v2/portfolio/positions"
    r = requests.get(f"{TRADING_URL}/portfolio/positions", headers=get_headers("GET", path), timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json().get("market_positions", [])

def fetch_markets() -> list:
    path = "/trade-api/v2/markets"
    r = requests.get(f"{BASE_URL}/markets", headers=get_headers("GET", path), params={"status": "open", "limit": MARKET_FETCH_LIMIT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json().get("markets", [])

def fetch_candlesticks(series_ticker: str, ticker: str, period_interval: int = 1) -> list:
    end_ts   = int(time.time())
    start_ts = end_ts - (6 * 60 * 60)
    path = f"/trade-api/v2/series/{series_ticker}/markets/{ticker}/candlesticks"
    r = requests.get(
        f"{BASE_URL}/series/{series_ticker}/markets/{ticker}/candlesticks",
        headers=get_headers("GET", path),
        params={"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("candlesticks", [])