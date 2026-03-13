from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from textual.binding import Binding


class NotificationPanel(Widget):
    BINDINGS = [Binding("escape", "close", "Close")]

    def compose(self) -> ComposeResult:
        yield Static("", id="notif_content")

    def action_close(self):
        self.hide()

    def refresh_content(self, store):
        alerts = store.alerts
        if not alerts:
            self.query_one("#notif_content", Static).update(
                "  [dim]No alerts yet[/dim]")
            return
        lines = ["  [dim]── Alerts (newest first) ──[/dim]", ""]
        for a in alerts[:20]:
            dim = "dim " if a.read else ""
            lines += [
                f"  [{dim}{a.color}]{a.icon}[/{dim}{a.color}]  "
                f"[{dim}bold white]{a.match}[/{dim}bold white]  "
                f"[{dim}#00e676]{a.price:.0%} YES[/{dim}#00e676]  "
                f"[dim]{a.time_str}[/dim]",
                f"     [{dim}white]{a.message}[/{dim}white]",
                "",
            ]
        self.query_one("#notif_content", Static).update("\n".join(lines))

    def show(self, store):
        self.display = True
        self.refresh_content(store)
        self.focus()

    def hide(self):
        self.display = False

    def on_click(self):
        self.hide()