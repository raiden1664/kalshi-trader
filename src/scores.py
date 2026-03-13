"""
Live tennis scores via SofaScore's unofficial public API.
No API key required.
"""
import requests
from difflib import SequenceMatcher

_S = requests.Session()
_S.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer":    "https://www.sofascore.com/",
    "Accept":     "application/json",
})
_BASE = "https://api.sofascore.com/api/v1"


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _best_match(events: list, p1: str, p2: str):
    """Return (event, score) for best fuzzy-matching event."""
    best, best_score = None, 0.0
    p1l, p2l = p1.lower(), p2.lower()
    for e in events:
        hn = e.get("homeTeam", {}).get("name", "")
        an = e.get("awayTeam", {}).get("name", "")
        # Match surnames (last word) for robustness
        h_sim = max(_sim(p1l, hn), _sim(p1l.split()[-1], hn.split()[-1] if hn else ""))
        a_sim = max(_sim(p2l, an), _sim(p2l.split()[-1], an.split()[-1] if an else ""))
        combined = h_sim + a_sim
        # Also try reversed
        h2 = max(_sim(p2l, hn), _sim(p2l.split()[-1], hn.split()[-1] if hn else ""))
        a2 = max(_sim(p1l, an), _sim(p1l.split()[-1], an.split()[-1] if an else ""))
        combined = max(combined, h2 + a2)
        if combined > best_score and combined > 1.1:
            best_score = combined
            best = e
    return best


def _parse_event(event: dict, p1: str, p2: str) -> dict:
    """Extract score info from a SofaScore event dict."""
    status_code = event.get("status", {}).get("code", 0)
    status_type = event.get("status", {}).get("type", "")

    # Determine which player is home/away
    hn = event.get("homeTeam", {}).get("name", p1)
    an = event.get("awayTeam", {}).get("name", p2)

    score_obj  = event.get("homeScore", {})
    score_obj2 = event.get("awayScore", {})

    # Period scores (sets for tennis)
    sets = []
    for i in range(1, 6):
        h = score_obj.get(f"period{i}")
        a = score_obj2.get(f"period{i}")
        if h is not None and a is not None:
            sets.append(f"{h}-{a}")

    # Current game score
    h_cur = score_obj.get("current", "")
    a_cur = score_obj2.get("current", "")
    score_str = ", ".join(sets) if sets else "—"

    # Who's serving
    serving = None
    if event.get("firstToServe") == 1:
        serving = "home"
    elif event.get("firstToServe") == 2:
        serving = "away"

    status_map = {
        "inprogress": "live",
        "finished":   "finished",
        "notstarted": "scheduled",
        "postponed":  "postponed",
        "canceled":   "cancelled",
    }
    status = status_map.get(status_type, status_type)

    return {
        "p1":      hn,
        "p2":      an,
        "sets":    sets,
        "score":   score_str,
        "status":  status,
        "serving": serving,
        "game":    f"{h_cur}-{a_cur}" if (h_cur != "" and a_cur != "") else None,
    }


def fetch_live_score(p1: str, p2: str) -> dict | None:
    """
    Fetch live/today's score for p1 vs p2 from SofaScore.
    Falls back to today's scheduled events if not in live feed.
    """
    # 1. Try live feed first
    try:
        r = _S.get(f"{_BASE}/sport/tennis/events/live", timeout=6)
        if r.status_code == 200:
            events = r.json().get("events", [])
            match = _best_match(events, p1, p2)
            if match:
                return _parse_event(match, p1, p2)
    except Exception:
        pass

    # 2. Fall back to today's scheduled events
    from datetime import date
    today = date.today().isoformat()
    try:
        r = _S.get(f"{_BASE}/sport/tennis/scheduled-events/{today}", timeout=6)
        if r.status_code == 200:
            events = r.json().get("events", [])
            match = _best_match(events, p1, p2)
            if match:
                return _parse_event(match, p1, p2)
    except Exception:
        pass

    return None