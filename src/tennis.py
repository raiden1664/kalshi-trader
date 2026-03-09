import requests
from .auth import get_headers
from .config import BASE_URL, REQUEST_TIMEOUT
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

SERIES = {
    "tennis": ["KXATPMATCH", "KXWTAMATCH"],
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
    return True

def group_by_match(markets: list) -> dict:
    groups = {}
    for m in markets:
        ticker = m.get("ticker", "")
        key = "-".join(ticker.split("-")[:-1])
        if key not in groups:
            groups[key] = []
        groups[key].append(m)
    return groups

def _price_color(p: float) -> str:
    if p >= 0.81 or p <= 0.00: return "#ff4444"
    if 0.70 <= p <= 0.80:      return "#ffd700"
    return "#00e676"

def _classify(p: float) -> str:
    if 0.80 <= p <= 0.90: return "[white]T1[/white]"
    if 0.55 <= p <= 0.75: return "[white]T2[/white]"
    return "[dim]—[/dim]"

def _extract_names(match_markets: list) -> tuple:
    title = match_markets[0].get("title", "")
    if " the " in title and " vs " in title:
        try:
            after_the = title.split(" the ", 1)[1]
            vs_parts  = after_the.split(" vs ", 1)
            p1 = vs_parts[0].strip()
            p2 = vs_parts[1].split(" : ")[0].strip()
            return p1, p2
        except Exception:
            pass
    return ("P1", "P2")

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
    table.add_column("Match",   min_width=38)
    table.add_column("YES",     width=7,  justify="right")
    table.add_column("NO",      width=7,  justify="right")
    table.add_column("Volume",  width=10, justify="right")
    table.add_column("Type",    width=5)

    for match_key, match_markets in groups.items():
        match_markets.sort(key=lambda m: m.get("ticker", ""))
        p1_name, p2_name = _extract_names(match_markets)

        p1_yes = (match_markets[0].get("yes_ask") or 0) / 100 if len(match_markets) > 0 else 0
        p1_no  = (match_markets[0].get("no_ask")  or 0) / 100 if len(match_markets) > 0 else 0
        p2_yes = (match_markets[1].get("yes_ask") or 0) / 100 if len(match_markets) > 1 else 0
        p2_no  = (match_markets[1].get("no_ask")  or 0) / 100 if len(match_markets) > 1 else 0
        volume = sum((m.get("volume") or 0) for m in match_markets)

        if p1_yes >= p2_yes:
            yes_p, no_p = p1_yes, p1_no
        else:
            yes_p, no_p = p2_yes, p2_no

        color    = _price_color(yes_p)
        bet_type = _classify(yes_p)

        table.add_row(
            f"{p1_name} vs {p2_name}",
            f"[{color}]{yes_p:.2f}[/{color}]",
            f"{no_p:.2f}",
            f"{volume:,}",
            bet_type,
        )

    console.print(table)
    console.print()

def show_tennis():
    show_sport("tennis")

def show_basketball():
    show_sport("basketball")