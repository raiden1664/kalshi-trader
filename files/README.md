# kalshi-trader

A terminal-based trading dashboard for [Kalshi](https://kalshi.com) focused on sports markets (tennis + NBA/NCAAB). Built around a disciplined momentum + mispricing strategy.

## Features

- Live terminal dashboard (auto-refreshes every 30s)
- Filters open markets to sports only
- Classifies opportunities by type:
  - **Type 1** (cyan) — 80–90¢ near-locks
  - **Type 2** (green) — 55–75¢ mispriced value plays
- Shows open positions and cash balance

## Project Structure

```
kalshi-trader/
├── src/
│   ├── dashboard.py   # Entry point & main loop
│   ├── config.py      # All settings (price ranges, keywords, etc.)
│   ├── auth.py        # Kalshi login / session token
│   ├── api.py         # API calls (balance, positions, markets)
│   ├── filter.py      # Market filtering & classification
│   └── render.py      # Terminal UI (Rich)
├── tests/
├── requirements.txt
└── .gitignore
```

## Setup

### 1. Clone and install dependencies
```bash
git clone git@github.com:YOUR_USERNAME/kalshi-trader.git
cd kalshi-trader
pip install -r requirements.txt
```

### 2. Set credentials as environment variables
```bash
export KALSHI_EMAIL='you@email.com'
export KALSHI_PASSWORD='yourpassword'
```

Add to `~/.zshrc` to make permanent:
```bash
echo "export KALSHI_EMAIL='you@email.com'" >> ~/.zshrc
echo "export KALSHI_PASSWORD='yourpassword'" >> ~/.zshrc
source ~/.zshrc
```

### 3. Run
```bash
python -m src.dashboard
```

Press `Ctrl+C` to exit.

## Configuration

Edit `src/config.py` to adjust:

| Setting | Default | Description |
|---|---|---|
| `REFRESH_SECONDS` | `30` | Dashboard refresh rate |
| `TYPE1_MIN/MAX` | `0.80–0.90` | Type 1 price range |
| `TYPE2_MIN/MAX` | `0.55–0.75` | Type 2 price range |
| `HARD_PRICE_CEILING` | `0.70` | Never buy above this |
| `SPORT_KEYWORDS` | tennis, nba... | Markets to surface |

## Roadmap

- [ ] Phase 2 — Live score feed (tennis momentum triggers, NBA live)
- [ ] Phase 3 — Telegram alerts on qualifying setups
- [ ] Phase 4 — Auto-execution with position sizing
- [ ] Phase 5 — Web UI

## ⚠️ Disclaimer

This is a personal tool. Prediction market trading involves risk. Never bet more than you can afford to lose.
