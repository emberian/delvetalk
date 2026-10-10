#!/usr/bin/env python3
"""Total <state>/model-spend.jsonl (written by transport.model) by UTC month and print the remaining grant.

  python3 -m deploy.spend --state /data/state [--month YYYY-MM] [--grant 200]
"""
import argparse
import json
import sys
import time
from pathlib import Path

RATES = {'input': 0.10, 'output': 0.50}  # dollars per million tokens, Haiku 5.5's published rates


def totals(state, month=None):
    """-> {month: {calls, inputTokens, outputTokens, dollars}} from <state>/model-spend.jsonl (UTC months), or just `month`."""
    path, out = Path(state) / 'model-spend.jsonl', {}
    for line in path.read_text().splitlines() if path.exists() else []:
        row = json.loads(line)
        key = time.strftime('%Y-%m', time.gmtime(row['at']))
        if month and key != month:
            continue
        t = out.setdefault(key, {'calls': 0, 'inputTokens': 0, 'outputTokens': 0})
        t['calls'] += 1
        t['inputTokens'] += row.get('inputTokens') or 0
        t['outputTokens'] += row.get('outputTokens') or 0
    for t in out.values():
        t['dollars'] = round((t['inputTokens'] * RATES['input'] + t['outputTokens'] * RATES['output']) / 1e6, 4)
    return out


def report(state, month, grant, out):
    month = month or time.strftime('%Y-%m', time.gmtime())
    for key, t in sorted(totals(state).items()):
        out.write(f"{key}  {t['calls']} calls  {t['inputTokens']} in  {t['outputTokens']} out  ${t['dollars']:.4f}\n")
    spent = totals(state, month).get(month, {}).get('dollars', 0.0)
    out.write(f'{month}: ${spent:.4f} of ${grant:.2f} grant spent, ${grant - spent:.4f} remaining '
              f"(at ${RATES['input']:.2f} per million input tokens, ${RATES['output']:.2f} per million output)\n")


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='spend.py')
    ap.add_argument('--state', required=True, help='the directory holding model-spend.jsonl')
    ap.add_argument('--month', metavar='YYYY-MM', help='default: this month (UTC)')
    ap.add_argument('--grant', type=float, default=200.0, help='the monthly API credit in dollars (default 200)')
    a = ap.parse_args(argv)
    report(a.state, a.month, a.grant, out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
