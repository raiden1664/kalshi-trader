"""
BuyWatcher — monitors prices and fires conditional buy orders.
Completely independent of the OCO sell poller.
"""
import threading
import time
import json
from pathlib import Path

WATCHES_FILE  = Path.home() / ".kalshi_trader" / "watches.json"
POLL_INTERVAL = 15  # seconds


class BuyWatcher:
    """
    Runs a single background thread that polls all active watches.
    Each watch: { id, ticker, side, trigger_price, dollars, label }
    When yes_ask <= trigger_price → places FOK buy → removes watch.
    """

    def __init__(self, app):
        self._app      = app
        self._watches  = {}   # id -> watch dict
        self._lock     = threading.Lock()
        self._stop     = threading.Event()
        self._thread   = None
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def add_watch(self, ticker: str, side: str, trigger_price: int,
                  dollars: float, label: str) -> str:
        """Add a new watch. Returns the watch ID."""
        import uuid
        wid = str(uuid.uuid4())[:8]
        watch = dict(
            id=wid, ticker=ticker, side=side,
            trigger_price=trigger_price, dollars=dollars, label=label
        )
        with self._lock:
            self._watches[wid] = watch
        self._save()
        return wid

    def remove_watch(self, wid: str):
        with self._lock:
            self._watches.pop(wid, None)
        self._save()

    def get_watches(self) -> list:
        with self._lock:
            return list(self._watches.values())

    def get_watch_for_ticker(self, ticker: str) -> dict | None:
        """Return first watch matching the given ticker (or match_key prefix)."""
        match_key = "-".join(ticker.split("-")[:-1]) if "-" in ticker else ticker
        with self._lock:
            for w in self._watches.values():
                w_key = "-".join(w["ticker"].split("-")[:-1])
                if w["ticker"] == ticker or w_key == match_key:
                    return w
        return None

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self):
        try:
            WATCHES_FILE.parent.mkdir(exist_ok=True)
            with self._lock:
                data = list(self._watches.values())
            WATCHES_FILE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _load(self):
        if not WATCHES_FILE.exists():
            return
        try:
            data = json.loads(WATCHES_FILE.read_text())
            with self._lock:
                self._watches = {w["id"]: w for w in data}
        except Exception:
            pass

    # ── Poll loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        self._stop.wait(2.0)  # small startup delay
        while not self._stop.is_set():
            self._check_all()
            self._stop.wait(POLL_INTERVAL)

    def _check_all(self):
        from src.api import fetch_market, place_order
        with self._lock:
            watches = list(self._watches.values())

        for w in watches:
            if self._stop.is_set():
                break
            try:
                market = fetch_market(w["ticker"])
                if not market:
                    continue

                side      = w["side"].lower()
                price_key = "yes_ask" if side == "yes" else "no_ask"
                live_price = market.get(price_key) or 999

                if live_price <= w["trigger_price"]:
                    self._fire(w, live_price)
            except Exception:
                pass

    def _fire(self, watch: dict, live_price: int):
        """Trigger condition met — place the buy order."""
        from src.api import place_order

        # Remove watch immediately so it doesn't double-fire
        self.remove_watch(watch["id"])

        try:
            side      = watch["side"].lower()
            yes_price = live_price if side == "yes" else (100 - live_price)
            no_price  = live_price if side == "no"  else (100 - live_price)

            order = place_order(
                ticker    = watch["ticker"],
                side      = side,
                action    = "buy",
                dollars   = watch["dollars"],
                yes_price = yes_price,
                no_price  = no_price,
            )
            filled = order.get("fill_count", order.get("count", "?"))
            msg    = (
                f"[#00e676]✓ Watch triggered: {watch['label']} {side.upper()} "
                f"@ {live_price}¢ — {filled} contracts filled[/#00e676]"
            )
        except Exception as e:
            msg = f"[#ff4444]✗ Watch triggered but order failed: {e}[/#ff4444]"

        # Notify the app
        try:
            self._app.call_from_thread(self._app.notify_watch_fired, watch, msg)
        except Exception:
            pass