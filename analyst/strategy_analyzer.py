"""
strategy_analyzer.py — Long-term game strategy analysis.

Separate from analyzer.py (volatility patterns).
Stores results in separate DB tables: strategy_batches, strategy_patterns, strategy_findings.
Focuses on:
- Pre-match favoritism and opening price as predictor
- Both player lines throughout the match
- Favorite hold rates by price bracket
- Set dominance and momentum compounding
- Upset fingerprints and warning signals
- Market speed — how fast does price update on score events?
"""

import sys, os, json, time
import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, init_db
from tagger import get_tagged_candles

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

BOLD  = "\033[1m"
RESET = "\033[0m"


SYSTEM_PROMPT = """You are an expert sports betting strategist analyzing Kalshi prediction markets. Your job is NOT to find price volatility patterns — that analysis is already complete. Your job is to understand FUNDAMENTAL GAME STRATEGY and whether there is a real predictive edge in sports match betting.

## Your Core Mission
Answer these questions with data from the matches:

### 1. Pre-Match Favoritism — Does the Market Know?
- What % of the time does the pre-match favorite (opening price > 50¢) win?
- Break this down by opening price bracket:
  * Heavy favorite: opening YES > 70¢
  * Moderate favorite: opening YES 55-70¢  
  * Slight favorite: opening YES 50-55¢
  * Coin flip: opening YES 45-55¢
- Be honest: if favorites simply win at their expected rate, state that clearly. There is no edge in backing favorites if the market is already efficient.

### 2. Both Player Lines — The Full Picture
- You will see BOTH player YES prices throughout the match
- HOME_YES + AWAY_YES should sum to ~100¢ (minus the spread)
- When HOME_YES rises, AWAY_YES falls — they are mirror images
- Look for: asymmetric reactions (one line moves more than the other should)
- Look for: delayed reactions (score event happens but price doesn't move for several candles)
- Look for: overreactions (price moves far more than the score event warrants)

### 3. Set Dominance — Does Quality of Win Matter?
- Compare: dominant set wins (6-0, 6-1, 6-2) vs competitive set wins (7-5, 7-6, 6-4)
- Does winning a set 6-0 predict winning the next set better than winning 7-6?
- Does getting bageled (losing 0-6) predict losing the match?

### 4. Momentum Compounding vs Regression
- After winning set 1, does the winner go on to win set 2 more often than not?
- Is there a fatigue/regression pattern in long 3-set matches?
- Do players who win quickly (under 90 min) show different price trajectories than players in 3-hour battles?

### 5. Upset Fingerprints
- In matches where the pre-match underdog won, what did the price action look like in the FIRST 25% of the match?
- Is there a warning signal that an upset is brewing? (e.g., favorite's price failing to recover after early break, underdog holding serve unexpectedly)
- What % of upsets showed early warning signs vs came from nowhere?

### 6. Market Efficiency Assessment
- How quickly does price update after a set win? (candles until price stabilizes)
- Are there systematic delays in certain match situations?
- What is the typical price overshoot after a set win before it corrects?

### 7. Honest Assessment
Be explicit about what does NOT work. If the data shows:
- Favorites win at their expected rate → state it
- No consistent upset patterns → state it
- Market is efficient → state it
The goal is to find REAL edges, not to manufacture patterns.

## Data Format
Each match shows:
- Opening prices for both players (first candle)
- Full timeline with both YES prices
- Score events (set wins, game wins) with exact timing
- Final result

## Output — JSON only:
{
  "favorite_hold_rates": {
    "heavy_favorite_over70": {"sample_size": N, "win_rate": 0.XX, "edge_exists": true/false},
    "moderate_55_70": {"sample_size": N, "win_rate": 0.XX, "edge_exists": true/false},
    "slight_50_55": {"sample_size": N, "win_rate": 0.XX, "edge_exists": true/false},
    "coin_flip_45_55": {"sample_size": N, "win_rate": 0.XX, "edge_exists": true/false}
  },
  "set_dominance": {
    "dominant_win_6_0_6_1_6_2": {"next_set_win_rate": 0.XX, "match_win_rate": 0.XX},
    "competitive_win_7_5_7_6": {"next_set_win_rate": 0.XX, "match_win_rate": 0.XX},
    "bagel_received_0_6": {"match_win_rate": 0.XX, "recovery_rate": 0.XX}
  },
  "momentum": {
    "set1_winner_wins_match_rate": 0.XX,
    "quick_match_under_90min_favorite_holds": 0.XX,
    "long_match_over_150min_favorite_holds": 0.XX,
    "fatigue_signal_exists": true/false,
    "fatigue_notes": "description"
  },
  "upset_fingerprints": [
    {
      "pattern": "description of what early price action looked like before upset",
      "frequency": "X of Y upsets showed this",
      "warning_window": "first X% of match",
      "actionable": true/false
    }
  ],
  "market_efficiency": {
    "avg_candles_to_stabilize_after_set_win": N,
    "typical_overshoot_cents": N,
    "delayed_reaction_rate": "X% of set wins showed delayed price update",
    "asymmetric_reactions_found": true/false,
    "asymmetric_notes": "description"
  },
  "honest_assessment": {
    "market_is_efficient": true/false,
    "favorites_win_at_expected_rate": true/false,
    "real_edges_found": ["edge 1", "edge 2"],
    "no_edge_areas": ["area 1", "area 2"],
    "overall_verdict": "one paragraph honest summary"
  },
  "key_strategic_findings": ["finding 1", "finding 2", "...up to 10"],
  "sport": "tennis_atp/tennis_wta/ncaab_men/all"
}"""


