"""
scores.py — fetches SofaScore point-by-point/game data and aligns with Kalshi candles.
Supports tennis (ATP/WTA) and basketball (NCAAB, etc.)
"""

import sys, os, time, json, re
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, get_markets, init_db

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Referer': 'https://www.sofascore.com/',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
}

session = requests.Session()
session.headers.update(HEADERS)

# Sport routing
TENNIS_SPORTS  = {'tennis_atp', 'tennis_wta'}
BASKETBALL_SPORTS = {'ncaab_men', 'ncaab_women', 'ncaab_bigeast', 'ncaab_bigten',
                     'nbl', 'cba', 'kbl', 'aba', 'acb', 'bbl', 'vtb', 'fiba'}
HOCKEY_SPORTS  = {'ahl', 'shl', 'liiga'}
BASEBALL_SPORTS = {'mlb'}

SOFA_SPORT_MAP = {
    'tennis_atp':   'tennis',
    'tennis_wta':   'tennis',
    'ncaab_men':    'basketball',
    'ncaab_women':  'basketball',
    'ncaab_bigeast':'basketball',
    'ncaab_bigten': 'basketball',
    'nbl':          'basketball',
    'cba':          'basketball',
    'kbl':          'basketball',
    'aba':          'basketball',
    'acb':          'basketball',
    'bbl':          'basketball',
    'vtb':          'basketball',
    'fiba':         'basketball',
    'ahl':          'ice-hockey',
    'shl':          'ice-hockey',
    'liiga':        'ice-hockey',
    'mlb':          'baseball',
}


# ── DB schema ──────────────────────────────────────────────────────────────

def init_scores_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS match_scores (
            ticker TEXT PRIMARY KEY,
            sofa_event_id INTEGER,
            player_home TEXT,
            player_away TEXT,
            start_ts INTEGER,
            end_ts INTEGER,
            winner TEXT,
            set1_home INTEGER, set1_away INTEGER,
            set2_home INTEGER, set2_away INTEGER,
            set3_home INTEGER, set3_away INTEGER,
            fetched_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS score_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            event_type TEXT NOT NULL,
            set_num INTEGER,
            game_num INTEGER,
            point_num INTEGER,
            server TEXT,
            scorer TEXT,
            home_sets INTEGER,
            away_sets INTEGER,
            home_games INTEGER,
            away_games INTEGER,
            home_point TEXT,
            away_point TEXT,
            estimated_ts INTEGER,
            UNIQUE(ticker, set_num, game_num, point_num)
        );

        CREATE INDEX IF NOT EXISTS idx_score_events_ticker ON score_events(ticker);
        CREATE INDEX IF NOT EXISTS idx_score_events_ts ON score_events(estimated_ts);
    """)
    conn.commit()
    conn.close()


# ── Ticker/title parsing ───────────────────────────────────────────────────

def parse_ticker(ticker: str, title: str = "", sport: str = "") -> dict:
    """
    Parse ticker and title into date + team/player info.
    Tennis: KXATPMATCH-26MAR17BELCAS-CAS
    Basketball: KXNCAAMBGAME-26MAR17DAVOKST-OKST  title: "Davidson at Oklahoma St. Winner?"
    """
    parts = ticker.split("-")
    if len(parts) < 3:
        return {}

    combined = parts[1]  # e.g. '26MAR17BELCAS' or '26MAR17DAVOKST' or '26MAR170430SEMA36'
    side = parts[2]

    # Parse date: first 7 chars are YYMONDD
    m = re.match(r'(\d{2}[A-Z]{3}\d{2})(.*)', combined)
    if not m:
        return {}

    date_part  = m.group(1)
    match_part = m.group(2)

    months = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
              "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}
    try:
        year_short = int(date_part[:2])
        mon_str    = date_part[2:5]
        day        = int(date_part[5:7])
        year       = 2000 + year_short
        month      = months.get(mon_str, 1)
        date_ts    = int(datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc).timestamp())
        date_str   = f"{year}-{month:02d}-{day:02d}"
    except Exception:
        return {}

    result = {
        "date_str":    date_str,
        "date_ts":     date_ts,
        "market_side": side,
        "match_code":  match_part,
    }

    # Tennis: parse player codes from ticker
    if sport in TENNIS_SPORTS:
        result["player1"] = match_part[:3]
        result["player2"] = match_part[3:6]
        result["search_type"] = "tennis"

    # Basketball/Hockey/Baseball: parse team names from title
    else:
        team1, team2 = _parse_title_teams(title)
        result["team1"] = team1
        result["team2"] = team2
        result["search_type"] = "team"

    return result


def _parse_title_teams(title: str):
    """Parse 'Davidson at Oklahoma St. Winner?' → ('Davidson', 'Oklahoma St.')"""
    # Remove trailing noise
    title = re.sub(r'\s*(Winner|winner|\?|Game|\-.*)?$', '', title).strip()
    # Split on ' at ' or ' vs ' or ' @ '
    for sep in [' at ', ' vs. ', ' vs ', ' @ ', ' - ']:
        if sep in title:
            parts = title.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return title, ""


# ── SofaScore API ──────────────────────────────────────────────────────────

def sofa_events_on_date(date_str: str, sofa_sport: str) -> list:
    url = f"https://api.sofascore.com/api/v1/sport/{sofa_sport}/scheduled-events/{date_str}"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception as e:
        print(f"  [warn] SofaScore fetch failed for {date_str} {sofa_sport}: {e}")
        return []


def sofa_point_by_point(event_id: int) -> list:
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/point-by-point"
    try:
        r = session.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get("pointByPoint", [])
    except Exception:
        return []


def sofa_incidents(event_id: int) -> list:
    """For basketball/hockey - get period scores via incidents."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/incidents"
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get("incidents", [])
        return []
    except Exception:
        return []


