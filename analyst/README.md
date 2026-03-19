# kalshi-analyst

Standalone AI-powered match analysis tool for Kalshi prediction markets.
Lives inside `kalshi-trader/analyst/` but runs independently.

## Setup

```bash
cd ~/Desktop/kalshi-trader
source venv/bin/activate
pip3 install anthropic --break-system-packages  # if not already installed

export KALSHI_KEY_ID=your_key_id
export ANTHROPIC_API_KEY=your_anthropic_key
```

## Commands

### 1. Fetch historical match data
```bash
# Fetch all sports (tennis ATP, tennis WTA, NCAAB)
python3 analyst/main.py fetch

# Fetch one sport only
python3 analyst/main.py fetch --sport tennis_atp
python3 analyst/main.py fetch --sport ncaab

# Control how many markets to pull (default 50)
python3 analyst/main.py fetch --limit 100
```

### 2. Browse fetched matches
```bash
# List all matches
python3 analyst/main.py list

# Filter by sport
python3 analyst/main.py list --sport tennis_atp
```
Green dot (●) = has candlestick data ready for replay.

### 3. Replay a match with AI verdicts
```bash
# Interactive step-through (press ENTER to advance)
python3 analyst/main.py replay KXATPMATCH-XXXXXXXX-PLAYERA-PLAYERB

# Auto-advance (no prompts)
python3 analyst/main.py replay KXATPMATCH-XXXXXXXX-PLAYERA-PLAYERB --auto

# Adjust step size (default 5 candles = 5 minutes)
python3 analyst/main.py replay KXATPMATCH-XXXXXXXX-PLAYERA-PLAYERB --step 10
```

At each step the AI gives:
- **Verdict**: BUY / HOLD / SELL / PASS
- **Bet type**: Type1 / Type2 / Type3 / N/A
- **Confidence**: high / medium / low
- **Reasoning**: 2–3 sentence explanation

AI verdicts are cached in SQLite so replaying the same match is instant.

Press `r` during replay to re-ask the AI at the current candle.

### 4. AI pattern analysis
```bash
# Analyze patterns across all fetched matches
python3 analyst/main.py patterns

# Sport-specific
python3 analyst/main.py patterns --sport tennis_atp
python3 analyst/main.py patterns --sport ncaab

# Adjust sample size
python3 analyst/main.py patterns --sample 50
```

### 5. View saved pattern analyses
```bash
python3 analyst/main.py history
python3 analyst/main.py history --sport tennis_atp
```

## Data Storage

All data stored in `analyst/data/analyst.db` (SQLite).

Tables:
- `markets` — settled market metadata
- `candlesticks` — 1-minute OHLC price data per market
- `ai_verdicts` — cached AI verdicts per candle
- `ai_patterns` — saved pattern analysis reports

## Notes

- Candlestick data is cached — fetching the same market twice won't re-download
- AI verdicts are also cached per candle — replaying a match reuses prior verdicts
- The AI uses your full trading framework (bet types, entry rules, hard ceilings) as its system prompt
- Pattern analysis works best with 20+ matches of the same sport