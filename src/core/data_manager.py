"""
data_manager.py — Orchestrates data fetching, processing, and state.

Owns the refresh loop and sport availability probing. Delegates all
fetching to markets_api, filtering to market_filter, parsing to
market_parser, and classification to classifier.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from src.constants import SERIES, SPORTS_SECTION, ANOMALY_VOLUME_THRESHOLD, \
    ANOMALY_ODDS_LOW, ANOMALY_ODDS_HIGH, PRICE_MOVE_THRESHOLD, LARGE_SINGLE_TRADE_USD
from src.data.markets_api import fetch_series, fetch_series_concurrent
from src.data.market_filter import filter_active, is_live
from src.data.market_parser import group_by_match, extract_names, match_label
from src.data.classifier import price_color, price_bucket
from src.api import fetch_balance, fetch_positions, fetch_trades
from src.core.notification_store import NotificationStore, Alert
from src.core import settings as cfg

# All sports the manager knows about (sports + politics)
_ALL_SPORTS = SPORTS_SECTION + ["politics"]


class DataManager:
    def __init__(self, app, refresh_interval: int = 60):
        self._app             = app
        self.refresh_interval = refresh_interval

        # Per-sport state
        self._rows:   dict[str, list] = {s: [] for s in _ALL_SPORTS}
        self._groups: dict[str, dict] = {s: {} for s in _ALL_SPORTS}
        self._loaded: dict[str, bool] = {s: False for s in _ALL_SPORTS}

        # Price tracking for move alerts
        self._prev_prices: dict[str, float] = {}
        self._seen_trades: set              = set()

        # Sports that are actively being fetched
        self._active_sports: set = {"tennis"}
        # Sports confirmed to have active markets (populated by probe)
        self._available_sports: set     = set()
        self._availability_callback     = None

        self.balance:   dict = {}
        self.positions: list = []
        self.notifications = NotificationStore()

        s = cfg.load()
        self.notification_filter: dict = dict(s.get("notifications", {
            "tennis": True, "basketball": True, "politics": True
        }))

        self._stop_event    = threading.Event()
        self._thread        = None
        self._refresh_count = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    # ── Public API ────────────────────────────────────────────────────────────

    def request_sport(self, sport: str):
        """Add a sport to the active set and kick off a fetch if not yet loaded."""
        self._active_sports.add(sport)
        if not self._loaded[sport]:
            threading.Thread(target=self._fetch_sport, args=(sport,), daemon=True).start()

    def get_rows(self, sport: str) -> list:
        return self._rows.get(sport, [])

    def get_groups(self, sport: str) -> dict:
        return self._groups.get(sport, {})

    def is_loaded(self, sport: str) -> bool:
        return self._loaded.get(sport, False)

    def available_sports(self) -> list:
        """Sports with confirmed active markets, returned in display order."""
        return [s for s in SPORTS_SECTION if s == "tennis" or s in self._available_sports]

    def probe_available_sports(self, callback: Callable = None):
        """
        Lightweight background probe for all non-tennis sports.
        Fires callback each time a sport is confirmed available.
        Called after tennis loads to avoid slowing initial render.
        """
        self._availability_callback = callback
        for sport in SPORTS_SECTION:
            if sport == "tennis":
                continue
            threading.Thread(target=self._probe_sport, args=(sport,), daemon=True).start()

    # ── Refresh loop ──────────────────────────────────────────────────────────

    def _loop(self):
        # Small delay so the UI is fully mounted before first data arrives
        self._stop_event.wait(1.5)
        if self._stop_event.is_set():
            return
        self._fetch_all()
        self._fetch_portfolio()
        while not self._stop_event.wait(self.refresh_interval):
            self._refresh_count += 1
            self._fetch_all()
            self._fetch_portfolio()
            # Trade scan runs every 3rd refresh to avoid hammering the API
            if self._refresh_count % 3 == 0:
                threading.Thread(target=self._scan_all_trades, daemon=True).start()

    def _fetch_all(self):
        sports = list(self._active_sports)
        if not sports:
            return
        with ThreadPoolExecutor(max_workers=len(sports)) as ex:
            futures = {ex.submit(self._fetch_sport, s): s for s in sports}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception:
                    pass

    # ── Sport fetching ────────────────────────────────────────────────────────

    def _fetch_sport(self, sport: str):
        """
        Two-phase fetch for a sport:
        Phase 1: serve stale disk cache immediately → screen renders right away
        Phase 2: fetch fresh data → silently update state
        """
        try:
            series_list = SERIES.get(sport, [])

            # Phase 1 — instant render from disk cache if available
            stale = []
            for s in series_list:
                stale.extend(fetch_series(s, stale_ok=True))
            if stale:
                groups = group_by_match(filter_active(stale))
                rows, _ = self._process(groups, sport)
                self._groups[sport] = groups
                self._rows[sport]   = rows
                self._loaded[sport] = True

            # Phase 2 — fresh network fetch
            fresh    = fetch_series_concurrent(series_list)
            groups   = group_by_match(filter_active(fresh))
            rows, alerts = self._process(groups, sport)

            self._groups[sport] = groups
            self._rows[sport]   = rows
            self._loaded[sport] = True

            for alert in alerts:
                self.notifications.add(alert)

        except Exception as e:
            import traceback
            self._last_error = f"{sport}: {e}\n{traceback.format_exc()}"

    def _probe_sport(self, sport: str):
        """Check if a sport has any active markets; mark it available if so."""
        try:
            markets = fetch_series_concurrent(SERIES.get(sport, []))
            if filter_active(markets):
                self._available_sports.add(sport)
                if self._availability_callback:
                    try:
                        self._app.call_from_thread(self._availability_callback)
                    except Exception:
                        pass
        except Exception:
            pass

    # ── Processing ────────────────────────────────────────────────────────────

    def _process(self, groups: dict, sport: str) -> tuple[list, list]:
        """
        Convert raw market groups into display rows and generate alerts.
        Returns (rows, alerts).
        """
        rows   = []
        alerts = []
        notif_on = self.notification_filter.get(sport, True)

        for key, mm in groups.items():
            mm.sort(key=lambda m: m.get("ticker", ""))
            label  = match_label(mm)
            p1, p2 = extract_names(mm)

            # Use the contract with the highest yes_ask as the representative price
            best  = max(mm, key=lambda m: m.get("yes_ask") or 0)
            yes_p = (best.get("yes_ask") or 0) / 100
            no_p  = (best.get("no_ask")  or 0) / 100
            vol   = sum((m.get("volume") or 0) for m in mm)
            live  = any(is_live(m) for m in mm)
            event_ticker = mm[0].get("event_ticker", "") if mm else ""

            rows.append((
                key, p1, p2, yes_p, no_p, vol,
                price_color(yes_p), price_bucket(yes_p), sport,
                live, event_ticker
            ))

            for m in mm:
                self._prev_prices[m.get("ticker", "")] = (m.get("yes_ask") or 0) / 100

            if not notif_on:
                continue

            # Volume anomaly alerts
            if vol >= ANOMALY_VOLUME_THRESHOLD:
                if yes_p <= ANOMALY_ODDS_LOW:
                    alerts.append(Alert(
                        message="Extreme low odds with high volume",
                        severity="warning", price=yes_p, match=label))
                elif yes_p >= ANOMALY_ODDS_HIGH:
                    alerts.append(Alert(
                        message=f"${vol:,} volume at near-lock odds",
                        severity="warning", price=yes_p, match=label))

            # Price movement alerts
            for m in mm:
                ticker     = m.get("ticker", "")
                curr_price = (m.get("yes_ask") or 0) / 100
                prev_price = self._prev_prices.get(ticker)
                if prev_price is not None:
                    move = abs(curr_price - prev_price)
                    if move >= PRICE_MOVE_THRESHOLD:
                        direction = "UP" if curr_price > prev_price else "DOWN"
                        alerts.append(Alert(
                            message=f"Price moved {direction}: {prev_price:.0%} → {curr_price:.0%}",
                            severity="information", price=curr_price, match=label))

        return rows, alerts

    # ── Portfolio ─────────────────────────────────────────────────────────────

    def _fetch_portfolio(self):
        try:
            self.balance   = fetch_balance()
            self.positions = fetch_positions()
        except Exception:
            pass

    # ── Trade scanning ────────────────────────────────────────────────────────

    def _scan_all_trades(self):
        """Scan recent trades across all active markets for large-order alerts."""
        all_markets = []
        for sport in list(self._active_sports):
            if not self.notification_filter.get(sport, True):
                continue
            for mm in self._groups.get(sport, {}).values():
                all_markets.extend(mm)

        alerts = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(self._scan_market_trades, m): m for m in all_markets}
            for f in as_completed(futures):
                try:
                    alerts.extend(f.result())
                except Exception:
                    pass
        for alert in alerts:
            self.notifications.add(alert)

    def _scan_market_trades(self, market: dict) -> list:
        alerts = []
        ticker = market.get("ticker", "")
        try:
            trades = fetch_trades(ticker, limit=20)
            for trade in trades:
                trade_id = trade.get("trade_id", "")
                if trade_id in self._seen_trades:
                    continue
                self._seen_trades.add(trade_id)
                count     = float(trade.get("count_fp") or trade.get("count") or 0)
                side      = trade.get("taker_side", "yes")
                price_key = "yes_price_dollars" if side == "yes" else "no_price_dollars"
                trade_usd = count * float(trade.get(price_key) or 0)
                yes_price = float(trade.get("yes_price_dollars") or 0)
                if trade_usd >= LARGE_SINGLE_TRADE_USD:
                    alerts.append(Alert(
                        message=f"${trade_usd:,.2f} single {side.upper()} bet",
                        severity="warning", price=yes_price,
                        match=match_label([market])))
        except Exception:
            pass
        return alerts