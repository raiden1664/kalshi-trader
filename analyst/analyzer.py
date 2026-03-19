"""
analyzer.py — AI-powered pattern analysis across all tagged matches.
"""

import sys, os, json, time
import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, get_markets, init_db
from tagger import get_tagged_candles, init_tagger_db

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

BOLD  = "\033[1m"
GREEN = "\033[92m"
DIM   = "\033[2m"
RESET = "\033[0m"

SYSTEM_PROMPT = """You are an expert quantitative analyst for Kalshi prediction markets. You watch real match data — price movement combined with live score context — to identify actionable trading patterns.

## Your Task
You will receive batches of matches. Each match contains:
- Sport, players/teams, final result, set/period scores
- A complete price timeline: key moments only (score events + big price moves), each showing:
  - % through match | price in cents | price change | set | games | point score | server | event type

## Critical Context
- Price = market probability for YES side winning (50¢ = 50% chance)
- Price moves AFTER score events — the action causes the spike
- Look for what happened JUST BEFORE each spike
- Break of serve > hold of serve in terms of price impact
- Set wins cause bigger moves than mid-set games
- Tiebreaks cause extreme volatility
- "H" = home player serving/scoring, "A" = away player

## What to Identify

### 1. Price Curve Shapes
Name each pattern, describe the shape, and what score context creates it.
Look for: Steady Climber, False Dawn, Rollercoaster, Rocket, Late Surge, Cliff Drop, and others.

### 2. Entry Timing
- Optimal price level and match state to BUY
- How many minutes after a score event does price peak?
- What confirms momentum is real vs fake?

### 3. Exit/Cashout Signals
- When to SELL or take profit
- What score event ends a move?

### 4. False Signal Traps
- What looks like a good entry but reverses?

### 5. Opening Price Edges
- What does opening price predict about match dynamics?

## Output Format — JSON only, no other text:
{
  "patterns": [
    {
      "name": "Pattern Name",
      "description": "What the price curve looks like",
      "score_context": "What score situation creates this",
      "frequency": "common/occasional/rare",
      "entry_signal": "When/where to buy",
      "entry_price_range": "e.g. 55-65c",
      "exit_signal": "When/where to sell",
      "false_signal_warning": "What to avoid",
      "example_tickers": ["TICKER1", "TICKER2"],
      "sport": "tennis/basketball/hockey/all"
    }
  ],
  "entry_timing": {
    "after_set_win_minutes": "typical minutes until price peaks after set win",
    "break_of_serve_move": "typical price move on break of serve",
    "tiebreak_volatility": "description of tiebreak price behavior"
  },
  "opening_price_insights": {
    "heavy_favorite": "under 25c — typical pattern",
    "moderate_favorite": "25-40c — typical pattern",
    "coin_flip": "40-55c — typical pattern"
  },
  "key_findings": ["finding 1", "finding 2", "finding 3", "finding 4", "finding 5"]
}"""


def serialize_match(ticker: str, candles: list, market: dict, score: dict) -> str:
    """Convert a match to a compact string for AI consumption."""
    if not candles:
        return None

    home = score.get("player_home", "Home") or "Home"
    away = score.get("player_away", "Away") or "Away"
    winner = score.get("winner", "?")
    result = market.get("result", "?")
    sport = market.get("sport", "?")

    set1 = f"{score.get('set1_home')}-{score.get('set1_away')}"
    set2 = f"{score.get('set2_home')}-{score.get('set2_away')}"
    set3_h = score.get("set3_home")
    sets = f"{set1}, {set2}" + (f", {set3_h}-{score.get('set3_away')}" if set3_h is not None else "")

    lines = [
        f"MATCH: {ticker}",
        f"Sport: {sport} | {home} vs {away}",
        f"Result: {winner} wins | Scores: {sets} | Market YES={result}",
        f"Timeline (pct|price|chg|set|games|point|srv|event):",
    ]

    for c in candles:
        price = c.get("price")
        if price is None:
            continue

        pct  = int((c.get("match_pct") or 0) * 100)
        p    = int(price * 100)
        chg  = c.get("price_change") or 0
        chgs = f"{'+' if chg >= 0 else ''}{int(chg*100)}"
        sn   = c.get("set_num") or 0
        hg   = c.get("home_games") or 0
        ag   = c.get("away_games") or 0
        hp   = c.get("home_point") or "0"
        ap   = c.get("away_point") or "0"
        srv  = "H" if c.get("server") == "home" else "A" if c.get("server") == "away" else "-"
        evt  = c.get("last_event_type") or "point"

        is_key = (
            evt in ("set_win", "game_win") or
            abs(chg) >= 0.04 or
            pct == 0 or pct >= 99
        )

        if is_key:
            lines.append(f"{pct:3d}%|{p:3d}c|{chgs:>4}|S{sn}|{hg}-{ag}|{hp}-{ap}|{srv}|{evt}")

    return "\n".join(lines)


