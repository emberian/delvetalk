#!/usr/bin/env python3
"""Record and submit one explicit logical tick; this is custody, not a scheduler."""
import argparse
import fcntl
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import world


def tick(database, attempt, *, clock, principal, intent, now):
    database = Path(database).resolve()
    attempt = Path(attempt).resolve()
    if attempt in (database, Path(str(database) + '.lock')):
        raise ValueError('tick attempt must be separate from world custody')
    attempt.parent.mkdir(parents=True, exist_ok=True)
    supplied = {'op': 'invoke', 'object': clock, 'command': 'tick',
                'principal': principal, 'intent': intent, 'input': {'now': now}}
    with open(str(attempt) + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if attempt.exists():
            retained = world.wire_loads(attempt.read_text())
            request = retained['request']
            if (retained.get('profile') != 'compiled' or retained.get('database') != str(database)
                    or {key: value for key, value in request.items() if key != 'expected'} != supplied):
                raise ValueError('tick attempt is bound to different custody or explicit inputs')
        else:
            root = world.exchange(database, {'op': 'inspect', 'object': clock,
                                            'principal': principal}, profile='compiled')
            request = {**supplied, 'expected': root}
            retained = {'profile': 'compiled', 'database': str(database), 'request': request}
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=attempt.parent,
                        prefix=attempt.name + '.', delete=False) as handle:
                    temporary = handle.name
                    handle.write(world.wire_dumps(retained) + '\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, attempt)
                temporary = None
            finally:
                if temporary is not None:
                    os.unlink(temporary)
        # Retrying after an uncertain preparation reestablishes custody barriers
        # before admitting the same exact request. Never refresh its preimage.
        descriptor = os.open(attempt, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        descriptor = os.open(attempt.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return world.exchange(database, request, profile='compiled')


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
