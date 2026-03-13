#!/usr/bin/env python3
"""
Run from project root:
  python3 test_process.py

Simulates the exact _process() pipeline from data_manager
and prints every row to show what the table SHOULD be displaying.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from src.tennis import (
    fetch_all_series_concurrent, filter_active,
    group_by_match, _extract_names, _price_color, TENNIS_SERIES, is_live
)
from src.constants import get_bucket

def _process(groups, sport):
    rows = []
    for key, mm in groups.items():
        mm.sort(key=lambda m: m.get("ticker", ""))
        p1, p2 = _extract_names(mm)

        p1y = (mm[0].get("yes_ask") or 0) / 100 if mm else 0
        p1n = (mm[0].get("no_ask")  or 0) / 100 if mm else 0
        p2y = (mm[1].get("yes_ask") or 0) / 100 if len(mm) > 1 else 0
        p2n = (mm[1].get("no_ask")  or 0) / 100 if len(mm) > 1 else 0
        vol  = sum((m.get("volume") or 0) for m in mm)
        yes_p, no_p = (p1y, p1n) if p1y >= p2y else (p2y, p2n)
        live = any(is_live(m) for m in mm)
        event_ticker = mm[0].get("event_ticker", "") if mm else ""

        rows.append((
            key, p1, p2, yes_p, no_p, vol,
            _price_color(yes_p), get_bucket(yes_p), sport,
            live, event_ticker
        ))
    return rows

print("Fetching all tennis series...")
markets = fetch_all_series_concurrent(TENNIS_SERIES)
print(f"Raw: {len(markets)} markets")

filtered = filter_active(markets)
print(f"Filtered: {len(filtered)} markets")

groups = group_by_match(filtered)
print(f"Groups: {len(groups)} matches")

rows = _process(groups, "tennis")
print(f"Rows: {len(rows)}")

print()
print(f"{'LIVE':<6} {'P1':<14} {'P2':<14} {'YES':>5} {'NO':>5} {'VOL':>8}  {'BUCKET':<8}")
print("-" * 65)

# Sort live first, then by volume
rows.sort(key=lambda r: (0 if r[9] else 1, -r[5]))

for r in rows:
    key, p1, p2, yes_p, no_p, vol, color, bucket, sport, live, et = r
    live_str = "🔴" if live else "  "
    print(f"{live_str}  {p1:<14} {p2:<14} {yes_p:>5.2f} {no_p:>5.2f} {vol:>8,}  {bucket}")

print()
print(f"Total rows that should appear in table: {len(rows)}")
print(f"Live: {sum(1 for r in rows if r[9])}")
print(f"Upcoming: {sum(1 for r in rows if not r[9])}")

# Now simulate exactly what _redraw does
print()
print("=== SIMULATING _redraw ===")
sport_filter = "all"
color_filter = "all"
sec_expanded = {"sports": True, "politics": False}

shown = 0
all_rows = {"tennis": rows, "basketball": [], "politics": []}

for sport_key, sport_rows in all_rows.items():
    section = "sports" if sport_key in ("tennis", "basketball") else "politics"
    if not sec_expanded[section]:
        print(f"  SKIP {sport_key}: section not expanded")
        continue
    if sport_key in ("tennis", "basketball") and sport_filter != "all":
        if sport_key != sport_filter:
            print(f"  SKIP {sport_key}: sport filter mismatch")
            continue

    filtered_rows = [r for r in sport_rows
                     if color_filter == "all" or r[7] == color_filter]

    if not filtered_rows:
        print(f"  {sport_key}: NO ROWS — shows 'No {sport_key} markets available'")
        continue

    print(f"  {sport_key}: {len(filtered_rows)} rows would be shown ✅")
    shown += len(filtered_rows)

print(f"\nTotal rows shown: {shown}")
if shown == 0:
    print("❌ BUG: _redraw would show nothing even with data!")
else:
    print("✅ _redraw should display rows correctly")