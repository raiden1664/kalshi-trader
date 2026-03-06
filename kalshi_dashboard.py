#!/usr/bin/env python3
"""
Kalshi Trading Dashboard
A live terminal dashboard for monitoring Kalshi markets based on your betting strategy.
"""

import os
import sys
import time
import json
import requests
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich import box

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Set these via environment variables or paste directly (not recommended for sharing)
KALSHI_EMAIL    = os.getenv("KALSHI_EMAIL", "YOUR_EMAIL_HERE")
KALSHI_PASSWORD = os.getenv("KALSHI_PASSWORD", "YOUR_PASSWORD_HERE")

REFRESH_SECONDS = 30

# Price range filters (in cents, so 0.55 = 55¢)
TYPE1_MIN = 0.80
TYPE1_MAX = 0.90
TYPE2_MIN = 0.55
TYPE2_MAX = 0.75

# Keywords to match tennis + NBA/NCAAB markets
SPORT_KEYWORDS = [
    "tennis", "nba", "ncaab", "basketball",
    "atp", "wta", "slam", "open"
]

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"

console = Console()


# ── AUTH ──────────────────────────────────────────────────────────────────────
def login(email: str, password: str) -> str:
    """Authenticate and return a session token."""
    resp = requests.post(
        f"{BASE_URL}/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json().get("token")
    if not token:
        raise ValueError("Login failed — check your credentials.")
    return token


def get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── API CALLS ─────────────────────────────────────────────────────────────────
def fetch_balance(token: str) -> dict:
    resp = requests.get(f"{BASE_URL}/portfolio/balance", headers=get_headers(token), timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_positions(token: str) -> list:
    resp = requests.get(f"{BASE_URL}/portfolio/positions", headers=get_headers(token), timeout=10)
    resp.raise_for_status()
    return resp.json().get("market_positions", [])


def fetch_markets(token: str, limit: int = 200) -> list:
    params = {"status": "open", "limit": limit}
    resp = requests.get(f"{BASE_URL}/markets", headers=get_headers(token), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("markets", [])


# ── FILTERING & CLASSIFICATION ────────────────────────────────────────────────
def is_sports_market(market: dict) -> bool:
    title = (market.get("title") or "").lower()
    subtitle = (market.get("subtitle") or "").lower()
    combined = title + " " + subtitle
    return any(kw in combined for kw in SPORT_KEYWORDS)


def classify_market(yes_price: float) -> str:
    """Return Type 1, Type 2, or None."""
    if TYPE1_MIN <= yes_price <= TYPE1_MAX:
        return "Type 1"
    if TYPE2_MIN <= yes_price <= TYPE2_MAX:
        return "Type 2"
    return None


def filter_markets(markets: list) -> list:
    """Return sports markets that fall in Type 1 or Type 2 price ranges."""
    results = []
    for m in markets:
        if not is_sports_market(m):
            continue
        yes_price = (m.get("yes_ask") or 0) / 100  # Kalshi prices in cents
        no_price  = (m.get("no_ask")  or 0) / 100
        bet_type  = classify_market(yes_price)
        if bet_type:
            results.append({
                "ticker":    m.get("ticker", ""),
                "title":     m.get("title", "")[:60],
                "yes_price": yes_price,
                "no_price":  no_price,
                "type":      bet_type,
                "volume":    m.get("volume", 0),
                "close_time": m.get("close_time", ""),
            })
    # Sort: Type 2 first (higher value), then by yes_price ascending
    results.sort(key=lambda x: (x["type"] != "Type 2", x["yes_price"]))
    return results


# ── RENDERING ─────────────────────────────────────────────────────────────────
def type_color(bet_type: str) -> str:
    return "green" if bet_type == "Type 2" else "cyan"


def build_header(balance: dict, last_refresh: str) -> Panel:
    cash_balance = balance.get("balance", 0) / 100  # cents → dollars
    portfolio_value = balance.get("portfolio_value", 0) / 100

    text = Text()
    text.append("💰 Cash: ", style="bold white")
    text.append(f"${cash_balance:.2f}   ", style="bold green")
    text.append("📈 Portfolio: ", style="bold white")
    text.append(f"${portfolio_value:.2f}   ", style="bold yellow")
    text.append("🕐 Last refresh: ", style="dim")
    text.append(last_refresh, style="dim")

    return Panel(text, title="[bold magenta]Kalshi Dashboard[/bold magenta]", border_style="magenta")


def build_opportunities_table(markets: list) -> Table:
    table = Table(
        title="🎯 Opportunities (Sports Markets in Range)",
        box=box.ROUNDED,
        border_style="blue",
        show_lines=False,
        header_style="bold blue",
    )
    table.add_column("Type",      width=8)
    table.add_column("Yes $",     width=7,  justify="right")
    table.add_column("No $",      width=7,  justify="right")
    table.add_column("Volume",    width=8,  justify="right")
    table.add_column("Market",    min_width=40)

    if not markets:
        table.add_row("—", "—", "—", "—", "[dim]No qualifying markets found right now[/dim]")
        return table

    for m in markets:
        color = type_color(m["type"])
        table.add_row(
            f"[{color}]{m['type']}[/{color}]",
            f"[{color}]{m['yes_price']:.2f}[/{color}]",
            f"{m['no_price']:.2f}",
            f"{m['volume']:,}",
            m["title"],
        )
    return table


def build_positions_table(positions: list) -> Table:
    table = Table(
        title="📂 Your Open Positions",
        box=box.ROUNDED,
        border_style="yellow",
        header_style="bold yellow",
    )
    table.add_column("Ticker",    width=20)
    table.add_column("Side",      width=6)
    table.add_column("Contracts", width=10, justify="right")
    table.add_column("Value",     width=10, justify="right")

    if not positions:
        table.add_row("—", "—", "—", "[dim]No open positions[/dim]")
        return table

    for p in positions:
        yes_qty = p.get("position", 0)
        side    = "YES" if yes_qty > 0 else "NO"
        qty     = abs(yes_qty)
        value   = p.get("market_exposure", 0) / 100
        color   = "green" if side == "YES" else "red"
        table.add_row(
            p.get("ticker", ""),
            f"[{color}]{side}[/{color}]",
            str(qty),
            f"${value:.2f}",
        )
    return table


def build_legend() -> Panel:
    text = Text()
    text.append("Type 1  ", style="bold cyan")
    text.append(f"80–90¢  Near-lock, ~30% of bankroll\n", style="white")
    text.append("Type 2  ", style="bold green")
    text.append(f"55–75¢  Mispriced value play, ~20–30% of bankroll\n", style="white")
    text.append("\n", style="white")
    text.append("Rules:  ", style="bold white")
    text.append("Never buy above 70¢  •  Keep cash reserve  •  Sell when momentum flips", style="dim")
    return Panel(text, title="Strategy Guide", border_style="dim", padding=(0, 1))


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def render(token: str) -> Layout:
    now = datetime.now().strftime("%H:%M:%S")
    try:
        balance   = fetch_balance(token)
        positions = fetch_positions(token)
        markets   = fetch_markets(token)
        filtered  = filter_markets(markets)
    except requests.HTTPError as e:
        console.print(f"[red]API error: {e}[/red]")
        return

    layout = Layout()
    layout.split_column(
        Layout(build_header(balance, now),            name="header",  size=3),
        Layout(build_opportunities_table(filtered),   name="opps",    ratio=3),
        Layout(build_positions_table(positions),      name="pos",     ratio=2),
        Layout(build_legend(),                        name="legend",  size=5),
    )
    return layout


def main():
    console.print("[bold magenta]Kalshi Dashboard[/bold magenta] — starting up...")

    if KALSHI_EMAIL == "YOUR_EMAIL_HERE":
        console.print(
            "[red]Set KALSHI_EMAIL and KALSHI_PASSWORD as env vars before running.[/red]\n"
            "  export KALSHI_EMAIL='you@email.com'\n"
            "  export KALSHI_PASSWORD='yourpassword'"
        )
        sys.exit(1)

    console.print("Logging in...", end=" ")
    try:
        token = login(KALSHI_EMAIL, KALSHI_PASSWORD)
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")
        sys.exit(1)
    console.print("[green]✓[/green]")

    with Live(render(token), refresh_per_second=1, screen=True) as live:
        last_fetch = time.time()
        while True:
            time.sleep(1)
            if time.time() - last_fetch >= REFRESH_SECONDS:
                live.update(render(token))
                last_fetch = time.time()


if __name__ == "__main__":
    main()
