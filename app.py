from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static, Header, Footer
from textual.screen import Screen
from textual.binding import Binding
from textual import work
from textual.reactive import reactive
from rich.text import Text
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from src.tennis import fetch_series_markets, group_by_match, _extract_names, _price_color, _classify
from src.api import fetch_balance, fetch_positions, fetch_candlesticks

SERIES = {
    "tennis": ["KXATPMATCH", "KXWTAMATCH"],
    "basketball": ["KXNCAAMBGAME", "KXNCAAWBGAME"],
}

MENU_ITEMS = [
    ("Tennis Markets",     "tennis"),
    ("Basketball Markets", "basketball"),
    ("Quit",               "quit"),
]

FILTERS = ["all", "green", "yellow", "red"]
FILTER_COLOR = {
    "all":    ("white",   "● All"),
    "green":  ("#00e676", "● Green"),
    "yellow": ("#ffd700", "● Yellow"),
    "red":    ("#ff4444", "● Red"),
}

def get_row_color(yes_p: float) -> str:
    if yes_p >= 0.81 or yes_p <= 0.00: return "red"
    if 0.70 <= yes_p <= 0.80:          return "yellow"
    return "green"


# ── Sparkline ─────────────────────────────────────────────────────────────────
SPARK_CHARS = " ▁▂▃▄▅▆▇█"

def sparkline(values: list, width: int = 40, color: str = "#00e676") -> str:
    if not values:
        return "[dim]no data[/dim]"
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    chars = []
    step  = max(1, len(values) // width)
    for i in range(0, len(values), step):
        v   = values[i]
        idx = int((v - lo) / span * (len(SPARK_CHARS) - 1))
        chars.append(SPARK_CHARS[idx])
    spark = "".join(chars[:width])
    pct   = f"{values[-1]:.0f}¢"
    arrow = "▲" if len(values) > 1 and values[-1] >= values[0] else "▼"
    arrow_color = "#00e676" if arrow == "▲" else "#ff4444"
    return f"[{color}]{spark}[/{color}] [{arrow_color}]{arrow} {pct}[/{arrow_color}]"


# ── Match Detail ──────────────────────────────────────────────────────────────
class MatchScreen(Screen):
    BINDINGS = [Binding("escape,q", "app.pop_screen", "Back")]

    def __init__(self, match_key: str, match_markets: list):
        super().__init__()
        self.match_key     = match_key
        self.match_markets = match_markets

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._build_detail(), id="detail")
        yield Footer()

    def on_mount(self):
        self.load_trends()

    @work(thread=True)
    def load_trends(self):
        trend_data = {}
        for m in self.match_markets:
            ticker = m.get("ticker", "")
            series = ticker.rsplit("-", 1)[0] if "-" in ticker else ticker
            try:
                candles = fetch_candlesticks(series, ticker, period_interval=1)
                closes  = [c["price"]["close"] for c in candles if c.get("price") and c["price"].get("close") is not None]
                trend_data[ticker] = closes
            except Exception:
                trend_data[ticker] = []
        self.app.call_from_thread(self._inject_trends, trend_data)

    def _parse_context(self, title: str):
        """Extract tournament and round from title like:
        'Will WINNER win the P1 vs P2 : Round 2, Indian Wells Masters 2026?'"""
        tournament, round_str = "", ""
        if ":" in title:
            right = title.split(":", 1)[1].strip().rstrip("?")
            parts = [p.strip() for p in right.split(",")]
            round_str  = parts[0] if parts else ""
            tournament = ", ".join(parts[1:]) if len(parts) > 1 else ""
        return tournament.strip(), round_str.strip()

    def _inject_trends(self, trend_data: dict):
        p1, p2   = _extract_names(self.match_markets)
        mm_sorted = sorted(self.match_markets, key=lambda x: x.get("ticker", ""))

        # Parse tournament/round from first market title
        title      = mm_sorted[0].get("title", "") if mm_sorted else ""
        tournament, round_str = self._parse_context(title)

        header = []
        header.append(f"[bold white]{p1}  vs  {p2}[/bold white]")
        if tournament:
            header.append(f"[dim]{tournament}[/dim]")
        if round_str:
            header.append(f"[dim]{round_str}[/dim]")
        header.append("")

        lines = header[:]

        for m in mm_sorted:
            ticker   = m.get("ticker", "")
            player   = ticker.split("-")[-1]  # e.g. FON or PAU
            yes_ask  = (m.get("yes_ask")  or 0) / 100
            yes_bid  = (m.get("yes_bid")  or 0) / 100
            no_ask   = (m.get("no_ask")   or 0) / 100
            no_bid   = (m.get("no_bid")   or 0) / 100
            volume   = m.get("volume", 0)
            open_int = m.get("open_interest", 0)
            last_px  = (m.get("last_price") or 0) / 100
            color    = _price_color(yes_ask)
            btype    = _classify(yes_ask)
            closes   = trend_data.get(ticker, [])
            spark    = sparkline(closes, width=44, color=color)

            # Direction arrow vs open
            if closes and len(closes) > 1:
                chg = closes[-1] - closes[0]
                chg_color = "#00e676" if chg >= 0 else "#ff4444"
                chg_str = f"[{chg_color}]{chg:+.0f}¢[/{chg_color}]"
            else:
                chg_str = "[dim]—[/dim]"

            lines += [
                f"[bold {color}]  {player}[/bold {color}]   [{color}]YES {yes_ask:.2f}[/{color}]  [dim]NO {no_ask:.2f}[/dim]   last [white]{last_px:.2f}[/white]  Δ {chg_str}",
                f"  {spark}",
                f"  [dim]vol {volume:,}  oi {open_int:,}  {btype}[/dim]",
                f"",
            ]

        self.query_one("#detail", Static).update("\n".join(lines))

    def _build_detail(self) -> str:
        p1, p2 = _extract_names(self.match_markets)
        lines = [f"[bold white]{p1} vs {p2}[/bold white]\n", "[dim]Loading trend data...[/dim]"]
        return "\n".join(lines)


