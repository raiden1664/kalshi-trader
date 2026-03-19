"""
server.py — local Flask server for the match simulator.
Run: python3 analyst/server.py
Then open: http://localhost:8181
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, Response, request
from db import get_markets, get_candles, get_conn, init_db
from scores import get_score_events, get_match_score, init_scores_db

HTML_PATH = "/Users/raidenshipley/Desktop/kalshi-trader/analyst/static/simulator.html"

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    with open(HTML_PATH, "r") as f:
        html = f.read()
    return Response(html, mimetype="text/html")


@app.route("/api/matches")
def matches():
    init_db()
    sport = request.args.get("sport", None)
    markets = get_markets(sport=sport, limit=2000)
    result = []
    for m in markets:
        m = dict(m)
        has_scores = bool(get_match_score(m["ticker"]))
        result.append({
            "ticker":      m["ticker"],
            "sport":       m["sport"],
            "result":      m["result"],
            "settle_time": m["settle_time"],
            "has_scores":  has_scores,
        })
    return jsonify(result)


@app.route("/api/sports")
def sports():
    init_db()
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT sport FROM markets ORDER BY sport").fetchall()
    conn.close()
    return jsonify([r["sport"] for r in rows])


@app.route("/api/match/<ticker>")
def match_data(ticker):
    init_db()
    candles      = [dict(c) for c in get_candles(ticker)]
    score_events = get_score_events(ticker)
    match_info   = get_match_score(ticker)
    return jsonify({
        "ticker":       ticker,
        "candles":      candles,
        "score_events": score_events,
        "match_info":   match_info,
    })


if __name__ == "__main__":
    init_db()
    init_scores_db()
    print("\nKalshi Match Simulator")
    print("Open http://localhost:8181 in your browser\n")
    app.run(host="127.0.0.1", port=8181, debug=False)