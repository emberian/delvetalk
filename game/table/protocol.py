"""Physical loading of the source-owned two-player table and its configuration.

No command, guard, state transition, grant or view is generated in Python.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / 'game/automatafl'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object

OPENING = json.loads((GAME / 'original-opening.json').read_text())


def modules():
    return source_object.read_closure([
        ('Automatafl', GAME / 'Automatafl.obend'),
        ('Validated', GAME / 'Validated.obend'),
        ('CommitRevealTable', HERE / 'CommitRevealTable.obend')])


def evaluate(entry, arguments):
    """Transport a pure source export's exact DataWire inputs and result."""
    deadline = time.monotonic() + 30
    native = source_object.adapter._native
    limits = source_object.adapter.LIMITS
    artifact = native({'op': 'compile', 'modules': modules(), 'entry': entry,
                       'limits': limits}, deadline)['artifact']
    return native({'op': 'run-data-v1', 'artifact': artifact,
                   'arguments': arguments, 'limits': limits}, deadline)['value']


@lru_cache(maxsize=32)
def _loaded(encoded_modules, encoded_config, pins):
    return source_object.load(json.loads(encoded_modules), syntax='objective-bend-object',
        constructor='initial', arguments=[source_object.data(json.loads(encoded_config))])


def protocol(table_id, seat0, seat1):
    # Cache physical compilation only, keyed by complete source/config/runtime pins.
    config = {'table': table_id, 'north': seat0, 'south': seat1}
    return deepcopy(_loaded(json.dumps(modules()), json.dumps(config),
                            json.dumps(source_object.pins('objective-bend-object'), sort_keys=True)))


def law(seat0, seat1):
    result = evaluate('authority', [source_object.data({'north': seat0, 'south': seat1})])
    return source_object.values('decode', [result])[0]


def create_request(table_id, seat0, seat1, principal, intent):
    return {'op': 'create', 'object': table_id, 'principal': principal, 'intent': intent,
            'protocol': protocol(table_id, seat0, seat1), 'law': law(seat0, seat1)}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Load the source-owned original two-player table.')
    parser.add_argument('--table', required=True)
    parser.add_argument('--seat0', required=True)
    parser.add_argument('--seat1', required=True)
    parser.add_argument('--principal', required=True)
    parser.add_argument('--intent', required=True)
    args = parser.parse_args()
    print(json.dumps(create_request(args.table, args.seat0, args.seat1, args.principal, args.intent),
                     ensure_ascii=False, separators=(',', ':')))
