"""
filter.py — Market filtering and bet-type classification.
"""

from .config import (
    SPORT_KEYWORDS,
    TYPE1_MIN, TYPE1_MAX,
    TYPE2_MIN, TYPE2_MAX,
)


def is_sports_market(market: dict) -> bool:
    combined = (
        (market.get("title") or "") + " " +
        (market.get("subtitle") or "")
    ).lower()
    return any(kw in combined for kw in SPORT_KEYWORDS)


def classify(yes_price: float) -> str | None:
    """Return 'Type 1', 'Type 2', or None."""
    if TYPE1_MIN <= yes_price <= TYPE1_MAX:
        return "Type 1"
    if TYPE2_MIN <= yes_price <= TYPE2_MAX:
        return "Type 2"
    return None


def filter_markets(markets: list) -> list:
    """
    Filter to sports markets in Type 1 or Type 2 price range.
    Returns list of dicts ready for rendering.
    """
    results = []
    for m in markets:
        if not is_sports_market(m):
            continue

        yes_price = (m.get("yes_ask") or 0) / 100
        no_price  = (m.get("no_ask")  or 0) / 100
        bet_type  = classify(yes_price)

        if bet_type:
            results.append({
                "ticker":    m.get("ticker", ""),
                "title":     (m.get("title") or "")[:65],
                "yes_price": yes_price,
                "no_price":  no_price,
                "type":      bet_type,
                "volume":    m.get("volume", 0),
            })

    # Type 2 first (higher edge), then by yes_price ascending within each type
    results.sort(key=lambda x: (x["type"] != "Type 2", x["yes_price"]))
    return results
