#!/usr/bin/env python3
"""
kalshi-analyst — standalone AI-powered match analysis tool
Usage: python3 analyst/main.py [command] [options]

Commands:
  fetch                 Fetch settled markets + candlesticks
  fetch --sport tennis_atp   (fetch single sport)
  fetch --all               (fetch ALL sports)
  list                  List fetched markets
  scores                Fetch SofaScore match timelines
  serve                 Start local simulator at localhost:8181
  patterns              AI pattern analysis
  history               Show saved pattern analyses
  replay <ticker>       Step-through replay with AI
"""

import sys
import os
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import db
import fetcher
import replay as replay_mod
import patterns as patterns_mod

BOLD  = "\033[1m"
DIM   = "\033[2m"
GREEN = "\033[92m"
RESET = "\033[0m"


def cmd_fetch(sport=None, fetch_all=False, limit=1000):
    db.init_db()
    print(f"\n{BOLD}Fetching markets...{RESET}")

    if fetch_all:
        all_markets = fetcher.fetch_all_sports(limit_per_sport=limit)
    elif sport:
        if sport not in fetcher.SPORT_SERIES:
            print(f"Unknown sport '{sport}'. Options: {list(fetcher.SPORT_SERIES.keys())}")
            return
        series = fetcher.SPORT_SERIES[sport]
        markets = fetcher.fetch_settled_markets(series, sport, limit=limit)
        all_markets = {sport: markets}
    else:
        # Default: fetch all
        all_markets = fetcher.fetch_all_sports(limit_per_sport=limit)

    total_candles = 0
    total_skipped_volume = 0

    for sp, markets in all_markets.items():
        print(f"\n{GREEN}{sp}{RESET} — {len(markets)} markets")
        for m in markets:
            db.upsert_market(m)
            ticker = m["ticker"]
            if not ticker:
                continue
            if db.market_has_candles(ticker):
                print(f"  {DIM}{ticker} (cached){RESET}")
                continue
            print(f"  Fetching candles: {ticker}...", end=" ", flush=True)
            candles = fetcher.fetch_candlesticks(ticker, m["open_time"], m["close_time"], period_interval=1)
            if candles and len(candles) >= fetcher.MIN_CANDLES:
                db.upsert_candles(ticker, candles)
                total_candles += len(candles)
                print(f"{len(candles)} candles")
            elif candles:
                print(f"skipped (only {len(candles)} candles < {fetcher.MIN_CANDLES} min)")
                total_skipped_volume += 1
            else:
                print("none")

    print(f"\n{BOLD}Done. {total_candles} new candles stored. {total_skipped_volume} low-volume markets skipped.{RESET}\n")


def cmd_list(sport=None, limit=100):
    db.init_db()
    markets = db.get_markets(sport=sport, limit=limit)
    if not markets:
        print("No markets found. Run 'fetch' first.")
        return

    print(f"\n{'TICKER':<50} {'SPORT':<15} {'RESULT':<8} {'SETTLED'}")
    print("-" * 90)
    for m in markets:
        settled = ""
        if m["settle_time"]:
            try:
                settled = datetime.utcfromtimestamp(m["settle_time"]).strftime("%Y-%m-%d")
            except Exception:
                settled = str(m["settle_time"])
        has_candles = db.market_has_candles(m["ticker"])
        flag = f"{GREEN}●{RESET}" if has_candles else " "
        print(f"{flag} {m['ticker']:<48} {m['sport']:<15} {(m['result'] or '?'):<8} {settled}")

    print(f"\n{DIM}{GREEN}●{RESET}{DIM} = has candlestick data{RESET}\n")


def cmd_replay(ticker: str, auto: bool = False, step: int = 5):
    db.init_db()
    replay_mod.replay_match(ticker, auto=auto, step=step)


def cmd_patterns(sport=None, sample=200):
    db.init_db()
    patterns_mod.analyze_patterns(sport=sport, sample=sample)


def cmd_history(sport=None):
    db.init_db()
    patterns_mod.show_recent_patterns(sport=sport)


def cmd_scores(sport=None, limit=1000):
    from scores import fetch_scores_for_all, init_scores_db
    init_scores_db()
    if sport:
        fetch_scores_for_all(sport=sport, limit=limit)
    else:
        # Run for all sports that have data
        conn = db.get_conn()
        sports = [r[0] for r in conn.execute("SELECT DISTINCT sport FROM markets").fetchall()]
        conn.close()
        for sp in sports:
            print(f"\n--- {sp} ---")
            fetch_scores_for_all(sport=sp, limit=limit)


