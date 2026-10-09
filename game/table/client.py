#!/usr/bin/env python3
"""Opaque commitment preparation and public display; no game/authority evaluator."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets

_spec = importlib.util.spec_from_file_location('commit_reveal_source', Path(__file__).with_name('protocol.py'))
table = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(table)


def same_game(program, qualified):
    """Require the complete source-owned program, including original configuration."""
    if not isinstance(program, dict):
        return False
    try:
        if isinstance(qualified, str):
            initial = table.source_object.plain(table.source_object.state_data(
                {'protocol': program, 'state': program['initial']}))
            qualified = table.protocol(qualified, initial['seats']['north'], initial['seats']['south'])
        return canonical(program) == canonical(qualified)
    except (KeyError, TypeError, ValueError):
        return False


def state(root):
    """Decode typed state; old retained receipts retain their historical display."""
    value = root['state']
    return table.source_object.plain(table.source_object.state_data(root)) if set(value) == {'model'} else value


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def prepare(table_id, round_number, seat, source, target, nonce=None):
    nonce = secrets.token_hex(32) if nonce is None else nonce
    digest = table.source_object.plain(table.evaluate('commitment',
        [table.source_object.data(value) for value in (table_id, round_number, seat, source, target, nonce)]))
    return {'table': table_id, 'seat': seat,
            'commit': {'round': round_number, 'digest': digest},
            'reveal': {'round': round_number, 'source': source, 'target': target, 'nonce': nonce}}


def public_view(root):
    s = state(root)
    game = s['game']
    count = s['width'] * s['height']
    board = game['board']
    cells = [(board // 4 ** index) % 4 for index in range(count)]
    return {'table': s['table'], 'round': s['round'], 'version': root['version'],
            'width': s['width'], 'height': s['height'], 'cells': cells,
            'marks': game['marks'], 'status': game['status'], 'winner': game['winner'],
            'committed': [s['commit0'] != '', s['commit1'] != ''],
            'revealed': [s['revealed0'], s['revealed1']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('prepare')
    make.add_argument('--table', required=True)
    make.add_argument('--round', type=int, required=True)
    make.add_argument('--seat', type=int, choices=[0, 1], required=True)
    make.add_argument('--source', type=int, required=True)
    make.add_argument('--target', type=int, required=True)
    make.add_argument('--private', type=Path, required=True, help='new private reveal file; mode 0600')
    view = commands.add_parser('view')
    view.add_argument('root', type=Path, help='JSON exact object root')
    args = parser.parse_args()
    if args.command == 'prepare':
        secret = prepare(args.table, args.round, args.seat, args.source, args.target)
        fd = os.open(args.private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(secret, stream, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(args.private.resolve().parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        print(json.dumps(secret['commit']))
    else:
        print(json.dumps(public_view(json.loads(args.root.read_text()))))


if __name__ == '__main__':
    main()
