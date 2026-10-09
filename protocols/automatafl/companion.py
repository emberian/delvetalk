#!/usr/bin/env python3
"""Capture a source-public game card and board under one native reference."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import history
import town_cards
import opaque_offers
import world
import public_board


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


client = module('companion_client', 'game/table/client.py')
table = module('companion_protocol', 'game/table/protocol.py')


board = public_board.render


def capture(database, object_id, book, alias=None, *, principal, panel='main', expected=None):
    if book.metadata()['runtime'] != history.runtime('compiled'):
        raise ValueError('Companion runtime differs from the configured cardbook')
    captured = world.opaque_view(database, object_id, principal=principal, panel=panel,
                                 audience='public', expected=expected)
    invitations = opaque_offers.capture(database, object_id, captured, principal)
    saved = book.capture_public(object_id, captured, alias=alias, invitations=invitations)
    return {'card': saved['alias'], 'reference': captured['reference'],
            'text': saved['body']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True, help='native world custody database')
    parser.add_argument('--principal', required=True, help='authenticated caller selecting the public panel')
    parser.add_argument('--table', required=True)
    parser.add_argument('--book', type=Path, required=True, help='existing explicitly configured cardbook')
    parser.add_argument('--alias')
    args = parser.parse_args()
    captured = capture(args.database, args.table, town_cards.CardBook(args.book), args.alias,
                       principal=args.principal)
    print(captured['text'])


if __name__ == '__main__':
    main()