# ── Filter Pill ───────────────────────────────────────────────────────────────
class FilterPill(Static):
    def __init__(self, filter_key: str, active: bool = False):
        color, label = FILTER_COLOR[filter_key]
        if active:
            initial = f"[bold {color} reverse] {label} [/bold {color} reverse]"
        else:
            initial = f"[{color}] {label} [/{color}]"
        super().__init__(initial)
        self.filter_key = filter_key
        self.active     = active

    def _repaint(self):
        color, label = FILTER_COLOR[self.filter_key]
        if self.active:
            self.update(f"[bold {color} reverse] {label} [/bold {color} reverse]")
        else:
            self.update(f"[{color}] {label} [/{color}]")

    def set_active(self, active: bool):
        self.active = active
        self._repaint()

    def on_click(self):
        self.screen.set_filter(self.filter_key)


# ── Match List ────────────────────────────────────────────────────────────────
class MatchListScreen(Screen):
    BINDINGS = [
        Binding("escape,q", "app.pop_screen", "Back"),
        Binding("r",        "refresh",        "Refresh"),
    ]

    def __init__(self, sport: str):
        super().__init__()
        self.sport          = sport
        self._groups        = {}
        self._all_rows      = []
        self._active_filter = "all"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[dim]Loading...[/dim]", id="status")
        with Static(id="pills"):
            for f in FILTERS:
                yield FilterPill(f, active=(f == "all"))
        yield DataTable(id="matches", cursor_type="row")
        yield Footer()

    def on_mount(self):
        t = self.query_one(DataTable)
        t.add_column("Match",  width=42)
        t.add_column("YES",    width=7)
        t.add_column("NO",     width=7)
        t.add_column("Volume", width=12)
        self.load_markets()

    @work(thread=True)
    def load_markets(self):
        all_markets = []
        for series in SERIES.get(self.sport, []):
            try:
                all_markets.extend(fetch_series_markets(series))
            except Exception as e:
                self.app.call_from_thread(self._set_status, f"[red]Error: {e}[/red]")
                return
        self.app.call_from_thread(self._populate_table, group_by_match(all_markets))

    def _set_status(self, msg: str):
        self.query_one("#status", Static).update(msg)

    def _populate_table(self, groups: dict):
        self._groups   = groups
        self._all_rows = []
        for match_key, mm in groups.items():
            mm.sort(key=lambda m: m.get("ticker", ""))
            p1, p2 = _extract_names(mm)
            p1y = (mm[0].get("yes_ask") or 0) / 100 if mm else 0
            p1n = (mm[0].get("no_ask")  or 0) / 100 if mm else 0
            p2y = (mm[1].get("yes_ask") or 0) / 100 if len(mm) > 1 else 0
            p2n = (mm[1].get("no_ask")  or 0) / 100 if len(mm) > 1 else 0
            vol  = sum((m.get("volume") or 0) for m in mm)
            yes_p, no_p = (p1y, p1n) if p1y >= p2y else (p2y, p2n)
            color  = _price_color(yes_p)
            bucket = get_row_color(yes_p)
            self._all_rows.append((match_key, p1, p2, yes_p, no_p, vol, color, bucket))
        self._redraw_table()

    def _redraw_table(self):
        t = self.query_one(DataTable)
        t.clear()
        shown = 0
        for (match_key, p1, p2, yes_p, no_p, vol, color, bucket) in self._all_rows:
            if self._active_filter != "all" and bucket != self._active_filter:
                continue
            t.add_row(
                f"{p1} vs {p2}",
                Text(f"{yes_p:.2f}", style=color),
                Text(f"{no_p:.2f}"),
                Text(f"{vol:,}"),
                key=match_key,
            )
            shown += 1
        fc, _ = FILTER_COLOR[self._active_filter]
        filt  = f" [{fc}]{self._active_filter}[/{fc}]" if self._active_filter != "all" else ""
        self._set_status(f"[dim]{shown} matches{filt} · Enter to view · R refresh · Esc back[/dim]")

    def set_filter(self, filter_key: str):
        self._active_filter = filter_key
        for pill in self.query(FilterPill):
            pill.set_active(pill.filter_key == filter_key)
        self._redraw_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        self.app.push_screen(MatchScreen(event.row_key.value, self._groups.get(event.row_key.value, [])))

    def action_refresh(self):
        self._set_status("[dim]Refreshing...[/dim]")
        self.query_one(DataTable).clear()
        self.load_markets()


