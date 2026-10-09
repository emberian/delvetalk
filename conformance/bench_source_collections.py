#!/usr/bin/env python3
"""Opt-in source collection experiment, using frozen existing native binaries.

No builds or source specialization. Python constructs input data and records native
results; RoomBench and imported place modules choose listing/selection/preparation.
Counters describe PackageData execution/conversion, not full host or portal load.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MODULES = {'List': 'world/lib/prelude/List.obend', 'Abi': 'world/lib/prelude/Abi.obend',
           'Encounter': 'world/lib/prelude/Encounter.obend',
           'ExhibitList': 'protocols/place-index/ExhibitList.obend',
           'Main': 'protocols/place-index/Main.obend',
           'RoomBench': 'conformance/fixtures/source-collections/RoomBench.obend'}
PAGE_MODULES = {'List': 'world/lib/prelude/List.obend', 'Encounter': 'world/lib/prelude/Encounter.obend',
                'EncounterPages': 'world/lib/prelude/EncounterPages.obend',
                'PagesBench': 'conformance/fixtures/source-collections/PagesBench.obend'}
DIAGNOSTICS = ('spec/Delvetalk/Package.lean', 'spec/Delvetalk/PackageData.lean',
               'scene/projection.py', 'protocols/place-index/README.md')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(directory, modules=MODULES):
    """Copy one immutable evidence bundle; never overwrite an existing bundle."""
    if directory.exists():
        manifest = json.loads((directory / 'manifest.json').read_bytes())
        if sha(directory / 'delvetalk-obend') != manifest['binarySha256']:
            raise RuntimeError('frozen binary digest differs')
        for name, digest in manifest['files'].items():
            if sha(directory / name) != digest: raise RuntimeError('frozen source digest differs: ' + name)
        return manifest
    directory.mkdir(parents=True, exist_ok=False)
    binary = ROOT / '.lake/build/bin/delvetalk-obend'
    before = sha(binary)
    shutil.copy2(binary, directory / 'delvetalk-obend')
    after = sha(binary)
    if before != after or sha(directory / 'delvetalk-obend') != before:
        raise RuntimeError('native binary changed during snapshot; keep evidence and choose a new snapshot')
    manifest = {'binarySha256': before, 'repository': str(ROOT), 'files': {}}
    for name in (*modules.values(), *DIAGNOSTICS):
        source = ROOT / name
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        target.write_bytes(raw)
        if sha(source) != hashlib.sha256(raw).hexdigest():
            raise RuntimeError('source changed during snapshot: ' + name)
        manifest['files'][name] = hashlib.sha256(raw).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': key, 'value': value} for key, value in fields.items()]}


def variant(label, payload):
    return {'tag': 'variant', 'label': label, 'payload': payload}


def text(value): return {'tag': 'label', 'value': value}
def natural(value): return {'tag': 'natural', 'value': str(value)}


def entries(size):
    value = variant('nil', record())
    for i in reversed(range(size)):
        entry = record(object=text(f'object-{i:03d}'), label=text(f'Exhibit {i:03d}'),
                       addedBy=text('curator'), observedVersion=natural(i))
        value = variant('cons', record(head=entry, tail=value))
    return value


def fields(value):
    return {item['name']: item['value'] for item in value['fields']}


def summarize(entry, reply):
    value = reply.get('value')
    if value is None: return None
    if entry in ('count', 'select'): return value
    row = fields(value)
    if entry == 'listing':
        children = row['children']; size = 0
        while children['label'] == 'cons':
            size += 1; children = fields(children['payload'])['tail']
        return {'children': size, 'title': row['title'], 'prose': row['prose']}
    if entry == 'prepare': return row
    return {key: row[key] for key in ('accepted', 'reason', 'result')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path, help='new private snapshot directory')
    parser.add_argument('--output', required=True, type=Path, help='private JSON result path')
    parser.add_argument('--representation', choices=('flat', 'pages'), default='flat')
    parser.add_argument('--sizes', default='8,32,50,200')
    parser.add_argument('--repeats', default=3, type=int)
    parser.add_argument('--exports', default='count,listing,select,prepare,add')
    args = parser.parse_args()
    sizes = [int(n) for n in args.sizes.split(',')]
    if args.representation == 'pages':
        return run_pages(args, sizes)
    exports = args.exports.split(',')
    if not exports or any(entry not in ('count', 'listing', 'select', 'prepare', 'add') for entry in exports):
        parser.error('unknown source export')
    if any(n < 0 or n > 200 for n in sizes) or not 1 <= args.repeats <= 5:
        parser.error('bounded experiment: sizes 0..200, repeats 1..5')
    # Deep JSON here is a wire list. This raises only Python's serialization stack,
    # never native fuel, heap, depth or work capacities.
    sys.setrecursionlimit(10000)
    frozen = args.snapshot.resolve()
    manifest = snapshot(frozen)
    modules = [{'name': name, 'source': (frozen / path).read_text()} for name, path in MODULES.items()]
    binary = frozen / 'delvetalk-obend'
    def call(request):
        raw = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
        if len(raw) > 2 * 1024 * 1024: raise ValueError('benchmark request exceeds explicit 2 MiB ceiling')
        begin = time.perf_counter()
        try:
            done = subprocess.run([str(binary)], input=raw, capture_output=True, timeout=30, check=True)
            elapsed = (time.perf_counter() - begin) * 1000
            if len(done.stdout) > 8 * 1024 * 1024: raise ValueError('benchmark result exceeds 8 MiB ceiling')
            return json.loads(done.stdout), elapsed
        except subprocess.TimeoutExpired:
            return {'status': 'timeout', 'message': '30 second benchmark wall limit'}, 30000
    results = {'snapshot': str(frozen), 'manifest': manifest,
        'scope': 'Native checked source export; separate compile then run-data-v1. Run wall time includes process startup and source artifact re-verification. Package counters exclude that verification. No admitted world, root validation, portal rendering, or complete room load claim.',
        'limits': 'Native defaults; no global or per-request increases', 'compilation': {}, 'cases': []}
    artifacts = {}
    for entry in exports:
        reply, ms = call({'op': 'compile', 'modules': modules, 'entry': entry})
        results['compilation'][entry] = {'milliseconds': ms, 'status': reply.get('status'), 'message': reply.get('message')}
        if reply.get('status') == 'compiled': artifacts[entry] = reply['artifact']
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
    for size in sizes:
        for entry in artifacts:
            modes = ('last', 'missing') if entry in ('select', 'prepare') else ('ordinary',)
            for mode in modes:
                arguments = [entries(size)]
                if mode != 'ordinary': arguments.append(text(f'object-{size-1:03d}' if mode == 'last' else 'missing-object'))
                runs = [call({'op': 'run-data-v1', 'artifact': artifacts[entry], 'arguments': arguments}) for _ in range(args.repeats)]
                reply = runs[-1][0]
                case = {'size': size, 'entry': entry, 'mode': mode, 'status': reply.get('status'),
                    'message': reply.get('message'), 'failure': reply.get('failure'),
                    'medianMs': statistics.median(ms for _, ms in runs),
                    'timesMs': [ms for _, ms in runs], 'summary': summarize(entry, reply),
                    'counters': {key: value for key, value in reply.items() if key not in ('value', 'status', 'message', 'failure', 'executionProfile', 'type')}}
                if reply.get('status') == 'finished':
                    summary = case['summary']
                    found = mode == 'last' and size > 0
                    if entry == 'count': assert summary == natural(size)
                    elif entry == 'listing': assert summary['children'] == size
                    elif entry == 'select': assert summary == {'tag': 'boolean', 'value': found}
                    elif entry == 'prepare':
                        assert summary['found'] == {'tag': 'boolean', 'value': found}
                        if found:
                            assert summary['object'] == text(f'object-{size-1:03d}')
                            assert summary['observedVersion'] == natural(size-1)
                    elif entry == 'add': assert summary['accepted']['value'] == (size < 32)
                results['cases'].append(case); save()
                print(json.dumps({key: case[key] for key in ('size', 'entry', 'mode', 'status', 'message', 'medianMs', 'counters')}), flush=True)
    if 'listing' in artifacts:
        reply, ms = call({'op': 'run-data-v1', 'artifact': artifacts['listing'],
            'arguments': [entries(125)], 'limits': {'nodes': 1}})
        results['cases'].append({'entry': 'listing', 'size': 125,
            'mode': 'bounded-output-stage-probe', 'medianMs': ms, **reply})
    if 'count' in artifacts:
        for mode, value, limits in [('low-work', entries(8), {'work': 1}),
                                    ('bad-shape', variant('cons', natural(1)), {})]:
            reply, ms = call({'op': 'run-data-v1', 'artifact': artifacts['count'], 'arguments': [value], 'limits': limits})
            results['cases'].append({'entry': 'count', 'mode': mode, 'medianMs': ms, **reply})
    save()
    if len(artifacts) != len(exports): raise SystemExit('Some source exports failed compilation; inspect recorded diagnostics')


def children(size, start=0):
    value = variant('nil', record())
    for i in reversed(range(start, start + size)):
        value = variant('cons', record(head=child(i), tail=value))
    return value


def child(i):
    return record(key=text(f'k{i}'), label=text(f'Exhibit {i}'), object=text(f'o{i}'), panel=text('main'))


def pages(size):
    value = variant('nil', record())
    for start in reversed(range(0, size, 16)):
        value = variant('cons', record(head=children(min(16, size - start), start), tail=value))
    return value


def child_keys(value):
    result = []
    while value['label'] == 'cons':
        row = fields(value['payload'])
        result.append(fields(row['head'])['key']['value'])
        value = row['tail']
    return result


def page_keys(value):
    result = []
    while value['label'] == 'cons':
        row = fields(value['payload'])
        keys = child_keys(row['head'])
        assert 0 < len(keys) <= 16
        result.extend(keys)
        value = row['tail']
    return result


def run_pages(args, sizes):
    if any(n < 0 or n > 200 for n in sizes) or not 1 <= args.repeats <= 5:
        raise SystemExit('bounded experiment: sizes 0..200, repeats 1..5')
    frozen = args.snapshot.resolve()
    manifest = snapshot(frozen, PAGE_MODULES)
    modules = [{'name': name, 'source': (frozen / path).read_text()} for name, path in PAGE_MODULES.items()]
    binary = frozen / 'delvetalk-obend'
    def call(request):
        begin = time.perf_counter()
        raw = json.dumps(request, separators=(',', ':')).encode() + b'\n'
        done = subprocess.run([str(binary)], input=raw, capture_output=True, timeout=30, check=True)
        assert len(done.stdout) <= 8 * 1024 * 1024
        return json.loads(done.stdout), (time.perf_counter() - begin) * 1000
    artifacts = {}
    for entry in ('count', 'pages', 'listing', 'select', 'prepare', 'add', 'remove'):
        compiled, _ = call({'op': 'compile', 'modules': modules, 'entry': entry})
        assert compiled['status'] == 'compiled', compiled
        artifacts[entry] = compiled['artifact']
    result = {'manifest': manifest, 'representation': '16-child pages; source-owned operations',
              'limits': 'Native defaults, no increases',
              'scope': 'PackageData counters exclude artifact reverification, process startup, admission and custody; wall includes startup and reverification.', 'cases': []}
    for size in sizes:
        state = pages(size)
        last = max(0, (size - 1) // 16)
        cases = [('count', [], 'ordinary'), ('pages', [], 'ordinary'),
                 ('listing', [natural(last)], 'last-page'),
                 ('listing', [natural(999)], 'absent-page'),
                 ('select', [text(f'k{size-1}')], 'last'),
                 ('select', [text('absent')], 'missing'),
                 ('prepare', [record(page=natural(last), target=text(f'k{size-1}'))], 'last'),
                 ('add', [child(size), natural(size+1)], 'append'),
                 ('add', [child(size), natural(size)], 'full'),
                 ('remove', [text('k0')], 'first'),
                 ('remove', [text('absent')], 'missing')]
        if size: cases.append(('add', [child(0), natural(size+1)], 'duplicate'))
        for entry, extra, mode in cases:
            runs = [call({'op': 'run-data-v1', 'artifact': artifacts[entry], 'arguments': [state] + extra}) for _ in range(args.repeats)]
            reply = runs[-1][0]
            case = {'size': size, 'entry': entry, 'mode': mode, 'status': reply.get('status'),
                    'message': reply.get('message'), 'failure': reply.get('failure'),
                    'medianMs': statistics.median(ms for _, ms in runs),
                    'counters': {k: reply[k] for k in ('ticksUsed', 'conversionNodes', 'heapCells', 'nodesUsed') if k in reply}}
            if reply.get('status') == 'finished':
                v = reply['value']; expected = [f'k{i}' for i in range(size)]
                if entry == 'count': assert v == natural(size)
                elif entry == 'pages': assert v == natural((size+15)//16)
                elif entry == 'listing': assert child_keys(v) == (expected[last*16:] if mode == 'last-page' else [])
                elif entry == 'select': assert v['value'] == (mode == 'last' and size > 0)
                elif entry == 'prepare':
                    assert fields(v)['found']['value'] == (size > 0)
                    assert child_keys(fields(v)['children']) == expected[last*16:]
                elif entry == 'add':
                    assert fields(v)['accepted']['value'] == (mode == 'append')
                    assert page_keys(fields(v)['pages']) == expected + ([f'k{size}'] if mode == 'append' else [])
                elif entry == 'remove': assert page_keys(v) == (expected[1:] if mode == 'first' else expected)
            result['cases'].append(case)
            print(json.dumps(case), flush=True)
    for mode, arguments, limits in [('low-work', [pages(8)], {'work': 1}),
                                    ('bad-shape', [variant('cons', natural(1))], {})]:
        reply, ms = call({'op': 'run-data-v1', 'artifact': artifacts['count'], 'arguments': arguments, 'limits': limits})
        assert reply['status'] != 'finished', reply
        result['cases'].append({'mode': mode, 'medianMs': ms, **reply})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    if any(case.get('status') != 'finished' for case in result['cases'] if 'size' in case):
        raise SystemExit('A collection operation reached a recorded native limit')


if __name__ == '__main__': main()
