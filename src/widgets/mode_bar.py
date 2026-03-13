"""
ModeBar — full-width colored status bar showing LIVE or PAPER mode.
Click toggles mode.
"""
from textual.widgets import Static
from src.core.paper import PAPER_COLOR


class ModeBar(Static):

    def on_mount(self):
        self.call_after_refresh(self._update)

    def _update(self):
        try:
            paper = self.app.paper_mode
        except Exception:
            paper = False
        if paper:
            self.styles.background = "#3a2a00"
            self.update(
                f"[bold {PAPER_COLOR}]  ◆ PAPER MODE  —  trades are simulated, no real money[/bold {PAPER_COLOR}]"
            )
        else:
            self.styles.background = "#003320"
            self.update(
                "[bold #00e676]  ◆ LIVE MODE  —  all trades are real[/bold #00e676]"
            )

    def on_click(self):
        self.app.toggle_paper_mode()

    def refresh_bar(self):
        self._update()