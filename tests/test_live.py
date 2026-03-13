#!/usr/bin/env python3
"""
Run: python3 test_live.py
Shows raw field values for known live vs upcoming matches so we can find the right signal.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from src.tennis import fetch_all_series_concurrent, TENNIS_SERIES

NOW = datetime.now(timezone.utc)
print(f"Current time: {NOW.strftime('%Y-%m-%d %H:%M UTC')}\n")

markets = fetch_all_series_concurrent(TENNIS_SERIES)

# Known live right now
LIVE_NAMES    = {"pegula", "ostapenko", "muchova", "ruzic"}
# Known upcoming
UPCOMING_NAMES = {"keys", "kartal", "swiatek", "sakkari", "rybakina", "kostyuk"}

def name_match(title, names):
    t = title.lower()
    return any(n in t for n in names)

print(f"{'MATCH':<35} {'OPEN_TIME':<25} {'CLOSE_TIME':<25} {'VOL':>8} {'V24H':>8} {'STATUS'}")
print("-"*115)

seen = set()
for m in markets:
    title = m.get("title","")
    ticker = m.get("ticker","")
    key = "-".join(ticker.split("-")[:-1])
    if key in seen: continue
    seen.add(key)

    is_target_live     = name_match(title, LIVE_NAMES)
    is_target_upcoming = name_match(title, UPCOMING_NAMES)
    if not (is_target_live or is_target_upcoming):
        continue

    open_str  = m.get("open_time","")
    close_str = m.get("close_time") or m.get("expiration_time","")
    vol       = m.get("volume") or 0
    vol_24h   = m.get("volume_24h") or 0
    status    = m.get("status","?")

    # Parse times
    def parse(s):
        if not s: return None
        try: return datetime.fromisoformat(s.replace("Z","+00:00"))
        except: return None

    open_ts  = parse(open_str)
    close_ts = parse(close_str)
    mins_open = (NOW - open_ts).total_seconds()/60 if open_ts and open_ts < NOW else None
    hours_to_close = (close_ts - NOW).total_seconds()/3600 if close_ts and close_ts > NOW else None

    tag = "🔴 LIVE    " if is_target_live else "⏰ UPCOMING"
    p1p2 = title.split("Will ")[-1].split(" win")[0] if "Will " in title else title[:34]

    print(f"{tag} {p1p2:<34} open={open_str[5:16] if open_str else '?':>11}  "
          f"mins_open={str(round(mins_open)) if mins_open else 'future':>6}  "
          f"vol={vol:>8,}  v24h={vol_24h:>8,}  status={status}")

print()
print("KEY QUESTION: What's different between live and upcoming?")
print("Look at: mins_open, vol_24h, status field")