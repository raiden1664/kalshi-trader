import requests
import time
from src.auth import get_headers
from src.config import BASE_URL

REQUEST_TIMEOUT = 10


def fetch_balance() -> dict:
    path = "/trade-api/v2/portfolio/balance"
    r = requests.get(f"{BASE_URL}/portfolio/balance",
                     headers=get_headers("GET", path),
                     timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}


def fetch_positions() -> list:
    path = "/trade-api/v2/portfolio/positions"
    r = requests.get(f"{BASE_URL}/portfolio/positions",
                     headers=get_headers("GET", path),
                     params={"count_filter": "position"},   # only non-zero positions
                     timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("market_positions", []) if isinstance(data, dict) else []


def fetch_market(ticker: str) -> dict:
    """Fetch a single market by ticker — used to get current price for P&L."""
    path = f"/trade-api/v2/markets/{ticker}"
    r = requests.get(f"{BASE_URL}/markets/{ticker}",
                     headers=get_headers("GET", path),
                     timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("market", {}) if isinstance(data, dict) else {}


def fetch_markets(series_ticker: str = None, status: str = "open") -> list:
    path = "/trade-api/v2/markets"
    params = {"status": status, "limit": 200}
    if series_ticker:
        params["series_ticker"] = series_ticker
    r = requests.get(f"{BASE_URL}/markets",
                     headers=get_headers("GET", path),
                     params=params,
                     timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("markets", []) if isinstance(data, dict) else []


def fetch_candlesticks(series_ticker: str, ticker: str, period_interval: int = 1) -> list:
    end_ts   = int(time.time())
    start_ts = end_ts - (6 * 60 * 60)
    path     = f"/trade-api/v2/series/{series_ticker}/markets/{ticker}/candlesticks"
    r = requests.get(
        f"{BASE_URL}/series/{series_ticker}/markets/{ticker}/candlesticks",
        headers=get_headers("GET", path),
        params={"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_interval},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("candlesticks", []) if isinstance(data, dict) else []


def fetch_trades(ticker: str, limit: int = 50) -> list:
    path   = "/trade-api/v2/markets/trades"
    params = {"ticker": ticker, "limit": limit}
    r = requests.get(f"{BASE_URL}/markets/trades",
                     headers=get_headers("GET", path),
                     params=params,
                     timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("trades", []) if isinstance(data, dict) else []


def place_order(ticker: str, side: str, action: str, dollars: float = None,
                yes_price: int = None, no_price: int = None, count: int = None) -> dict:
    """
    Place a limit order.
    - side: "yes" or "no"
    - action: "buy" or "sell"
    - dollars: budget — derives count = floor(dollars / price_per_contract)
    - yes_price: limit price in cents for YES side (1-99)
    - no_price: limit price in cents for NO side (1-99)
    - count: number of contracts (required for sells, derived for buys)
    """
    import uuid, math
    path = "/trade-api/v2/portfolio/orders"

    # Determine price in cents for this side
    price_cents = yes_price if side == "yes" else no_price

    # Derive count from dollar budget if not given
    if dollars is not None and price_cents is not None and count is None:
        count = max(1, math.floor(dollars / (price_cents / 100)))

    body = {
        "ticker":          ticker,
        "side":            side,
        "action":          action,
        "client_order_id": str(uuid.uuid4()),
        "count":           count,
    }
    # Kalshi requires yes_price for YES orders, no_price for NO orders
    if side == "yes" and yes_price is not None:
        body["yes_price"] = yes_price
    elif side == "no" and no_price is not None:
        body["no_price"] = no_price
    # Buys: fill immediately or cancel — never leave resting orders
    if action == "buy":
        body["time_in_force"] = "fill_or_kill"


    r = requests.post(
        f"{BASE_URL}/portfolio/orders",
        headers={**get_headers("POST", path), "Content-Type": "application/json"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if not r.ok:
        try:
            msg = r.json().get("error", r.text)
        except Exception:
            msg = r.text
        raise Exception(f"{r.status_code}: {msg}")
    return r.json().get("order", {})


def cancel_order(order_id: str) -> dict:
    path = f"/trade-api/v2/portfolio/orders/{order_id}"
    r = requests.delete(
        f"{BASE_URL}/portfolio/orders/{order_id}",
        headers=get_headers("DELETE", path),
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("order", {})


def fetch_open_orders(ticker: str = None) -> list:
    path = "/trade-api/v2/portfolio/orders"
    params = {"status": "resting"}
    if ticker:
        params["ticker"] = ticker
    r = requests.get(
        f"{BASE_URL}/portfolio/orders",
        headers=get_headers("GET", path),
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("orders", [])