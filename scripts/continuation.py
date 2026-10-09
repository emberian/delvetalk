#!/usr/bin/env python3
"""Prepare and replay an offline continuation; never publish or admit requests."""
import argparse
import html
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
import history
import worker

FORMAT = 'delvetalk-continuation-v1'
canonical, loads = history.canonical, history.loads


def required_blobs(manifest, bundle):
    required = set(manifest['genesis']['profile']['files'].values())
    for entry in manifest['entries']:
        for ref in entry['artifacts']:
            required.add(ref['sha256'])
            raw = history.read_blob(bundle, ref['sha256']).read_bytes()
            try:
                value = loads(raw)
            except (ValueError, UnicodeError):
                # An opaque attachment has no JSON dependency declaration.
                continue
            required.update(history.declared_files(value).values())
    return required


def anchored_receipts(manifest, bundle):
    found = {}
    for entry in manifest['entries']:
        for ref in entry['artifacts']:
            try:
                value = loads(history.read_blob(bundle, ref['sha256']).read_bytes())
            except (ValueError, UnicodeError):
                continue
            for item in bootstrap.artifact_envelopes(value):
                if item.get('format') == 'delvetalk-clerk-receipt-v1':
                    found[history.digest(item)] = item
    return [found[key] for key in sorted(found)]


def index_for(manifest, state, selected):
    """Describe replay results; source identities remain unauthenticated claims."""
    admissions = {history.digest(entry['request']): entry for entry in manifest['entries']}
    prepared, retained = [], []
    for receipt in selected:
        try:
            worker.receipts.encode('receipt', canonical(receipt).decode())
        except worker.receipts.Failure as error:
            raise ValueError(str(error)) from error
        if receipt.get('id') != history.digest({k: v for k, v in receipt.items() if k != 'id'}):
            raise ValueError('clerk receipt identity mismatch')
        entry = admissions.get(history.digest(receipt['request']))
        if (entry is None or canonical(entry['request']) != canonical(receipt['request'])
                or canonical(entry['reply']) != canonical(receipt['reply'])):
            raise ValueError('clerk receipt does not match retained admission')
        retained.append({'admission': entry['id'], 'receipt': receipt})
        prepared.extend(worker.publication_artifacts(receipt))
    if len({item['receipt']['id'] for item in retained}) != len(retained):
        raise ValueError('duplicate selected clerk receipt')
    retained.sort(key=lambda item: item['receipt']['id'])
    prepared.sort(key=lambda item: (item['kind'], item['id']))
    roots = [{'object': name, 'root': root} for name, root in sorted(state['objects'].items())]
    return {'format': FORMAT, 'status': 'prepared-offline', 'history': {
                'path': 'history', 'genesis': manifest['genesis']['id'], 'head': manifest['head'],
                'entries': len(manifest['entries']), 'worldSha256': manifest['worldSha256']},
            'roots': roots, 'receipts': retained, 'publicationArtifacts': prepared,
            'scope': 'Local Lean replay. Caller anchors identify history; source claims are not authenticated. Nothing has been published.'}


def page(index):
    rows = ''.join('<li>' + html.escape(item['object']) + ' · version ' +
                   html.escape(str(item['root']['version'])) + '</li>' for item in index['roots'])
    details = html.escape(canonical(index['history']).decode())
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Continue this world</title><style>body{max-width:48rem;margin:3rem auto;'
            'padding:0 1rem;font:18px/1.5 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
            '<h1>Continue this world</h1><p>Offline package · ' + str(len(index['roots'])) +
            ' objects · ' + str(index['history']['entries']) + ' retained admissions.</p>'
            '<ul>' + rows + '</ul><p><a href="index.json">Machine entry point and exact roots</a> · '
            '<a href="history/manifest.json">Replay history and source artifacts</a></p>'
            '<p>Replay with scripts/continuation.py verify and your known genesis and head. '
            'Use the history directory with history.py verify or bootstrap.py restore.</p>'
            '<details><summary>Identity and verification details</summary><pre>' + details +
            '</pre><p>' + html.escape(index['scope']) + '</p></details></html>')


def _replay(bundle, expected_genesis, expected_head, base_head=None):
    with tempfile.TemporaryDirectory(prefix='delvetalk-continuation-replay-') as temporary:
        database = Path(temporary) / 'world.json'
        raw = (Path(bundle) / 'manifest.json').read_bytes()
        evidence = history.verify_history(bundle, expected_genesis=expected_genesis,
                                          expected_head=expected_head, base_head=base_head, output=database)
        if raw != (Path(bundle) / 'manifest.json').read_bytes():
            raise ValueError('history changed during continuation replay')
        manifest = loads(raw)
        if manifest['inlineReprogram']:
            raise ValueError('continuation requires source custody; inline-only provenance refuses')
        if manifest['head'] != evidence['head'] or manifest['worldSha256'] != evidence['worldSha256']:
            raise ValueError('history changed during continuation replay')
        return manifest, loads(database.read_bytes()), evidence


