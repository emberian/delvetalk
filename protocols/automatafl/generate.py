#!/usr/bin/env python3
"""Add a resident view to the unchanged qualified two-player game protocol."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('companion_table_protocol', ROOT / 'game/table/protocol.py')
table = importlib.util.module_from_spec(spec)
spec.loader.exec_module(table)


def presentation():
    return {'description': 'Original 11x11 two-player Automatafl; private operator custody precedes public openings.',
        'affordances': {'resolve': {'label': 'Resolve both opened moves',
            'fields': {'round': {'type': 'nat', 'maximum': (1 << 53) - 1}}}},
        'viewProgram': {'profile': 'delvetalk-obend-menu-v1', 'package': {
            'modules': [{'name': 'Table', 'source': (HERE / 'Table.obend').read_text()}], 'entry': 'view'}},
        'viewPanels': [{'id': 'result', 'label': 'Last result'},
                       {'id': 'custody', 'label': 'Before choosing'},
                       {'id': 'rules', 'label': 'The shared board'}]}


def protocol(table_id):
    return {**table.protocol(table_id), **presentation()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', required=True)
    parser.add_argument('--seat0', required=True, help='configured North principal')
    parser.add_argument('--seat1', required=True, help='configured South principal')
    parser.add_argument('--principal', required=True)
    parser.add_argument('--intent', required=True)
    args = parser.parse_args()
    request = table.create_request(args.table, args.seat0, args.seat1, args.principal, args.intent)
    request['protocol'] = protocol(args.table)
    print(json.dumps(request, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
