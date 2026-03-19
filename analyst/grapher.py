"""
grapher.py — generates price chart images for each canonical pattern.
Uses matplotlib to render actual price charts from example tickers.
Saves charts as PNG files in analyst/graphs/
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

from db import get_conn, init_db
from tagger import get_tagged_candles
from analyzer import get_pattern_library

GRAPHS_DIR = os.path.join(os.path.dirname(__file__), "graphs")
BOLD  = "\033[1m"
RESET = "\033[0m"


def init_graphs_dir():
    os.makedirs(GRAPHS_DIR, exist_ok=True)


def get_best_example_ticker(example_tickers: list, pattern_name: str) -> str:
    """Find the best example ticker that has tagged candle data."""
    if not example_tickers:
        return None
    for ticker in example_tickers:
        candles = get_tagged_candles(ticker)
        if candles and len(candles) >= 30:
            return ticker
    return None


def render_pattern_chart(pattern: dict, ticker: str, output_path: str):
    """Render a price chart for a pattern using matplotlib."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np
    except ImportError:
        print("  [warn] matplotlib not installed. Run: pip3 install matplotlib --break-system-packages")
        return False

    candles = get_tagged_candles(ticker)
    if not candles:
        return False

    conn = get_conn()
    score = dict(conn.execute("SELECT * FROM match_scores WHERE ticker=?", (ticker,)).fetchone() or {})
    market = dict(conn.execute("SELECT * FROM markets WHERE ticker=?", (ticker,)).fetchone() or {})
    conn.close()

    prices     = [c["price"] * 100 for c in candles if c.get("price")]
    pcts       = [c["match_pct"] * 100 for c in candles if c.get("price")]
    changes    = [c.get("price_change", 0) or 0 for c in candles if c.get("price")]

    if not prices:
        return False

    # Find key events
    set_wins   = [(c["match_pct"]*100, c["price"]*100) for c in candles
                  if c.get("last_event_type") == "set_win" and c.get("price")]
    game_wins  = [(c["match_pct"]*100, c["price"]*100) for c in candles
                  if c.get("last_event_type") == "game_win" and c.get("price")]
    spikes     = [(c["match_pct"]*100, c["price"]*100) for c in candles
                  if abs(c.get("price_change") or 0) >= 0.05 and c.get("price")]

    # Figure setup
    fig, axes = plt.subplots(2, 1, figsize=(14, 8),
                              gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#0d1117')

    ax = axes[0]
    ax2 = axes[1]

    for a in [ax, ax2]:
        a.set_facecolor('#161b22')
        a.tick_params(colors='#8b949e', labelsize=9)
        for spine in a.spines.values():
            spine.set_edgecolor('#30363d')

    # Price line
    ax.plot(pcts, prices, color='#58a6ff', linewidth=2, zorder=3)
    ax.fill_between(pcts, prices, alpha=0.1, color='#58a6ff')

    # Entry zone shading based on pattern
    entry_range = pattern.get("entry_price_range", "")
    if entry_range:
        try:
            parts = entry_range.replace('c','').replace('¢','').split('-')
            if len(parts) == 2:
                lo, hi = float(parts[0].strip()), float(parts[1].strip())
                ax.axhspan(lo, hi, alpha=0.12, color='#3fb950', zorder=1, label=f'Entry zone {lo:.0f}-{hi:.0f}¢')
        except Exception:
            pass

    # Set wins — green triangles
    if set_wins:
        sx, sy = zip(*set_wins)
        ax.scatter(sx, sy, marker='^', s=120, color='#3fb950', zorder=5, label='Set win')

    # Big spikes — orange dots
    if spikes:
        spx, spy = zip(*spikes)
        ax.scatter(spx, spy, s=60, color='#f0883e', zorder=4, alpha=0.8, label='Price spike >5¢')

    # Price change bars
    bar_colors = ['#3fb950' if c >= 0 else '#f85149' for c in changes]
    ax2.bar(pcts, [c*100 for c in changes], color=bar_colors, width=0.5, zorder=3)
    ax2.axhline(0, color='#30363d', linewidth=0.5)

    # Labels
    home = score.get("player_home", "Home") or "Home"
    away = score.get("player_away", "Away") or "Away"
    winner = score.get("winner", "?")
    set1 = f"{score.get('set1_home')}-{score.get('set1_away')}"
    set2 = f"{score.get('set2_home')}-{score.get('set2_away')}"

    title = f"Pattern: {pattern['name']}  |  {home} vs {away}  |  Winner: {winner}  |  {set1}, {set2}"
    ax.set_title(title, color='#e6edf3', fontsize=11, pad=10)
    ax.set_ylabel('Price (¢)', color='#8b949e', fontsize=9)
    ax.set_ylim(-2, 102)
    ax.set_xlim(0, 100)
    ax.grid(True, color='#21262d', linewidth=0.5, alpha=0.5)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.0f}¢'))

    ax2.set_xlabel('Match Progress (%)', color='#8b949e', fontsize=9)
    ax2.set_ylabel('Δ¢', color='#8b949e', fontsize=9)
    ax2.set_xlim(0, 100)
    ax2.grid(True, color='#21262d', linewidth=0.5, alpha=0.5)

    # Description box
    desc = pattern.get("description", "")
    entry = pattern.get("entry_rule", pattern.get("entry_signal", ""))
    exit_ = pattern.get("exit_rule", pattern.get("exit_signal", ""))
    avoid = pattern.get("false_signal", pattern.get("false_signal_warning", ""))
    info = f"Entry: {entry[:80]}\nExit: {exit_[:80]}\nAvoid: {avoid[:80]}"
    ax.text(0.01, 0.02, info, transform=ax.transAxes, fontsize=8,
            color='#8b949e', verticalalignment='bottom',
            bbox=dict(boxstyle='round', facecolor='#21262d', alpha=0.8, edgecolor='#30363d'))

    # Legend
    handles = []
    if set_wins:
        handles.append(mpatches.Patch(color='#3fb950', label='Set Win'))
    if spikes:
        handles.append(mpatches.Patch(color='#f0883e', label='Spike >5¢'))
    handles.append(mpatches.Patch(color='#58a6ff', alpha=0.3, label='Entry Zone'))
    ax.legend(handles=handles, loc='upper left', fontsize=8,
              facecolor='#21262d', edgecolor='#30363d', labelcolor='#e6edf3')

    plt.tight_layout(pad=1.5)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#0d1117')
    plt.close()
    return True


