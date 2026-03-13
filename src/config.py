import os
from pathlib import Path

# Auto-load .env from project root
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

KALSHI_KEY_ID   = os.getenv("KALSHI_KEY_ID", "")
KALSHI_KEY_PATH = os.path.expanduser(os.getenv("KALSHI_KEY_PATH", "~/.kalshi/kalshi.key"))

REFRESH_SECONDS = 30

TYPE1_MIN = 0.80
TYPE1_MAX = 0.90
TYPE2_MIN = 0.55
TYPE2_MAX = 0.75

HARD_PRICE_CEILING = 0.70

SPORT_KEYWORDS = ["tennis", "nba", "ncaab", "basketball", "atp", "wta", "slam", "open"]

BASE_URL          = "https://api.elections.kalshi.com/trade-api/v2"
TRADING_URL       = BASE_URL  # trading-api.kalshi.com is deprecated
REQUEST_TIMEOUT   = 5         # was 10 — cuts worst-case wait in half
MARKET_FETCH_LIMIT = 100      # 200 is overkill for most series