def verify(destination, *, expected_genesis, expected_head, base_head=None):
    destination = Path(destination).resolve()
    index = loads((destination / 'index.json').read_bytes())
    manifest, state, evidence = _replay(destination / 'history', expected_genesis, expected_head, base_head)
    expected = index_for(manifest, state, anchored_receipts(manifest, destination / 'history'))
    if canonical(index) != canonical(expected):
        raise ValueError('continuation index omits or changes replayed roots, heads or artifacts')
    if (destination / 'index.html').read_text() != page(expected):
        raise ValueError('continuation human entry point differs')
    return {**evidence, 'status': 'verified-offline', 'objects': len(expected['roots']),
            'entryPoint': str(destination / 'index.html')}


def prepare(bundle, destination, *, expected_genesis, expected_head, base_head=None, receipts=()):
    """Copy an anchored history, replay, and publish a complete local directory atomically.

    A crash before rename leaves the destination absent. A crash after rename is
    reconciled by the same call. Existing changed packages never get replaced.
    """
    bundle, destination = Path(bundle).resolve(), Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Freeze caller-owned receipt objects before replay can yield to another writer.
    selected = loads(canonical(list(receipts)))
    with tempfile.TemporaryDirectory(prefix='.continuation-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        copied = staging / 'history'
        (copied / 'blobs').mkdir(parents=True)
        raw_manifest = (bundle / 'manifest.json').read_bytes()
        manifest = loads(raw_manifest)
        for sha in required_blobs(manifest, bundle):
            if history.store_file(copied, history.read_blob(bundle, sha)) != sha:
                raise ValueError('source artifact changed during continuation copy')
        (copied / 'manifest.json').write_bytes(raw_manifest)
        manifest, state, _ = _replay(copied, expected_genesis, expected_head, base_head)
        anchored = anchored_receipts(manifest, copied)
        for receipt in selected:
            if canonical(receipt) not in [canonical(item) for item in anchored]:
                raise ValueError('selected clerk receipt is not anchored in history source custody')
        index = index_for(manifest, state, anchored)
        bootstrap.save_new(staging / 'index.json', index)
        with (staging / 'index.html').open('x') as stream:
            stream.write(page(index))
            stream.flush()
            os.fsync(stream.fileno())
        # All history bytes are durable before the atomic local visibility step.
        with (copied / 'manifest.json').open('rb') as stream:
            os.fsync(stream.fileno())
        for directory in (copied / 'blobs', copied, staging):
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        try:
            bootstrap._publish_directory(staging, destination)
        except FileExistsError:
            verify(destination, expected_genesis=expected_genesis, expected_head=expected_head, base_head=base_head)
            if canonical(loads((destination / 'index.json').read_bytes())) != canonical(index):
                raise ValueError('existing continuation has different selected content')
    return {'status': 'prepared-offline', 'objects': len(index['roots']),
            'admissions': index['history']['entries'], 'entryPoint': str(destination / 'index.html'),
            'details': index['history']}


def prepare_bootstrap(directory, destination):
    """Join the existing source catalog and exact retained-prefix exporter."""
    with tempfile.TemporaryDirectory(prefix='delvetalk-continuation-export-') as temporary:
        bundle = Path(temporary) / 'history'
        evidence = bootstrap.export_bootstrap(directory, bundle)
        return prepare(bundle, destination, expected_genesis=evidence['genesis'], expected_head=evidence['head'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    boot = commands.add_parser('bootstrap', help='prepare from existing inhabited source custody')
    boot.add_argument('directory', type=Path)
    boot.add_argument('destination', type=Path)
    prep = commands.add_parser('prepare', help='prepare from an explicitly anchored history bundle')
    prep.add_argument('bundle', type=Path)
    prep.add_argument('destination', type=Path)
    prep.add_argument('--receipt', type=Path, action='append', default=[])
    check = commands.add_parser('verify', help='actually replay an offline continuation')
    check.add_argument('destination', type=Path)
    for command in (prep, check):
        command.add_argument('--genesis', required=True)
        command.add_argument('--head', required=True)
        command.add_argument('--base-head')
    args = parser.parse_args()
    try:
        if args.command == 'bootstrap':
            result = prepare_bootstrap(args.directory, args.destination)
        else:
            options = dict(expected_genesis=args.genesis, expected_head=args.head, base_head=args.base_head)
            result = (prepare(args.bundle, args.destination, receipts=[loads(path.read_bytes()) for path in args.receipt],
                              **options) if args.command == 'prepare' else verify(args.destination, **options))
        print(history.world.wire_dumps(result))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print('continuation: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
