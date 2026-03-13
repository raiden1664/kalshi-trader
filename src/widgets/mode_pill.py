"""
ModePill — iOS-style LIVE / PAPER toggle pill.
Lives in the bell_row so it persists across all screen pushes.
"""
from textual.widgets import Static


class ModePill(Static):

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)

    @staticmethod
    def _pill_markup(paper: bool) -> str:
        if paper:
            return (
                "[dim] LIVE [/dim]"
                "[bold #ff9800 reverse]  PAPER  [/bold #ff9800 reverse]"
            )
        else:
            return (
                "[bold #00e676 reverse]  LIVE  [/bold #00e676 reverse]"
                "[dim]  PAPER [/dim]"
            )

    def on_mount(self):
        self.update(self._pill_markup(self.app.paper_mode))

    def on_click(self):
        self.app.toggle_paper_mode()

    def refresh_pill(self):
        self.update(self._pill_markup(self.app.paper_mode))