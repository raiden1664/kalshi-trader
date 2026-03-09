import sys, time, requests
from rich.console import Console
from rich.live import Live
from .auth import verify_auth, AuthError
from .api import fetch_balance, fetch_positions, fetch_markets
from .filter import filter_markets
from .render import render_layout
from .tennis import show_tennis, show_basketball
from .config import REFRESH_SECONDS, KALSHI_KEY_ID

console = Console()

def run_dashboard():
    def refresh():
        try:
            return render_layout(fetch_balance(), fetch_positions(), filter_markets(fetch_markets()))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return None

    layout = refresh()
    if not layout:
        return

    with Live(layout, refresh_per_second=1, screen=True) as live:
        last = time.time()
        while True:
            time.sleep(1)
            if time.time() - last >= REFRESH_SECONDS:
                updated = refresh()
                if updated:
                    live.update(updated)
                last = time.time()

def main():
    console.print("[bold magenta]kalshi-trader[/bold magenta] — starting up...")

    if not KALSHI_KEY_ID:
        console.print("[red]Missing KALSHI_KEY_ID. Run: export KALSHI_KEY_ID='your-id'[/red]")
        sys.exit(1)

    console.print("Verifying auth...", end=" ")
    try:
        verify_auth()
    except AuthError as e:
        console.print(f"[red]Failed: {e}[/red]")
        sys.exit(1)
    console.print("[green]✓[/green]\n")

    while True:
        console.print("[bold]Commands:[/bold] [cyan][t][/cyan] tennis  [cyan][b][/cyan] basketball  [cyan][d][/cyan] dashboard  [cyan][q][/cyan] quit")
        cmd = input("> ").strip().lower()

        if cmd == "q":
            console.print("bye")
            break
        elif cmd == "t":
            show_tennis()
        elif cmd == "b":
            show_basketball()
        elif cmd == "d":
            run_dashboard()
        else:
            console.print("[dim]Unknown command[/dim]")

if __name__ == "__main__":
    main()