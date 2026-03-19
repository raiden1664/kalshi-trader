"""
quality_check.py — AI quality check pass over all patterns and findings.

Reviews the consolidated pattern library for:
1. Accuracy — are the patterns real or hallucinated?
2. Redundancy — merge duplicate/overlapping patterns
3. Confidence scoring — how confident is each pattern?
4. Completeness — are there gaps?

Produces a final refined pattern library saved to DB.
"""

import sys, os, json, time
import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from db import get_conn, init_db
from analyzer import get_pattern_library, init_analyzer_db

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

BOLD  = "\033[1m"
GREEN = "\033[92m"
RESET = "\033[0m"

QUALITY_CHECK_PROMPT = """You are a senior quantitative analyst reviewing an AI-generated pattern library for Kalshi prediction markets.

Your job is to:

1. **Remove redundancies** — merge patterns that describe the same phenomenon with different names. Keep the clearest description.

2. **Verify accuracy** — flag any patterns that seem inconsistent, contradictory, or unlikely based on your knowledge of tennis/basketball/hockey market dynamics.

3. **Add confidence scores** — rate each pattern 1-5:
   - 5: Extremely reliable, seen consistently across many matches
   - 4: Reliable, solid evidence
   - 3: Moderate confidence, needs more data
   - 2: Weak signal, treat with caution
   - 1: Likely noise or hallucination, remove

4. **Refine entry/exit rules** — make them more precise and actionable where possible.

5. **Add missing patterns** — if you notice obvious gaps based on sports market dynamics.

6. **Sport specificity** — clarify which patterns are tennis-specific vs universal.

## Input: Current Pattern Library
You will receive the full consolidated pattern library plus a sample of raw findings.

## Output Format — JSON only:
{
  "refined_patterns": [
    {
      "name": "Pattern Name",
      "description": "Clear, precise description",
      "confidence": 5,
      "sport": "tennis/basketball/hockey/all",
      "frequency": "very_common/common/occasional/rare",
      "entry_rule": "Precise rule: price level + score context + timing",
      "exit_rule": "Precise rule: price level or event trigger",
      "false_signal": "Specific scenario that looks like this but isn't",
      "example_tickers": ["TICKER1", "TICKER2"],
      "merged_from": ["Original Pattern 1", "Original Pattern 2"],
      "notes": "Any additional context"
    }
  ],
  "removed_patterns": [
    {"name": "Removed Pattern", "reason": "Why removed"}
  ],
  "top_insights": [
    "Most important actionable insight 1",
    "Most important actionable insight 2",
    "...(up to 15)"
  ],
  "entry_timing_rules": {
    "set_win_entry_window": "minutes after set win to enter",
    "break_serve_reaction": "price move and timing on break of serve",
    "tiebreak_rule": "how to handle tiebreaks",
    "pre_match_rule": "how to use opening price"
  },
  "bankroll_rules": {
    "type1_plays": "when to use 30% bankroll",
    "type2_plays": "when to use 20-30% bankroll", 
    "avoid": "when to pass entirely"
  },
  "quality_notes": "Overall assessment of the pattern library"
}"""