def cmd_serve():
    import subprocess, sys
    subprocess.run([sys.executable,
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")])


def cmd_graphs(sport=None):
    from pattern_graphs import run
    run(sport=sport)


def cmd_graph(sport=None, limit=2000):
    from pattern_graphs import run_pattern_analysis
    run_pattern_analysis(sport=sport, limit=limit)


def cmd_analyze_strategy(sport=None, batch_size=5, max_batches=50):
    from strategy_analyzer import analyze_strategy_sport, init_strategy_db
    init_strategy_db()
    if sport:
        analyze_strategy_sport(sport=sport, batch_size=batch_size, max_batches=max_batches)
    else:
        for sp in ['tennis_atp', 'tennis_wta', 'ncaab_men']:
            analyze_strategy_sport(sport=sp, batch_size=batch_size, max_batches=max_batches)


def cmd_consolidate_strategy(sport=None):
    from strategy_analyzer import consolidate_strategy
    consolidate_strategy(sport=sport)


def cmd_quality_check_strategy():
    from strategy_analyzer import quality_check_strategy
    quality_check_strategy()


def cmd_graphs(sport=None, force=False):
    from grapher import generate_all_graphs, generate_index_html
    import subprocess
    try:
        import matplotlib
    except ImportError:
        print("Installing matplotlib...")
        subprocess.run(["pip3", "install", "matplotlib", "--break-system-packages"])
    generate_all_graphs(force=force)
    generate_index_html()


def cmd_quality_check():
    from quality_check import run_quality_check
    run_quality_check()


def cmd_analyze(sport=None, batch_size=15, max_batches=50):
    from analyzer import analyze_sport, init_analyzer_db
    init_analyzer_db()
    if sport:
        analyze_sport(sport=sport, batch_size=batch_size, max_batches=max_batches)
    else:
        # Run for all sports with tagged data
        sports = ['tennis_atp', 'tennis_wta', 'ncaab_men', 'ncaab_women',
                  'ahl', 'shl', 'liiga', 'nbl', 'cba', 'kbl', 'aba', 'acb', 'bbl', 'vtb', 'fiba']
        for sp in sports:
            analyze_sport(sport=sp, batch_size=batch_size, max_batches=max_batches)


def cmd_consolidate(sport=None):
    from analyzer import consolidate_patterns
    consolidate_patterns(sport=sport)


def cmd_tag(sport=None, limit=10000):
    from tagger import tag_all, init_tagger_db
    init_tagger_db()
    tag_all(sport=sport, limit=limit)


def cmd_reanchor(sport=None, dry_run=False, min_candles=50):
    from reanchor import reanchor_all
    reanchor_all(sport=sport, min_candles=min_candles, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(
        description="kalshi-analyst: AI-powered Kalshi match analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="command")

    # fetch
    p_fetch = sub.add_parser("fetch", help="Fetch settled markets and candlesticks")
    p_fetch.add_argument("--sport", default=None, help=f"One of: {list(fetcher.SPORT_SERIES.keys())}")
    p_fetch.add_argument("--all", action="store_true", dest="fetch_all", help="Fetch all sports")
    p_fetch.add_argument("--limit", type=int, default=1000)

    # list
    p_list = sub.add_parser("list", help="List fetched markets")
    p_list.add_argument("--sport", default=None)
    p_list.add_argument("--limit", type=int, default=100)

    # replay
    p_replay = sub.add_parser("replay", help="Replay a match with AI verdicts")
    p_replay.add_argument("ticker")
    p_replay.add_argument("--auto", action="store_true")
    p_replay.add_argument("--step", type=int, default=5)

    # patterns
    p_pat = sub.add_parser("patterns", help="AI pattern analysis")
    p_pat.add_argument("--sport", default=None)
    p_pat.add_argument("--sample", type=int, default=200)

    # history
    p_hist = sub.add_parser("history", help="Show saved pattern analyses")
    p_hist.add_argument("--sport", default=None)

    # scores
    p_scores = sub.add_parser("scores", help="Fetch SofaScore match timelines")
    p_scores.add_argument("--sport", default=None)
    p_scores.add_argument("--limit", type=int, default=1000)

    # analyze-strategy
    p_astrat = sub.add_parser("analyze-strategy", help="Run strategy analysis (favoritism, momentum, upsets)")
    p_astrat.add_argument("--sport", default=None)
    p_astrat.add_argument("--batch-size", type=int, default=5)
    p_astrat.add_argument("--max-batches", type=int, default=50)

    # consolidate-strategy
    p_cstrat = sub.add_parser("consolidate-strategy", help="Consolidate strategy findings")
    p_cstrat.add_argument("--sport", default=None)

    # quality-check-strategy
    sub.add_parser("quality-check-strategy", help="Quality check strategy report")

    # graphs
    p_graphs = sub.add_parser("graphs", help="Generate pattern curve charts")
    p_graphs.add_argument("--sport", default=None)

    # graph
    p_graph = sub.add_parser("graph", help="Generate pattern library charts")
    p_graph.add_argument("--sport", default=None)
    p_graph.add_argument("--limit", type=int, default=2000)

    # analyze-strategy
    # consolidate-strategy
    # quality-check-strategy
    # graphs
    # quality-check
    sub.add_parser("quality-check", help="AI quality check and dedup of pattern library")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Run AI pattern analysis on tagged matches")
    p_analyze.add_argument("--sport", default=None)
    p_analyze.add_argument("--batch-size", type=int, default=15)
    p_analyze.add_argument("--max-batches", type=int, default=50)

    # consolidate
    p_cons = sub.add_parser("consolidate", help="Consolidate AI patterns into final report")
    p_cons.add_argument("--sport", default=None)

    # tag
    p_tag = sub.add_parser("tag", help="Tag candles with score state for AI analysis")
    p_tag.add_argument("--sport", default=None)
    p_tag.add_argument("--limit", type=int, default=10000)

    # reanchor
    p_reanchor = sub.add_parser("reanchor", help="Re-fetch candles anchored to SofaScore match start times")
    p_reanchor.add_argument("--sport", default=None)
    p_reanchor.add_argument("--dry-run", action="store_true")
    p_reanchor.add_argument("--min-candles", type=int, default=50)

    # serve
    sub.add_parser("serve", help="Start local simulator at localhost:8181")

    args = parser.parse_args()

    if args.command == "fetch":
        cmd_fetch(sport=args.sport, fetch_all=args.fetch_all, limit=args.limit)
    elif args.command == "list":
        cmd_list(sport=args.sport, limit=args.limit)
    elif args.command == "replay":
        cmd_replay(args.ticker, auto=args.auto, step=args.step)
    elif args.command == "patterns":
        cmd_patterns(sport=args.sport, sample=args.sample)
    elif args.command == "history":
        cmd_history(sport=args.sport)
    elif args.command == "scores":
        cmd_scores(sport=args.sport, limit=args.limit)
    elif args.command == "analyze-strategy":
        cmd_analyze_strategy(sport=args.sport, batch_size=args.batch_size, max_batches=args.max_batches)
    elif args.command == "consolidate-strategy":
        cmd_consolidate_strategy(sport=args.sport)
    elif args.command == "quality-check-strategy":
        cmd_quality_check_strategy()
    elif args.command == "graphs":
        cmd_graphs(sport=args.sport)
    elif args.command == "graph":
        cmd_graph(sport=args.sport, limit=args.limit)
    elif args.command == "analyze-strategy":
        cmd_analyze_strategy(sport=args.sport, batch_size=args.batch_size, max_batches=args.max_batches)
    elif args.command == "consolidate-strategy":
        cmd_consolidate_strategy(sport=args.sport)
    elif args.command == "quality-check-strategy":
        cmd_quality_check_strategy()
    elif args.command == "graphs":
        cmd_graphs(force=args.force)
    elif args.command == "quality-check":
        cmd_quality_check()
    elif args.command == "analyze":
        cmd_analyze(sport=args.sport, batch_size=args.batch_size, max_batches=args.max_batches)
    elif args.command == "consolidate":
        cmd_consolidate(sport=args.sport)
    elif args.command == "tag":
        cmd_tag(sport=args.sport, limit=args.limit)
    elif args.command == "reanchor":
        cmd_reanchor(sport=args.sport, dry_run=args.dry_run, min_candles=args.min_candles)
    elif args.command == "serve":
        cmd_serve()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()