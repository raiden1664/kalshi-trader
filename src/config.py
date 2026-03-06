"""
config.py — Central settings for kalshi-trader.
Tweak these to adjust strategy parameters.
"""

import os

# ── Credentials (set as env vars, never hardcode) ─────────────────────────────
KALSHI_EMAIL    = os.getenv("KALSHI_EMAIL", "")
KALSHI_PASSWORD = os.getenv("KALSHI_PASSWORD", "")

# ── Dashboard ──────────────────────────────────────────────────────────────────
REFRESH_SECONDS = 30

# ── Strategy: price ranges (0.0–1.0 scale) ────────────────────────────────────
TYPE1_MIN = 0.80   # Near-locks: 80–90¢
TYPE1_MAX = 0.90
TYPE2_MIN = 0.55   # Value plays: 55–75¢
TYPE2_MAX = 0.75

HARD_PRICE_CEILING = 0.70   # Never buy above this

# ── Markets to track ──────────────────────────────────────────────────────────
SPORT_KEYWORDS = [
    "tennis", "nba", "ncaab", "basketball",
    "atp", "wta", "slam", "open",
]

# ── API ────────────────────────────────────────────────────────────────────────
BASE_URL       = "https://trading-api.kalshi.com/trade-api/v2"
REQUEST_TIMEOUT = 10
MARKET_FETCH_LIMIT = 200
