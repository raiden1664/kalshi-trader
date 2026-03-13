from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import HorizontalScroll
from src.constants import SPORT_COLOR, SPORT_LABEL

SPORT_ORDER = [
    "tennis", "basketball", "hockey", "baseball",
    "soccer", "football", "mma", "golf", "cricket",
]

PAGE_SIZE = 3


class _PillContent(Static):
    def on_mouse_up(self, event):
        self.parent._handle_click_x(event.x)
        event.stop()


class SportPillBar(HorizontalScroll):
    DEFAULT_CSS = """
    SportPillBar {
        height: 1;
        scrollbar-size: 0 0;
        overflow-x: hidden;
        overflow-y: hidden;
        background: transparent;
    }
    _PillContent {
        width: auto;
        height: 1;
        background: transparent;
    }
    """

    can_focus = False

    def __init__(self, **kwargs):
        self._active    = "tennis"
        self._collapsed = False
        self._sports    = ["tennis"]
        self._expanded  = False   # False = show 3, True = show all
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield _PillContent(self._build(), id="pill_content")

    def _ordered(self) -> list:
        ordered = [s for s in SPORT_ORDER if s in self._sports]
        for s in self._sports:
            if s not in ordered:
                ordered.append(s)
        return ordered

    def _build(self) -> str:
        ordered = self._ordered()
        visible = ordered if self._expanded else ordered[:PAGE_SIZE]

        parts = []

        # When expanded, put ◂ FIRST so it's always on screen
        if self._expanded:
            parts.append("[bold]◂  [/bold]")

        for sport in visible:
            color = SPORT_COLOR.get(sport, "white")
            label = SPORT_LABEL.get(sport, sport)
            if sport == self._active:
                if self._collapsed:
                    parts.append(f"[{color}]  ● {label} ▸  [/{color}]")
                else:
                    parts.append(f"[bold {color} reverse]  ● {label}  [/bold {color} reverse]")
            else:
                parts.append(f"[dim]  ● {label}  [/dim]")

        # Expand arrow at the end when collapsed
        if not self._expanded and len(ordered) > PAGE_SIZE:
            parts.append("[bold]  ▸  [/bold]")

        return "  " + "  ".join(parts)

    def _refresh_content(self):
        try:
            self.query_one("#pill_content", _PillContent).update(self._build())
        except Exception:
            pass

    def refresh_sports(self, sports: list):
        self._sports = sports
        if self._active not in self._sports and self._sports:
            self._active = self._ordered()[0]
        self._refresh_content()

    def set_state(self, active: str, collapsed: bool):
        self._active    = active
        self._collapsed = collapsed
        self._refresh_content()

    def _pill_widths(self) -> list:
        """Returns list of (kind, key_or_none, start_x, end_x)."""
        ordered = self._ordered()
        visible = ordered if self._expanded else ordered[:PAGE_SIZE]

        result = []
        cumulative = 2

        # ◂ is FIRST when expanded — always on screen
        if self._expanded:
            result.append(("collapse", None, cumulative, cumulative + 6))
            cumulative += 8

        for sport in visible:
            label = SPORT_LABEL.get(sport, sport)
            width = len(label) + 7
            result.append(("sport", sport, cumulative, cumulative + width))
            cumulative += width + 2

        # ▸ at the end when collapsed
        if not self._expanded and len(ordered) > PAGE_SIZE:
            result.append(("expand", None, cumulative, cumulative + 20))

        return result

    def _handle_click_x(self, x: int):
        for kind, key, start, end in self._pill_widths():
            if start <= x < end:
                if kind == "sport":
                    self.screen.on_sport_pill_clicked(key)
                elif kind == "expand":
                    self._expanded = True
                    self._refresh_content()
                elif kind == "collapse":
                    self._expanded = False
                    self._refresh_content()
                return

    def on_mouse_up(self, event):
        self._handle_click_x(event.x)