# ── Match finding ──────────────────────────────────────────────────────────

def _find_tennis_event(events: list, p1_code: str, p2_code: str) -> dict:
    p1, p2 = p1_code.upper(), p2_code.upper()
    best, best_score = None, 0

    for e in events:
        ht = e.get("homeTeam", {}).get("name", "").upper()
        at = e.get("awayTeam", {}).get("name", "").upper()
        hc = e.get("homeTeam", {}).get("nameCode", "").upper()
        ac = e.get("awayTeam", {}).get("nameCode", "").upper()

        score = 0
        for pa, pb in [(p1, p2), (p2, p1)]:
            s = 0
            if pa == hc: s += 4
            if pb == ac: s += 4
            if ht.split()[-1][:3] == pa: s += 2
            if at.split()[-1][:3] == pb: s += 2
            if pa[:2] in ht: s += 1
            if pb[:2] in at: s += 1
            score = max(score, s)

        if score > best_score:
            best_score = score
            best = e

    return best if best_score >= 3 else {}


def _normalize_team(name: str) -> str:
    """Normalize team name for fuzzy matching."""
    name = name.upper().strip()
    # Remove common suffixes
    for suffix in [' ST.', ' STATE', ' UNIVERSITY', ' COLLEGE', ' UNIV', ' U.']:
        name = name.replace(suffix, '')
    # Remove punctuation
    name = re.sub(r'[^A-Z0-9 ]', '', name)
    return name.strip()


def _team_similarity(a: str, b: str) -> int:
    """Simple similarity score between two team names."""
    a, b = _normalize_team(a), _normalize_team(b)
    if a == b: return 10
    if a in b or b in a: return 6
    # Check first word match
    a_words = a.split()
    b_words = b.split()
    if a_words and b_words and a_words[0] == b_words[0]: return 4
    # Check any word overlap
    overlap = len(set(a_words) & set(b_words))
    if overlap >= 2: return 3
    if overlap == 1 and len(a_words[0]) > 3: return 2
    # Prefix match
    if len(a) >= 3 and b.startswith(a[:3]): return 2
    if len(b) >= 3 and a.startswith(b[:3]): return 2
    return 0


def _find_team_event(events: list, team1: str, team2: str) -> dict:
    best, best_score = None, 0

    for e in events:
        ht = e.get("homeTeam", {}).get("name", "")
        at = e.get("awayTeam", {}).get("name", "")

        # Try both orderings
        for t1, t2 in [(team1, team2), (team2, team1)]:
            s1 = _team_similarity(t1, ht)
            s2 = _team_similarity(t2, at)
            score = s1 + s2
            if score > best_score:
                best_score = score
                best = e

    return best if best_score >= 4 else {}


# ── Timeline reconstruction ────────────────────────────────────────────────