def init_strategy_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS strategy_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT,
            tickers TEXT,
            raw_response TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS strategy_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            sport TEXT,
            category TEXT,
            finding TEXT,
            value TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
    """)
    conn.commit()
    conn.close()


def serialize_match_both_lines(ticker_base: str, market: dict, score: dict) -> str:
    """
    Serialize a match showing BOTH player YES lines throughout.
    ticker_base is the match key e.g. KXATPMATCH-26MAR14ALCMED
    """
    conn = get_conn()

    # Get all markets for this match (YES and NO sides for both players)
    rows = conn.execute("""
        SELECT DISTINCT ticker FROM markets
        WHERE ticker LIKE ?
        ORDER BY ticker
    """, (f"{ticker_base}%",)).fetchall()
    conn.close()

    tickers = [r["ticker"] for r in rows]
    if not tickers:
        return None

    # Get candles for all tickers
    all_candles = {}
    for t in tickers:
        candles = get_tagged_candles(t)
        if candles:
            all_candles[t] = candles

    if not all_candles:
        return None

    # Use first available ticker's candles as the timeline
    base_ticker = list(all_candles.keys())[0]
    candles = all_candles[base_ticker]

    home = score.get("player_home", "Home") or "Home"
    away = score.get("player_away", "Away") or "Away"
    winner = score.get("winner", "?")
    sport = market.get("sport", "?")

    set1 = f"{score.get('set1_home')}-{score.get('set1_away')}"
    set2 = f"{score.get('set2_home')}-{score.get('set2_away')}"
    set3_h = score.get("set3_home")
    sets = f"{set1}, {set2}" + (f", {set3_h}-{score.get('set3_away')}" if set3_h is not None else "")

    # Determine opening prices
    first_candle = candles[0] if candles else {}
    opening_price = first_candle.get("price", 0.5) if first_candle else 0.5
    opening_home_yes = int(opening_price * 100)
    opening_away_yes = 100 - opening_home_yes

    pre_match_favorite = home if opening_home_yes > 50 else away
    pre_match_fav_price = max(opening_home_yes, opening_away_yes)

    lines = [
        f"MATCH: {ticker_base}",
        f"Sport: {sport} | {home} (HOME) vs {away} (AWAY)",
        f"Opening: {home}={opening_home_yes}¢  {away}={opening_away_yes}¢",
        f"Pre-match favorite: {pre_match_favorite} @ {pre_match_fav_price}¢",
        f"Result: {winner} wins | Sets: {sets}",
        f"Candles: {len(candles)}",
        "",
        f"Timeline (pct|HOME_YES¢|AWAY_YES¢|Δhome|set|games|event):",
    ]

    for c in candles:
        price = c.get("price")
        if price is None:
            continue

        pct   = int((c.get("match_pct") or 0) * 100)
        home_yes = int(price * 100)
        away_yes = 100 - home_yes
        chg   = c.get("price_change") or 0
        chgs  = f"{'+' if chg >= 0 else ''}{int(chg*100)}"
        sn    = c.get("set_num") or 0
        hg    = c.get("home_games") or 0
        ag    = c.get("away_games") or 0
        evt   = c.get("last_event_type") or "point"

        is_key = (
            evt in ("set_win", "game_win") or
            abs(chg) >= 0.04 or
            pct == 0 or pct >= 99
        )

        if is_key:
            lines.append(
                f"{pct:3d}%|{home_yes:3d}c|{away_yes:3d}c|{chgs:>4}|S{sn}|{hg}-{ag}|{evt}"
            )

    return "\n".join(lines)


def analyze_strategy_sport(sport: str, batch_size: int = 5, max_batches: int = 50):
    init_strategy_db()

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
    print(f"\n{BOLD}Strategy analysis: {len(tickers)} {sport} matches in batches of {batch_size}...{RESET}")

    batches_run = 0
    for batch_start in range(0, min(len(tickers), max_batches * batch_size), batch_size):
        batch_tickers = tickers[batch_start:batch_start + batch_size]
        batches_run += 1
        total = min(max_batches, (len(tickers)-1)//batch_size + 1)
        print(f"\n  Batch {batches_run}/{total}: {len(batch_tickers)} matches...", flush=True)

        match_texts = []
        for ticker in batch_tickers:
            # Get the match base key (strip -YES/-NO suffix)
            parts = ticker.split("-")
            base = "-".join(parts[:-1]) if parts[-1] in ("YES", "NO") else ticker

            conn = get_conn()
            market = dict(conn.execute("SELECT * FROM markets WHERE ticker=?", (ticker,)).fetchone() or {})
            score  = dict(conn.execute("SELECT * FROM match_scores WHERE ticker=?", (ticker,)).fetchone() or {})
            conn.close()

            text = serialize_match_both_lines(base, market, score)
            if text:
                match_texts.append(text)

        if not match_texts:
            continue

        prompt = (
            f"Here are {len(match_texts)} {sport.replace('_', ' ')} matches.\n"
            f"Each shows BOTH player YES prices throughout the match.\n\n"
            + "\n\n---\n\n".join(match_texts)
            + "\n\nAnalyze and respond with the JSON strategy report only."
        )

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

                conn = get_conn()
                cursor = conn.execute(
                    "INSERT INTO strategy_batches (sport, tickers, raw_response) VALUES (?, ?, ?)",
                    (sport, json.dumps(batch_tickers), raw)
                )
                batch_id = cursor.lastrowid
                conn.commit()

                # Save key findings
                for finding in result.get("key_strategic_findings", []):
                    conn.execute(
                        "INSERT INTO strategy_patterns (batch_id, sport, category, finding, value) VALUES (?, ?, ?, ?, ?)",
                        (batch_id, sport, "key_finding", finding, "")
                    )

                # Save honest assessment
                assessment = result.get("honest_assessment", {})
                for k, v in assessment.items():
                    conn.execute(
                        "INSERT INTO strategy_patterns (batch_id, sport, category, finding, value) VALUES (?, ?, ?, ?, ?)",
                        (batch_id, sport, "honest_assessment", k, json.dumps(v))
                    )

                # Save upset fingerprints
                for fp in result.get("upset_fingerprints", []):
                    conn.execute(
                        "INSERT INTO strategy_patterns (batch_id, sport, category, finding, value) VALUES (?, ?, ?, ?, ?)",
                        (batch_id, sport, "upset_fingerprint", fp.get("pattern",""), json.dumps(fp))
                    )

                conn.commit()
                conn.close()

                findings = result.get("key_strategic_findings", [])
                verdict = result.get("honest_assessment", {}).get("overall_verdict", "")[:80]
                print(f"    → {len(findings)} findings | {verdict}...")
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

    print(f"\n{BOLD}Done. {batches_run} strategy batches for {sport}.{RESET}\n")


def consolidate_strategy(sport: str = None):
    """Consolidate all strategy batch findings into a final report."""
    init_strategy_db()

    if not ANTHROPIC_API_KEY:
        print("No ANTHROPIC_API_KEY set.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    conn = get_conn()
    q = "SELECT * FROM strategy_batches WHERE tickers != 'STRATEGY_CONSOLIDATED'"
    if sport:
        q += " AND sport=?"
    batches = conn.execute(q, [sport] if sport else []).fetchall()

    findings_q = "SELECT * FROM strategy_patterns WHERE category='key_finding'"
    if sport:
        findings_q += " AND sport=?"
    findings = conn.execute(findings_q, [sport] if sport else []).fetchall()

    assessments_q = "SELECT * FROM strategy_patterns WHERE category='honest_assessment'"
    if sport:
        assessments_q += " AND sport=?"
    assessments = conn.execute(assessments_q, [sport] if sport else []).fetchall()

    upsets_q = "SELECT * FROM strategy_patterns WHERE category='upset_fingerprint'"
    if sport:
        upsets_q += " AND sport=?"
    upsets = conn.execute(upsets_q, [sport] if sport else []).fetchall()
    conn.close()

    if not batches:
        print("No strategy batches found. Run analyze-strategy first.")
        return

    findings_text = "\n".join([f"- {dict(f)['finding']}" for f in findings[:200]])
    assessments_text = "\n".join([
        f"- {dict(a)['finding']}: {dict(a)['value']}"
        for a in assessments[:100]
    ])
    upsets_text = "\n".join([f"- {dict(u)['finding']}" for u in upsets[:50]])

    prompt = f"""I have analyzed {len(batches)} batches of sports matches for strategic patterns.

