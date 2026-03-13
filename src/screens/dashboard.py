from textual.screen import Screen
from textual.widgets import Static, Header, Footer
from textual.binding import Binding
from textual import work
from datetime import datetime

from src.api import fetch_balance, fetch_positions, fetch_market
from src.widgets.bell import BellWidget
from src.widgets.mode_bar import ModeBar
from src.widgets.notification_panel import NotificationPanel
from src.core.paper import PAPER_COLOR


class DashboardScreen(Screen):
    BINDINGS = [
        Binding("m", "markets",       "Markets"),
        Binding("s", "settings",      "Settings"),
        Binding("n", "notifications", "Notifications"),
        Binding("q", "app.quit",      "Quit"),
    ]

    _positions:   list = []
    _pos_markets: dict = {}
    _cursor:      int  = 0

    def compose(self):
        yield Header()
        yield ModeBar(id="mode_bar")
        with Static(id="bell_row"):
            yield Static("", id="bell_spacer")
            yield BellWidget(id="bell")
        yield NotificationPanel(id="notif_panel")
        yield Static("", id="stats")
        yield Footer()

    def on_mount(self):
        self._load_stats()
        self.set_interval(30, self._load_stats)

    def action_notifications(self): self.app.toggle_notifications()
    def action_markets(self):
        from src.screens.markets import MatchListScreen
        self.app.push_screen(MatchListScreen())
    def action_settings(self):
        from src.screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen())

    @work(thread=True)
    def _load_stats(self):
        try:
            if self.app.paper_mode:
                self.app.call_from_thread(self._draw_paper)
            else:
                bal = fetch_balance()
                pos = fetch_positions()
                self.app.data_manager.balance   = bal
                self.app.data_manager.positions = pos
                self._prefetch_pos_markets(pos)
                self.app.call_from_thread(self._draw, bal, pos)
        except Exception as e:
            self.app.call_from_thread(
                self.query_one("#stats", Static).update,
                f"[#ff4444]Error: {e}[/#ff4444]")

    def _draw_paper(self):
        ledger = self.app.paper_ledger
        cash   = ledger.balance
        pos    = ledger.positions
        now    = datetime.now().strftime("%H:%M:%S")
        pc     = PAPER_COLOR

        lines = [
            f"[bold magenta]kalshi-trader[/bold magenta]  [dim]{now}[/dim]"
            f"  [bold {pc}]◆ PAPER MODE[/bold {pc}]", "",
            f"  [dim]Cash[/dim]       [bold {pc}]${cash:.2f}[/bold {pc}]",
            f"  [dim]Portfolio[/dim]  [bold {pc}]${'%.2f' % sum(p.get('current_value', 0) for p in pos)}[/bold {pc}]",
            f"  [dim]Total[/dim]      [bold {pc}]${'%.2f' % (cash + sum(p.get('current_value', 0) for p in pos))}[/bold {pc}]",
            "",
        ]

        if pos:
            lines.append(f"  [dim]Paper Positions — ↑↓ to move, Enter to open[/dim]")
            for i, p in enumerate(pos[:8]):
                label = p.get("label", p.get("ticker", ""))
                side  = p.get("side", "yes").upper()
                count = p.get("count", 0)
                avg   = p.get("avg_price", 0)
                row   = f"  [{pc}]{side}[/{pc}]  {label}  [dim]{count} × {avg}¢[/dim]"
                lines.append(f"[reverse]{row}[/reverse]" if i == self._cursor else row)
        else:
            lines.append(f"  [dim {pc}]No paper positions[/dim {pc}]")

        self.query_one("#stats", Static).update("\n".join(lines))

    def _prefetch_pos_markets(self, pos: list):
        import concurrent.futures
        def fetch_pair(ticker):
            parts     = ticker.split("-")
            match_key = "-".join(parts[:-1]) if len(parts) > 1 else ticker
            if match_key in self._pos_markets:
                return
            markets = []
            for side in ("YES", "NO"):
                try:
                    m = fetch_market(f"{match_key}-{side}")
                    if m: markets.append(m)
                except Exception:
                    pass
            if markets:
                self._pos_markets[match_key] = markets
        tickers = [p.get("ticker", "") for p in (pos or []) if p.get("ticker")]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(fetch_pair, tickers))

    def _resolve_label(self, ticker: str, cached: list) -> str:
        """Derive a human-readable 'P1 vs P2' label from cached market data."""
        from src.tennis import _extract_names
        parts     = ticker.split("-")
        match_key = "-".join(parts[:-1]) if len(parts) > 1 else ticker

        if cached:
            p1, p2 = _extract_names(cached)
            if p1 != "P1":
                return f"{p1} vs {p2}"
            title = cached[0].get("title", "")
            if " vs " in title:
                before = title[:title.index(" vs ")].split()[-1]
                after  = title[title.index(" vs ")+4:].split(":")[0].strip()
                return f"{before} vs {after.split()[-1] if after.split() else 'P2'}"

        return match_key

    def _draw(self, bal, pos):
        raw_bal  = bal.get("balance", 0)
        raw_port = bal.get("portfolio_value", 0)
        cash = (raw_bal  if isinstance(raw_bal,  (int, float)) else 0) / 100
        port = (raw_port if isinstance(raw_port, (int, float)) else 0) / 100
        now  = datetime.now().strftime("%H:%M:%S")

        self._positions = pos or []
        if self._cursor >= len(self._positions):
            self._cursor = max(0, len(self._positions) - 1)

        lines = [
            f"[bold magenta]kalshi-trader[/bold magenta]  [dim]{now}[/dim]", "",
            f"  [dim]Cash[/dim]       [bold #00e676]${cash:.2f}[/bold #00e676]",
            f"  [dim]Portfolio[/dim]  [bold #ffd700]${port:.2f}[/bold #ffd700]",
            f"  [dim]Total[/dim]      [bold white]${cash+port:.2f}[/bold white]",
            "",
        ]

        if self._positions:
            lines.append("  [dim]Open Positions — ↑↓ to move, Enter to open[/dim]")
            for i, p in enumerate(self._positions[:8]):
                ticker    = p.get("ticker", "")
                parts     = ticker.split("-")
                match_key = "-".join(parts[:-1]) if len(parts) > 1 else ticker

                # Get cached markets for label + side derivation
                cached = self._pos_markets.get(match_key, [])
                dm     = self.app.data_manager
                for sport in ("tennis", "basketball", "politics"):
                    if match_key in dm.get_groups(sport):
                        cached = dm.get_groups(sport)[match_key]
                        break
                label = self._resolve_label(ticker, cached)

                # Derive side from ticker slug — last segment is the YES player
                slug = parts[-1].upper() if parts else ""
                side = "YES"
                if cached:
                    for m in cached:
                        m_slug = m.get("ticker", "").split("-")[-1].upper()
                        if m_slug == slug:
                            side = "YES"
                            break
                    else:
                        side = "NO"

                # contracts and value — API returns strings
                contracts = int(float(p.get("position_fp") or 0))
                value_usd = float(p.get("market_exposure_dollars") or 0)

                col = "#00e676" if side == "YES" else "#ff4444"
                row = (
                    f"  [{col}]{side}[/{col}]  {label}"
                    f"  [dim]{contracts} contracts · [/dim]"
                    f"[white]${value_usd:.2f}[/white]"
                )
                lines.append(f"[reverse]{row}[/reverse]" if i == self._cursor else row)
        else:
            lines.append("  [dim]No open positions[/dim]")

        self.query_one("#stats", Static).update("\n".join(lines))

    def on_key(self, event):
        if event.key == "up":
            self._cursor = max(0, self._cursor - 1)
            if self.app.paper_mode:
                self._draw_paper()
            else:
                bal = self.app.data_manager.balance or {}
                self._draw(bal, self._positions)
        elif event.key == "down":
            n = len(self.app.paper_ledger.positions if self.app.paper_mode else self._positions)
            self._cursor = min(max(n - 1, 0), self._cursor + 1)
            if self.app.paper_mode:
                self._draw_paper()
            else:
                bal = self.app.data_manager.balance or {}
                self._draw(bal, self._positions)
        elif event.key == "enter":
            if self._positions and not self.app.paper_mode:
                self._open_position(self._positions[self._cursor])

    @work(thread=True)
    def _open_position(self, pos: dict):
        from src.screens.position_detail import PositionMatchScreen
        ticker    = pos.get("ticker", "")
        parts     = ticker.split("-")
        match_key = "-".join(parts[:-1]) if len(parts) > 1 else ticker

        dm = self.app.data_manager
        markets = None
        for sport in ("tennis", "basketball", "politics"):
            groups = dm.get_groups(sport)
            if match_key in groups:
                markets = groups[match_key]
                break

        if not markets:
            try:
                from src.api import fetch_markets
                series = parts[0]
                all_markets = fetch_markets(series_ticker=series)
                from src.tennis import group_by_match
                groups = group_by_match(all_markets)
                markets = groups.get(match_key)
            except Exception:
                pass

        if not markets:
            return

        self.app.call_from_thread(
            self.app.push_screen,
            PositionMatchScreen(match_key=match_key, match_markets=markets, position=pos)
        )