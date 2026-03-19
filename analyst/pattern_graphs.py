"""
pattern_graphs.py — identifies common price curve shapes and generates example charts.

Clusters matches by shape and renders the most frequently occurring patterns
as HTML charts the AI and trader can reference.
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, get_markets, init_db
from tagger import get_tagged_candles

BOLD  = "\033[1m"
GREEN = "\033[92m"
RESET = "\033[0m"


# ── Shape extraction ────────────────────────────────────────────────────────

def extract_shape(candles: list, buckets: int = 20) -> list:
    """
    Reduce a full candle timeline to N price points (normalized 0-1).
    This is the "shape" fingerprint of the match.
    """
    if not candles:
        return []

    prices = [c["price"] for c in candles if c.get("price") is not None]
    if len(prices) < 5:
        return []

    # Sample N evenly spaced points
    step = len(prices) / buckets
    sampled = [prices[min(int(i * step), len(prices)-1)] for i in range(buckets)]

    # Normalize to 0-1 range
    mn, mx = min(sampled), max(sampled)
    rng = mx - mn or 0.01
    return [round((p - mn) / rng, 3) for p in sampled]


def classify_shape(candles: list) -> str:
    """
    Classify a match into a named pattern based on its price curve shape.
    """
    if not candles:
        return "unknown"

    prices = [c["price"] for c in candles if c.get("price") is not None]
    if len(prices) < 10:
        return "unknown"

    start = prices[0]
    end   = prices[-1]
    mid   = prices[len(prices)//2]
    mx    = max(prices)
    mn    = min(prices)
    rng   = mx - mn

    # Straight sets favorite win — price rises steadily from low to high
    if end > 0.85 and start < 0.60 and mid > start and rng > 0.30:
        return "steady_climb"

    # Heavy favorite — starts high, never really threatened
    if start > 0.70 and end > 0.85 and mn > 0.55:
        return "dominant_favorite"

    # Upset — started as underdog (low price), won
    if start < 0.35 and end > 0.85:
        return "underdog_upset"

    # False dawn — spiked mid-match but ultimately lost
    if end < 0.15 and mx > 0.55 and start < 0.50:
        return "false_dawn"

    # Rollercoaster — high volatility, multiple big swings
    changes = [abs(prices[i]-prices[i-1]) for i in range(1, len(prices))]
    big_moves = sum(1 for c in changes if c > 0.05)
    if big_moves > len(prices) * 0.15:
        return "rollercoaster"

    # Late surge — flat for most of match, decisive move at end
    early_rng = max(prices[:len(prices)//2]) - min(prices[:len(prices)//2])
    late_rng  = max(prices[len(prices)//2:]) - min(prices[len(prices)//2:])
    if late_rng > early_rng * 2 and late_rng > 0.25:
        return "late_surge"

    # Close match — stayed near 50¢ most of the time
    near_50 = sum(1 for p in prices if 0.35 < p < 0.65)
    if near_50 > len(prices) * 0.5:
        return "tight_match"

    # Gradual collapse — started competitive, slowly faded
    if end < 0.15 and start > 0.30 and mid > end * 2:
        return "gradual_collapse"

    return "other"


PATTERN_DESCRIPTIONS = {
    "steady_climb":       "Steady Climb — Favorite wins cleanly. Price rises steadily from ~40¢ to 90¢+. Best entry: early at 45-55¢.",
    "dominant_favorite":  "Dominant Favorite — Heavy favorite, never threatened. Price opens high (70¢+) and barely dips. Low edge, Type 1 only.",
    "underdog_upset":     "Underdog Upset — Underdog starts at 20-35¢ and wins. Watch for momentum confirmation before entry.",
    "false_dawn":         "False Dawn — Underdog spikes to 55-70¢ mid-match but ultimately collapses. Classic trap — don't chase the spike.",
    "rollercoaster":      "Rollercoaster — Multiple big swings 20¢+. High volatility, difficult to trade. Wait for decisive momentum.",
    "late_surge":         "Late Surge — Flat for 60%+ of match, then decisive move at end. Patience required, entry window is brief.",
    "tight_match":        "Tight Match — Price stays near 50¢ most of match. Markets correctly pricing uncertainty. Avoid unless clear break.",
    "gradual_collapse":   "Gradual Collapse — Loser fades slowly over match. Price drifts from 40¢ to 5¢. No sharp reversal opportunity.",
    "other":              "Other — Doesn't fit standard patterns.",
}


# ── Clustering ──────────────────────────────────────────────────────────────

def analyze_patterns(sport: str = None, limit: int = 2000) -> dict:
    """
    Analyze all tagged matches, classify by shape, find best examples.
    Returns pattern stats + best example ticker for each pattern.
    """
    init_db()
    conn = get_conn()

    query = """
        SELECT DISTINCT m.ticker, m.sport, m.result
        FROM markets m
        WHERE EXISTS (SELECT 1 FROM tagged_candles tc WHERE tc.ticker = m.ticker)
    """
    params = []
    if sport:
        query += " AND m.sport = ?"
        params.append(sport)
    query += f" LIMIT {limit}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    patterns = {}
    total = len(rows)
    print(f"\nClassifying {total} matches...")

    for i, row in enumerate(rows):
        ticker = row["ticker"]
        sp     = row["sport"]
        result = row["result"]

        candles = get_tagged_candles(ticker)
        if not candles:
            continue

        shape = classify_shape(candles)

        if shape not in patterns:
            patterns[shape] = {
                "count":    0,
                "examples": [],
                "sports":   {},
                "win_rate": {"yes": 0, "no": 0},
            }

        patterns[shape]["count"] += 1
        patterns[shape]["win_rate"][result or "no"] = patterns[shape]["win_rate"].get(result or "no", 0) + 1
        patterns[shape]["sports"][sp] = patterns[shape]["sports"].get(sp, 0) + 1

        # Keep up to 3 examples per pattern
        if len(patterns[shape]["examples"]) < 3:
            patterns[shape]["examples"].append({
                "ticker": ticker,
                "sport":  sp,
                "result": result,
            })

        if (i+1) % 200 == 0:
            print(f"  {i+1}/{total} processed...")

    # Sort by count
    sorted_patterns = dict(sorted(patterns.items(), key=lambda x: x[1]["count"], reverse=True))

    print(f"\n{BOLD}Pattern Distribution:{RESET}")
    for name, data in sorted_patterns.items():
        pct = round(data["count"]/total*100)
        desc = PATTERN_DESCRIPTIONS.get(name, name)
        print(f"  {name:<20} {data['count']:>5} ({pct:>2}%) — {desc[:60]}")

    return sorted_patterns


# ── HTML chart generator ─────────────────────────────────────────────────────

def generate_pattern_charts(patterns: dict, output_path: str = None) -> str:
    """
    Generate an HTML page with example charts for each pattern type.
    """
    if not output_path:
        output_path = os.path.join(os.path.dirname(__file__), "static", "patterns.html")

    charts_js = []
    for pattern_name, pdata in patterns.items():
        if not pdata["examples"]:
            continue

        # Get candle data for first example
        example = pdata["examples"][0]
        ticker  = example["ticker"]
        candles = get_tagged_candles(ticker)
        if not candles:
            continue

        prices     = [c["price"] for c in candles if c.get("price") is not None]
        timestamps = [f"{int(c['match_pct']*100)}%" for c in candles if c.get("price") is not None]

        # Find set wins and breaks
        set_wins = []
        breaks   = []
        for j, c in enumerate(candles):
            if c.get("price") is None:
                continue
            if c.get("last_event_type") == "set_win":
                set_wins.append({"x": f"{int(c['match_pct']*100)}%", "y": c["price"]})
            if c.get("last_event_type") == "game_win" and c.get("server") and c.get("scorer") and c.get("server") != c.get("scorer"):
                breaks.append({"x": f"{int(c['match_pct']*100)}%", "y": c["price"]})

        desc = PATTERN_DESCRIPTIONS.get(pattern_name, pattern_name)
        sport_breakdown = ", ".join(f"{k}:{v}" for k,v in sorted(pdata["sports"].items(), key=lambda x: -x[1])[:3])

        chart_id = f"chart_{pattern_name}"
        charts_js.append(f"""
        {{
          id: '{chart_id}',
          name: '{pattern_name.replace("_"," ").title()}',
          desc: '{desc}',
          count: {pdata['count']},
          sports: '{sport_breakdown}',
          ticker: '{ticker}',
          labels: {json.dumps(timestamps[:200])},
          prices: {json.dumps([round(p,3) for p in prices[:200]])},
          setWins: {json.dumps(set_wins[:10])},
          breaks: {json.dumps(breaks[:10])},
        }}""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Kalshi Pattern Library</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#0d1117; color:#e6edf3; font-family:'SF Mono',monospace; padding:20px; }}
