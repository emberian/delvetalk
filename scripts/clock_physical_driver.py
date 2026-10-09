#!/usr/bin/env python3
"""Retain one physical clock observation before native admission; retry it exactly."""
import argparse
from pathlib import Path
import time

import retained_invocation
import world

SOURCE = 'unix-milliseconds'


def sample(database, attempt, *, clock, principal, intent, source=SOURCE):
    if source != SOURCE:
        raise ValueError('physical driver supports the explicit unix-milliseconds source')
    identity = {'op': 'invoke', 'object': clock, 'command': 'sample',
                'principal': principal, 'intent': intent}
    # This is the physical measurement's encoding, not its world-time meaning.
    # Epoch, quantum, monotonicity, expiry and due selection belong to Clock Bend.
    return retained_invocation.submit(database, attempt, identity=identity, source=source,
        input_factory=lambda: {'unixMillis': time.time_ns() // 1_000_000})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('attempt', type=Path)
    parser.add_argument('--clock', required=True)
    parser.add_argument('--principal', required=True)
    parser.add_argument('--intent', required=True)
    parser.add_argument('--source', choices=[SOURCE], default=SOURCE)
    args = parser.parse_args()
    print(world.wire_dumps(sample(args.database, args.attempt, clock=args.clock,
        principal=args.principal, intent=args.intent, source=args.source)))


if __name__ == '__main__':
    main()
