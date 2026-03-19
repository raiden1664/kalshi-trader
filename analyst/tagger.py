"""
tagger.py — joins every candle with its exact score state at that moment.

For each market with both candles and score_events, produces a tagged timeline:
  candle_ts | price | set | games | point | server | last_event | price_change

Stored in tagged_candles table. This is the input the AI uses to "watch" each game.
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, get_markets, init_db

BOLD  = "\033[1m"
GREEN = "\033[92m"
DIM   = "\033[2m"
RESET = "\033[0m"


def init_tagger_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tagged_candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            candle_ts INTEGER NOT NULL,
            price REAL,
            price_change REAL,
            set_num INTEGER,
            home_games INTEGER,
            away_games INTEGER,
            home_point TEXT,
            away_point TEXT,
            server TEXT,
            scorer TEXT,
            last_event_type TEXT,
            home_sets INTEGER,
            away_sets INTEGER,
            match_pct REAL,
            UNIQUE(ticker, candle_ts)
        );
        CREATE INDEX IF NOT EXISTS idx_tagged_ticker ON tagged_candles(ticker);
        CREATE INDEX IF NOT EXISTS idx_tagged_event ON tagged_candles(last_event_type);
    """)
    conn.commit()
    conn.close()


def market_is_tagged(ticker: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM tagged_candles WHERE ticker=?", (ticker,)
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def tag_market(ticker: str) -> int:
    """
    Join candles with score events for a single market.
    For each candle, find the most recent score event at or before that candle's timestamp.
    Returns number of tagged candles stored.
    """
    conn = get_conn()

    # Get candles in order
    candles = conn.execute(
        "SELECT * FROM candlesticks WHERE ticker=? ORDER BY end_ts ASC", (ticker,)
    ).fetchall()

    # Get score events in order
    score_events = conn.execute(
        "SELECT * FROM score_events WHERE ticker=? ORDER BY estimated_ts ASC", (ticker,)
    ).fetchall()

    conn.close()

    if not candles or not score_events:
        return 0

    candles = [dict(c) for c in candles]
    score_events = [dict(s) for s in score_events]

    total_candles = len(candles)
    first_ts = candles[0]["end_ts"]
    last_ts  = candles[-1]["end_ts"]
    duration = last_ts - first_ts or 1

    # Current score state — starts at match beginning
    state = {
        "set_num":        1,
        "home_games":     0,
        "away_games":     0,
        "home_point":     "0",
        "away_point":     "0",
        "server":         "",
        "scorer":         "",
        "last_event_type":"pre_match",
        "home_sets":      0,
        "away_sets":      0,
    }

    tagged = []
    prev_price = None
    se_idx = 0  # pointer into score_events

    for i, candle in enumerate(candles):
        ts    = candle["end_ts"]
        price = _get_price(candle)

        # Advance score state — apply all score events that happened at or before this candle
        while se_idx < len(score_events):
            se = score_events[se_idx]
            if se["estimated_ts"] <= ts:
                state = {
                    "set_num":        se["set_num"],
                    "home_games":     se["home_games"],
                    "away_games":     se["away_games"],
                    "home_point":     se["home_point"] or "0",
                    "away_point":     se["away_point"] or "0",
                    "server":         se["server"] or "",
                    "scorer":         se["scorer"] or "",
                    "last_event_type":se["event_type"],
                    "home_sets":      se["home_sets"],
                    "away_sets":      se["away_sets"],
                }
                se_idx += 1
            else:
                break

        price_change = round(price - prev_price, 4) if prev_price is not None and price is not None else 0.0
        match_pct    = round((ts - first_ts) / duration, 4)

        tagged.append((
            ticker,
            ts,
            price,
            price_change,
            state["set_num"],
            state["home_games"],
            state["away_games"],
            state["home_point"],
            state["away_point"],
            state["server"],
            state["scorer"],
            state["last_event_type"],
            state["home_sets"],
            state["away_sets"],
            match_pct,
        ))

        prev_price = price

    # Store in DB
    conn = get_conn()
    conn.executemany("""
        INSERT OR IGNORE INTO tagged_candles
        (ticker, candle_ts, price, price_change, set_num, home_games, away_games,
         home_point, away_point, server, scorer, last_event_type, home_sets, away_sets, match_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, tagged)
    conn.commit()
    conn.close()

    return len(tagged)


def _get_price(candle: dict) -> float:
    """Extract best available price from candle."""
    for field in ["price_close", "price_open", "price_mean"]:
        v = candle.get(field)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    # Fall back to bid/ask mid
    try:
        bid = float(candle.get("yes_bid_close") or 0)
        ask = float(candle.get("yes_ask_close") or 0)
        if bid and ask:
            return (bid + ask) / 2
    except Exception:
        pass
    return None


def tag_all(sport: str = None, limit: int = 10000):
    """Tag all markets that have both candles and score events."""
    init_tagger_db()
    conn = get_conn()

    query = """
        SELECT DISTINCT m.ticker, m.sport
        FROM markets m
        WHERE EXISTS (SELECT 1 FROM candlesticks c WHERE c.ticker = m.ticker)
        AND EXISTS (SELECT 1 FROM score_events se WHERE se.ticker = m.ticker)
    """
    params = []
    if sport:
        query += " AND m.sport = ?"
        params.append(sport)
    query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    total = len(rows)
    print(f"\n{BOLD}Tagging {total} markets...{RESET}")

    tagged_count = skipped = 0
    for row in rows:
        ticker = row["ticker"]
        sp     = row["sport"]

        if market_is_tagged(ticker):
            skipped += 1
            continue

        n = tag_market(ticker)
        if n > 0:
            tagged_count += 1
            if tagged_count % 50 == 0:
                print(f"  {tagged_count}/{total} tagged ({sp})...")

    print(f"\n{BOLD}Done. {tagged_count} markets tagged, {skipped} skipped (cached).{RESET}\n")


def get_tagged_candles(ticker: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tagged_candles WHERE ticker=? ORDER BY candle_ts ASC", (ticker,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tagged_summary(ticker: str) -> dict:
    """Get a compact summary of a match for AI analysis."""
    candles = get_tagged_candles(ticker)
    if not candles:
        return {}

    conn = get_conn()
    market = conn.execute("SELECT * FROM markets WHERE ticker=?", (ticker,)).fetchone()
    score  = conn.execute("SELECT * FROM match_scores WHERE ticker=?", (ticker,)).fetchone()
    conn.close()

    market = dict(market) if market else {}
    score  = dict(score) if score else {}

    # Find key moments — set wins, breaks, big price moves
    key_moments = []
    for c in candles:
        evt = c.get("last_event_type", "")
        chg = c.get("price_change", 0) or 0
        if evt in ("set_win", "game_win") or abs(chg) >= 0.05:
            key_moments.append({
                "ts":         c["candle_ts"],
                "match_pct":  c["match_pct"],
                "price":      c["price"],
                "change":     chg,
                "event":      evt,
                "set":        c["set_num"],
                "home_games": c["home_games"],
                "away_games": c["away_games"],
                "home_point": c["home_point"],
                "away_point": c["away_point"],
                "home_sets":  c["home_sets"],
                "away_sets":  c["away_sets"],
                "scorer":     c["scorer"],
                "server":     c["server"],
            })

    return {
        "ticker":       ticker,
        "sport":        market.get("sport", ""),
        "result":       market.get("result", ""),
        "winner":       score.get("winner", ""),
        "player_home":  score.get("player_home", ""),
        "player_away":  score.get("player_away", ""),
        "set_scores":   f"{score.get('set1_home')}-{score.get('set1_away')}, {score.get('set2_home')}-{score.get('set2_away')}",
        "total_candles":len(candles),
        "start_price":  candles[0]["price"],
        "end_price":    candles[-1]["price"],
        "max_price":    max(c["price"] for c in candles if c["price"]),
        "min_price":    min(c["price"] for c in candles if c["price"]),
        "key_moments":  key_moments,
        "full_timeline": candles,  # every candle with full score state
    }