"""
SettingsScreen — notification toggles + default sport filter.
Persisted to ~/.kalshi-trader/settings.json on every change.
"""
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Switch, Label
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal

from src import settings as cfg
from src.widgets.bell import BellWidget
from src.widgets.mode_bar import ModeBar
from src.widgets.notification_panel import NotificationPanel

SPORTS = [
    ("tennis",     "Tennis"),
    ("basketball", "Basketball"),
    ("politics",   "Politics"),
]


class SettingsScreen(Screen):
    BINDINGS = [
        Binding("escape,q", "app.pop_screen", "Back"),
        Binding("n",        "notifications",  "Notifications"),
    ]

    CSS = """
    #settings_body  { padding: 2 4; }
    .setting_row    { height: 3; layout: horizontal; align: left middle; }
    .setting_label  { width: 28; }
    .section_title  { color: #00bcd4; padding: 1 0 0 0; }
    .section_desc   { color: #666; }
    """

    def __init__(self):
        super().__init__()
        self._settings = cfg.load()

    def compose(self) -> ComposeResult:
        yield Header()
        yield ModeBar(id="mode_bar")
        with Static(id="bell_row"):
            yield Static("", id="bell_spacer")
            yield BellWidget(id="bell")
        yield NotificationPanel(id="notif_panel")
        with Vertical(id="settings_body"):
            yield Static("Default Sports", classes="section_title")
            yield Static("[dim]Which sports load when opening the markets screen[/dim]", classes="section_desc")
            tennis_only = self._settings.get("default_sports", ["tennis"]) == ["tennis"]
            with Horizontal(classes="setting_row"):
                yield Label("Tennis only (recommended)", classes="setting_label")
                yield Switch(value=tennis_only, id="switch_tennis_only")

            yield Static("Notifications", classes="section_title")
            yield Static("[dim]Toggle which sports fire alert popups[/dim]", classes="section_desc")
            for sport_key, sport_label in SPORTS:
                enabled = self._settings["notifications"].get(sport_key, True)
                with Horizontal(classes="setting_row"):
                    yield Label(f"{sport_label} alerts", classes="setting_label")
                    yield Switch(value=enabled, id=f"switch_{sport_key}")
        yield Footer()

    def action_notifications(self):
        self.app.toggle_notifications()

    def on_switch_changed(self, event: Switch.Changed):
        sid = event.switch.id

        if sid == "switch_tennis_only":
            if event.value:
                self._settings["default_sports"] = ["tennis"]
            else:
                self._settings["default_sports"] = ["tennis", "basketball", "politics"]
            cfg.save(self._settings)
            return

        sport_key = sid.replace("switch_", "")
        self._settings["notifications"][sport_key] = event.value
        cfg.save(self._settings)
        self.app.data_manager.notification_filter = dict(self._settings["notifications"])