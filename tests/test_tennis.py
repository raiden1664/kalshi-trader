#!/usr/bin/env python3
"""
Run from your project root:
  cd ~/Desktop/kalshi-trader
  source venv/bin/activate
  python3 test_tennis.py

Tests:
  1. What series + markets come back for each tennis series
  2. Whether Indian Wells games appear (Pegula, Ostapenko, Muchova, etc.)
  3. Whether is_live() correctly flags the live ones
  4. Whether filter_active() is dropping anything it shouldn't
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone
from src.tennis import (
    fetch_series_markets, filter_active, is_live,
    group_by_match, _extract_names, TENNIS_SERIES
)

NOW = datetime.now(timezone.utc)

TARGET_LIVE    = {"pegula", "ostapenko", "muchova", "ruzic"}
TARGET_UPCOMING = {"keys", "kartal", "bencic", "mertens", "swiatek", "sakkari",
                   "andreeva", "siniakova", "rybakina", "kostyuk", "svitolina", "kreger"}
ALL_TARGETS    = TARGET_LIVE | TARGET_UPCOMING

print(f"\n{'='*60}")
print(f"  KALSHI TENNIS FETCH TEST — {NOW.strftime('%H:%M UTC')}")
print(f"{'='*60}\n")

all_raw = []
for series in TENNIS_SERIES:
    print(f"── Fetching {series}...", end=" ", flush=True)
    try:
        markets = fetch_series_markets(series)
        print(f"{len(markets)} markets")
        for m in markets:
            m["_series"] = series   # tag for debugging
        all_raw.extend(markets)
    except Exception as e:
        print(f"ERROR: {e}")

print(f"\nTotal raw markets: {len(all_raw)}")

# ── Filter ────────────────────────────────────────────────────────────────────
filtered = filter_active(all_raw)
print(f"After filter_active (18h window): {len(filtered)}")

dropped = [m for m in all_raw if m not in filtered]
print(f"Dropped by filter: {len(dropped)}")

# Check if any target players were dropped
for m in dropped:
    title = m.get("title", "").lower()
    for name in ALL_TARGETS:
        if name in title:
            ot = m.get("open_time","?")
            ct = m.get("close_time") or m.get("expiration_time","?")
            print(f"  ⚠️  DROPPED target '{name}': {m.get('ticker')}  open={ot}  close={ct}")

# ── Group ─────────────────────────────────────────────────────────────────────
groups = group_by_match(filtered)
print(f"\nMatch groups: {len(groups)}\n")

print(f"{'STATUS':<10} {'MATCH':<32} {'YES':>5} {'VOL':>8}  SERIES")
print("-"*70)

found = set()
for key, mm in sorted(groups.items()):
    p1, p2 = _extract_names(mm)
    live   = any(is_live(m) for m in mm)
    yes_p  = max((m.get("yes_ask") or 0) for m in mm) / 100
    vol    = sum((m.get("volume") or 0) for m in mm)
    series = mm[0].get("_series", "?")
    status = "🔴 LIVE" if live else "⏰ upcoming"
    label  = f"{p1} vs {p2}"

    print(f"{status:<10} {label:<32} {yes_p:>5.0%} {vol:>8,}  {series}")

    for name in ALL_TARGETS:
        if name.lower() in label.lower():
            found.add(name.lower())

# ── Results ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("TARGET PLAYER CHECK:")
for name in sorted(ALL_TARGETS):
    tag = "✅" if name in found else "❌ MISSING"
    print(f"  {tag}  {name}")

missing = ALL_TARGETS - found
if missing:
    print(f"\n⚠️  {len(missing)} players not found — check series or filter logic")
else:
    print("\n✅ All target players found!")

# ── is_live check ─────────────────────────────────────────────────────────────
print(f"\nLIVE DETECTION CHECK:")
for key, mm in groups.items():
    p1, p2 = _extract_names(mm)
    label  = f"{p1} vs {p2}".lower()
    live   = any(is_live(m) for m in mm)
    for name in TARGET_LIVE:
        if name in label:
            tag = "✅ correctly LIVE" if live else "❌ NOT flagged live"
            m0  = mm[0]
            print(f"  {tag}: {p1} vs {p2}")
            print(f"         open={m0.get('open_time')}  vol={m0.get('volume')}  vol_24h={m0.get('volume_24h')}")