"""
classifier.py — Price classification and color coding for the trading framework.

All bet-type logic lives here. If thresholds change, this is the only file
that needs updating.
"""
from src.constants import TYPE1_MIN, TYPE1_MAX, TYPE2_MIN, TYPE2_MAX


def classify(yes_price: float) -> str:
    """Return 'Type 1', 'Type 2', or '—' based on trading framework thresholds."""
    if TYPE1_MIN <= yes_price <= TYPE1_MAX:
        return "Type 1"
    if TYPE2_MIN <= yes_price <= TYPE2_MAX:
        return "Type 2"
    return "—"


def price_color(price: float) -> str:
    """
    Rich markup color for a YES price.
    Green  = Type 2 value range (55-75¢)
    Cyan   = Type 1 near-lock range (80-90¢)
    Gold   = Extreme lock (>90¢) — rarely traded
    White  = Outside any range
    """
    if 0.55 <= price <= 0.75:
        return "#00e676"   # green — Type 2
    if 0.80 <= price <= 0.90:
        return "#00bcd4"   # cyan  — Type 1
    if price >= 0.91:
        return "#ffd700"   # gold  — near-lock
    return "white"


def price_bucket(yes_p: float) -> str:
    """
    Map price to color filter bucket used by the ColorFilterBar.
    Red    = outside tradeable range (too high or zero)
    Yellow = borderline / soft ceiling zone
    Green  = active trading range
    """
    if yes_p >= 0.81 or yes_p <= 0.00:
        return "red"
    if 0.70 <= yes_p <= 0.80:
        return "yellow"
    return "green"