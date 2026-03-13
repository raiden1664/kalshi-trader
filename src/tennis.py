"""
tennis.py — Compatibility shim.

All logic has been moved to focused modules:
  - src/markets_api.py   — fetching and normalization
  - src/cache.py         — disk-backed caching
  - src/market_filter.py — filter_active, is_live
  - src/market_parser.py — group_by_match, extract_names
  - src/classifier.py    — price_color, classify

This file re-exports everything so existing imports keep working without
changes. Delete it once all import sites are updated.
"""
from src.data.markets_api import fetch_series as fetch_series_markets, fetch_series_concurrent as fetch_all_series_concurrent
from src.data.market_filter import filter_active, is_live, filter_active as filter_18h
from src.data.market_parser import group_by_match, extract_names as _extract_names, match_label
from src.data.classifier import price_color as _price_color, classify as _classify
from src.constants import SERIES

# Tennis series list — kept here as it was referenced directly in a few places
TENNIS_SERIES = SERIES["tennis"]