def generate_all_graphs(force: bool = False):
    """Generate charts for all canonical patterns."""
    init_db()
    init_graphs_dir()

    library = get_pattern_library()
    patterns = library.get("canonical_patterns", [])

    if not patterns:
        # Fall back to analysis_patterns table
        conn = get_conn()
        rows = conn.execute("""
            SELECT pattern_name, example_tickers, description, entry_signal, exit_signal,
                   false_signal_warning, entry_price_range, sport, frequency
            FROM analysis_patterns
            GROUP BY pattern_name
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """).fetchall()
        conn.close()
        patterns = []
        for r in rows:
            d = dict(r)
            try:
                d["example_tickers"] = json.loads(d.get("example_tickers") or "[]")
            except Exception:
                d["example_tickers"] = []
            d["name"] = d.pop("pattern_name", "Unknown")
            d["frequency_rank"] = len(patterns) + 1
            patterns.append(d)

    print(f"\n{BOLD}Generating graphs for {len(patterns)} patterns...{RESET}")

    generated = 0
    for i, pattern in enumerate(patterns):
        name = pattern.get("name", f"pattern_{i}")
        safe_name = name.lower().replace(" ", "_").replace("/", "_")
        output_path = os.path.join(GRAPHS_DIR, f"{i+1:02d}_{safe_name}.png")

        if os.path.exists(output_path) and not force:
            print(f"  {name} (cached)")
            continue

        example_tickers = pattern.get("example_tickers", [])
        if isinstance(example_tickers, str):
            try:
                example_tickers = json.loads(example_tickers)
            except Exception:
                example_tickers = []

        ticker = get_best_example_ticker(example_tickers, name)

        if not ticker:
            # Find a matching ticker from DB based on pattern name keywords
            ticker = find_ticker_for_pattern(name)

        if not ticker:
            print(f"  {name} — no example ticker found, skipping")
            continue

        print(f"  {name} → {ticker}...", end=" ", flush=True)
        success = render_pattern_chart(pattern, ticker, output_path)
        if success:
            generated += 1
            print(f"saved")
        else:
            print(f"failed")

    print(f"\n{BOLD}Done. {generated} graphs saved to {GRAPHS_DIR}{RESET}\n")
    return GRAPHS_DIR


