from textual.widgets import Static


class SectionHeader(Static):
    """Clickable collapsible section header."""

    def __init__(self, label: str, color: str, section: str,
                 expanded: bool = False, loading: bool = False, count: int = 0, **kwargs):
        self._label    = label
        self._color    = color
        self._section  = section
        self._expanded = expanded
        self._loading  = loading
        self._count    = count
        super().__init__(self._build(), **kwargs)

    def _build(self) -> str:
        arrow  = "▼" if self._expanded else "▶"
        suffix = (" [dim]loading...[/dim]" if self._loading
                  else (f" [dim]({self._count} markets)[/dim]" if self._count else ""))
        return f"[{self._color}]{arrow} {self._label}[/{self._color}]{suffix}"

    def set_state(self, expanded=None, loading=None, count=None):
        if expanded is not None: self._expanded = expanded
        if loading  is not None: self._loading  = loading
        if count    is not None: self._count     = count
        self.update(self._build())

    def on_click(self):
        self.screen.toggle_section(self._section)