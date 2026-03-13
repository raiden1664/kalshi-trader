"""
constants.py — Pure data: series tickers, display metadata, thresholds.
No logic here — see classifier.py for price_bucket/classify.
"""
# ── Market series ─────────────────────────────────────────────────────────────
SERIES = {
    "tennis":     ["KXATPMATCH", "KXWTAMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH"],
    "basketball": ["KXNBAGAME", "KXNCAAMBGAME", "KXNCAAWBGAME"],
    "hockey":     ["KXNHLGAME"],
    "baseball":   ["KXMLBGAME"],
    "football":   ["KXNFLGAME", "KXNFL"],
    "golf":       ["KXPGA", "KXGOLF", "KXMASTERS", "KXUSOPEN"],
    "soccer":     ["KXMLSGAME", "KXMLS", "KXSOCCER", "KXEPL", "KXEPLGAME",
                   "KXUEFAGAME", "KXUEFA", "KXWORLDCUP"],
    "mma":        ["KXMMA", "KXUFC", "KXUFCGAME"],
    "cricket":    ["KXCRICKET", "KXIPL", "KXIPLGAME"],
    "politics":   ["KXPRESCONTROL", "KXSENATECONTROL", "KXHOUSECONTROL",
                   "KXPRES", "KXSENATE", "KXHOUSE", "KXGOV"],
}

SPORT_COLOR = {
    "tennis":     "#00bcd4",
    "basketball": "#ff9800",
    "hockey":     "#64b5f6",
    "baseball":   "#ef5350",
    "football":   "#8d6e63",
    "golf":       "#81c784",
    "soccer":     "#fff176",
    "mma":        "#ff7043",
    "cricket":    "#26a69a",
    "politics":   "#ce93d8",
}
SPORT_LABEL = {
    "tennis":     "Tennis",
    "basketball": "Bball",
    "hockey":     "Hockey",
    "baseball":   "Baseball",
    "football":   "NFL",
    "golf":       "Golf",
    "soccer":     "Soccer",
    "mma":        "MMA",
    "cricket":    "Cricket",
    "politics":   "Politics",
}

# Ordered list — probe filters to only those with active markets
SPORTS_SECTION = [
    "tennis", "basketball", "hockey", "baseball",
    "soccer", "football", "mma", "golf", "cricket",
]

# ── Color filter ──────────────────────────────────────────────────────────────
COLOR_FILTERS = ["all", "green", "yellow", "red"]
COLOR_META = {
    "all":    ("white",   "● All"),
    "green":  ("#00e676", "● Green"),
    "yellow": ("#ffd700", "● Yellow"),
    "red":    ("#ff4444", "● Red"),
}

# ── Bet type thresholds ───────────────────────────────────────────────────────
TYPE1_MIN = 0.80
TYPE1_MAX = 0.90
TYPE2_MIN = 0.55
TYPE2_MAX = 0.75
HARD_CEILING = 0.70

# ── Anomaly detection ─────────────────────────────────────────────────────────
LARGE_SINGLE_TRADE_USD   = 200
ANOMALY_VOLUME_THRESHOLD = 500
ANOMALY_ODDS_LOW         = 0.05
ANOMALY_ODDS_HIGH        = 0.95
PRICE_MOVE_THRESHOLD     = 0.10