#!/usr/bin/env python3
"""Independent source-bound worlds from explicit seeds and an exact empty genesis."""
import argparse
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap

FORMAT = 'delvetalk-workspace-v1'
loads, canonical = bootstrap.loads, bootstrap.canonical


def initialize(directory, objects, *, entry_objects, principal, profile='transactions',
               title='A shared world', default_object=None, world_id=None,
               backend='file', messaging=False, pending_limit=128):
    """Admit explicit creation requests in private staging, then publish custody once."""
    if backend not in ('file', 'resident'):
        raise ValueError('unknown workspace backend')
    if type(messaging) is not bool or (messaging and profile != 'compiled'):
        raise ValueError('messaging requires the compiled profile and an explicit boolean')
    destination = Path(directory).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('workspace destination already exists; choose a fresh path')
    if not isinstance(title, str) or not title or not isinstance(principal, str) or not principal:
        raise ValueError('title and creation principal must be nonempty strings')
    if not isinstance(objects, list) or not objects:
        raise ValueError('supply at least one explicit seed object')
    ids = []
    for seed in objects:
        if not isinstance(seed, dict) or set(seed) != {'id', 'syntax', 'source', 'law'}:
            raise ValueError('seed object requires exactly id, syntax, source bytes and law')
        if not isinstance(seed['id'], str) or not seed['id'] or not isinstance(seed['source'], bytes):
            raise ValueError('seed id must be nonempty and source must be exact bytes')
        ids.append(seed['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('seed object IDs must be distinct')
    if not isinstance(entry_objects, list) or not entry_objects:
        raise ValueError('choose explicit entry objects')
    selected_default = entry_objects[0] if default_object is None else default_object
    namespace = 'urn:uuid:' + str(uuid.uuid4()) if world_id is None else world_id
    if not isinstance(namespace, str) or not namespace or len(namespace) > 256:
        raise ValueError('world identity must be an explicit nonempty string of at most 256 characters')
    metadata = {'format': FORMAT, 'worldId': namespace, 'title': title, 'entryObjects': entry_objects,
                'defaultObject': selected_default, 'seedObjects': ids, 'runtime': bootstrap.history.runtime(profile)}
    if messaging:
        metadata['messaging'] = {'lineage': namespace, 'pendingLimit': pending_limit}
    bootstrap.entry_objects(metadata)
    if any(identity not in ids for identity in entry_objects):
        raise ValueError('entry objects must be among the explicit seeds')
    genesis = {'profile': metadata['runtime'], 'world': {'objects': {}, 'receipts': []}}
    genesis['id'] = bootstrap.history.digest(genesis)
    metadata['genesis'] = genesis
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.workspace-init-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        world = bootstrap.desk_module.world
        if backend == 'resident':
            world.configure_resident(staging / 'world.json', profile=profile)
        session = (world.resident_session(staging / 'world.json', profile=profile)
                   if backend == 'resident' else nullcontext())
        with session:
            desk = bootstrap.desk_module.Desk(staging / 'world.json', staging / 'artifacts', profile=profile)
            if messaging:
                receipt = desk.exchange({'op': 'messages-init', 'principal': principal,
                    'intent': f'workspace-messages:{namespace}', **metadata['messaging']})
                if receipt['kind'] != 'committed':
                    raise ValueError('message bootstrap refused by Lean: ' + str(receipt['data']))
            for index, seed in enumerate(objects):
                artifact = bootstrap.desk_module.translate.translate(seed['syntax'], seed['source'])
                if artifact['target'] == 'local-protocol-v1':
                    protocol = artifact['lowered']
                elif artifact['target'] == 'spween-protocol-bundle-v1':
                    wrapped = bootstrap.room.wrap_bundle(artifact['lowered'])
                    bootstrap.room.store_artifact(staging / 'artifacts/rooms', wrapped)
                    bootstrap.preserve_dependencies(staging, wrapped)
                    protocol = wrapped['protocol']
                else:
                    raise ValueError('seed syntax must lower to an executable local protocol or Spween bundle')
                identity = bootstrap.history.digest(artifact)
                bootstrap.desk_module.immutable(staging / 'artifacts/lowerings' / (identity + '.json'), artifact)
                bootstrap.preserve_dependencies(staging, artifact)
                receipt = desk.exchange({'op': 'create', 'object': seed['id'], 'principal': principal,
                    'intent': f'workspace-seed:{namespace}:{index}', 'protocol': protocol, 'law': seed['law']})
                if receipt['kind'] != 'committed':
                    raise ValueError('seed refused by Lean: ' + seed['id'] + ': ' + str(receipt['data']))
            if canonical(bootstrap.history.runtime(profile)) != canonical(metadata['runtime']):
                raise ValueError('runtime changed during workspace initialization')
            bootstrap.save_new(staging / 'manifest.json', metadata)
            bootstrap.save_new(staging / 'genesis.json', genesis)
            for index, identity in enumerate(entry_objects):
                view = bootstrap.inspect_view(staging, identity)
                filename = 'index.html' if identity == selected_default else f'entry-{index}.html'
                with (staging / filename).open('x') as stream:
                    stream.write(bootstrap.room.html_view(view))
            # A populated seed history is distinct from its shared empty runtime genesis.
            anchors = bootstrap.export_bootstrap(staging, staging / 'seed-history')
            if anchors['genesis'] != genesis['id']:
                raise ValueError('seed history differs from declared public genesis')
            seed = {'format': 'delvetalk-workspace-seed-v1',
                    **{key: anchors[key] for key in ('genesis', 'head', 'entries', 'worldSha256')},
                    'worldId': namespace, 'entryObjects': entry_objects, 'defaultObject': selected_default,
                    'scope': 'Explicit seed admissions only; no demonstration or private history was copied.'}
            bootstrap.save_new(staging / 'seed.json', seed)
        bootstrap._publish_directory(staging, destination)
    return {**seed, 'directory': str(destination), 'view': str(destination / 'index.html')}


def initialize_plan(directory, plan, *, base, principal, profile='transactions', world_id=None,
                    backend='file', messaging=False, pending_limit=128):
    if not isinstance(plan, dict) or set(plan) != {'title', 'entryObjects', 'defaultObject', 'objects'}:
        raise ValueError('plan requires exactly title, entryObjects, defaultObject and objects')
    if not isinstance(plan['objects'], list):
        raise ValueError('plan objects must be an array')
    seeds = []
    for item in plan['objects']:
        if not isinstance(item, dict) or set(item) != {'id', 'syntax', 'source', 'law'}:
            raise ValueError('plan object requires id, syntax, source path and law')
        if not isinstance(item['source'], str):
            raise ValueError('plan source must be an explicit file path')
        seeds.append({**item, 'source': (Path(base) / item['source']).read_bytes()})
    return initialize(directory, seeds, entry_objects=plan['entryObjects'],
                      default_object=plan['defaultObject'], title=plan['title'],
                      principal=principal, profile=profile, world_id=world_id,
                      backend=backend, messaging=messaging, pending_limit=pending_limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('directory', type=Path)
    init.add_argument('--plan', required=True, type=Path)
    init.add_argument('--principal', required=True)
    init.add_argument('--world-id', help='optional explicit immutable namespace; otherwise a fresh urn:uuid')
    init.add_argument('--profile', choices=bootstrap.desk_module.world.PROFILES, default='transactions')
    init.add_argument('--backend', choices=('file', 'resident'), default='file')
    init.add_argument('--messaging', action='store_true', help='initialize native message lineage before seeds (compiled only)')
    init.add_argument('--pending-limit', type=int, default=128)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('directory', type=Path)
    inspect.add_argument('--object')
    inspect.add_argument('--panel', default='main')
    inspect.add_argument('--html', action='store_true')
    export = commands.add_parser('export')
    export.add_argument('directory', type=Path)
    export.add_argument('bundle', type=Path)
    verify = commands.add_parser('verify')
    restore = commands.add_parser('restore')
    for command in (verify, restore):
        command.add_argument('bundle', type=Path)
        command.add_argument('--genesis', required=True)
        command.add_argument('--head', required=True)
        command.add_argument('--base-head')
    restore.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'init':
            result = initialize_plan(args.directory, loads(args.plan.read_bytes()), base=args.plan.parent,
                                     principal=args.principal, profile=args.profile, world_id=args.world_id,
                                     backend=args.backend, messaging=args.messaging, pending_limit=args.pending_limit)
        elif args.command == 'inspect':
            result = bootstrap.inspect_view(args.directory, args.object, args.panel)
            if args.html:
                print(bootstrap.room.html_view(result))
                return 0
        elif args.command == 'export':
            result = bootstrap.export_bootstrap(args.directory, args.bundle)
        else:
            options = dict(expected_genesis=args.genesis, expected_head=args.head, base_head=args.base_head)
            result = (bootstrap.verify_bootstrap(args.bundle, **options) if args.command == 'verify' else
                      bootstrap.restore_bootstrap(args.bundle, args.directory, **options))
        sys.stdout.buffer.write(canonical(result) + b'\n')
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        print('workspace: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