def init_analyzer_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analysis_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            sport TEXT,
            pattern_name TEXT,
            description TEXT,
            score_context TEXT,
            frequency TEXT,
            entry_signal TEXT,
            entry_price_range TEXT,
            exit_signal TEXT,
            false_signal_warning TEXT,
            example_tickers TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            sport TEXT,
            finding TEXT,
            category TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS analysis_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT,
            tickers TEXT,
            raw_response TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
    """)
    conn.commit()
    conn.close()


def save_batch_results(batch_id: int, sport: str, result: dict):
    conn = get_conn()
    for p in result.get("patterns", []):
        conn.execute("""
            INSERT INTO analysis_patterns
            (batch_id, sport, pattern_name, description, score_context, frequency,
             entry_signal, entry_price_range, exit_signal, false_signal_warning, example_tickers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            batch_id, sport,
            p.get("name", ""), p.get("description", ""), p.get("score_context", ""),
            p.get("frequency", ""), p.get("entry_signal", ""), p.get("entry_price_range", ""),
            p.get("exit_signal", ""), p.get("false_signal_warning", ""),
            json.dumps(p.get("example_tickers", [])),
        ))
    for finding in result.get("key_findings", []):
        conn.execute(
            "INSERT INTO analysis_findings (batch_id, sport, finding, category) VALUES (?, ?, ?, ?)",
            (batch_id, sport, finding, "key_finding")
        )
    timing = result.get("entry_timing", {})
    for k, v in timing.items():
        conn.execute(
            "INSERT INTO analysis_findings (batch_id, sport, finding, category) VALUES (?, ?, ?, ?)",
            (batch_id, sport, f"{k}: {v}", "entry_timing")
        )
    opening = result.get("opening_price_insights", {})
    for k, v in opening.items():
        conn.execute(
            "INSERT INTO analysis_findings (batch_id, sport, finding, category) VALUES (?, ?, ?, ?)",
            (batch_id, sport, f"{k}: {v}", "opening_price")
        )
    conn.commit()
    conn.close()


