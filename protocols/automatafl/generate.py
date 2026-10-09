#!/usr/bin/env python3
"""Load the ordinary source-owned original two-player table and its public view."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('companion_table_protocol', ROOT / 'game/table/protocol.py')
table = importlib.util.module_from_spec(spec)
spec.loader.exec_module(table)


def protocol(table_id, seat0, seat1):
    return table.protocol(table_id, seat0, seat1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', required=True)
    parser.add_argument('--seat0', required=True, help='configured North principal')
    parser.add_argument('--seat1', required=True, help='configured South principal')
    parser.add_argument('--principal', required=True)
    parser.add_argument('--intent', required=True)
    args = parser.parse_args()
    request = table.create_request(args.table, args.seat0, args.seat1, args.principal, args.intent)
    print(json.dumps(request, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
