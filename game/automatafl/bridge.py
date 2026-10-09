#!/usr/bin/env python3
"""Transport and reversible board encoding for the actual Objective Bend package.

All validation/gameplay functions execute in Mini's compiled checker/demand
machine. Python neither decides legal moves nor computes game transitions.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'


def exchange(job, timeout=120):
    process = subprocess.run([str(BINARY)], input=json.dumps(job) + '\n', text=True,
                             capture_output=True, timeout=timeout)
    if process.returncode:
        raise RuntimeError(process.stderr or process.stdout)
    return json.loads(process.stdout)


def export(entry='play', validated=True):
    modules = [{'name': 'Automatafl', 'source': (HERE / 'Automatafl.obend').read_bytes().decode('utf-8')}]
    if validated:
        modules.append({'name': 'Validated', 'source': (HERE / 'Validated.obend').read_bytes().decode('utf-8')})
    result = exchange({'op': 'compile', 'modules': modules, 'entry': entry})
    if result['status'] != 'compiled':
        raise RuntimeError(result)
    return result['artifact']


def pack(cells, base=4):
    """Reversible first-order wire encoding, not a game decision."""
    return sum(int(cell) * base ** index for index, cell in enumerate(cells))


def unpack(value, count, base=4):
    value = int(value)
    cells = []
    for _ in range(count):
        cells.append(value % base)
        value //= base
    if value:
        raise ValueError('encoded value has digits beyond declared dimensions')
    return cells


def data(value):
    if value['tag'] == 'natural':
        return int(value['value'])
    if value['tag'] in ('boolean', 'label'):
        return value['value']
    if value['tag'] == 'record':
        return {field['name']: data(field['value']) for field in value['fields']}
    raise ValueError('unexpected package result data')


def run(artifact, arguments, limits=None):
    job = {'op': 'run', 'artifact': artifact,
           'arguments': [{'tag': 'natural', 'value': str(n)} for n in arguments]}
    if limits is not None:
        job['limits'] = limits
    return exchange(job)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('export')
    build.add_argument('--entry', default='play')
    build.add_argument('--raw', action='store_true', help='exact original package, without board-validation wrapper')
    build.add_argument('--output', type=Path, required=True)
    play = commands.add_parser('play')
    play.add_argument('artifact', type=Path)
    play.add_argument('arguments', type=Path, help='JSON array: w,h,board,automaton,marks,s0,t0,s1,t1')
    play.add_argument('--ticks', type=int, default=100000)
    args = parser.parse_args()
    if args.command == 'export':
        if args.output.exists():
            raise ValueError('output already exists')
        artifact = export(args.entry, not args.raw)
        with args.output.open('x') as stream:
            json.dump(artifact, stream, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n')
        print(json.dumps({'artifact': str(args.output), 'entry': args.entry,
                          'packetSha256': artifact['packetSha256'],
                          'bytes': args.output.stat().st_size}))
    else:
        artifact = json.loads(args.artifact.read_text())
        arguments = json.loads(args.arguments.read_text())
        result = run(artifact, arguments, {'ticks': args.ticks})
        print(json.dumps(result))
        return 0 if result['status'] == 'finished' else 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