def find_ticker_for_pattern(pattern_name: str) -> str:
    """Find a representative ticker for a pattern based on its characteristics."""
    conn = get_conn()
    name_lower = pattern_name.lower()

    # Look for matches in analysis_patterns with this pattern name
    rows = conn.execute("""
        SELECT example_tickers FROM analysis_patterns
        WHERE LOWER(pattern_name) LIKE ?
        AND example_tickers != '[]'
        LIMIT 10
    """, (f"%{name_lower[:10]}%",)).fetchall()
    conn.close()

    for row in rows:
        try:
            tickers = json.loads(row["example_tickers"])
            for t in tickers:
                candles = get_tagged_candles(t)
                if candles and len(candles) >= 30:
                    return t
        except Exception:
            continue
    return None


def generate_index_html():
    """Generate an HTML index page showing all pattern graphs."""
    graphs = sorted([f for f in os.listdir(GRAPHS_DIR) if f.endswith('.png')])
    if not graphs:
        print("No graphs found. Run generate_all_graphs first.")
        return

    library = get_pattern_library()
    patterns = {p["name"].lower().replace(" ", "_").replace("/", "_"): p
                for p in library.get("canonical_patterns", [])}

    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Kalshi Pattern Library</title>
<style>
body { background: #0d1117; color: #e6edf3; font-family: 'SF Mono', monospace; margin: 0; padding: 20px; }
h1 { color: #58a6ff; font-size: 18px; letter-spacing: 2px; margin-bottom: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(700px, 1fr)); gap: 24px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }
.card img { width: 100%; display: block; }
.card-body { padding: 14px; }
.card-title { font-size: 14px; font-weight: bold; color: #58a6ff; margin-bottom: 6px; }
.card-desc { font-size: 12px; color: #8b949e; line-height: 1.5; }
.tag { display: block; background: #21262d; border-radius: 4px; padding: 6px 10px; font-size: 11px; margin: 4px 0; color: #3fb950; line-height: 1.5; white-space: normal; word-wrap: break-word; }
.tag.exit { color: #f85149; }
.tag.avoid { color: #f0883e; }
</style>
</head>
<body>
<h1>⚡ KALSHI PATTERN LIBRARY</h1>
<div class="grid">
"""

    for graph_file in graphs:
        pattern_key = '_'.join(graph_file.replace('.png','').split('_')[1:])
        pattern = patterns.get(pattern_key, {})
        name = pattern.get("name", graph_file.replace('.png','').replace('_',' ').title())
        desc = pattern.get("description", "")
        entry = pattern.get("entry_rule", pattern.get("entry_signal", ""))
        exit_ = pattern.get("exit_rule", pattern.get("exit_signal", ""))
        avoid = pattern.get("false_signal", pattern.get("false_signal_warning", ""))
        sport = pattern.get("sport", "")

        html += f"""
<div class="card">
  <img src="{graph_file}" alt="{name}">
  <div class="card-body">
    <div class="card-title">{name} <small style="color:#8b949e;font-size:10px;">[{sport}]</small></div>
    <div class="card-desc">{desc}</div>
    <div style="margin-top:8px;">
      <span class="tag">▶ {entry}</span>
      <span class="tag exit">■ {exit_}</span>
      <span class="tag avoid">⚠ {avoid}</span>
    </div>
  </div>
</div>"""

    html += "\n</div></body></html>"

    index_path = os.path.join(GRAPHS_DIR, "index.html")
    with open(index_path, "w") as f:
        f.write(html)
    print(f"Index saved: {index_path}")
    return index_path