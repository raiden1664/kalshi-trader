"""
api.py — Kalshi API calls.
"""

import requests
from .auth import get_headers
from .config import BASE_URL, REQUEST_TIMEOUT, MARKET_FETCH_LIMIT


def fetch_balance(token: str) -> dict:
    resp = requests.get(
        f"{BASE_URL}/portfolio/balance",
        headers=get_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_positions(token: str) -> list:
    resp = requests.get(
        f"{BASE_URL}/portfolio/positions",
        headers=get_headers(token),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("market_positions", [])


def fetch_markets(token: str) -> list:
    resp = requests.get(
        f"{BASE_URL}/markets",
        headers=get_headers(token),
        params={"status": "open", "limit": MARKET_FETCH_LIMIT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("markets", [])
