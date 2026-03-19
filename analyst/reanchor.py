"""
reanchor.py — re-fetch candles using SofaScore match start timestamps for precise alignment.

For each market that has match_scores data, fetches candles using:
  start_ts - 30min  to  start_ts + 5hr

This ensures candles are centered on the actual match, not Kalshi's market open time.
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

from db import get_conn, init_db, upsert_candles

_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_src_path  = os.path.join(_root_path, "src")
sys.path.insert(0, _root_path)

import types as _types
_pkg = _types.ModuleType("src")
_pkg.__path__ = [_src_path]
_pkg.__package__ = "src"
sys.modules.setdefault("src", _pkg)

from src.auth import get_headers as get_auth_headers
import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
session = requests.Session()

BOLD  = "\033[1m"
GREEN = "\033[92m"
DIM   = "\033[2m"
RESET = "\033[0m"


def _get(path: str, params: dict = None):
    url = f"{BASE_URL}{path}"
    headers = get_auth_headers("GET", f"/trade-api/v2{path}")
    r = session.get(url, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_candles_anchored(ticker: str, start_ts: int, period_interval: int = 1) -> list:
    """Fetch candles anchored to actual match start time."""
    parts = ticker.split("-")
    series_ticker = parts[0] if parts else ""

    # Window: 30 min before match start to 5 hours after
    fetch_start = start_ts - 1800
    fetch_end   = start_ts + 18000  # 5 hours

    # Try live endpoint first
    try:
        path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
        data = _get(path, {
            "period_interval": period_interval,
            "start_ts": fetch_start,
            "end_ts": fetch_end,
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
            "start_ts": fetch_start,
            "end_ts": fetch_end,
        })
        return data.get("candlesticks", [])
    except Exception as e:
        return []


def delete_candles(ticker: str):
    conn = get_conn()
    conn.execute("DELETE FROM candlesticks WHERE ticker=?", (ticker,))
    conn.commit()
    conn.close()


def reanchor_all(sport: str = None, min_candles: int = 50, dry_run: bool = False):
    """
    Re-fetch candles for all markets that have match_scores data.
    Uses SofaScore start_ts as the anchor.
    """
    init_db()
    conn = get_conn()

    query = """
        SELECT ms.ticker, ms.start_ts, m.sport
        FROM match_scores ms
        JOIN markets m ON m.ticker = ms.ticker
        WHERE ms.start_ts > 0
    """
    params = []
    if sport:
        query += " AND m.sport = ?"
        params.append(sport)

    query += " ORDER BY ms.start_ts DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    print(f"\n{BOLD}Re-anchoring candles for {len(rows)} markets...{RESET}")
    if dry_run:
        print(f"{DIM}(dry run — no changes){RESET}")

    improved = skipped = failed = 0

    for row in rows:
        ticker   = row["ticker"]
        start_ts = row["start_ts"]
        sp       = row["sport"]

        if not start_ts:
            skipped += 1
            continue

        # Check current candle count
        conn = get_conn()
        current = conn.execute(
            "SELECT COUNT(*) as cnt FROM candlesticks WHERE ticker=?", (ticker,)
        ).fetchone()["cnt"]
        conn.close()

        print(f"  {ticker[:50]} start={start_ts}...", end=" ", flush=True)

        if dry_run:
            print(f"[dry run, currently {current} candles]")
            continue

        candles = fetch_candles_anchored(ticker, start_ts)
        time.sleep(0.1)

        if not candles:
            print(f"no candles returned (kept {current})")
            skipped += 1
            continue

        if len(candles) < min_candles:
            print(f"too few ({len(candles)} < {min_candles}, kept {current})")
            skipped += 1
            continue

        # Replace candles
        delete_candles(ticker)
        upsert_candles(ticker, candles)
        improved += 1
        delta = len(candles) - current
        sign = "+" if delta >= 0 else ""
        print(f"{current}→{len(candles)} candles ({sign}{delta})")

    print(f"\n{BOLD}Done. {improved} re-anchored, {skipped} skipped, {failed} failed.{RESET}\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Re-anchor candles to SofaScore match start times")
    p.add_argument("--sport", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-candles", type=int, default=50)
    args = p.parse_args()
    reanchor_all(sport=args.sport, min_candles=args.min_candles, dry_run=args.dry_run)