RAW STRATEGIC FINDINGS ({len(findings)} total):
{findings_text}

HONEST ASSESSMENTS FROM BATCHES:
{assessments_text}

UPSET FINGERPRINTS OBSERVED:
{upsets_text}

Consolidate into a FINAL STRATEGIC REPORT. Be completely honest — if the market is efficient and favorites win at expected rates, say so clearly. Only report edges that appeared consistently across multiple batches.

Respond in JSON:
{{
  "market_efficiency_verdict": "efficient/partially_efficient/inefficient",
  "favorite_hold_summary": {{
    "overall_verdict": "Do favorites win at their expected rate?",
    "heavy_favorite_edge": "Is there edge backing heavy favorites?",
    "moderate_favorite_edge": "Is there edge backing moderate favorites?",
    "underdog_edge": "Is there edge backing underdogs in any situation?"
  }},
  "set_dominance_verdict": {{
    "dominant_win_predicts_next_set": true/false,
    "confidence": "high/medium/low",
    "notes": "description"
  }},
  "momentum_verdict": {{
    "set1_winner_advantage": "How strong is winning set 1?",
    "fatigue_signal": "Is there a fatigue effect in long matches?",
    "compounding_exists": true/false
  }},
  "upset_signals": [
    {{
      "signal": "description",
      "reliability": "high/medium/low",
      "entry_window": "when to act",
      "actionable": true/false
    }}
  ],
  "real_edges": [
    {{
      "edge": "description of real edge",
      "context": "when it applies",
      "confidence": "high/medium/low",
      "sport": "tennis/basketball/all"
    }}
  ],
  "dead_ends": ["things that looked like edges but aren't"],
  "strategic_rules": [
    "Rule 1: ...",
    "Rule 2: ...",
    "Rule 3: ..."
  ],
  "top_strategic_insights": ["insight 1", "insight 2", "...up to 10"],
  "overall_verdict": "honest one-paragraph summary of what the data actually shows"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system="You are a quantitative sports betting analyst. Be completely honest. Only report real edges backed by data. Do not manufacture patterns.",
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
            "INSERT INTO strategy_batches (sport, tickers, raw_response) VALUES (?, ?, ?)",
            (sport or "all", "STRATEGY_CONSOLIDATED", raw)
        )
        conn.commit()
        conn.close()

        print(f"\n{'='*65}")
        print(f"STRATEGY REPORT — {(sport or 'ALL').upper()}")
        print(f"{'='*65}")
        print(f"\nMARKET EFFICIENCY: {result.get('market_efficiency_verdict','?').upper()}")

        fav = result.get("favorite_hold_summary", {})
        print(f"\nFAVORITE ANALYSIS:")
        for k, v in fav.items():
            print(f"  {k}: {v}")

        print(f"\nREAL EDGES FOUND ({len(result.get('real_edges',[]))}):")
        for e in result.get("real_edges", []):
            print(f"  [{e.get('confidence','?').upper()}] {e.get('edge','')}")
            print(f"    Context: {e.get('context','')}")

        print(f"\nDEAD ENDS:")
        for d in result.get("dead_ends", []):
            print(f"  ✗ {d}")

        print(f"\nSTRATEGIC RULES:")
        for r in result.get("strategic_rules", []):
            print(f"  {r}")

        print(f"\nTOP INSIGHTS:")
        for i, ins in enumerate(result.get("top_strategic_insights", []), 1):
            print(f"  {i}. {ins}")

        print(f"\nVERDICT: {result.get('overall_verdict','')}")
        print(f"{'='*65}\n")
        return result

    except Exception as e:
        print(f"Consolidation failed: {e}")
        return None


def quality_check_strategy():
    """Quality check pass on the consolidated strategy report."""
    init_strategy_db()

    if not ANTHROPIC_API_KEY:
        print("No ANTHROPIC_API_KEY set.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    conn = get_conn()
    row = conn.execute(
        "SELECT raw_response FROM strategy_batches WHERE tickers='STRATEGY_CONSOLIDATED' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        print("No consolidated strategy found. Run consolidate-strategy first.")
        return

    consolidated = json.loads(row["raw_response"])

    prompt = f"""Here is a consolidated sports betting strategy report derived from analyzing 575+ Kalshi prediction market matches.

{json.dumps(consolidated, indent=2)}

Your job: quality check this report.

1. Remove any edges that are obvious (e.g. "heavy favorites win often" — that's just market efficiency, not an edge)
2. Flag any findings that contradict each other
3. Add confidence scores to each real edge (1-5)
4. Specifically address: is pre-match opening price useful for anything beyond what the market already prices in?
5. Refine the strategic rules to be maximally actionable
6. Add a section on: what CONTEXT is needed before entering any bet (score situation, match time, serve patterns)

The trader's framework:
- Type 1: 30% bankroll, 80-90¢ entries, near-locks only
- Type 2: 20-30% bankroll, 55-75¢ entries, momentum confirmed
- Never enter above 70¢ (soft ceiling 80¢ for Type 1)
- Stop loss: sell if drops to ~59¢ on ~85¢ entry

Respond in JSON:
{{
  "refined_edges": [
    {{
      "edge": "description",
      "confidence": 5,
      "context_required": "what you need to know before entering",
      "entry_trigger": "specific entry condition",
      "sport": "tennis/basketball/all",
      "bet_type": "Type 1/Type 2/avoid"
    }}
  ],
  "opening_price_utility": "Is pre-match opening price useful? How?",
  "context_checklist": [
    "Before any bet, check: ...",
    "Before any bet, check: ...",
    "..."
  ],
  "refined_strategic_rules": ["rule 1", "rule 2", "..."],
  "top_insights": ["insight 1", "insight 2", "...up to 10"],
  "honest_final_verdict": "Final honest assessment"
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system="You are a senior quantitative sports betting analyst. Be completely honest. Remove noise. Only keep real, actionable edges.",
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
            "INSERT INTO strategy_batches (sport, tickers, raw_response) VALUES (?, ?, ?)",
            ("all", "STRATEGY_QUALITY_CHECKED", raw)
        )
        conn.commit()
        conn.close()

        print(f"\n{'='*65}")
        print(f"STRATEGY QUALITY CHECK — FINAL REPORT")
        print(f"{'='*65}")

        print(f"\nREFINED EDGES ({len(result.get('refined_edges',[]))}):")
        for e in result.get("refined_edges", []):
            conf = "★" * e.get("confidence", 0)
            print(f"\n  [{conf}] {e.get('edge','')} [{e.get('sport','?')}] — {e.get('bet_type','?')}")
            print(f"    Context: {e.get('context_required','')}")
            print(f"    Entry:   {e.get('entry_trigger','')}")

        print(f"\nOPENING PRICE UTILITY: {result.get('opening_price_utility','')}")

        print(f"\nCONTEXT CHECKLIST:")
        for c in result.get("context_checklist", []):
            print(f"  ✓ {c}")

        print(f"\nSTRATEGIC RULES:")
        for r in result.get("refined_strategic_rules", []):
            print(f"  {r}")

        print(f"\nTOP INSIGHTS:")
        for i, ins in enumerate(result.get("top_insights", []), 1):
            print(f"  {i}. {ins}")

        print(f"\nFINAL VERDICT: {result.get('honest_final_verdict','')}")
        print(f"{'='*65}\n")
        return result

    except Exception as e:
        print(f"Quality check failed: {e}")
        return None


def get_strategy_library() -> dict:
    """Get the latest quality-checked strategy library."""
    conn = get_conn()
    for label in ("STRATEGY_QUALITY_CHECKED", "STRATEGY_CONSOLIDATED"):
        row = conn.execute(
            "SELECT raw_response FROM strategy_batches WHERE tickers=? ORDER BY created_at DESC LIMIT 1",
            (label,)
        ).fetchone()
        if row:
            conn.close()
            try:
                return json.loads(row["raw_response"])
            except Exception:
                pass
    conn.close()
    return {}