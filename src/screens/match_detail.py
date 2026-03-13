"""
match_detail.py — Match detail screen.

Shows live prices, sparklines, and score for a single match.
Buy flow logic is delegated to BuyFlow in buy_flow.py.
"""
import concurrent.futures
from textual.screen import Screen
from textual.widgets import Static, Header, Footer
from textual.binding import Binding
from textual import work

from src.api import fetch_candlesticks
from src.data.market_parser import extract_names
from src.data.classifier import price_color as _price_color, classify as _classify
from src.widgets.sparkline import sparkline
from src.widgets.mode_bar import ModeBar
from src.core.paper import PAPER_COLOR
from src.screens.buy_flow import BuyFlow, BUY_OFF

MATCH_REFRESH_INTERVAL = 20


class MatchScreen(Screen):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "Back")]

    def __init__(self, match_key: str, match_markets: list):
        super().__init__()
        self.match_key     = match_key
        self.match_markets = match_markets
        self._buy          = BuyFlow(self)   # owns all buy state

    def compose(self):
        p1, p2 = extract_names(self.match_markets)
        yield Header()
        yield ModeBar(id="mode_bar")
        yield Static(
            f"[bold white]{p1} vs {p2}[/bold white]\n\n[dim]Loading...[/dim]",
            id="detail"
        )
        yield Static("", id="buy_block")
        yield Static("", id="watch_block")
        yield Footer()

    def on_mount(self):
        self._load()
        self._refresh_buy_block()
        self._refresh_watch_block()
        self.set_interval(MATCH_REFRESH_INTERVAL, self._auto_refresh)

    def _auto_refresh(self):
        # Don't refresh display while user is mid-buy
        if self._buy.state != BUY_OFF:
            return
        self._load()

    # ── Data loading ──────────────────────────────────────────────────────────

    @work(thread=True)
    def _load(self):
        from src.scores import fetch_live_score
        from src.api import fetch_markets
        from src.data.market_parser import group_by_match
        p1, p2 = extract_names(self.match_markets)

        # Fetch fresh prices for this match
        try:
            series = (self.match_markets[0].get("event_ticker") or
                      self.match_key.rsplit("-", 2)[0])
            fresh  = fetch_markets(series_ticker=series)
            groups = group_by_match(fresh)
            if self.match_key in groups:
                candidates = groups[self.match_key]
                has_prices = any(
                    (m.get("yes_ask") or 0) > 0 or (m.get("no_ask") or 0) > 0
                    for m in candidates
                )
                if has_prices:
                    self.match_markets = candidates
        except Exception:
            pass

        # Fetch score and candlesticks concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            score_fut   = ex.submit(fetch_live_score, p1, p2)
            candle_futs = {
                m.get("ticker", ""): ex.submit(self._fetch_candles, m.get("ticker", ""))
                for m in self.match_markets
            }
            live_score = score_fut.result()
            trend_data = {t: f.result() for t, f in candle_futs.items()}

        self.app.call_from_thread(self._show, trend_data, live_score)

    def _fetch_candles(self, ticker: str) -> list:
        try:
            candles = fetch_candlesticks(
                ticker.rsplit("-", 1)[0] if "-" in ticker else ticker,
                ticker, period_interval=1
            )
            return [c["price"]["close"] for c in candles
                    if c.get("price") and c["price"].get("close") is not None]
        except Exception:
            return []

    # ── Display ───────────────────────────────────────────────────────────────

    def _show(self, trend_data: dict, live_score: dict | None):
        from datetime import datetime, timezone
        mm     = sorted(self.match_markets, key=lambda x: x.get("ticker", ""))
        p1, p2 = extract_names(self.match_markets)
        title  = mm[0].get("title", "") if mm else ""

        tournament, round_str = "", ""
        if ":" in title:
            right = title.split(":", 1)[1].strip().rstrip("?")
            parts = [p.strip() for p in right.split(",")]
            round_str  = parts[0] if parts else ""
            tournament = ", ".join(parts[1:]) if len(parts) > 1 else ""

        def fmt_time(ts):
            if not ts: return ""
            try:
                dt     = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                now    = datetime.now(timezone.utc)
                diff_m = (dt - now).total_seconds() / 60
                t_str  = dt.astimezone().strftime("%I:%M %p").lstrip("0")
                if diff_m < -1:    return f"{t_str} [#ff4444](LIVE)[/#ff4444]"
                elif diff_m < 60:  return f"{t_str} [#ffd700](in {int(diff_m)}m)[/#ffd700]"
                else:
                    h, m = int(diff_m // 60), int(diff_m % 60)
                    return f"{t_str} [dim](in {h}h {m}m)[/dim]"
            except Exception:
                return ts[:16]

        open_fmt  = fmt_time(mm[0].get("open_time",  "") if mm else "")
        close_fmt = fmt_time(mm[0].get("close_time", "") if mm else "")

        lines = [f"[bold white]{p1}  vs  {p2}[/bold white]"]
        if tournament: lines.append(f"[dim]{tournament}[/dim]")
        if round_str:  lines.append(f"[dim]{round_str}[/dim]")
        if open_fmt:   lines.append(f"  [dim]Start:[/dim]  {open_fmt}")
        if close_fmt:  lines.append(f"  [dim]Closes:[/dim] {close_fmt}")
        lines.append("")

        # Live score block
        if live_score and live_score.get("sets"):
            sets   = live_score["sets"]
            status = live_score.get("status", "live")
            game   = live_score.get("game")
            sn     = live_score.get("serving")

            status_tag = (
                "[bold #ff4444]● LIVE[/bold #ff4444]" if status == "live" else
                "[dim]FINAL[/dim]" if status == "finished" else
                f"[dim]{status.upper()}[/dim]"
            )
            sp1 = "● " if sn == "home" else "  "
            sp2 = "● " if sn == "away" else "  "

            col_w = 16
            def short(name, w):
                return name.ljust(w) if len(name) <= w else name.split()[-1][:w].ljust(w)

            p1_disp     = short(live_score.get("p1", p1), col_w)
            p2_disp     = short(live_score.get("p2", p2), col_w)
            set_headers = "  ".join(f"S{i+1}" for i in range(len(sets)))
            lines += [f"  {status_tag}", ""]
            lines.append(f"  [dim]{'':>{col_w}}   {set_headers}{'   Game' if game else ''}[/dim]")

            def set_row(idx):
                return "  ".join(
                    f"[bold #00e676]{s.split('-')[idx]}[/bold #00e676]"
                    if int(s.split("-")[idx]) > int(s.split("-")[1-idx])
                    else f"[dim]{s.split('-')[idx]}[/dim]"
                    for s in sets
                )
            p1_game = f"   [white]{game.split('-')[0]}[/white]" if game else ""
            p2_game = f"   [white]{game.split('-')[1]}[/white]" if game else ""
            lines.append(f"  [white]{sp1}{p1_disp}[/white]   {set_row(0)}{p1_game}")
            lines.append(f"  [white]{sp2}{p2_disp}[/white]   {set_row(1)}{p2_game}")
        else:
            lines.append("  [dim]Score not yet available[/dim]")

        lines += ["", "─" * 52, ""]

        # Per-contract price rows with sparklines
        for m in mm:
            ticker  = m.get("ticker", "")
            player  = ticker.split("-")[-1].capitalize()
            yes_ask = (m.get("yes_ask")  or 0) / 100
            no_ask  = (m.get("no_ask")   or 0) / 100
            vol     = m.get("volume", 0)
            oi      = m.get("open_interest", 0)
            last_px = (m.get("last_price") or 0) / 100
            color   = _price_color(yes_ask)
            btype   = _classify(yes_ask)
            closes  = trend_data.get(ticker, [])
            spark   = sparkline(closes, color=color)
            chg_str = "[dim]—[/dim]"
            if closes and len(closes) > 1:
                chg     = closes[-1] - closes[0]
                cc      = "#00e676" if chg >= 0 else "#ff4444"
                chg_str = f"[{cc}]{chg:+.0f}¢[/{cc}]"
            lines += [
                f"[bold {color}]  {player}[/bold {color}]"
                f"   [{color}]YES {yes_ask:.2f}[/{color}]"
                f"  [dim]NO {no_ask:.2f}[/dim]"
                f"   last [white]{last_px:.2f}[/white]  Δ {chg_str}",
                f"  {spark}",
                f"  [dim]vol {vol:,}  oi {oi:,}  {btype}[/dim]",
                "",
            ]

        self.query_one("#detail", Static).update("\n".join(lines))
        self._refresh_buy_block()

    # ── Buy block (delegated to BuyFlow) ──────────────────────────────────────

    def _refresh_buy_block(self):
        try:
            self.query_one("#buy_block", Static).update(self._buy.render())
        except Exception:
            pass

    # ── Watch block ───────────────────────────────────────────────────────────

    def _refresh_watch_block(self):
        try:
            block   = self.query_one("#watch_block", Static)
            watcher = self.app.buy_watcher
        except Exception:
            return

        watch = None
        for m in self.match_markets:
            w = watcher.get_watch_for_ticker(m.get("ticker", ""))
            if w:
                watch = w
                break

        if watch:
            lines = [
                "─" * 52, "",
                f"  [bold #ffd700]⏱ Buy Watch Active[/bold #ffd700]",
                f"  [white]{watch['label']}[/white] {watch['side'].upper()}"
                f"  trigger @ [#ffd700]{watch['trigger_price']}¢[/#ffd700]"
                f"  [dim]${watch['dollars']:.2f}[/dim]",
                "",
                "  [dim]C[/dim] = Cancel watch",
                "",
            ]
        else:
            lines = ["─" * 52, "", "  [dim]W[/dim] = Set buy watch", ""]
        block.update("\n".join(lines))

    # ── Key handling ──────────────────────────────────────────────────────────

    def on_key(self, event):
        # Buy flow gets first crack at keys
        if self._buy.handle_key(event):
            event.stop()
            return

        if event.key == "w":
            self._set_buy_status("[dim]Use W on the markets list to set a watch[/dim]")
            event.stop()
        elif event.key == "c":
            try:
                for m in self.match_markets:
                    w = self.app.buy_watcher.get_watch_for_ticker(m.get("ticker", ""))
                    if w:
                        self.app.buy_watcher.remove_watch(w["id"])
                        break
                self._refresh_watch_block()
            except Exception:
                pass
            event.stop()

    # ── Buy helpers (called by BuyFlow) ───────────────────────────────────────

    def _set_buy_status(self, msg: str):
        self._buy._status = msg
        self._refresh_buy_block()

    @work(thread=True)
    def _fetch_confirm_price(self):
        """Fetch live price then hand control back to BuyFlow for confirm step."""
        from src.api import fetch_market
        from src.data.markets_api import _normalize

        mm        = sorted(self.match_markets, key=lambda x: x.get("ticker", ""))
        m         = mm[self._buy._cursor] if self._buy._cursor < len(mm) else mm[0]
        side      = "yes" if self._buy._side_cur == 0 else "no"
        price_key = "yes_ask" if side == "yes" else "no_ask"
        ticker    = m.get("ticker", "")

        try:
            live_m     = fetch_market(ticker)
            _normalize(live_m)
            live_price = live_m.get(price_key) or m.get(price_key) or 99
            m[price_key] = live_price
            if side == "yes":
                m["no_ask"]  = live_m.get("no_ask")  or m.get("no_ask")  or 99
            else:
                m["yes_ask"] = live_m.get("yes_ask") or m.get("yes_ask") or 99
        except Exception:
            live_price = m.get(price_key) or 99

        from src.screens.buy_flow import BUY_CONFIRM
        self._buy._confirm_price = live_price
        self._buy._confirm_type  = _classify(live_price / 100)
        self._buy.state          = BUY_CONFIRM
        self._buy._status        = ""
        self.app.call_from_thread(self._refresh_buy_block)

    @work(thread=True)
    def _confirm_paper_buy(self):
        dollars = float(self._buy._input)
        mm      = sorted(self.match_markets, key=lambda x: x.get("ticker", ""))
        m       = mm[self._buy._cursor] if self._buy._cursor < len(mm) else mm[0]
        side    = "yes" if self._buy._side_cur == 0 else "no"
        slug    = m.get("ticker", "").split("-")[-1].capitalize()
        try:
            order  = self.app.paper_ledger.buy(
                ticker=m.get("ticker", ""), side=side,
                yes_price_cents=self._buy._confirm_price,
                dollars=dollars, label=slug,
            )
            filled = order.get("fill_count", "?")
            self._buy.reset()
            self.app.call_from_thread(
                self._set_buy_status,
                f"[{PAPER_COLOR}]✓ PAPER: {filled} × {slug} {side.upper()} @ {self._buy._confirm_price}¢[/{PAPER_COLOR}]"
            )
        except Exception as e:
            self.app.call_from_thread(self._set_buy_status, f"[red]{e}[/red]")

    @work(thread=True)
    def _confirm_buy(self):
        from src.api import place_order
        dollars = float(self._buy._input)
        mm      = sorted(self.match_markets, key=lambda x: x.get("ticker", ""))
        m       = mm[self._buy._cursor] if self._buy._cursor < len(mm) else mm[0]
        side    = "yes" if self._buy._side_cur == 0 else "no"
        slug    = m.get("ticker", "").split("-")[-1].capitalize()
        ticker  = m.get("ticker", "")
        yes_price = m.get("yes_ask") or 99
        no_price  = m.get("no_ask")  or 99

        self.app.call_from_thread(
            self._set_buy_status,
            f"Placing {slug} {side.upper()} ${dollars:.2f} @ {self._buy._confirm_price}¢..."
        )
        try:
            order  = place_order(
                ticker=ticker, side=side, action="buy",
                dollars=dollars, yes_price=yes_price, no_price=no_price,
            )
            filled   = order.get("contracts_filled", order.get("count", "?"))
            order_id = str(order.get("order_id", "?"))
            self._buy.reset()
            self.app.call_from_thread(
                self._set_buy_status,
                f"[green]✓ {filled} × {slug} {side.upper()} filled  ({order_id[:8]}...)[/green]"
            )
        except Exception as e:
            self.app.call_from_thread(self._set_buy_status, f"[red]{e}[/red]")