def run_quality_check():
    init_analyzer_db()

    if not ANTHROPIC_API_KEY:
        print("No ANTHROPIC_API_KEY set.")
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Get current consolidated library
    library = get_pattern_library()
    patterns = library.get("canonical_patterns", [])

    if not patterns:
        print("No consolidated patterns found. Run consolidate first.")
        return

    # Also get raw findings for context
    conn = get_conn()
    findings = conn.execute("""
        SELECT DISTINCT finding, category, sport
        FROM analysis_findings
        WHERE category IN ('key_finding', 'entry_timing')
        ORDER BY sport, category
        LIMIT 100
    """).fetchall()
    conn.close()

    findings_text = "\n".join([f"[{dict(f)['sport']}] {dict(f)['finding']}" for f in findings])

    # Build the review prompt
    patterns_text = json.dumps(patterns, indent=2)

    prompt = f"""Here is the consolidated pattern library from analyzing 115 batches of Kalshi prediction market matches across ATP tennis, WTA tennis, and NCAAB basketball.

## CURRENT CANONICAL PATTERNS:
{patterns_text}

## RAW FINDINGS SAMPLE:
{findings_text}

## Additional Context:
- ATP/WTA tennis: 85 batches analyzed (425 matches)
- NCAAB basketball: 30 batches analyzed (150 matches)
- All matches have full candle data with score context
- The trader uses these bet types:
  - Type 1 (30% bankroll): 80-90¢ near-locks
  - Type 2 (20-30% bankroll): 55-75¢ value plays requiring momentum confirmation
  - Never buy above 70¢ entry (soft ceiling 80¢ for passive Type 1)
  - Stop-loss: sell if drops to ~59¢ on ~85¢ entry

Please perform a thorough quality check, remove redundancies, add confidence scores, and produce the refined pattern library. Respond with JSON only."""

    print(f"\n{BOLD}Running quality check on {len(patterns)} patterns...{RESET}")

    for attempt in range(5):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=6000,
                system=QUALITY_CHECK_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            result = json.loads(raw)

            # Save to DB
            conn = get_conn()
            conn.execute("""
                INSERT INTO analysis_batches (sport, tickers, raw_response)
                VALUES (?, ?, ?)
            """, ("all", "QUALITY_CHECKED", raw))
            conn.commit()
            conn.close()

            # Print results
            refined = result.get("refined_patterns", [])
            removed = result.get("removed_patterns", [])

            print(f"\n{'='*65}")
            print(f"QUALITY-CHECKED PATTERN LIBRARY")
            print(f"{'='*65}")
            print(f"Refined: {len(refined)} patterns | Removed: {len(removed)} duplicates/noise")
            print()

            for p in refined:
                conf = p.get('confidence', '?')
                stars = '★' * int(conf) + '☆' * (5 - int(conf)) if isinstance(conf, int) else str(conf)
                print(f"[{stars}] #{p.get('frequency_rank', '?') if 'frequency_rank' in p else ''} {p['name']} [{p.get('sport','?')}]")
                print(f"  {p.get('description','')}")
                print(f"  ▶ Entry: {p.get('entry_rule','')}")
                print(f"  ■ Exit:  {p.get('exit_rule','')}")
                print(f"  ⚠ Avoid: {p.get('false_signal','')}")
                if p.get('merged_from'):
                    print(f"  ↳ Merged from: {', '.join(p['merged_from'])}")
                print()

            if removed:
                print(f"REMOVED ({len(removed)}):")
                for r in removed:
                    print(f"  ✗ {r['name']}: {r['reason']}")

            print(f"\nTOP INSIGHTS:")
            for i, ins in enumerate(result.get("top_insights", []), 1):
                print(f"  {i}. {ins}")

            timing = result.get("entry_timing_rules", {})
            if timing:
                print(f"\nTIMING RULES:")
                for k, v in timing.items():
                    print(f"  {k}: {v}")

            bankroll = result.get("bankroll_rules", {})
            if bankroll:
                print(f"\nBANKROLL RULES:")
                for k, v in bankroll.items():
                    print(f"  {k}: {v}")

            print(f"\nQUALITY NOTES: {result.get('quality_notes','')}")
            print(f"{'='*65}\n")

            return result

        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"  [rate limit] waiting {wait}s...")
            time.sleep(wait)
        except json.JSONDecodeError as e:
            print(f"  [error] JSON parse failed: {e}")
            print(f"  Raw: {raw[:300]}")
            break
        except Exception as e:
            print(f"  [error] {e}")
            break

    return None


def get_quality_checked_library() -> dict:
    """Get the latest quality-checked pattern library."""
    conn = get_conn()
    row = conn.execute("""
        SELECT raw_response FROM analysis_batches
        WHERE tickers='QUALITY_CHECKED'
        ORDER BY created_at DESC LIMIT 1
    """).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["raw_response"])
        except Exception:
            return {}
    return {}