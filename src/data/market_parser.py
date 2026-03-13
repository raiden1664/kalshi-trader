"""
market_parser.py — Parses raw market dicts into structured, display-ready data.

Handles name extraction and match grouping. Kept separate from filtering and
fetching so each layer can be tested and changed independently.
"""


def group_by_match(markets: list) -> dict:
    """
    Group YES/NO contracts for the same match under a shared key.
    Ticker format: KXATPMATCH-26MAR09P1P2-YES → key = KXATPMATCH-26MAR09P1P2
    """
    groups: dict = {}
    for m in markets:
        parts = m.get("ticker", "").split("-")
        key   = "-".join(parts[:-1]) if len(parts) > 1 else m.get("ticker", "")
        groups.setdefault(key, []).append(m)
    return groups


def extract_names(markets: list) -> tuple[str, str]:
    """
    Extract player/team names from a group of contracts for the same match.

    Priority order:
    1. yes_sub_title / subtitle fields — cleanest, set explicitly by Kalshi
    2. Title string with ' vs ' — tennis format
    3. Title string with ' at ' — team sports
    4. Ticker slug fallback
    """
    if not markets:
        return "P1", "P2"

    # Collect unique subtitle values across all contracts in the group
    subtitles = []
    seen = set()
    for m in markets:
        for field in ("yes_sub_title", "subtitle"):
            val = (m.get(field) or "").strip()
            if val and val not in seen:
                subtitles.append(val)
                seen.add(val)
    if len(subtitles) >= 2:
        return subtitles[0], subtitles[1]
    if len(subtitles) == 1:
        return subtitles[0], "?"

    # Fallback: parse the title string
    title = markets[0].get("title", "")
    if " vs " in title:
        vs_idx = title.index(" vs ")
        p1     = title[:vs_idx].split()[-1]
        after  = title[vs_idx + 4:]
        for delim in (" :", " match", "?", " -"):
            if delim in after:
                after = after[:after.index(delim)]
        p2_words = after.strip().split()
        return p1, (p2_words[-1] if p2_words else "P2")

    if " at " in title:
        at_idx = title.index(" at ")
        p1     = title[:at_idx].split()[-1]
        after  = title[at_idx + 4:]
        for delim in (" Winner", "?", " Game"):
            if delim in after:
                after = after[:after.index(delim)]
        return p1, (after.strip().split()[-1] if after.strip() else "P2")

    # Last resort: ticker slug
    parts = markets[0].get("ticker", "").split("-")
    if len(parts) >= 2:
        return parts[-2].capitalize(), parts[-1].capitalize()
    return "P1", "P2"


def match_label(markets: list) -> str:
    """Human-readable 'P1 vs P2' label for a match group."""
    p1, p2 = extract_names(markets)
    if p1 and p1 != "P1":
        return f"{p1} vs {p2}"
    title = markets[0].get("title", "") if markets else ""
    if " vs " in title:
        vs_idx = title.index(" vs ")
        p1     = title[:vs_idx].split()[-1]
        after  = title[vs_idx + 4:].split(" :")[0].split(" match")[0].split("?")[0].strip()
        words  = after.split()
        return f"{p1} vs {words[-1] if len(words) > 2 else after}"
    return title[:40] or "Unknown"