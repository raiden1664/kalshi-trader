"""Run this once to see raw API responses and diagnose issues."""
import sys
sys.path.insert(0, "/Users/raidenshipley/Desktop/kalshi-trader")

from src.api import fetch_balance, fetch_positions, fetch_markets

print("=== BALANCE ===")
b = fetch_balance()
print(b)

print("\n=== POSITIONS ===")
p = fetch_positions()
print(p[:2] if p else "empty")

print("\n=== TENNIS MARKETS (first 2) ===")
m = fetch_markets("KXATPMATCH")
print(f"count: {len(m)}")
if m:
    print("keys:", list(m[0].keys()))
    print("sample:", {k: m[0][k] for k in ["ticker","title","yes_ask","no_ask","volume"] if k in m[0]})