# ── Dashboard ─────────────────────────────────────────────────────────────────
class DashboardScreen(Screen):
    BINDINGS = [
        Binding("up",    "move_up",   "Up",   show=False),
        Binding("down",  "move_down", "Down", show=False),
        Binding("enter", "select",    "Select"),
        Binding("q",     "app.quit",  "Quit"),
    ]

    selected = reactive(0)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="stats")
        yield Static("", id="menu")
        yield Footer()

    def on_mount(self):
        self.render_menu()
        self.load_stats()

    @work(thread=True)
    def load_stats(self):
        try:
            bal = fetch_balance()
            pos = fetch_positions()
            self.app.call_from_thread(self._show_stats, bal, pos)
        except Exception as e:
            self.app.call_from_thread(self._show_stats_error, str(e))

    def _show_stats(self, bal: dict, pos: list):
        cash      = bal.get("balance", 0) / 100
        portfolio = bal.get("portfolio_value", 0) / 100
        total     = cash + portfolio
        now       = datetime.now().strftime("%H:%M:%S")
        lines = [
            f"[bold magenta]kalshi-trader[/bold magenta]  [dim]{now}[/dim]",
            f"",
            f"  [dim]Cash[/dim]          [bold #00e676]${cash:.2f}[/bold #00e676]",
            f"  [dim]Portfolio[/dim]     [bold #ffd700]${portfolio:.2f}[/bold #ffd700]",
            f"  [dim]Total[/dim]         [bold white]${total:.2f}[/bold white]",
        ]
        if pos:
            lines += ["", f"  [dim]Open Positions ({len(pos)})[/dim]"]
            for p in pos[:5]:
                qty  = p.get("position", 0)
                side = "YES" if qty > 0 else "NO"
                col  = "#00e676" if side == "YES" else "#ff4444"
                exp  = (p.get("market_exposure") or 0) / 100
                lines.append(f"    [{col}]{side}[/{col}]  {p.get('ticker','')[:30]}  ${exp:.2f}")
        else:
            lines += ["", "  [dim]No open positions[/dim]"]
        self.query_one("#stats", Static).update("\n".join(lines))

    def _show_stats_error(self, err: str):
        self.query_one("#stats", Static).update(f"[#ff4444]Could not load stats: {err}[/#ff4444]")

    def render_menu(self):
        lines = ["", "  [dim]Navigate[/dim]", ""]
        for i, (label, _) in enumerate(MENU_ITEMS):
            if i == self.selected:
                lines.append(f"  [bold reverse] {label} [/bold reverse]")
            else:
                lines.append(f"    [white]{label}[/white]")
        self.query_one("#menu", Static).update("\n".join(lines))

    def watch_selected(self, _):
        self.render_menu()

    def action_move_up(self):
        self.selected = (self.selected - 1) % len(MENU_ITEMS)

    def action_move_down(self):
        self.selected = (self.selected + 1) % len(MENU_ITEMS)

    def action_select(self):
        _, action = MENU_ITEMS[self.selected]
        if action == "quit":
            self.app.exit()
        else:
            self.app.push_screen(MatchListScreen(action))


# ── App ───────────────────────────────────────────────────────────────────────
class KalshiApp(App):
    CSS = """
    #stats      { padding: 1 2; height: auto; }
    #menu       { padding: 0 2; height: auto; }
    #status     { height: 1; padding: 0 1; color: gray; }
    #detail     { padding: 1 2; overflow-y: auto; height: 1fr; }
    #pills      { height: 1; padding: 0 1; layout: horizontal; }
    FilterPill  { width: auto; padding: 0 2; }
    DataTable   { height: 1fr; }
    """
    TITLE = "kalshi-trader"

    def on_mount(self):
        self.push_screen(DashboardScreen())


if __name__ == "__main__":
    KalshiApp().run()