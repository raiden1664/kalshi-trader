"""
watch_flow.py — Watch flow state machine for the markets screen.

Handles the multi-step W → player → trigger price → dollar amount flow.
Extracted from markets.py to keep MatchListScreen focused on display/routing.
Instantiated by MatchListScreen and given a reference back to the screen.
"""

# Watch flow states
WATCH_OFF     = 0
WATCH_PLAYER  = 1
WATCH_PRICE   = 2
WATCH_DOLLARS = 3


class WatchFlow:
    """
    Self-contained watch flow. The screen delegates W-key handling here
    and calls _draw() to render into the #watch_panel Static widget.
    """

    def __init__(self, screen):
        self._screen  = screen
        self.state    = WATCH_OFF
        self._key     = ""    # match key being watched
        self._cursor  = 0     # which player is selected
        self._input   = ""    # user's typed input
        self._price   = 0     # confirmed trigger price in cents
        self._status  = ""    # status/error message

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, match_key: str):
        """Kick off the watch flow for a given match key."""
        self._key    = match_key
        self.state   = WATCH_PLAYER
        self._cursor = 0
        self._input  = ""
        self._status = ""
        self._draw()

    def reset(self):
        self.state   = WATCH_OFF
        self._status = ""
        self._draw()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_mm(self):
        """Fetch sorted markets for the current match key."""
        dm     = self._screen.app.data_manager
        groups = {}
        for sport in ("tennis", "basketball", "politics"):
            groups.update(dm.get_groups(sport))
        return sorted(groups.get(self._key, []), key=lambda x: x.get("ticker", ""))

    # ── Render ────────────────────────────────────────────────────────────────

    def _draw(self):
        """Update the #watch_panel Static widget with current flow state."""
        try:
            panel = self._screen.query_one("#watch_panel")
        except Exception:
            return

        if self.state == WATCH_OFF:
            panel.update("")
            return

        mm    = self._get_mm()
        lines = ["─" * 52, "", "  [bold white]Set Buy Watch[/bold white]", ""]

        if self.state == WATCH_PLAYER:
            lines.append("  Pick player to watch:")
            for i, m in enumerate(mm):
                slug    = m.get("ticker", "").split("-")[-1].capitalize()
                yes_ask = m.get("yes_ask") or 0
                row     = f"  {slug}   YES {yes_ask}¢"
                lines.append(f"[reverse]{row}[/reverse]" if i == self._cursor else row)
            lines += ["", "  [dim]↑↓ move · Enter select · Esc cancel[/dim]", ""]

        elif self.state == WATCH_PRICE:
            m       = mm[self._cursor] if self._cursor < len(mm) else mm[0]
            slug    = m.get("ticker", "").split("-")[-1].capitalize()
            yes_ask = m.get("yes_ask") or 0
            price   = self._input or "_"
            lines += [
                f"  [white]{slug}[/white] YES — currently [white]{yes_ask}¢[/white]",
                f"  Trigger buy when price drops to:",
                f"  [bold #ffd700]{price}¢[/bold #ffd700]   [dim]Enter confirm · Esc back[/dim]",
                "",
            ]

        elif self.state == WATCH_DOLLARS:
            m    = mm[self._cursor] if self._cursor < len(mm) else mm[0]
            slug = m.get("ticker", "").split("-")[-1].capitalize()
            amt  = self._input or "_"
            status = f"\n  [yellow]{self._status}[/yellow]" if self._status else ""
            lines += [
                f"  [white]{slug}[/white] YES  trigger @ [#ffd700]{self._price}¢[/#ffd700]",
                f"  How much to spend:",
                f"  [bold cyan]${amt}[/bold cyan]   [dim]Enter confirm · Esc back[/dim]",
                status, "",
            ]

        if self._status and self.state != WATCH_DOLLARS:
            lines.append(f"  [yellow]{self._status}[/yellow]")

        panel.update("\n".join(lines))

    # ── Key handling ──────────────────────────────────────────────────────────

    def handle_key(self, event) -> bool:
        """
        Process a key event. Returns True if the event was consumed.
        The screen calls this when state != WATCH_OFF.
        """
        mm = self._get_mm()

        if self.state == WATCH_PLAYER:
            if event.key == "escape":
                self.reset()
            elif event.key == "up":
                self._cursor = max(0, self._cursor - 1)
                self._draw()
            elif event.key == "down":
                self._cursor = min(len(mm) - 1, self._cursor + 1)
                self._draw()
            elif event.key == "enter":
                self.state  = WATCH_PRICE
                self._input = ""
                self._draw()
            return True

        elif self.state == WATCH_PRICE:
            if event.key == "escape":
                self.state  = WATCH_PLAYER
                self._input = ""
                self._draw()
            elif event.key == "backspace":
                self._input = self._input[:-1]
                self._draw()
            elif event.key == "enter":
                try:
                    p = int(self._input)
                    assert 1 <= p <= 99
                    self._price = p
                    self.state  = WATCH_DOLLARS
                    self._input = ""
                    self._draw()
                except Exception:
                    self._status = "[red]Enter whole cents 1–99[/red]"
                    self._draw()
            elif event.character and event.character in "0123456789":
                self._input += event.character
                self._draw()
            return True

        elif self.state == WATCH_DOLLARS:
            if event.key == "escape":
                self.state  = WATCH_PRICE
                self._input = str(self._price)
                self._draw()
            elif event.key == "backspace":
                self._input = self._input[:-1]
                self._draw()
            elif event.key == "enter":
                try:
                    dollars = float(self._input)
                    assert dollars > 0
                except Exception:
                    self._status = "[red]Enter a valid dollar amount[/red]"
                    self._draw()
                    return True

                m      = mm[self._cursor] if self._cursor < len(mm) else mm[0]
                ticker = m.get("ticker", "")
                slug   = ticker.split("-")[-1].capitalize()
                wid    = self._screen.app.buy_watcher.add_watch(
                    ticker=ticker, side="yes",
                    trigger_price=self._price,
                    dollars=dollars,
                    label=slug,
                )
                self.reset()
                # Show a success flash in the status bar
                try:
                    from textual.widgets import Static
                    self._screen.query_one("#status", Static).update(
                        f"[#00e676]✓ Watch set: {slug} YES @ {self._price}¢ for ${dollars:.2f} (id:{wid})[/#00e676]"
                    )
                except Exception:
                    pass
            elif event.character and event.character in "0123456789.":
                self._input += event.character
                self._draw()
            return True

        return False