def reconstruct_tennis_timeline(event: dict, pbp: list) -> list:
    start_ts = event.get("startTimestamp", 0)
    total_points = sum(
        len(game.get("points", []))
        for s in pbp
        for game in s.get("games", [])
    )
    if not total_points or not start_ts:
        return []

    estimated_duration = total_points * 30
    events = []
    home_sets = away_sets = point_idx = 0

    for set_data in pbp:
        set_num = set_data.get("set", 1)
        games = set_data.get("games", [])
        home_games = away_games = 0

        for game in games:
            game_num = game.get("game", 1)
            points   = game.get("points", [])
            serving  = game.get("score", {}).get("serving", 1)

            for pt_idx, point in enumerate(points):
                frac   = point_idx / max(total_points, 1)
                est_ts = int(start_ts + frac * estimated_duration)
                scorer = "home" if point.get("homePointType") == 1 else "away"

                events.append({
                    "event_type": "point",
                    "set_num": set_num, "game_num": game_num, "point_num": pt_idx + 1,
                    "server": "home" if serving == 1 else "away",
                    "scorer": scorer,
                    "home_sets": home_sets, "away_sets": away_sets,
                    "home_games": home_games, "away_games": away_games,
                    "home_point": point.get("homePoint", "0"),
                    "away_point": point.get("awayPoint", "0"),
                    "estimated_ts": est_ts,
                })
                point_idx += 1

            if points:
                last = points[-1]
                if last.get("homePointType") == 1:
                    home_games += 1
                    scorer = "home"
                else:
                    away_games += 1
                    scorer = "away"
                events.append({
                    "event_type": "game_win",
                    "set_num": set_num, "game_num": game_num, "point_num": 999,
                    "server": "home" if serving == 1 else "away", "scorer": scorer,
                    "home_sets": home_sets, "away_sets": away_sets,
                    "home_games": home_games, "away_games": away_games,
                    "home_point": "Game", "away_point": "Game",
                    "estimated_ts": events[-1]["estimated_ts"] + 5 if events else start_ts,
                })

        if home_games > away_games:
            home_sets += 1; winner = "home"
        else:
            away_sets += 1; winner = "away"

        events.append({
            "event_type": "set_win",
            "set_num": set_num, "game_num": 999, "point_num": 999,
            "server": "", "scorer": winner,
            "home_sets": home_sets, "away_sets": away_sets,
            "home_games": home_games, "away_games": away_games,
            "home_point": "", "away_point": "",
            "estimated_ts": events[-1]["estimated_ts"] + 10 if events else start_ts,
        })

    return events


def reconstruct_basketball_timeline(event: dict) -> list:
    """
    For basketball: build timeline from period scores.
    Uses homeScore/awayScore period fields.
    """
    start_ts = event.get("startTimestamp", 0)
    if not start_ts:
        return []

    hs = event.get("homeScore", {})
    aws = event.get("awayScore", {})

    # Estimate ~20 min per period
    period_duration = 20 * 60
    events = []

    periods = []
    for p in range(1, 6):
        h_score = hs.get(f"period{p}")
        a_score = aws.get(f"period{p}")
        if h_score is not None and a_score is not None:
            periods.append((p, h_score, a_score))

    home_total = away_total = 0
    for period_num, h_pts, a_pts in periods:
        home_total += h_pts
        away_total += a_pts
        est_ts = int(start_ts + period_num * period_duration)

        scorer = "home" if h_pts > a_pts else "away"
        events.append({
            "event_type": "set_win",  # reuse set_win as period_end
            "set_num": period_num, "game_num": 1, "point_num": 999,
            "server": "", "scorer": scorer,
            "home_sets": period_num, "away_sets": period_num,
            "home_games": home_total, "away_games": away_total,
            "home_point": str(h_pts), "away_point": str(a_pts),
            "estimated_ts": est_ts,
        })

    # Also add halftime as a key event
    if len(periods) >= 2:
        h_half = sum(p[1] for p in periods[:2])
        a_half = sum(p[2] for p in periods[:2])
        events.append({
            "event_type": "game_win",  # reuse as halftime marker
            "set_num": 0, "game_num": 0, "point_num": 0,
            "server": "", "scorer": "home" if h_half > a_half else "away",
            "home_sets": 2, "away_sets": 2,
            "home_games": h_half, "away_games": a_half,
            "home_point": str(h_half), "away_point": str(a_half),
            "estimated_ts": int(start_ts + 2 * period_duration),
        })

    return sorted(events, key=lambda e: e["estimated_ts"])


# ── DB storage ─────────────────────────────────────────────────────────────

