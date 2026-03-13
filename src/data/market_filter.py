"""
market_filter.py — Decides which markets are active and which are live.

Separates the "is this market worth showing?" logic from fetching and parsing.
Two main concerns:
  - filter_active: trim the raw API response to markets worth displaying
  - is_live: determine if a match is currently in progress
"""
from datetime import datetime, timezone, timedelta


def _parse_ts(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def filter_active(markets: list) -> list:
    """
    Keep markets that are currently open or starting within 18 hours.
    Drops already-closed/resolved markets and anything without timing data.
    """
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=18)
    result = []
    for m in markets:
        open_ts  = _parse_ts(m.get("open_time"))
        close_ts = _parse_ts(m.get("close_time") or m.get("expiration_time"))

        if close_ts and close_ts < now:
            continue  # already settled
        if open_ts and open_ts <= cutoff:
            result.append(m)
    return result


# Per-series volume floors for live detection.
# Main tour markets accumulate high volume quickly; challengers much less.
# These are intentionally low — time gating is the primary mechanism.
_LIVE_VOL = {
    "KXATPMATCH":           5_000,
    "KXWTAMATCH":           5_000,
    "KXATPCHALLENGERMATCH":   500,
    "KXWTACHALLENGERMATCH":   500,
    "KXNBAGAME":            5_000,
    "KXNHLGAME":            5_000,
    "KXMLBGAME":            5_000,
    "KXNCAAMBGAME":         2_000,
    "KXNCAAWBGAME":         2_000,
}
_LIVE_VOL_DEFAULT = 2_000


def is_live(market: dict) -> bool:
    """
    Three-gate check for in-play status:
    1. Market must be open (open_time past, not yet closed)
    2. Time gate: if expected_expiration_time is > 4h away, match hasn't started.
       Falls back to requiring 30min since open_time if that field is absent.
    3. Volume floor: filters dead/abandoned markets (low bar — time gate does
       the heavy lifting).
    """
    now = datetime.now(timezone.utc)

    open_ts  = _parse_ts(market.get("open_time"))
    close_ts = _parse_ts(market.get("close_time") or market.get("expiration_time"))
    exp_ts   = _parse_ts(market.get("expected_expiration_time"))

    # Gate 1: must be open
    if not open_ts or open_ts > now:
        return False
    if close_ts and close_ts < now:
        return False

    # Gate 2: time-based start detection
    if exp_ts:
        if (exp_ts - now).total_seconds() / 3600 > 4.0:
            return False
    else:
        if (now - open_ts).total_seconds() < 1800:
            return False

    # Gate 3: volume floor
    series    = market.get("ticker", "").split("-")[0]
    threshold = _LIVE_VOL.get(series, _LIVE_VOL_DEFAULT)
    vol       = float(market.get("volume") or market.get("volume_fp") or 0)
    return vol >= threshold