from textual.widgets import Static
from src.constants import COLOR_FILTERS, COLOR_META


class ColorFilterBar(Static):
    """Color filter pills — always visible, no expand/collapse."""

    def __init__(self, **kwargs):
        self._active = "all"
        super().__init__(self._build(), **kwargs)

    def _build(self) -> str:
        parts = []
        for key in COLOR_FILTERS:
            color, label = COLOR_META[key]
            if key == self._active:
                parts.append(f"[bold {color} reverse]  {label}  [/bold {color} reverse]")
            else:
                parts.append(f"[{color}]  {label}  [/{color}]")
        return "  " + "  ".join(parts)

    def set_active(self, key: str):
        self._active = key
        self.update(self._build())

    def on_mouse_up(self, event):
        pills = COLOR_FILTERS
        x = event.x
        cumulative = 2
        clicked = self._active
        for key in pills:
            _, label = COLOR_META[key]
            width = len(label) + 6
            if x < cumulative + width:
                clicked = key
                break
            cumulative += width + 2

        self.set_active(clicked)
        self.screen.apply_color_filter(clicked)