def store_match_score(ticker: str, event: dict, timeline: list):
    conn = get_conn()
    hs = event.get("homeScore", {})
    home_name    = event.get("homeTeam", {}).get("name", "")
    away_name    = event.get("awayTeam", {}).get("name", "")
    winner_code  = event.get("winnerCode", 0)
    winner       = "home" if winner_code == 1 else "away"

    conn.execute("""
        INSERT INTO match_scores
        (ticker, sofa_event_id, player_home, player_away, start_ts, end_ts,
         winner, set1_home, set1_away, set2_home, set2_away, set3_home, set3_away, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            sofa_event_id=excluded.sofa_event_id,
            player_home=excluded.player_home, player_away=excluded.player_away,
            start_ts=excluded.start_ts, winner=excluded.winner,
            set1_home=excluded.set1_home, set1_away=excluded.set1_away,
            set2_home=excluded.set2_home, set2_away=excluded.set2_away,
            fetched_at=excluded.fetched_at
    """, (
        ticker, event.get("id"), home_name, away_name,
        event.get("startTimestamp", 0),
        timeline[-1]["estimated_ts"] if timeline else 0,
        winner,
        hs.get("period1"), event.get("awayScore", {}).get("period1"),
        hs.get("period2"), event.get("awayScore", {}).get("period2"),
        hs.get("period3"), event.get("awayScore", {}).get("period3"),
        int(time.time()),
    ))

    conn.executemany("""
        INSERT OR IGNORE INTO score_events
        (ticker, event_type, set_num, game_num, point_num, server, scorer,
         home_sets, away_sets, home_games, away_games, home_point, away_point, estimated_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        ticker,
        e["event_type"], e["set_num"], e["game_num"], e["point_num"],
        e["server"], e["scorer"],
        e["home_sets"], e["away_sets"],
        e["home_games"], e["away_games"],
        e["home_point"], e["away_point"],
        e["estimated_ts"],
    ) for e in timeline])

    conn.commit()
    conn.close()


def match_has_scores(ticker: str) -> bool:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM score_events WHERE ticker=?", (ticker,)
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


# ── Main fetch loop ────────────────────────────────────────────────────────

def fetch_scores_for_all(sport: str = "tennis_atp", limit: int = 1000):
    init_scores_db()
    markets = get_markets(sport=sport, limit=limit)
    sofa_sport = SOFA_SPORT_MAP.get(sport, "tennis")

    matched = failed = skipped = 0
    date_cache = {}

    print(f"\nFetching SofaScore data for {len(markets)} {sport} markets (sofa: {sofa_sport})...")

    for m in markets:
        m = dict(m)
        ticker = m["ticker"]
        title  = m.get("title", "") or ""

        if match_has_scores(ticker):
            skipped += 1
            continue

        info = parse_ticker(ticker, title=title, sport=sport)
        if not info:
            print(f"  [skip] Could not parse: {ticker}")
            failed += 1
            continue

        date_str = info["date_str"]

        # Cache SofaScore events per date+sport
        cache_key = f"{date_str}:{sofa_sport}"
        if cache_key not in date_cache:
            date_cache[cache_key] = sofa_events_on_date(date_str, sofa_sport)
            time.sleep(0.25)

        events_on_date = date_cache[cache_key]

        # Find matching event
        if info.get("search_type") == "tennis":
            event = _find_tennis_event(events_on_date, info["player1"], info["player2"])
        else:
            event = _find_team_event(events_on_date, info.get("team1",""), info.get("team2",""))

        if not event:
            failed += 1
            continue

        event_id  = event.get("id")
        home_name = event.get("homeTeam", {}).get("name", "?")
        away_name = event.get("awayTeam", {}).get("name", "?")
        print(f"  {ticker[:45]} → {home_name} vs {away_name}...", end=" ", flush=True)

        # Build timeline
        if sport in TENNIS_SPORTS:
            pbp = sofa_point_by_point(event_id)
            time.sleep(0.2)
            if not pbp:
                print("no pbp")
                failed += 1
                continue
            timeline = reconstruct_tennis_timeline(event, pbp)
        else:
            # Basketball/hockey: use period scores from event data
            timeline = reconstruct_basketball_timeline(event)

        if not timeline:
            print("no timeline")
            failed += 1
            continue

        store_match_score(ticker, event, timeline)
        matched += 1
        print(f"{len(timeline)} events")

    print(f"\nDone. {matched} matched, {skipped} skipped (cached), {failed} failed.\n")


def get_score_events(ticker: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM score_events WHERE ticker=? ORDER BY estimated_ts ASC", (ticker,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_match_score(ticker: str) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM match_scores WHERE ticker=?", (ticker,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}