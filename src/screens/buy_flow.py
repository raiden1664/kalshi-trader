"""
buy_flow.py — Buy flow state machine for the match detail screen.

Handles the multi-step B → player → YES/NO → amount → confirm flow.
Extracted from match_detail.py to keep the screen class focused on display.
Instantiated by MatchScreen and given a reference back to the screen.
"""
from src.data.classifier import price_color, classify
from src.core.paper import PAPER_COLOR

# Buy flow states
BUY_OFF     = 0
BUY_PLAYER  = 1
BUY_SIDE    = 2
BUY_AMOUNT  = 3
BUY_CONFIRM = 4   # live price fetched, waiting for final Enter


class BuyFlow:
    """
    Self-contained buy flow. The screen delegates all B-key handling here
    and calls refresh_block() whenever the UI needs updating.
    """

    def __init__(self, screen):
        self._screen        = screen   # back-reference to MatchScreen
        self.state          = BUY_OFF
        self._cursor        = 0        # which player is selected
        self._side_cur      = 0        # 0=YES, 1=NO
        self._input         = ""       # dollar amount being typed
        self._status        = ""       # status/error message
        self._confirm_price = 0        # live-fetched price in cents
        self._confirm_type  = ""       # Type 1 / Type 2 / —

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _mm(self):
        return sorted(self._screen.match_markets, key=lambda x: x.get("ticker", ""))

    def _money_color(self) -> str:
        return PAPER_COLOR if self._screen.app.paper_mode else "cyan"

    def reset(self):
        self.state     = BUY_OFF
        self._cursor   = 0
        self._side_cur = 0
        self._input    = ""
        self._status   = ""

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> str:
        """Return Rich markup string for the buy block."""
        mm     = self._mm()
        mc     = self._money_color()
        paper  = self._screen.app.paper_mode
        p_tag  = f" [bold {PAPER_COLOR}][PAPER][/bold {PAPER_COLOR}]" if paper else ""
        hint   = (f"  [dim]↑↓ move · Enter to buy [/dim][bold {PAPER_COLOR}]paper[/bold {PAPER_COLOR}][dim] bet · Esc cancel[/dim]"
                  if paper else
                  f"  [dim]↑↓ move · Enter to buy [/dim][bold #00e676]live[/bold #00e676][dim] bet · Esc cancel[/dim]")

        if self.state == BUY_OFF:
            return "\n".join(["─" * 52, "", f"  [dim]B[/dim] = Place a bet{p_tag}", ""])

        elif self.state == BUY_PLAYER:
            lines = ["─" * 52, "", f"  [bold white]Buy{p_tag} — Pick a player[/bold white]", ""]
            for i, m in enumerate(mm):
                slug    = m.get("ticker", "").split("-")[-1].capitalize()
                yes_ask = m.get("yes_ask") or 0
                no_ask  = m.get("no_ask")  or 0
                row     = f"  {slug}   YES [{mc}]{yes_ask}¢[/{mc}]  ·  NO {no_ask}¢"
                lines.append(f"[reverse]{row}[/reverse]" if i == self._cursor else row)
            lines += ["", hint, ""]
            return "\n".join(lines)

        elif self.state == BUY_SIDE:
            m       = mm[self._cursor] if self._cursor < len(mm) else mm[0]
            slug    = m.get("ticker", "").split("-")[-1].capitalize()
            yes_ask = m.get("yes_ask") or 0
            no_ask  = m.get("no_ask")  or 0
            sides   = [f"  YES  [{mc}]{yes_ask}¢[/{mc}]", f"  NO   {no_ask}¢"]
            lines   = ["─" * 52, "", f"  [bold white]Buy {slug}{p_tag} — YES or NO?[/bold white]", ""]
            for i, s in enumerate(sides):
                lines.append(f"[reverse]{s}[/reverse]" if i == self._side_cur else s)
            side_hint = (f"  [dim]↑↓ move · Enter to buy [/dim][bold {PAPER_COLOR}]paper[/bold {PAPER_COLOR}][dim] bet · Esc back[/dim]"
                         if paper else
                         f"  [dim]↑↓ move · Enter to buy [/dim][bold #00e676]live[/bold #00e676][dim] bet · Esc back[/dim]")
            lines += ["", side_hint, ""]
            return "\n".join(lines)

        elif self.state == BUY_AMOUNT:
            m     = mm[self._cursor] if self._cursor < len(mm) else mm[0]
            slug  = m.get("ticker", "").split("-")[-1].capitalize()
            side  = "YES" if self._side_cur == 0 else "NO"
            price = (m.get("yes_ask") if side == "YES" else m.get("no_ask")) or 0
            amt   = self._input or "_"
            status = f"\n  [yellow]{self._status}[/yellow]" if self._status else ""
            return "\n".join([
                "─" * 52, "",
                f"  [bold white]Buy {slug} {side} @ [{mc}]{price}¢[/{mc}]{p_tag}[/bold white]",
                "",
                f"  Amount: [bold {mc}]${amt}[/bold {mc}]",
                f"  [dim]type dollars · Enter confirm · Esc back[/dim]",
                status, "",
            ])

        elif self.state == BUY_CONFIRM:
            m    = mm[self._cursor] if self._cursor < len(mm) else mm[0]
            slug = m.get("ticker", "").split("-")[-1].capitalize()
            side = "YES" if self._side_cur == 0 else "NO"
            btype = self._confirm_type
            type_str = (
                "[#00bcd4]Type 1[/#00bcd4]" if btype == "Type 1" else
                "[#00e676]Type 2[/#00e676]" if btype == "Type 2" else
                "[dim]—[/dim]"
            )
            warning = (
                f"  [bold {PAPER_COLOR}]◆ PAPER ORDER — simulated, no real money[/bold {PAPER_COLOR}]"
                if paper else
                f"  [bold #ff4444]⚠  LIVE ORDER — real money will be spent[/bold #ff4444]"
            )
            status = f"\n  [yellow]{self._status}[/yellow]" if self._status else ""
            return "\n".join([
                "─" * 52, "",
                warning, "",
                f"  {slug} {side}  [{mc}]{self._confirm_price}¢[/{mc}]"
                f"  [bold {mc}]${self._input}[/bold {mc}]  {type_str}",
                "",
                f"  [bold]Enter[/bold] = confirm   [bold]Esc[/bold] = cancel",
                status, "",
            ])

        return ""

    # ── Key handling ──────────────────────────────────────────────────────────

    def handle_key(self, event) -> bool:
        """
        Process a key event. Returns True if the event was consumed.
        The screen calls this first; if True, it stops the event.
        """
        if self.state == BUY_OFF:
            if event.key == "b":
                self.state    = BUY_PLAYER
                self._cursor  = 0
                self._status  = ""
                self._refresh()
                return True
            return False

        elif self.state == BUY_PLAYER:
            mm = self._mm()
            if event.key == "escape":
                self.state = BUY_OFF
            elif event.key == "up":
                self._cursor = max(0, self._cursor - 1)
            elif event.key == "down":
                self._cursor = min(len(mm) - 1, self._cursor + 1)
            elif event.key == "enter":
                self.state     = BUY_SIDE
                self._side_cur = 0
            self._refresh()
            return True

        elif self.state == BUY_SIDE:
            if event.key == "escape":
                self.state = BUY_PLAYER
            elif event.key == "up":
                self._side_cur = max(0, self._side_cur - 1)
            elif event.key == "down":
                self._side_cur = min(1, self._side_cur + 1)
            elif event.key == "enter":
                self.state  = BUY_AMOUNT
                self._input = ""
            self._refresh()
            return True

        elif self.state == BUY_AMOUNT:
            if event.key == "escape":
                self.state = BUY_SIDE
            elif event.key == "backspace":
                self._input = self._input[:-1]
            elif event.key == "enter":
                try:
                    assert float(self._input) > 0
                    self._status = "Fetching live price..."
                    self._refresh()
                    self._screen._fetch_confirm_price()
                except Exception:
                    self._status = "[red]Enter a valid dollar amount[/red]"
            elif event.character and event.character in "0123456789.":
                self._input += event.character
            self._refresh()
            return True

        elif self.state == BUY_CONFIRM:
            if event.key == "escape":
                self.state   = BUY_AMOUNT
                self._status = ""
                self._refresh()
            elif event.key == "enter":
                if self._screen.app.paper_mode:
                    self._screen._confirm_paper_buy()
                else:
                    self._screen._confirm_buy()
            return True

        return False

    def _refresh(self):
        self._screen._refresh_buy_block()