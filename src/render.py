"""
render.py — Terminal UI layout using Rich.
"""

from datetime import datetime
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


def _header(balance: dict) -> Panel:
    cash      = balance.get("balance", 0) / 100
    portfolio = balance.get("portfolio_value", 0) / 100
    now       = datetime.now().strftime("%H:%M:%S")

    t = Text()
    t.append("💰 Cash: ",      style="bold white")
    t.append(f"${cash:.2f}   ", style="bold green")
    t.append("📈 Portfolio: ", style="bold white")
    t.append(f"${portfolio:.2f}   ", style="bold yellow")
    t.append("🕐 ",            style="dim")
    t.append(now,              style="dim")

    return Panel(t, title="[bold magenta]kalshi-trader[/bold magenta]", border_style="magenta")


def _opportunities_table(markets: list) -> Table:
    table = Table(
        title="🎯 Opportunities — Sports Markets In Range",
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold blue",
        show_lines=False,
    )
    table.add_column("Type",    width=8)
    table.add_column("YES $",   width=7,  justify="right")
    table.add_column("NO $",    width=7,  justify="right")
    table.add_column("Volume",  width=9,  justify="right")
    table.add_column("Market",  min_width=40)

    if not markets:
        table.add_row("—", "—", "—", "—", "[dim]No qualifying markets right now[/dim]")
        return table

    for m in markets:
        color = "green" if m["type"] == "Type 2" else "cyan"
        table.add_row(
            f"[{color}]{m['type']}[/{color}]",
            f"[{color}]{m['yes_price']:.2f}[/{color}]",
            f"{m['no_price']:.2f}",
            f"{m['volume']:,}",
            m["title"],
        )
    return table


def _positions_table(positions: list) -> Table:
    table = Table(
        title="📂 Open Positions",
        box=box.ROUNDED,
        border_style="yellow",
        header_style="bold yellow",
    )
    table.add_column("Ticker",    min_width=20)
    table.add_column("Side",      width=6)
    table.add_column("Contracts", width=10, justify="right")
    table.add_column("Exposure",  width=10, justify="right")

    if not positions:
        table.add_row("—", "—", "—", "[dim]No open positions[/dim]")
        return table

    for p in positions:
        qty    = p.get("position", 0)
        side   = "YES" if qty > 0 else "NO"
        color  = "green" if side == "YES" else "red"
        value  = p.get("market_exposure", 0) / 100
        table.add_row(
            p.get("ticker", ""),
            f"[{color}]{side}[/{color}]",
            str(abs(qty)),
            f"${value:.2f}",
        )
    return table


def _legend() -> Panel:
    t = Text()
    t.append("Type 1  ", style="bold cyan")
    t.append("80–90¢  Near-lock · ~30% of bankroll\n")
    t.append("Type 2  ", style="bold green")
    t.append("55–75¢  Value play · ~20–30% of bankroll\n\n")
    t.append("Rules   ", style="bold white")
    t.append("Never buy above 70¢  ·  Keep cash reserve  ·  Sell when momentum flips", style="dim")
    return Panel(t, title="Strategy", border_style="dim", padding=(0, 1))


def render_layout(balance: dict, positions: list, markets: list) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(_header(balance),              name="header", size=3),
        Layout(_opportunities_table(markets), name="opps",   ratio=3),
        Layout(_positions_table(positions),   name="pos",    ratio=2),
        Layout(_legend(),                     name="legend", size=5),
    )
    return layout
