"""
PaperLedger — simulated trading state for paper mode.
Persisted to ~/.kalshi_trader/paper.json
"""
import json
import math
from pathlib import Path
from datetime import datetime

PAPER_FILE = Path.home() / ".kalshi_trader" / "paper.json"
PAPER_COLOR = "#ff9800"          # orange — used everywhere money is fake
PAPER_STARTING_BALANCE = 50.00  # dollars

DEFAULTS = {
    "balance":   PAPER_STARTING_BALANCE,
    "positions": [],   # list of position dicts
    "history":   [],   # list of trade dicts
}


class PaperLedger:
    def __init__(self):
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if PAPER_FILE.exists():
            try:
                data = json.loads(PAPER_FILE.read_text())
                # merge with defaults so new keys always exist
                for k, v in DEFAULTS.items():
                    data.setdefault(k, v)
                return data
            except Exception:
                pass
        return dict(DEFAULTS)

    def _save(self):
        try:
            PAPER_FILE.parent.mkdir(parents=True, exist_ok=True)
            PAPER_FILE.write_text(json.dumps(self._data, indent=2))
        except Exception:
            pass

    def reset(self):
        self._data = dict(DEFAULTS)
        self._data["balance"] = PAPER_STARTING_BALANCE
        self._data["positions"] = []
        self._data["history"] = []
        self._save()

    # ── Read ──────────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        return float(self._data.get("balance", PAPER_STARTING_BALANCE))

    @property
    def positions(self) -> list:
        return self._data.get("positions", [])

    @property
    def history(self) -> list:
        return self._data.get("history", [])

    def portfolio_value(self) -> float:
        """Sum of (count * yes_ask) for all paper positions — caller must supply current prices."""
        # Without live prices this is approximate; dashboard will pass prices in
        return sum(p.get("current_value", 0.0) for p in self.positions)

    # ── Write ─────────────────────────────────────────────────────────────────

    def buy(self, ticker: str, side: str, yes_price_cents: int,
            dollars: float, label: str) -> dict:
        """
        Simulate an instant FOK buy. Deducts dollars from balance.
        Returns a fake order dict.
        """
        price = yes_price_cents / 100
        count = max(1, math.floor(dollars / price))
        cost  = count * price

        if cost > self._data["balance"]:
            raise ValueError(f"Insufficient paper balance (${self._data['balance']:.2f})")

        self._data["balance"] -= cost

        # Merge into existing position if same ticker+side, else append
        existing = next(
            (p for p in self._data["positions"]
             if p["ticker"] == ticker and p["side"] == side), None
        )
        if existing:
            total_count = existing["count"] + count
            avg_price   = (existing["avg_price"] * existing["count"] + yes_price_cents * count) / total_count
            existing["count"]     = total_count
            existing["avg_price"] = avg_price
        else:
            self._data["positions"].append({
                "ticker":        ticker,
                "side":          side,
                "count":         count,
                "avg_price":     yes_price_cents,   # cents
                "current_value": cost,
                "label":         label,
            })

        trade = {
            "type":      "buy",
            "ticker":    ticker,
            "side":      side,
            "count":     count,
            "price":     yes_price_cents,
            "dollars":   cost,
            "label":     label,
            "timestamp": datetime.now().isoformat(),
        }
        self._data["history"].insert(0, trade)
        self._save()

        return {
            "order_id":    f"PAPER-{ticker[:8]}",
            "fill_count":  count,
            "side":        side,
            "yes_price":   yes_price_cents,
            "dollars":     cost,
        }

    def sell(self, ticker: str, side: str, yes_price_cents: int,
             count: int, label: str) -> dict:
        """Simulate a sell — removes position, credits balance."""
        existing = next(
            (p for p in self._data["positions"]
             if p["ticker"] == ticker and p["side"] == side), None
        )
        if not existing:
            raise ValueError("No paper position found for this ticker")

        sell_count = min(count, existing["count"])
        proceeds   = sell_count * (yes_price_cents / 100)
        self._data["balance"] += proceeds

        if sell_count >= existing["count"]:
            self._data["positions"].remove(existing)
        else:
            existing["count"] -= sell_count

        trade = {
            "type":      "sell",
            "ticker":    ticker,
            "side":      side,
            "count":     sell_count,
            "price":     yes_price_cents,
            "dollars":   proceeds,
            "label":     label,
            "timestamp": datetime.now().isoformat(),
        }
        self._data["history"].insert(0, trade)
        self._save()

        return {
            "order_id":   f"PAPER-SELL-{ticker[:8]}",
            "fill_count": sell_count,
            "proceeds":   proceeds,
        }

    def update_position_value(self, ticker: str, current_yes_ask_cents: int):
        """Call this when refreshing prices to keep portfolio_value current."""
        for p in self._data["positions"]:
            if p["ticker"] == ticker:
                p["current_value"] = p["count"] * (current_yes_ask_cents / 100)
        self._save()