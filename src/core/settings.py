"""
Settings — persisted to ~/.kalshi-trader/settings.json
Only load/save what's needed, never wipe unknown keys.
"""
import json
import os
from pathlib import Path

SETTINGS_PATH = Path.home() / ".kalshi-trader" / "settings.json"

DEFAULTS = {
    "notifications": {
        "tennis":     True,
        "basketball": True,
        "politics":   True,
    },
    "default_sports": ["tennis"],   # "tennis" only, or ["tennis","basketball","politics"]
}


def load() -> dict:
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH) as f:
                data = json.load(f)
            merged = _deep_merge(DEFAULTS, data)
            return merged
        except Exception:
            pass
    return _deep_merge(DEFAULTS, {})


def save(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result