h1 {{ font-size:16px; color:#58a6ff; letter-spacing:2px; margin-bottom:20px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(480px,1fr)); gap:16px; }}
.pattern-card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px; }}
.pattern-name {{ font-size:14px; font-weight:bold; color:#e6edf3; margin-bottom:4px; }}
.pattern-count {{ font-size:11px; color:#58a6ff; margin-bottom:4px; }}
.pattern-desc {{ font-size:11px; color:#8b949e; margin-bottom:10px; line-height:1.5; }}
.pattern-sports {{ font-size:10px; color:#30363d; margin-bottom:8px; }}
.chart-wrap {{ height:180px; position:relative; }}
.ticker-ref {{ font-size:9px; color:#30363d; margin-top:4px; }}
</style>
</head>
<body>
<h1>⚡ Kalshi Price Pattern Library</h1>
<div class="grid" id="grid"></div>
<script>
const patterns = [{','.join(charts_js)}];

patterns.forEach(p => {{
  const card = document.createElement('div');
  card.className = 'pattern-card';
  card.innerHTML = `
    <div class="pattern-name">${{p.name}}</div>
    <div class="pattern-count">${{p.count}} matches</div>
    <div class="pattern-desc">${{p.desc}}</div>
    <div class="pattern-sports">${{p.sports}}</div>
    <div class="chart-wrap"><canvas id="${{p.id}}"></canvas></div>
    <div class="ticker-ref">Example: ${{p.ticker}}</div>
  `;
  document.getElementById('grid').appendChild(card);

  const ctx = document.getElementById(p.id).getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: p.labels,
      datasets: [
        {{ label:'Price', data:p.prices, borderColor:'#58a6ff', backgroundColor:'rgba(88,166,255,0.08)', borderWidth:2, pointRadius:0, fill:true, tension:0.3 }},
        {{ label:'Set Win', data:p.setWins, borderColor:'transparent', backgroundColor:'#3fb950', pointRadius:8, pointStyle:'triangle', showLine:false }},
        {{ label:'Break', data:p.breaks, borderColor:'transparent', backgroundColor:'#f85149', pointRadius:6, pointStyle:'rectRot', showLine:false }},
      ]
    }},
    options: {{
      responsive:true, maintainAspectRatio:false, animation:{{duration:0}},
      scales: {{
        x:{{ ticks:{{color:'#8b949e', maxTicksLimit:5, font:{{size:8}}}}, grid:{{color:'#1c2128'}} }},
        y:{{ min:0, max:1, ticks:{{color:'#8b949e', callback:v=>(v*100).toFixed(0)+'¢', font:{{size:8}}}}, grid:{{color:'#1c2128'}} }}
      }},
      plugins:{{ legend:{{display:false}} }}
    }}
  }});
}});
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"\nPattern charts saved to: {output_path}")
    return output_path


def run_pattern_analysis(sport: str = None, limit: int = 2000):
    """Full pipeline: analyze → generate charts."""
    patterns = analyze_patterns(sport=sport, limit=limit)
    output = generate_pattern_charts(patterns)
    print(f"Open in browser: http://localhost:8181/patterns")
    return patterns


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--sport", default=None)
    p.add_argument("--limit", type=int, default=2000)
    args = p.parse_args()
    run_pattern_analysis(sport=args.sport, limit=args.limit)