# Kalshi Terminal Dashboard

A live terminal dashboard that surfaces Kalshi sports markets matching your betting strategy.

## What it does
- Pulls all open Kalshi markets and filters for **tennis + NBA/NCAAB**
- Flags markets in your price ranges:
  - **Type 1** (cyan): 80–90¢ near-locks
  - **Type 2** (green): 55–75¢ mispriced value plays
- Shows your **open positions** and **cash balance**
- Auto-refreshes every **30 seconds**

---

## Setup

### 1. Install dependencies
```bash
pip install requests rich
```

### 2. Set your Kalshi credentials as environment variables
```bash
export KALSHI_EMAIL='you@email.com'
export KALSHI_PASSWORD='yourpassword'
```

To make these permanent, add those lines to your `~/.zshrc` (or `~/.bash_profile`) and run `source ~/.zshrc`.

### 3. Run the dashboard
```bash
python kalshi_dashboard.py
```

Press `Ctrl+C` to exit.

---

## Customizing

All key settings are at the top of `kalshi_dashboard.py`:

| Variable | Default | What it controls |
|---|---|---|
| `REFRESH_SECONDS` | 30 | How often to refresh |
| `TYPE1_MIN/MAX` | 0.80–0.90 | Type 1 price range |
| `TYPE2_MIN/MAX` | 0.55–0.75 | Type 2 price range |
| `SPORT_KEYWORDS` | tennis, nba, etc. | Markets to show |

---

## Next steps (Phase 2)
- Add Telegram alerts when a qualifying market appears
- Add live score feed (FlashScore / sports API) alongside market prices
- Add auto-execution with position sizing logic
