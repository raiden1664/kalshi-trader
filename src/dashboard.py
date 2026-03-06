#!/usr/bin/env python3
"""
Kalshi Trader — Terminal Dashboard
Entry point. Run with: python -m src.dashboard
"""

import sys
import time
import requests
from rich.console import Console
from rich.live import Live

from .auth import login, AuthError
from .api import fetch_balance, fetch_positions, fetch_markets
from .filter import filter_markets
from .render import render_layout
from .config import REFRESH_SECONDS, KALSHI_EMAIL, KALSHI_PASSWORD

console = Console()


def main():
    console.print("[bold magenta]kalshi-trader[/bold magenta] — starting up...")

    if not KALSHI_EMAIL or not KALSHI_PASSWORD:
        console.print(
            "[red]Missing credentials.[/red] Set env vars before running:\n"
            "  export KALSHI_EMAIL='you@email.com'\n"
            "  export KALSHI_PASSWORD='yourpassword'"
        )
        sys.exit(1)

    console.print("Logging in...", end=" ")
    try:
        token = login(KALSHI_EMAIL, KALSHI_PASSWORD)
    except AuthError as e:
        console.print(f"[red]Failed: {e}[/red]")
        sys.exit(1)
    console.print("[green]✓[/green]")

    def refresh():
        try:
            balance   = fetch_balance(token)
            positions = fetch_positions(token)
            markets   = fetch_markets(token)
            filtered  = filter_markets(markets)
            return render_layout(balance, positions, filtered)
        except requests.HTTPError as e:
            console.print(f"[red]API error: {e}[/red]")
            return None

    layout = refresh()
    if layout is None:
        sys.exit(1)

    with Live(layout, refresh_per_second=1, screen=True) as live:
        last_fetch = time.time()
        while True:
            time.sleep(1)
            if time.time() - last_fetch >= REFRESH_SECONDS:
                updated = refresh()
                if updated:
                    live.update(updated)
                last_fetch = time.time()


if __name__ == "__main__":
    main()
