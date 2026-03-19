import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "analyst.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS markets (
            ticker TEXT PRIMARY KEY,
            title TEXT,
            sport TEXT,
            status TEXT,
            result TEXT,
            open_time INTEGER,
            close_time INTEGER,
            settle_time INTEGER,
            fetched_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS candlesticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            end_ts INTEGER NOT NULL,
            yes_bid_open TEXT,
            yes_bid_close TEXT,
            yes_ask_open TEXT,
            yes_ask_close TEXT,
            price_open TEXT,
            price_close TEXT,
            price_high TEXT,
            price_low TEXT,
            price_mean TEXT,
            volume TEXT,
            open_interest TEXT,
            UNIQUE(ticker, end_ts)
        );

        CREATE TABLE IF NOT EXISTS ai_verdicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            end_ts INTEGER NOT NULL,
            verdict TEXT,
            reasoning TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE(ticker, end_ts)
        );

        CREATE TABLE IF NOT EXISTS ai_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT,
            analysis TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE INDEX IF NOT EXISTS idx_candles_ticker ON candlesticks(ticker);
        CREATE INDEX IF NOT EXISTS idx_verdicts_ticker ON ai_verdicts(ticker);
    """)
    conn.commit()
    conn.close()


def _p(obj, *keys):
    """Extract first non-None value from a dict using multiple possible key names."""
    for k in keys:
        v = obj.get(k)
        if v is not None:
            return str(v)
    return None


def upsert_market(m: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO markets (ticker, title, sport, status, result, open_time, close_time, settle_time, fetched_at)
        VALUES (:ticker, :title, :sport, :status, :result, :open_time, :close_time, :settle_time, :fetched_at)
        ON CONFLICT(ticker) DO UPDATE SET
            title=excluded.title, status=excluded.status, result=excluded.result,
            settle_time=excluded.settle_time, fetched_at=excluded.fetched_at
    """, m)
    conn.commit()
    conn.close()


def upsert_candles(ticker: str, candles: list):
    conn = get_conn()
    rows = []
    for c in candles:
        bid  = c.get("yes_bid", {}) or {}
        ask  = c.get("yes_ask", {}) or {}
        pr   = c.get("price", {}) or {}

        # Compute mid-price from bid/ask as fallback when price fields are null
        def mid(b, a):
            try:
                bv = float(_p(bid, b) or 0)
                av = float(_p(ask, a) or 0)
                if bv and av:
                    return f"{(bv + av) / 2:.4f}"
                return _p(bid, b) or _p(ask, a)
            except Exception:
                return None

        price_open  = _p(pr, "open_dollars", "open") or mid("open_dollars", "open_dollars")
        price_close = _p(pr, "close_dollars", "close") or mid("close_dollars", "close_dollars")
        price_high  = _p(pr, "high_dollars", "high")
        price_low   = _p(pr, "low_dollars", "low")
        price_mean  = _p(pr, "mean_dollars", "mean")

        rows.append((
            ticker,
            c.get("end_period_ts"),
            _p(bid, "open_dollars", "open"),
            _p(bid, "close_dollars", "close"),
            _p(ask, "open_dollars", "open"),
            _p(ask, "close_dollars", "close"),
            price_open,
            price_close,
            price_high,
            price_low,
            price_mean,
            _p(c, "volume_fp", "volume"),
            _p(c, "open_interest_fp", "open_interest"),
        ))

    conn.executemany("""
        INSERT OR IGNORE INTO candlesticks
        (ticker, end_ts, yes_bid_open, yes_bid_close, yes_ask_open, yes_ask_close,
         price_open, price_close, price_high, price_low, price_mean, volume, open_interest)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    conn.close()


def save_verdict(ticker: str, end_ts: int, verdict: str, reasoning: str):
    conn = get_conn()
    conn.execute("""
        INSERT INTO ai_verdicts (ticker, end_ts, verdict, reasoning)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ticker, end_ts) DO UPDATE SET verdict=excluded.verdict, reasoning=excluded.reasoning
    """, (ticker, end_ts, verdict, reasoning))
    conn.commit()
    conn.close()


def save_pattern(sport: str, analysis: str):
    conn = get_conn()
    conn.execute("INSERT INTO ai_patterns (sport, analysis) VALUES (?, ?)", (sport, analysis))
    conn.commit()
    conn.close()


def get_markets(sport=None, limit=50):
    conn = get_conn()
    if sport:
        rows = conn.execute(
            "SELECT * FROM markets WHERE sport=? ORDER BY settle_time DESC LIMIT ?",
            (sport, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM markets ORDER BY settle_time DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return rows


def get_candles(ticker: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM candlesticks WHERE ticker=? ORDER BY end_ts ASC", (ticker,)
    ).fetchall()
    conn.close()
    return rows


def get_verdicts(ticker: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ai_verdicts WHERE ticker=? ORDER BY end_ts ASC", (ticker,)
    ).fetchall()
    conn.close()
    return rows


def get_latest_patterns(sport=None, limit=5):
    conn = get_conn()
    if sport:
        rows = conn.execute(
            "SELECT * FROM ai_patterns WHERE sport=? ORDER BY created_at DESC LIMIT ?",
            (sport, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ai_patterns ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return rows


def market_has_candles(ticker: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM candlesticks WHERE ticker=?", (ticker,)
    ).fetchone()
    conn.close()
    return row["cnt"] > 0