#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from datetime import datetime, timezone
from src.tennis import fetch_all_series_concurrent, TENNIS_SERIES

NOW = datetime.now(timezone.utc)
markets = fetch_all_series_concurrent(TENNIS_SERIES)

LIVE_NAMES     = {"pegula", "ostapenko", "muchova", "ruzic"}
UPCOMING_NAMES = {"keys", "kartal", "swiatek", "sakkari", "rybakina", "kostyuk", "svitolina", "andreeva"}

def parse(s):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except: return None

seen = set()
for m in sorted(markets, key=lambda x: x.get("title","")):
    title  = m.get("title","").lower()
    ticker = m.get("ticker","")
    key    = "-".join(ticker.split("-")[:-1])
    if key in seen: continue
    seen.add(key)

    is_live     = any(n in title for n in LIVE_NAMES)
    is_upcoming = any(n in title for n in UPCOMING_NAMES)
    if not (is_live or is_upcoming): continue

    open_ts  = parse(m.get("open_time"))
    close_ts = parse(m.get("close_time") or m.get("expiration_time"))
    hours_to_close = (close_ts - NOW).total_seconds()/3600 if close_ts else 999
    hours_since_open = (NOW - open_ts).total_seconds()/3600 if open_ts and open_ts < NOW else -1

    tag  = "🔴 LIVE    " if is_live else "⏰ UPCOMING"
    name = m.get("title","")[:40]
    print(f"{tag}  close_in={hours_to_close:>6.1f}h  open_ago={hours_since_open:>5.1f}h  vol={m.get('volume',0):>8,}  {name}")