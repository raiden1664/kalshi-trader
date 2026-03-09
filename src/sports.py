import requests
from .auth import get_headers
from .config import BASE_URL, REQUEST_TIMEOUT
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

SERIES = {
    "tennis": ["KXATPGAME", "KXWTAGAME"],
    "basketball": ["KXNCAAMBGAME", "KXNCAAWBGAME"],
}

def fetch_series_markets(series_ticker: str) -> list:
    path = "/trade-api/v2/markets"
    r = requests.get(
        f"{BASE_URL}/markets",
        headers=get_headers("GET", path),
        params={"status": "open", "limit": 100, "series_ticker": series_ticker},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("markets", [])

def is_live(market: dict) -> bool:
    # No longer filtering by time — return all open markets from the series
    return True

def group_by_match(markets: list) -> dict:
    groups = {}
    for m in markets:
        # ticker format: SERIES-DATECODETEAMS-SIDE
        # group by stripping the last part after final dash
        ticker = m.get("ticker", "")
        key = "-".join(ticker.split("-")[:-1])
        if key not in groups:
            groups[key] = []
        groups[key].append(m)
    return groups

def _price_color(yes_price: float) -> str:
    if 0.55 <= yes_price <= 0.75:
        return "green"
    if 0.80 <= yes_price <= 0.90:
        return "cyan"
    return "white"

def _classify(p: float) -> str:
    if 0.80 <= p <= 0.90: return "[cyan]T1[/cyan]"
    if 0.55 <= p <= 0.75: return "[green]T2[/green]"
    return "[dim]—[/dim]"

def _extract_names(match_markets: list) -> tuple:
    """Parse 'Will P1 win the P1 vs P2 : Round...' title into (p1, p2)."""
    title = match_markets[0].get("title", "")
    if " vs " in title:
        try:
            left  = title.split(" vs ")[0]
            right = title.split(" vs ")[1]
            p1 = left.split("Will ")[-1].split(" win")[0].strip()
            p2 = right.split(" : ")[0].strip() if " : " in right else right.split("?")[0].strip()
            return p1, p2
        except Exception:
            pass
    return ("Player 1", "Player 2")

def show_sport(sport: str):
    series_list = SERIES.get(sport, [])
    console.print(f"\n[bold cyan]{sport.title()} Markets[/bold cyan]")

    all_markets = []
    for series in series_list:
        try:
            markets = fetch_series_markets(series)
            all_markets.extend(m for m in markets if is_live(m))
        except Exception as e:
            console.print(f"[red]Error fetching {series}: {e}[/red]")

    if not all_markets:
        console.print(f"[dim]No {sport} markets right now.[/dim]\n")
        return

    groups = group_by_match(all_markets)
    console.print(f"[dim]{len(groups)} matches[/dim]\n")

    table = Table(
        box=box.SIMPLE_HEAD,
        border_style="dim",
        header_style="bold white",
        show_lines=False,
        pad_edge=False,
    )
    table.add_column("Match",   min_width=36)
    table.add_column("P1 YES",  width=8, justify="right")
    table.add_column("P2 YES",  width=8, justify="right")
    table.add_column("Volume",  width=10, justify="right")
    table.add_column("Type",    width=5)

    for match_key, match_markets in groups.items():
        match_markets.sort(key=lambda m: m.get("ticker", ""))
        p1_name, p2_name = _extract_names(match_markets)

        p1_yes = (match_markets[0].get("yes_ask") or 0) / 100 if len(match_markets) > 0 else 0
        p2_yes = (match_markets[1].get("yes_ask") or 0) / 100 if len(match_markets) > 1 else 0
        volume = sum((m.get("volume") or 0) for m in match_markets)

        c1 = _price_color(p1_yes)
        c2 = _price_color(p2_yes)
        bet_type = _classify(p1_yes) if p1_yes >= p2_yes else _classify(p2_yes)

        table.add_row(
            f"{p1_name} vs {p2_name}",
            f"[{c1}]{p1_yes:.2f}[/{c1}]",
            f"[{c2}]{p2_yes:.2f}[/{c2}]",
            f"{volume:,}",
            bet_type,
        )

    console.print(table)
    console.print()

def show_tennis():
    show_sport("tennis")

def show_basketball():
    show_sport("basketball")