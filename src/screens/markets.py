"""
markets.py — Markets list screen.

Shows all active matches grouped by sport. Handles sport/color filtering,
section expand/collapse, and match navigation. Watch flow logic is delegated
to WatchFlow in watch_flow.py.
"""
import subprocess
from textual.screen import Screen
from textual.widgets import DataTable, Static, Header, Footer
from textual.binding import Binding
from textual.timer import Timer
from textual import work
from rich.text import Text

from src.constants import SPORTS_SECTION, SPORT_COLOR, SPORT_LABEL
from src.widgets.section_header import SectionHeader
from src.widgets.sport_pill_bar import SportPillBar
from src.widgets.color_filter_bar import ColorFilterBar
from src.widgets.bell import BellWidget
from src.widgets.mode_bar import ModeBar
from src.widgets.notification_panel import NotificationPanel
from src.screens.match_detail import MatchScreen
from src.screens.watch_flow import WatchFlow, WATCH_OFF

KALSHI_BASE = "https://kalshi.com/markets/"


class MatchListScreen(Screen):
    BINDINGS = [
        Binding("escape,q", "app.pop_screen", "Back"),
        Binding("r",        "refresh",        "Refresh"),
        Binding("n",        "notifications",  "Notifications"),
        Binding("p",        "positions",      "Positions"),
        Binding("w",        "watch",          "Watch"),
    ]

    def __init__(self):
        super().__init__()
        self._sec_expanded     = {"sports": True, "politics": False}
        self._sport_filter     = "tennis"
        self._color_filter     = "all"
        self._sport_collapsed  = False
        self._highlighted_key  = None
        self._event_tickers: dict = {}
        self._poll_timer: Timer   = None
        self._watch               = WatchFlow(self)   # owns all watch state

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self):
        yield Header()
        yield ModeBar(id="mode_bar")
        with Static(id="bell_row"):
            yield Static("", id="bell_spacer")
            yield BellWidget(id="bell")
        yield NotificationPanel(id="notif_panel")
        yield ColorFilterBar(id="colorfilter")
        yield SectionHeader("Sports",   "#00bcd4", "sports",
                            expanded=True, loading=True, id="hdr_sports")
        yield SportPillBar(id="sport_pills")
        yield SectionHeader("Politics", "#ce93d8", "politics",
                            expanded=False, id="hdr_politics")
        yield Static("[dim]Loading...[/dim]", id="status")
        yield DataTable(id="table", cursor_type="row")
        yield Static("", id="watch_panel")
        yield Footer()

    def on_mount(self):
        t = self.query_one(DataTable)
        t.add_column("Match",  width=36)
        t.add_column("YES",    width=7)
        t.add_column("NO",     width=7)
        t.add_column("Volume", width=10)
        t.add_column("Sport",  width=8)

        dm = self.app.data_manager
        dm.request_sport("tennis")
        if dm.is_loaded("tennis"):
            self.call_after_refresh(self._redraw)
            dm.probe_available_sports(callback=self._refresh_pill_bar)
            self._poll_timer = self.set_interval(20.0, self._refresh_prices)
        else:
            self._poll_timer = self.set_interval(0.1, self._poll)

    def on_unmount(self):
        if self._poll_timer:
            self._poll_timer.stop()

    # ── Polling / refresh ─────────────────────────────────────────────────────

    def _poll(self):
        """Fast poll (0.1s) until tennis is loaded, then switch to 20s refresh."""
        try:
            self.query_one("#status", Static).update("[dim]Fetching markets...[/dim]")
        except Exception:
            pass
        dm = self.app.data_manager
        if dm.is_loaded("tennis"):
            self._redraw()
            if self._poll_timer:
                self._poll_timer.stop()
            self._poll_timer = self.set_interval(20.0, self._refresh_prices)
            dm.probe_available_sports(callback=self._refresh_pill_bar)

    def _refresh_prices(self):
        """Invalidate loaded state and re-fetch all active sports."""
        dm = self.app.data_manager
        for sport in list(dm._active_sports):
            dm._loaded[sport] = False
            dm.request_sport(sport)
        self.set_timer(3.0, self._redraw)

    def _refresh_pill_bar(self):
        try:
            sports = self.app.data_manager.available_sports()
            self.query_one("#sport_pills", SportPillBar).refresh_sports(sports)
        except Exception:
            pass

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_notifications(self):
        self.app.toggle_notifications()

    def action_positions(self):
        from src.screens.positions import PositionsScreen
        self.app.push_screen(PositionsScreen())

    def action_watch(self):
        if self._highlighted_key and not self._highlighted_key.startswith("__empty_"):
            self._watch.start(self._highlighted_key)

    def action_refresh(self):
        """Force-clear cache and re-fetch everything."""
        from src import cache
        cache._cache.clear()
        dm = self.app.data_manager
        for sport in list(dm._active_sports):
            dm._loaded[sport] = False
            dm.request_sport(sport)
        if self._poll_timer:
            self._poll_timer.stop()
        self._poll_timer = self.set_interval(1.0, self._poll)

    # ── Section / sport / color filters ───────────────────────────────────────

    def toggle_section(self, section: str):
        # Sports section is always expanded — only politics is collapsible
        if section == "sports":
            return
        hdr       = self.query_one(f"#hdr_{section}", SectionHeader)
        new_state = not hdr._expanded
        hdr.set_state(expanded=new_state)
        self._sec_expanded[section] = new_state
        if new_state and section == "politics":
            dm = self.app.data_manager
            if not dm.is_loaded("politics"):
                hdr.set_state(loading=True)
                dm.request_sport("politics")
        self._redraw()

    def on_sport_pill_clicked(self, key: str):
        if key == self._sport_filter:
            self._sport_collapsed = not self._sport_collapsed
        else:
            self._sport_filter    = key
            self._sport_collapsed = False
            dm = self.app.data_manager
            if not dm.is_loaded(key):
                dm.request_sport(key)
                if self._poll_timer:
                    self._poll_timer.stop()
                self._poll_timer = self.set_interval(1.0, self._poll)
        self.query_one("#sport_pills", SportPillBar).set_state(
            self._sport_filter, self._sport_collapsed)
        self._redraw()

    def apply_color_filter(self, key):
        self._color_filter = key
        self._redraw()

    # ── Table rendering ───────────────────────────────────────────────────────

    def _redraw(self):
        dm = self.app.data_manager
        t  = self.query_one(DataTable)
        t.clear()
        shown      = 0
        all_sports = SPORTS_SECTION + ["politics"]

        # Update section headers
        sports_active  = [s for s in SPORTS_SECTION if s in dm._active_sports]
        n_sports       = sum(len(dm.get_rows(s)) for s in sports_active)
        still_loading  = bool(sports_active) and not all(dm.is_loaded(s) for s in sports_active)
        self.query_one("#hdr_sports",   SectionHeader).set_state(count=n_sports, loading=still_loading)
        self.query_one("#hdr_politics", SectionHeader).set_state(count=len(dm.get_groups("politics")), loading=False)

        for sport in all_sports:
            rows    = dm.get_rows(sport)
            section = "sports" if sport in SPORTS_SECTION else "politics"

            if not self._sec_expanded[section]:
                continue
            if sport in SPORTS_SECTION and sport != self._sport_filter:
                continue
            if sport not in dm._active_sports and not dm.is_loaded(sport):
                continue
            if sport in SPORTS_SECTION and self._sport_collapsed:
                continue

            filtered = [r for r in rows
                        if self._color_filter == "all" or r[7] == self._color_filter]

            if not filtered:
                if dm.is_loaded(sport):
                    sc = SPORT_COLOR.get(sport, "white")
                    sl = SPORT_LABEL.get(sport, sport)
                    t.add_row(f"[dim]No {sl} markets[/dim]",
                              Text(""), Text(""), Text(""), Text(sl, style=sc),
                              key=f"__empty_{sport}")
                continue

            for r in filtered:
                self._event_tickers[r[0]] = r[10]

            # Live matches first, then by volume descending
            filtered.sort(key=lambda r: (0 if r[9] else 1, -r[5]))

            for row in filtered:
                key, p1, p2, yes_p, no_p, vol, color, bucket, sport_tag, live, event_ticker = row
                sc = SPORT_COLOR.get(sport_tag, "white")
                sl = SPORT_LABEL.get(sport_tag, sport_tag)

                match_text = Text()
                if live:
                    match_text.append("● ", style="bold #ff4444")
                    match_text.append(f"{p1} vs {p2}", style="bold #ff4444")
                else:
                    match_text.append(f"{p1} vs {p2}", style="white")

                def price_col(p: float) -> str:
                    if p <= 0:    return "dim"
                    if p >= 0.81: return "#ff4444"
                    if p >= 0.65: return "#ffd700"
                    if p >= 0.45: return "#00e676"
                    return "dim"

                t.add_row(
                    match_text,
                    Text(f"{yes_p:.2f}" if yes_p > 0 else "--", style=price_col(yes_p)),
                    Text(f"{no_p:.2f}"  if no_p  > 0 else "--", style=price_col(no_p)),
                    Text(f"{vol:,}", style="white"),
                    Text(sl, style=sc),
                    key=key,
                )
                shown += 1

        self.query_one("#status", Static).update(
            f"[dim]{shown} matches · Enter=detail · O=open Kalshi · R=refresh · N=alerts · Esc=back[/dim]"
        )

    # ── Match opening ─────────────────────────────────────────────────────────

    def _open_match(self, key: str):
        if not key or key.startswith("__empty_"):
            return
        self._open_match_fresh(key)

    @work(thread=True)
    def _open_match_fresh(self, key: str):
        """Fetch fresh prices for the match then push the detail screen."""
        from src.api import fetch_markets
        from src.data.market_parser import group_by_match
        from src.data.market_filter import filter_active

        dm     = self.app.data_manager
        groups = {}
        for sport in SPORTS_SECTION + ["politics"]:
            groups.update(dm.get_groups(sport))
        mm = groups.get(key, [])

        try:
            if mm:
                series = mm[0].get("event_ticker") or key.rsplit("-", 2)[0]
                fresh  = fetch_markets(series_ticker=series)
                fresh  = filter_active(fresh)
                fresh_groups = group_by_match(fresh)
                if key in fresh_groups:
                    mm = fresh_groups[key]
                    for sport in SPORTS_SECTION + ["politics"]:
                        if key in dm.get_groups(sport):
                            dm._groups[sport][key] = mm
                            break
        except Exception:
            pass

        if mm:
            self.app.call_from_thread(
                self.app.push_screen,
                MatchScreen(match_key=key, match_markets=mm)
            )

    # ── Events ────────────────────────────────────────────────────────────────

    def on_data_table_row_selected(self, event):
        self._open_match(event.row_key.value)

    def on_data_table_row_highlighted(self, event):
        self._highlighted_key = event.row_key.value if event.row_key else None

    def on_key(self, event):
        # Watch flow gets first crack when active
        if self._watch.state != WATCH_OFF:
            if self._watch.handle_key(event):
                event.stop()
                return

        if event.key == "enter":
            if self._highlighted_key:
                self._open_match(self._highlighted_key)
        elif event.key == "o":
            key = self._highlighted_key
            if key and not key.startswith("__empty_"):
                event_ticker = self._event_tickers.get(key, "")
                if event_ticker:
                    subprocess.Popen(["open", f"{KALSHI_BASE}{event_ticker.lower()}"])