def analyze_sport(sport: str, batch_size: int = 5, max_batches: int = 50):
    init_analyzer_db()

    if not ANTHROPIC_API_KEY:
        print("No ANTHROPIC_API_KEY set.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT m.ticker
        FROM markets m
        JOIN match_scores ms ON ms.ticker = m.ticker
        WHERE m.sport = ?
        AND EXISTS (SELECT 1 FROM tagged_candles tc WHERE tc.ticker = m.ticker)
        ORDER BY m.settle_time DESC
    """, (sport,)).fetchall()
    conn.close()

    tickers = [r["ticker"] for r in rows]
    print(f"\n{BOLD}Analyzing {len(tickers)} {sport} matches in batches of {batch_size}...{RESET}")

    batches_run = 0
    for batch_start in range(0, min(len(tickers), max_batches * batch_size), batch_size):
        batch_tickers = tickers[batch_start:batch_start + batch_size]
        batches_run += 1

        print(f"\n  Batch {batches_run}/{min(max_batches, (len(tickers)-1)//batch_size + 1)}: {len(batch_tickers)} matches...", flush=True)

        match_texts = []
        for ticker in batch_tickers:
            candles = get_tagged_candles(ticker)
            if not candles:
                continue
            conn = get_conn()
            market = dict(conn.execute("SELECT * FROM markets WHERE ticker=?", (ticker,)).fetchone() or {})
            score  = dict(conn.execute("SELECT * FROM match_scores WHERE ticker=?", (ticker,)).fetchone() or {})
            conn.close()
            text = serialize_match(ticker, candles, market, score)
            if text:
                match_texts.append(text)

        if not match_texts:
            continue

        prompt = (
            f"Here are {len(match_texts)} {sport.replace('_', ' ')} matches from Kalshi.\n\n"
            + "\n\n---\n\n".join(match_texts)
            + "\n\nAnalyze and respond with the JSON pattern report only."
        )

        # Retry loop for rate limits
        success = False
        for attempt in range(5):
            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4000,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = response.content[0].text.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                raw = raw.strip()
                result = json.loads(raw)
                result["batch_tickers"] = batch_tickers

                conn = get_conn()
                cursor = conn.execute(
                    "INSERT INTO analysis_batches (sport, tickers, raw_response) VALUES (?, ?, ?)",
                    (sport, json.dumps(batch_tickers), raw)
                )
                batch_id = cursor.lastrowid
                conn.commit()
                conn.close()

                save_batch_results(batch_id, sport, result)
                patterns = result.get("patterns", [])
                findings = result.get("key_findings", [])
                print(f"    → {len(patterns)} patterns, {len(findings)} findings")
                success = True
                break

            except anthropic.RateLimitError:
                wait = 30 * (attempt + 1)
                print(f"    [rate limit] waiting {wait}s...", flush=True)
                time.sleep(wait)
            except json.JSONDecodeError as e:
                print(f"    [warn] JSON parse failed: {e}")
                break
            except Exception as e:
                print(f"    [error] {e}")
                break

        time.sleep(3)

    print(f"\n{BOLD}Done. {batches_run} batches for {sport}.{RESET}\n")


def consolidate_patterns(sport: str = None):
    init_analyzer_db()

    if not ANTHROPIC_API_KEY:
        print("No ANTHROPIC_API_KEY set.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    conn = get_conn()
    q = "SELECT * FROM analysis_patterns" + (" WHERE sport=?" if sport else "")
    patterns = conn.execute(q, [sport] if sport else []).fetchall()
    fq = "SELECT * FROM analysis_findings" + (" WHERE sport=?" if sport else "")
    findings = conn.execute(fq, [sport] if sport else []).fetchall()
    conn.close()

    if not patterns:
        print("No patterns found. Run analyze first.")
        return

    pattern_list = "\n".join([
        f"- [{dict(p)['pattern_name']}] ({dict(p)['sport']}): {dict(p)['description']} | Entry: {dict(p)['entry_signal']} | Exit: {dict(p)['exit_signal']}"
        for p in patterns
    ])
    findings_list = "\n".join([f"- {dict(f)['finding']}" for f in findings[:150]])

    prompt = f"""I have {len(patterns)} pattern observations across {len(set(dict(p)['pattern_name'] for p in patterns))} named patterns.

RAW PATTERNS:
{pattern_list}

RAW FINDINGS:
{findings_list}

Consolidate into a FINAL DEFINITIVE pattern library. Merge duplicates, rank by frequency, synthesize actionable rules.

Respond in JSON:
{{
  "canonical_patterns": [
    {{
      "name": "Pattern Name",
      "description": "Definitive description",
      "frequency_rank": 1,
      "sport": "tennis/basketball/hockey/all",
      "entry_rule": "Precise entry rule with price levels",
      "exit_rule": "Precise exit rule",
      "false_signal": "What to avoid",
      "example_tickers": ["TICKER1", "TICKER2", "TICKER3"]
    }}
  ],
  "top_10_insights": ["insight 1", "insight 2", "insight 3", "insight 4", "insight 5", "insight 6", "insight 7", "insight 8", "insight 9", "insight 10"],
  "entry_timing_summary": "Consolidated entry timing rules",
  "sport_differences": "Key differences between sports"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system="You are a quantitative trading analyst. Consolidate pattern observations into actionable trading rules. Be specific and concise.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())

        conn = get_conn()
        conn.execute(
            "INSERT INTO analysis_batches (sport, tickers, raw_response) VALUES (?, ?, ?)",
            (sport or "all", "CONSOLIDATED", raw)
        )
        conn.commit()
        conn.close()

        print(f"\n{'='*60}")
        print(f"CONSOLIDATED PATTERN LIBRARY — {(sport or 'ALL').upper()}")
        print(f"{'='*60}")
        for p in result.get("canonical_patterns", []):
            print(f"\n#{p['frequency_rank']} {p['name']} [{p['sport']}]")
            print(f"  {p['description']}")
            print(f"  Entry: {p['entry_rule']}")
            print(f"  Exit:  {p['exit_rule']}")
            print(f"  Avoid: {p['false_signal']}")
        print(f"\nTOP 10 INSIGHTS:")
        for i, ins in enumerate(result.get("top_10_insights", []), 1):
            print(f"  {i}. {ins}")
        print(f"\nTIMING: {result.get('entry_timing_summary','')}")
        print(f"SPORTS: {result.get('sport_differences','')}")
        print(f"{'='*60}\n")
        return result

    except Exception as e:
        print(f"Consolidation failed: {e}")
        return None


def get_pattern_library() -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT raw_response FROM analysis_batches WHERE tickers='CONSOLIDATED' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["raw_response"])
        except Exception:
            return {}
    return {}