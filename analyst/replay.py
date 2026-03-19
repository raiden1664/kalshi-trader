import os
import time
import json
import anthropic
from datetime import datetime
from db import get_candles, get_verdicts, save_verdict, get_conn

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are a real-time trade advisor for Kalshi prediction markets, specializing in tennis and college basketball (NCAAB) match markets.

You will be given 1-minute candlestick snapshots from a live match market one step at a time, along with the market ticker and sport. Your job is to give a clear verdict at each step.

## Your Trading Framework

### Bet Types
- **Type 1** (30% bankroll): Near-locks at 80-90c. Steady accumulation plays.
- **Type 2** (20-30% bankroll): Mispriced value at 55-75c. Requires BOTH price edge AND momentum confirmation.
- **Type 3** (long shots <50c): Skip — not in play.

### Hard Rules
- Never buy above 70c (soft ceiling ~80c for passive Type 1 plays only)
- Never add to a losing position
- Sell when momentum fully flips
- Stop-loss: sell if contract drops to ~59c on an ~85c entry
- No entries mid-swing on single-point moves — wait for set/game confirmation

### Tennis Signals
- 2-set lead or deep third-set lead = strong entry trigger
- Winning a set 6-0 = strong momentum signal
- First-set win alone = insufficient for entry
- Split sets cancel momentum signals
- Low-volume Challenger/125K markets misprice more — bigger edge windows
- Act immediately when a player is closing out a set

### NCAAB Signals
- Large lead in second half + clock running = Type 1 territory
- Close game in final 5 min = avoid (high variance)
- Blowout markets often correctly priced — check volume before entry

### Price Interpretation
- Price = implied probability (0.65 = 65% chance of YES resolving)
- Zero or low volume = thin market, wider mispricing windows but also less reliable signals
- Rapid price rise without volume = spread adjustment, not real momentum
- Pre-match candles (no volume, stable price) = no action needed, just tracking

## Output Format
Respond ONLY with a JSON object — no other text:
{
  "verdict": "BUY" | "HOLD" | "SELL" | "PASS",
  "bet_type": "Type1" | "Type2" | "Type3" | "N/A",
  "confidence": "high" | "medium" | "low",
  "reasoning": "2-3 sentence max explanation"
}"""


def _call_ai(messages: list) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"verdict": "PASS", "bet_type": "N/A", "confidence": "low", "reasoning": "No ANTHROPIC_API_KEY set."}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except Exception:
        return {"verdict": "PASS", "bet_type": "N/A", "confidence": "low", "reasoning": text}


def _format_ts(ts: int) -> str:
    try:
        return datetime.utcfromtimestamp(ts).strftime("%H:%M:%S UTC")
    except Exception:
        return str(ts)


def _verdict_color(verdict: str) -> str:
    colors = {"BUY": "\033[92m", "SELL": "\033[91m", "HOLD": "\033[93m", "PASS": "\033[90m"}
    return colors.get(verdict, "")


def _get_market_info(ticker: str) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM markets WHERE ticker=?", (ticker,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def _parse_players(ticker: str) -> str:
    """Extract player names from ticker e.g. KXATPMATCH-26MAR17BELCAS-CAS -> BEL vs CAS"""
    try:
        parts = ticker.split("-")
        if len(parts) >= 3:
            matchup = parts[2]  # e.g. BELCAS
            player2 = parts[3]  # e.g. CAS
            mid = len(matchup) // 2
            player1 = matchup[:mid] if len(matchup) == 6 else matchup.replace(player2, "")
            return f"{player1} vs {player2} (YES = {player2} wins)"
    except Exception:
        pass
    return ticker


RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"


def replay_match(ticker: str, auto: bool = False, step: int = 5):
    candles = get_candles(ticker)
    if not candles:
        print(f"No candlestick data found for {ticker}. Run 'fetch' first.")
        return

    existing_verdicts = {v["end_ts"]: v for v in get_verdicts(ticker)}
    market_info = _get_market_info(ticker)
    sport = market_info.get("sport", "unknown")
    players = _parse_players(ticker)

    # Build match context header for AI
    match_context = (
        f"Sport: {sport.replace('_', ' ').upper()}\n"
        f"Market: {ticker}\n"
        f"Players: {players}\n"
        f"Total match duration: ~{len(candles)} minutes of data\n"
    )

    print(f"\n{BOLD}Replaying: {ticker}{RESET}")
    print(f"Sport: {sport} | {players}")
    print(f"Total candles: {len(candles)} | Step size: {step} candles")
    print(f"Result will be revealed at end. Press ENTER to advance, 'r' to re-ask, 'q' to quit.\n")

    history = []

    for i in range(0, len(candles), step):
        chunk = list(candles[i:i+step])
        if not chunk:
            break

        current = chunk[-1]
        ts = current["end_ts"]
        price_close = current["price_close"] or "?"
        price_open  = current["price_open"] or "?"
        vol         = current["volume"] or "0"
        time_str    = _format_ts(ts)

        # Build price history summary for context (last 5 closes)
        history_prices = []
        for j in range(max(0, i - 20), i + 1, step):
            prev_chunk = list(candles[j:j+step])
            if prev_chunk:
                p = prev_chunk[-1]["price_close"]
                if p:
                    history_prices.append(p)

        trend = " → ".join(history_prices[-5:]) if history_prices else "no history"

        candle_summary = (
            f"{match_context}"
            f"Time into match: ~{i} minutes\n"
            f"Current price: {price_close} (opened this step at {price_open})\n"
            f"Recent price trend: {trend}\n"
            f"Volume this candle: {vol}\n"
        )

        if ts in existing_verdicts:
            v = existing_verdicts[ts]
            result = {"verdict": v["verdict"], "bet_type": "?", "confidence": "?", "reasoning": v["reasoning"]}
        else:
            history.append({"role": "user", "content": f"Match snapshot:\n{candle_summary}\n\nWhat is your verdict?"})
            result = _call_ai(history)
            history.append({"role": "assistant", "content": json.dumps(result)})
            save_verdict(ticker, ts, result["verdict"], result["reasoning"])
            if len(history) > 20:
                history = history[-20:]

        color = _verdict_color(result["verdict"])
        print(f"{DIM}{time_str}{RESET}  ~{i}min  Price: {BOLD}{price_close}{RESET}  Trend: {trend}  Vol: {vol}")
        print(f"  Verdict: {color}{BOLD}{result['verdict']}{RESET}  [{result.get('bet_type','?')} | {result.get('confidence','?')}]")
        print(f"  {DIM}{result.get('reasoning','')}{RESET}\n")

        if not auto:
            try:
                cmd = input("  [ENTER] next  [r] re-ask AI  [q] quit > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if cmd == "q":
                break
            elif cmd == "r":
                history.append({"role": "user", "content": f"Reconsider. Same snapshot:\n{candle_summary}"})
                result = _call_ai(history)
                history.append({"role": "assistant", "content": json.dumps(result)})
                save_verdict(ticker, ts, result["verdict"], result["reasoning"])
                color = _verdict_color(result["verdict"])
                print(f"  Re-ask → {color}{BOLD}{result['verdict']}{RESET}: {result.get('reasoning','')}\n")
        else:
            time.sleep(0.3)

    print(f"\n{'='*50}")
    print(f"MATCH RESULT for {ticker}")
    market_result = market_info.get("result") or "unknown"
    print(f"Resolved: {BOLD}{market_result}{RESET}")
    print(f"{'='*50}\n")