"""
Position detail screen — opened from the dashboard when viewing an open position.
Inherits full buy flow from MatchScreen, adds position summary + OCO exit orders
(take profit + stop loss). App-managed: poller cancels survivor when one fills.
"""
from textual.binding import Binding
from textual.widgets import Static, Header, Footer
from textual import work
import threading
import time
import json
from pathlib import Path

from src.screens.match_detail import MatchScreen, BUY_OFF
from src.tennis import _extract_names


# Input sub-states for the OCO setup flow
_OCO_OFF = "off"
_OCO_TP  = "tp"   # entering take profit price
_OCO_SL  = "sl"   # entering stop loss price

POLL_INTERVAL = 30  # seconds
OCO_DIR = Path.home() / ".kalshi_trader"
OCO_DIR.mkdir(exist_ok=True)


class PositionMatchScreen(MatchScreen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    _oco_mode:    str  = _OCO_OFF
    _oco_input:   str  = ""
    _oco_status:  str  = ""

    # Active OCO order IDs (empty string = not placed)
    _tp_order_id: str  = ""
    _sl_order_id: str  = ""

    # Stored prices for display
    _tp_price:    int  = 0
    _sl_price:    int  = 0

    # Poller state
    _poll_thread: object = None
    _poll_stop:   bool   = False

    def __init__(self, match_key: str, match_markets: list, position: dict = None):
        super().__init__(match_key=match_key, match_markets=match_markets)
        self.position = position or {}

    def compose(self):
        p1, p2 = _extract_names(self.match_markets)
        yield Header()
        yield Static(
            f"[bold white]{p1} vs {p2}[/bold white]\n\n[dim]Loading...[/dim]",
            id="detail"
        )
        yield Static("", id="buy_block")
        yield Static("", id="pos_block")
        yield Static("", id="limit_block")
        yield Footer()

    # ── OCO state persistence ─────────────────────────────────────────────────

    def _oco_state_path(self) -> Path:
        ticker = self.position.get("ticker", "unknown")
        safe   = ticker.replace("/", "_")
        return OCO_DIR / f"oco_{safe}.json"

    def _save_oco_state(self):
        """Persist OCO order IDs to disk so they survive app restarts."""
        data = {
            "tp_order_id": self._tp_order_id,
            "sl_order_id": self._sl_order_id,
            "tp_price":    self._tp_price,
            "sl_price":    self._sl_price,
            "ticker":      self.position.get("ticker", ""),
        }
        try:
            self._oco_state_path().write_text(json.dumps(data))
        except Exception:
            pass

    def _load_oco_state(self):
        """Load persisted OCO state on screen open. Resumes poller if orders exist."""
        path = self._oco_state_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._tp_order_id = data.get("tp_order_id", "")
            self._sl_order_id = data.get("sl_order_id", "")
            self._tp_price    = data.get("tp_price", 0)
            self._sl_price    = data.get("sl_price", 0)
            if self._tp_order_id or self._sl_order_id:
                self._oco_status = f"[dim]OCO restored from {path.name}[/dim]"
                self._maybe_start_poller()
                self._refresh_limit_block()
        except Exception as e:
            self._oco_status = f"[red]OCO load failed: {e}[/red]"
            self._refresh_limit_block()

    def _clear_oco_state(self):
        """Delete persisted state file when all orders are gone."""
        try:
            self._oco_state_path().unlink(missing_ok=True)
        except Exception:
            pass

    def on_mount(self):
        """Load persisted OCO state as soon as screen mounts."""
        self._load_oco_state()
        self._oco_loaded = True

    def on_unmount(self):
        """Stop poller when screen is removed."""
        self._poll_stop = True

    def _show(self, trend_data: dict, live_score):
        super()._show(trend_data, live_score)
        self._show_position()
        self._refresh_limit_block()

    def _show_position(self):
        pos = self.position
        if not pos:
            return

        ticker   = pos.get("ticker", "")
        slug     = ticker.split("-")[-1].upper()
        count    = abs(pos.get("position", 0))
        exposure = (pos.get("market_exposure") or 0) / 100
        traded   = (pos.get("total_traded") or 0) / 100
        pnl_raw  = pos.get("realized_pnl", 0)
        pnl      = (pnl_raw if isinstance(pnl_raw, (int, float)) else 0) / 100
        fees     = (pos.get("fees_paid") or 0) / 100
        avg_cost = (traded / count * 100) if count else 0

        unrealized = None
        for m in self.match_markets:
            if m.get("ticker", "").split("-")[-1].upper() == slug:
                yes_ask = m.get("yes_ask") or 0
                if yes_ask and avg_cost:
                    unrealized = (yes_ask - avg_cost) * count / 100
                break

        lines = [
            "─" * 52, "",
            "  [bold white]Your Position[/bold white]", "",
            f"  [dim]Contract[/dim]   [#00e676]YES[/#00e676] {slug.capitalize()}",
            f"  [dim]Contracts[/dim]  [white]{count}[/white]",
            f"  [dim]Avg cost[/dim]   [white]{avg_cost:.0f}¢[/white]",
            f"  [dim]Exposure[/dim]   [white]${exposure:.2f}[/white]",
        ]
        if unrealized is not None:
            col  = "#00e676" if unrealized >= 0 else "#ff4444"
            sign = "+" if unrealized >= 0 else ""
            lines.append(f"  [dim]Unrealized[/dim] [{col}]{sign}${unrealized:.2f}[/{col}]")
        if pnl != 0:
            col  = "#00e676" if pnl >= 0 else "#ff4444"
            sign = "+" if pnl >= 0 else ""
            lines.append(f"  [dim]Realized[/dim]   [{col}]{sign}${pnl:.2f}[/{col}]")
        lines += [f"  [dim]Fees paid[/dim]  [dim]${fees:.2f}[/dim]", ""]
        self.query_one("#pos_block", Static).update("\n".join(lines))

    # ── OCO block rendering ───────────────────────────────────────────────────

    def _refresh_limit_block(self):
        pos    = self.position
        count  = abs(pos.get("position", 0)) if pos else 0
        ticker = pos.get("ticker", "")
        slug   = ticker.split("-")[-1].capitalize() if ticker else ""

        lines = ["─" * 52, "", "  [bold white]Exit Orders[/bold white]", ""]

        if self._oco_mode == _OCO_TP:
            price  = self._oco_input or "_"
            status = f"\n  [yellow]{self._oco_status}[/yellow]" if self._oco_status else ""
            lines += [
                f"  Take profit for [white]{count}[/white] × {slug} YES:",
                f"  [bold #00e676]{price}¢[/bold #00e676]   [dim]Enter confirm · Esc cancel[/dim]",
                status, "",
                "  [dim](Stop loss can be set with S after)[/dim]", "",
            ]
            self.query_one("#limit_block", Static).update("\n".join(lines))
            return

        if self._oco_mode == _OCO_SL:
            price  = self._oco_input or "_"
            status = f"\n  [yellow]{self._oco_status}[/yellow]" if self._oco_status else ""
            lines += [
                f"  Stop loss for [white]{count}[/white] × {slug} YES:",
                f"  [bold #ff4444]{price}¢[/bold #ff4444]   [dim]Enter confirm · Esc cancel[/dim]",
                status, "",
                "  [dim](Take profit can be set with T after)[/dim]", "",
            ]
            self.query_one("#limit_block", Static).update("\n".join(lines))
            return

        has_tp = bool(self._tp_order_id)
        has_sl = bool(self._sl_order_id)

        if has_tp or has_sl:
            if has_tp:
                lines.append(
                    f"  [#00e676]▲ Take profit[/#00e676]  [white]{self._tp_price}¢[/white]"
                    f"  [green]● resting[/green]  [dim]{self._tp_order_id[:10]}[/dim]"
                )
            else:
                lines.append("  [dim]▲ Take profit  not set — T to add[/dim]")

            if has_sl:
                lines.append(
                    f"  [#ff4444]▼ Stop loss[/#ff4444]    [white]{self._sl_price}¢[/white]"
                    f"  [green]● resting[/green]  [dim]{self._sl_order_id[:10]}[/dim]"
                )
            else:
                lines.append("  [dim]▼ Stop loss    not set — S to add[/dim]")

            lines += [
                "",
                "  [dim]T[/dim] = Change take profit   "
                "[dim]S[/dim] = Change stop loss   "
                "[dim]X[/dim] = Cancel all",
                "",
            ]
        else:
            if self._oco_status:
                lines += [f"  [yellow]{self._oco_status}[/yellow]", ""]
            lines += [
                "  [dim]T[/dim] = Set take profit  (sell high)",
                "  [dim]S[/dim] = Set stop loss   (sell low)",
                "  [dim]Both active = OCO: first fill cancels other[/dim]",
                "",
            ]

        self.query_one("#limit_block", Static).update("\n".join(lines))

    # ── Key handling ─────────────────────────────────────────────────────────

    def on_key(self, event):
        if self._oco_mode != _OCO_OFF:
            if event.key == "escape":
                self._oco_mode   = _OCO_OFF
                self._oco_input  = ""
                self._oco_status = ""
                self._refresh_limit_block()
                event.stop()
            elif event.key == "backspace":
                self._oco_input = self._oco_input[:-1]
                self._refresh_limit_block()
                event.stop()
            elif event.key == "enter":
                self._commit_oco_input()
                event.stop()
            elif event.character and event.character in "0123456789":
                self._oco_input += event.character
                self._refresh_limit_block()
                event.stop()
            return

        if self._buy_state == BUY_OFF:
            if event.key == "t":
                self._oco_mode   = _OCO_TP
                self._oco_input  = ""
                self._oco_status = ""
                self._refresh_limit_block()
                event.stop()
                return
            if event.key == "s":
                self._oco_mode   = _OCO_SL
                self._oco_input  = ""
                self._oco_status = ""
                self._refresh_limit_block()
                event.stop()
                return
            if event.key == "x" and (self._tp_order_id or self._sl_order_id):
                self._cancel_all_exits()
                event.stop()
                return

        super().on_key(event)

    # ── Order placement ───────────────────────────────────────────────────────

    def _commit_oco_input(self):
        try:
            price_cents = int(self._oco_input)
        except ValueError:
            self._oco_status = "[red]Enter whole cents 1–99[/red]"
            self._refresh_limit_block()
            return
        if not 1 <= price_cents <= 99:
            self._oco_status = "[red]Must be 1–99[/red]"
            self._refresh_limit_block()
            return

        mode = self._oco_mode
        self._oco_mode  = _OCO_OFF
        self._oco_input = ""
        self._place_exit_order(price_cents, is_tp=(mode == _OCO_TP))

    @work(thread=True)
    def _place_exit_order(self, price_cents: int, is_tp: bool):
        from src.api import place_order, cancel_order

        pos    = self.position
        count  = abs(pos.get("position", 0))
        ticker = pos.get("ticker", "")
        if not ticker or not count:
            return

        label = "take profit" if is_tp else "stop loss"

        # Cancel existing order of this type before replacing
        existing_id = self._tp_order_id if is_tp else self._sl_order_id
        if existing_id:
            try:
                cancel_order(existing_id)
            except Exception:
                pass

        self.app.call_from_thread(
            self._set_oco_status,
            f"Placing {label}: {count} × @ {price_cents}¢..."
        )
        try:
            order    = place_order(
                ticker=ticker, side="yes", action="sell",
                yes_price=price_cents, count=count,
            )
            order_id = order.get("order_id", "")
            if is_tp:
                self._tp_order_id = order_id
                self._tp_price    = price_cents
            else:
                self._sl_order_id = order_id
                self._sl_price    = price_cents

            self.app.call_from_thread(self._set_oco_status, "")
            self._save_oco_state()
            self.app.call_from_thread(self._refresh_limit_block)
            self._maybe_start_poller()

        except Exception as e:
            self.app.call_from_thread(self._set_oco_status, f"[red]{e}[/red]")

    @work(thread=True)
    def _cancel_all_exits(self):
        from src.api import cancel_order
        for oid in [self._tp_order_id, self._sl_order_id]:
            if oid:
                try:
                    cancel_order(oid)
                except Exception:
                    pass
        self._tp_order_id = ""
        self._sl_order_id = ""
        self._tp_price    = 0
        self._sl_price    = 0
        self._poll_stop   = True
        self._clear_oco_state()
        self.app.call_from_thread(self._set_oco_status, "All exit orders cancelled.")
        self.app.call_from_thread(self._refresh_limit_block)

    # ── OCO poller ────────────────────────────────────────────────────────────

    def _maybe_start_poller(self):
        if self._poll_thread and self._poll_thread.is_alive():
            return
        if not (self._tp_order_id or self._sl_order_id):
            return
        self._poll_stop   = False
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        """Poll every POLL_INTERVAL seconds. Cancel survivor when one fills."""
        from src.api import fetch_open_orders, cancel_order

        while not self._poll_stop:
            time.sleep(POLL_INTERVAL)
            if self._poll_stop:
                break

            tp_id = self._tp_order_id
            sl_id = self._sl_order_id

            if not tp_id and not sl_id:
                break

            try:
                ticker   = self.position.get("ticker", "")
                open_ids = {
                    o.get("order_id")
                    for o in fetch_open_orders(ticker=ticker)
                }

                tp_filled = bool(tp_id) and tp_id not in open_ids
                sl_filled = bool(sl_id) and sl_id not in open_ids

                if tp_filled and sl_filled:
                    self._tp_order_id = ""
                    self._sl_order_id = ""
                    self._clear_oco_state()
                    self.app.call_from_thread(
                        self._set_oco_status, "[yellow]Both orders filled![/yellow]"
                    )
                    self.app.call_from_thread(self._refresh_limit_block)
                    break

                elif tp_filled and sl_id:
                    try:
                        cancel_order(sl_id)
                    except Exception:
                        pass
                    self._tp_order_id = ""
                    self._sl_order_id = ""
                    self._clear_oco_state()
                    self.app.call_from_thread(
                        self._set_oco_status,
                        "[#00e676]Take profit filled! Stop loss cancelled.[/#00e676]"
                    )
                    self.app.call_from_thread(self._refresh_limit_block)
                    break

                elif sl_filled and tp_id:
                    try:
                        cancel_order(tp_id)
                    except Exception:
                        pass
                    self._tp_order_id = ""
                    self._sl_order_id = ""
                    self._clear_oco_state()
                    self.app.call_from_thread(
                        self._set_oco_status,
                        "[#ff4444]Stop loss filled! Take profit cancelled.[/#ff4444]"
                    )
                    self.app.call_from_thread(self._refresh_limit_block)
                    break

            except Exception:
                pass  # network hiccup — retry next interval

    def _set_oco_status(self, msg: str):
        self._oco_status = msg
        self._refresh_limit_block()