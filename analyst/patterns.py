import os
import json
import anthropic
from db import get_markets, get_candles, save_pattern, get_latest_patterns

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

PATTERN_SYSTEM = """You are an expert quantitative analyst for Kalshi prediction markets, specializing in tennis and college basketball match markets.

Your job is to analyze historical price data across multiple matches and identify actionable, recurring patterns that a trader can exploit.

Focus on:
1. Price levels where contracts consistently over/underprice the true probability
2. Momentum patterns — when does a price move sustain vs reverse?
3. Entry timing — what price/score combinations produce the best risk-reward?
4. Volume patterns — how does thin vs thick volume affect price reliability?
5. Common traps — situations that look like edges but aren't

Be specific and quantitative where possible. Reference actual price levels (e.g. "contracts at 62–68¢ after a set win tend to reach 80¢+ within 15 minutes").

Respond in clean plain text with numbered insights. No markdown headers."""


def _build_match_summary(ticker: str, result: str) -> str:
    candles = get_candles(ticker)
    if not candles:
        return None

    prices = [float(c["price_close"]) for c in candles if c["price_close"]]
    if not prices:
        return None

    start_price  = prices[0]
    end_price    = prices[-1]
    max_price    = max(prices)
    min_price    = min(prices)
    total_candles = len(prices)
    
    # Find biggest single-candle moves
    moves = []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        moves.append(delta)
    
    big_up   = max(moves) if moves else 0
    big_down = min(moves) if moves else 0

    # Volatility buckets
    vol_changes = sum(1 for m in moves if abs(m) > 0.03)

    return (
        f"Ticker: {ticker} | Result: {result} | "
        f"Start: {start_price:.2f} End: {end_price:.2f} | "
        f"Max: {max_price:.2f} Min: {min_price:.2f} | "
        f"Candles: {total_candles} | "
        f"Biggest up move: +{big_up:.3f} | Biggest down move: {big_down:.3f} | "
        f"Volatile candles (>3¢): {vol_changes}"
    )


def analyze_patterns(sport: str = None, sample: int = 30):
    """
    Pull recent settled matches, summarize their price trajectories,
    and ask the AI to identify patterns.
    """
    print(f"\nAnalyzing patterns for: {sport or 'all sports'} (sample={sample})")
    
    markets = get_markets(sport=sport, limit=sample)
    if not markets:
        print("No markets in DB. Run 'fetch' first.")
        return

    summaries = []
    for m in markets:
        s = _build_match_summary(m["ticker"], m["result"] or "unknown")
        if s:
            summaries.append(s)

    if not summaries:
        print("No candlestick data found. Run 'fetch' first.")
        return

    print(f"  Built summaries for {len(summaries)} matches...")

    prompt = (
        f"Here are price trajectory summaries for {len(summaries)} settled Kalshi "
        f"{'tennis' if sport and 'tennis' in sport else sport or 'sports'} match markets.\n\n"
        + "\n".join(summaries)
        + "\n\nIdentify the most actionable patterns a trader should know about."
    )

    if not ANTHROPIC_API_KEY:
        print("No ANTHROPIC_API_KEY set — skipping AI call.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=PATTERN_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    analysis = response.content[0].text.strip()
    save_pattern(sport or "all", analysis)

    print(f"\n{'='*60}")
    print(f"PATTERN ANALYSIS — {(sport or 'all').upper()}")
    print(f"{'='*60}")
    print(analysis)
    print(f"{'='*60}\n")
    print("(Saved to DB)")


def show_recent_patterns(sport: str = None):
    rows = get_latest_patterns(sport=sport, limit=3)
    if not rows:
        print("No pattern analyses saved yet. Run 'patterns' command first.")
        return
    for row in rows:
        from datetime import datetime
        ts = datetime.utcfromtimestamp(row["created_at"]).strftime("%Y-%m-%d %H:%M UTC")
        print(f"\n{'='*60}")
        print(f"Pattern Analysis — {row['sport'].upper()} — {ts}")
        print(f"{'='*60}")
        print(row["analysis"])
    print()