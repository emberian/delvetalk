#!/usr/bin/env python3
"""Capture a public game card and coordinate board from the same exact root."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import history
import town_cards


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


client = module('companion_client', 'game/table/client.py')
table = module('companion_protocol', 'game/table/protocol.py')


def board(root):
    """Decode existing board/mark digits for display; no movement decisions."""
    view = client.public_view(root)
    width, height = view['width'], view['height']
    if width != 5 or height != 5:
        raise ValueError('This companion displays the ordinary qualified 5 by 5 table')
    lines = [f'Round {view["round"]} · table version {view["version"]}', '    A B C D E']
    for row in range(height):
        cells = view['cells'][row * width:(row + 1) * width]
        lines.append(f'  {row + 1} ' + ' '.join('.+-@'[cell] for cell in cells))
    marks = [chr(65 + i % width) + str(i // width + 1)
             for i in range(width * height) if view['marks'] & (1 << i)]
    lines += ['Marked: ' + (', '.join(marks) if marks else 'none'),
              'A1 is index 0; E1 is 4; A2 is 5. Rows increase downward.',
              '+ attractor, - repulsor, @ automaton. North owns top corners; South owns bottom corners.']
    def coordinate(index):
        return (chr(65 + index % width) + str(index // width + 1) if index < width * height
                else 'index ' + str(index) + ' (outside board)')
    for seat, name in enumerate(('North', 'South')):
        if view['revealed'][seat]:
            source, target = (root['state'][key + str(seat)] for key in ('source', 'target'))
            lines.append(name + ' opened: ' + coordinate(source) + ' to ' + coordinate(target))
    return '\n'.join(lines)


def capture(root, object_id, book, alias=None):
    if not client.same_game(root.get('protocol'), table.protocol(object_id)):
        raise ValueError('Companion requires the unchanged qualified two-player game')
    if 'viewProgram' not in root['protocol']:
        raise ValueError('Install the companion presentation before capturing a resident card')
    view = town_cards.projection.project(root, object_id, expected_runtime=book.metadata()['runtime'])
    saved = book.capture(view, alias)
    return {'card': saved['alias'], 'version': root['version'],
            'text': board(view['root']) + '\n\n' + saved['body']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='saved exact public table root JSON')
    parser.add_argument('--table', required=True)
    parser.add_argument('--book', type=Path, required=True, help='existing explicitly configured cardbook')
    parser.add_argument('--alias')
    args = parser.parse_args()
    captured = capture(history.loads(args.root.read_bytes()), args.table,
                       town_cards.CardBook(args.book), args.alias)
    print(captured['text'])


if __name__ == '__main__':
    main()
