#!/usr/bin/env python3
"""Record and submit one explicit logical tick; this is custody, not a scheduler."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import retained_invocation
import world


def tick(database, attempt, *, clock, principal, intent, now):
    return retained_invocation.submit(database, attempt, identity={
        'op': 'invoke', 'object': clock, 'command': 'tick', 'principal': principal,
        'intent': intent, 'input': {'now': now}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('attempt', type=Path, help='private file retaining the exact tick request')
    parser.add_argument('--clock', default='clock')
    parser.add_argument('--principal', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--now', type=int, required=True, help='explicit logical time; no wall clock is read')
    args = parser.parse_args()
    print(world.wire_dumps(tick(args.database, args.attempt, clock=args.clock,
        principal=args.principal, intent=args.intent, now=args.now)))


if __name__ == '__main__':
    main()
