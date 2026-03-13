"""
cache.py — Disk-backed in-memory cache for Kalshi market data.

Markets are cached per series ticker. On app start the disk cache is loaded
into memory instantly, so the first M press feels instant after the first run.
"""
import json
import pathlib
import threading
from datetime import datetime, timezone

_CACHE_TTL_SECONDS = 90
_CACHE_PATH        = pathlib.Path.home() / ".kalshi_trader" / "market_cache.json"
_cache: dict[str, tuple[list, datetime]] = {}
_lock  = threading.Lock()


def load_from_disk():
    """Populate in-memory cache from last session's disk file."""
    try:
        if _CACHE_PATH.exists():
            raw = json.loads(_CACHE_PATH.read_text())
            with _lock:
                for ticker, (markets, ts_str) in raw.items():
                    _cache[ticker] = (markets, datetime.fromisoformat(ts_str))
    except Exception:
        pass


def save_to_disk():
    """Persist in-memory cache to disk after every fresh fetch."""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            raw = {
                ticker: (markets, fetched_at.isoformat())
                for ticker, (markets, fetched_at) in _cache.items()
            }
        _CACHE_PATH.write_text(json.dumps(raw))
    except Exception:
        pass


def get(series_ticker: str, stale_ok: bool = False) -> list | None:
    """
    Return cached markets for a series if available.
    - Fresh cache (< TTL): always returned.
    - Stale cache: returned only if stale_ok=True.
    - Returns None if no cache entry exists.
    """
    with _lock:
        entry = _cache.get(series_ticker)
    if entry is None:
        return None
    markets, fetched_at = entry
    age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    if age < _CACHE_TTL_SECONDS or stale_ok:
        return markets
    return None


def set(series_ticker: str, markets: list):
    """Store fresh market data and persist to disk."""
    with _lock:
        _cache[series_ticker] = (markets, datetime.now(timezone.utc))
    save_to_disk()


def cached_tickers() -> list:
    """All series tickers currently in memory."""
    with _lock:
        return list(_cache.keys())


# Load disk cache the moment this module is imported
load_from_disk()