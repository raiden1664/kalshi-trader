"""
BellWidget — shows unread count, toggles notification dropdown on click.
"""
from textual.widgets import Static
from textual.reactive import reactive


class BellWidget(Static):
    unread = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(self._build(0), **kwargs)

    def _build(self, count: int) -> str:
        if count == 0:
            return "[dim]🔔[/dim]"
        return f"[bold #ffd700]🔔 {count}[/bold #ffd700]"

    def watch_unread(self, count: int):
        self.update(self._build(count))

    def on_click(self):
        self.app.toggle_notifications()