#!/usr/bin/env python3
"""One bounded operator tick: receive, compile, reconcile, prepare offline continuation."""
import argparse
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
import clerk
import compiler_queue
import continuation
import desk
import history
import message_relay
import source_store
import worker

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'delvetalk-service-v1'
canonical, loads, digest, save = clerk.canonical, clerk.loads, clerk.digest, clerk.save


def epoch(profile, clerk_profile):
    """A deliberate source/binary epoch; an upgrade requires explicit new custody."""
    files = dict(clerk_profile['pins'])
    registry = loads((ROOT / 'syntaxes/registry.json').read_bytes())
    for syntax in registry['syntaxes']:
        files.update(compiler_queue.compiler_pins(profile,
            {'state': {'proposal': {'syntax': syntax}}})['files'])
    for name in ('service', 'bootstrap', 'history', 'continuation', 'watch', 'desk', 'source_store', 'message_relay'):
        path = 'scripts/' + name + '.py'
        files[path] = history.file_hash(ROOT / path)
    for path in (*desk.SOURCE_CANDIDATE_FILES, 'scene/room.py'):
        files[path] = history.file_hash(ROOT / path)
    return {'profile': profile, 'python': list(sys.version_info[:3]),
            'platform': [platform.system(), platform.machine()], 'files': files}


def same(left, right, message):
    if canonical(left) != canonical(right):
        raise ValueError(message)


def checkpoint(config, plan_path):
    """Called inside one bounded process group; replays never admit into the live world."""
    plan_path = Path(plan_path)
    plan = loads(plan_path.read_bytes())
    directory = plan_path.parent
    snapshot = loads((directory / 'world.json').read_bytes())
    if digest(snapshot) != plan['worldSha256']:
        raise ValueError('checkpoint snapshot changed')
    attachments = {}
    retained = {digest(item['request']): item for item in snapshot['receipts']}
    for path in sorted((directory / 'journals').glob('*.json')):
        entry = loads(path.read_bytes())
        sha = digest(entry['request'])
        if sha not in retained:
            raise ValueError('checkpoint journal is outside captured admissions')
        attachments.setdefault(sha, []).append(path)
    previous = plan.get('previous')
    bundle = directory / 'history'
    if not bundle.exists():
        with tempfile.TemporaryDirectory(prefix='.service-export-', dir=directory) as temporary:
            staging = Path(temporary) / 'history'
            evidence = bootstrap.export_bootstrap(directory, staging, extra_attachments=attachments)
            if evidence['worldSha256'] != plan['worldSha256'] or evidence['genesis'] != config['publicGenesis']:
                raise ValueError('checkpoint export differs from selected public world/genesis')
            bootstrap._publish_directory(staging, bundle)
    manifest = loads((bundle / 'manifest.json').read_bytes())
    evidence = {'genesis': manifest['genesis']['id'], 'head': manifest['head'],
                'worldSha256': manifest['worldSha256'], 'entries': len(manifest['entries'])}
    if evidence['worldSha256'] != plan['worldSha256'] or evidence['genesis'] != config['publicGenesis']:
        raise ValueError('checkpoint history differs from selected public world/genesis')
    result = continuation.prepare(bundle, plan['destination'],
        expected_genesis=evidence['genesis'], expected_head=evidence['head'],
        base_head=previous['head'] if previous else config['seed']['head'])
    return {**evidence, 'destination': plan['destination'], 'entryPoint': result['entryPoint'],
            'status': 'prepared-offline', 'publication': 'paused'}


class Service:
    def __init__(self, state, *, receiver=None):
        self.state = Path(state).expanduser().resolve()
        self.receiver = receiver  # Tests only; production Worker owns bounded receiver subprocesses.

    def initialize(self, world_directory, clerk_state, compiler_principal, *, public_genesis, watch_state=None,
                   relay_principal=None):
        if not isinstance(compiler_principal, str) or not compiler_principal or len(compiler_principal) > 256:
            raise ValueError('explicit compiler principal required')
        directory = Path(world_directory).expanduser().resolve()
        receiver = clerk.Clerk(clerk_state)
        same(str(receiver.database.resolve()), str((directory / 'world.json').resolve()),
             'clerk and selected public world must share exact database custody')
        metadata = loads((directory / 'manifest.json').read_bytes())
        if metadata.get('format') != 'delvetalk-workspace-v1':
            raise ValueError('service requires an explicitly initialized public workspace')
        same(metadata['genesis']['id'], public_genesis, 'selected public genesis differs from workspace')
        seed = loads((directory / 'seed.json').read_bytes())
        same(seed['genesis'], public_genesis, 'public seed genesis differs')
        same(seed['worldId'], metadata['worldId'], 'public seed world identity differs')
        seed_manifest = loads((directory / 'seed-history/manifest.json').read_bytes())
        same(seed_manifest['head'], seed['head'], 'public seed head differs')
        config = receiver.config()
        selected = config.get('runtimeProfile', 'world')
        same(config['profile']['pins'], clerk.pins(selected), 'clerk runtime pins changed')
        profile = 'compiled' if selected == 'compiled' else 'transactions'
        same(metadata['runtime'], history.runtime(profile), 'workspace runtime differs from clerk/service profile')
        origin_path = self.state / 'origin.json'
        snapshot = clerk.world.snapshot(receiver.database, timeout=10)
        if relay_principal is not None:
            registry = clerk.world.query(receiver.database, {'op': 'messages-pending', 'principal': 'service-reader'},
                                         profile=profile, timeout=10)
            message_relay.MessageRelay(self.state / 'messages', receiver.database, relay_principal, profile=profile).bind(registry)
        origin = desk.immutable(origin_path, snapshot) if not origin_path.exists() else loads(origin_path.read_bytes())
        same(snapshot['receipts'][:len(origin['receipts'])], origin['receipts'], 'world no longer extends selected public prefix')
        value = {'format': FORMAT, 'clerkState': str(receiver.state),
                 'worldDirectory': str(directory), 'publicGenesis': public_genesis,
                 'originSha256': digest(origin), 'manifest': metadata, 'seed': seed,
                 'database': str(receiver.database.resolve()),
                 'artifacts': str(directory / 'artifacts'),
                 'compilerPrincipal': compiler_principal, 'profile': profile,
                 'relayPrincipal': relay_principal,
                 'clerkProfile': config['profile'],
                 'watchState': str(Path(watch_state).expanduser().resolve()) if watch_state else None,
                 'publication': 'paused', 'epoch': epoch(profile, config['profile'])}
        value['epochId'] = digest(value['epoch'])
        stored = desk.immutable(self.state / 'service.json', value)
        same(stored, value, 'service configuration or runtime epoch changed; preserve existing custody')
        return {'format': FORMAT, 'epoch': value['epochId'], 'publication': 'paused', 'status': 'configured'}

    def config(self):
        value = loads((self.state / 'service.json').read_bytes())
        if (value.get('format') != FORMAT or value.get('publication') != 'paused'
                or value.get('epochId') != digest(value['epoch'])):
            raise ValueError('unsupported service configuration')
        return value

    def check_epoch(self, config):
        metadata = loads((Path(config['worldDirectory']) / 'manifest.json').read_bytes())
        same(metadata, config['manifest'], 'selected public workspace manifest changed')
        receiver = clerk.Clerk(config['clerkState'])
        same(str(receiver.database.resolve()), config['database'], 'selected clerk database custody changed')
        current = receiver.config()
        same(current['profile'], config['clerkProfile'], 'clerk epoch changed')
        selected = current.get('runtimeProfile', 'world')
        same(current['profile']['pins'], clerk.pins(selected), 'clerk runtime pins changed')
        same(epoch(config['profile'], current['profile']), config['epoch'], 'service runtime epoch changed')

    def receiving(self, config, memory_mib):
        return worker.Worker(self.state / 'receiving', config['clerkState'],
                             receiver=self.receiver, memory_mib=memory_mib)

    def compiler(self, config, memory_mib):
        return compiler_queue.CompilerQueue(self.state / 'compiler', config['database'],
            config['artifacts'], profile=config['profile'], memory_mib=memory_mib)

    def enqueue(self, uri, cid, *, deadline_seconds=10, memory_mib=2048):
        if not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 300:
            raise ValueError('enqueue deadline must be finite and in (0,300]')
        config = self.config()
        self.check_epoch(config)
        return worker.command([str(ROOT / 'scripts/worker.py'), '--state', str(self.state / 'receiving'),
            '--clerk-state', config['clerkState'], 'enqueue', uri, '--cid', cid], deadline_seconds, memory_mib)

    def _snapshot(self, config, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('world custody deadline reached')
        snapshot = clerk.world.snapshot(config['database'], timeout=remaining)
        origin = loads((self.state / 'origin.json').read_bytes())
        same(digest(origin), config['originSha256'], 'selected public prefix changed')
        same(snapshot['receipts'][:len(origin['receipts'])], origin['receipts'], 'world no longer extends selected public prefix')
        return snapshot

    def _plan(self, config, progress, deadline):
        # Clerk lock prevents an authenticated admission from being captured
        # without its completed source journal. Direct local writers remain
        # represented by the exact world snapshot they committed.
        with worker.bounded_lock(Path(config['clerkState']) / 'clerk.lock', deadline, time.monotonic) as acquired:
            if not acquired:
                raise TimeoutError('clerk custody deadline reached')
            snapshot = self._snapshot(config, deadline)
            sha = digest(snapshot)
            if progress.get('continuation', {}).get('worldSha256') == sha:
                return None
            directory = self.state / 'checkpoints' / sha
            previous = progress.get('continuation')
            plan = {'format': 'delvetalk-service-checkpoint-v1', 'worldSha256': sha,
                    'epoch': config['epochId'], 'previous': previous,
                    'destination': str(self.state / 'continuations' / sha)}
            def bounded():
                if time.monotonic() >= deadline:
                    raise TimeoutError('checkpoint capture deadline reached')
            retained_requests = {digest(item['request']): canonical(item['request']) for item in snapshot['receipts']}
            # Capture matching journals under their stable content digests.
            for item in snapshot['receipts']:
                bounded()
                request = item['request']
                if not request.get('intent', '').startswith('delve:'):
                    continue
                uri = request['intent'][len('delve:'):]
                path = Path(config['clerkState']) / 'requests' / (worker.key(uri) + '.json')
                entry = loads(path.read_bytes())
                same(entry['request'], request, 'clerk journal request differs from checkpoint')
                if 'receipt' not in entry:
                    raise ValueError('pending clerk receipt must reconcile before checkpoint')
                same(entry['receipt']['reply'], item['receipt'], 'clerk receipt differs from checkpoint')
                desk.immutable(directory / 'journals' / (digest(entry) + '.json'), entry)
            # Retain management source translations and compiler attempts too.
            for location in (Path(config['clerkState']) / 'requests', Path(config['artifacts']) / 'attempts'):
                for path in sorted(location.glob('*.json')):
                    bounded()
                    entry = loads(path.read_bytes())
                    request = entry.get('request')
                    if retained_requests.get(digest(request)) == canonical(request):
                        desk.immutable(directory / 'journals' / (digest(entry) + '.json'), entry)
            same(desk.immutable(directory / 'manifest.json', config['manifest']), config['manifest'], 'checkpoint manifest differs')
            frozen_artifacts = directory / 'artifacts'
            frozen_artifacts.mkdir(exist_ok=True)
            for family in ('rooms', 'builds', 'lowerings', 'pins'):
                source = Path(config['artifacts']) / family
                target = frozen_artifacts / family
                if source.exists() and not target.exists():
                    target.symlink_to(source, target_is_directory=True)
            for reference in source_store.collect_references(snapshot):
                bounded()
                raw = source_store.read_bytes(config['artifacts'], reference, kind='scenarios')
                same(source_store.store_bytes(frozen_artifacts, raw, kind='scenarios'), reference,
                     'captured source blob differs')
            prefix_head = previous['head'] if previous else config['seed']['head']
            prefix_source = Path(previous['destination']) / 'history' if previous else Path(config['worldDirectory']) / 'seed-history'
            prefix_path = frozen_artifacts / 'history' / prefix_head
            prefix_path.parent.mkdir(exist_ok=True)
            if not prefix_path.exists():
                prefix_path.symlink_to(prefix_source, target_is_directory=True)
            same(desk.immutable(directory / 'world.json', snapshot), snapshot, 'checkpoint world differs')
            same(desk.immutable(directory / 'plan.json', plan), plan, 'checkpoint plan differs')
        return str(directory / 'plan.json')

    def tick(self, *, limit=10, deadline_seconds=60, max_attempts=3, memory_mib=2048):
        if (type(limit) is not int or not 1 <= limit <= 100 or not math.isfinite(deadline_seconds)
                or not 0 < deadline_seconds <= 300 or type(max_attempts) is not int or not 1 <= max_attempts <= 20
                or type(memory_mib) is not int or not 64 <= memory_mib <= 8192):
            raise ValueError('invalid service bounds')
        deadline = time.monotonic() + deadline_seconds
        report = {'format': 'delvetalk-service-tick-v1', 'publication': 'paused', 'status': 'running',
                  'phases': {}, 'errors': [], 'deadlineReached': False}
        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise TimeoutError('service tick deadline reached')
            return value
        with worker.bounded_lock(self.state / 'service.lock', deadline, time.monotonic) as acquired:
            if not acquired:
                return {**report, 'status': 'deadline', 'deadlineReached': True, 'lockTimedOut': True}
            config = self.config()
            report['epoch'] = config['epochId']
            progress_path = self.state / 'progress.json'
            progress = loads(progress_path.read_bytes()) if progress_path.exists() else {}
            def phase(name, operation):
                remaining()
                report['phase'] = name
                save(self.state / 'status.json', report)
                result = operation()
                report['phases'][name] = result
                save(self.state / 'status.json', report)
                return result
            def finish_checkpoint():
                plan = progress['checkpoint']
                result = phase('continuation', lambda: worker.command(
                    [str(Path(__file__).resolve()), '_checkpoint', str(self.state), plan], remaining(), memory_mib))
                progress['continuation'] = result
                progress.pop('checkpoint')
                save(progress_path, progress)
            try:
                self.check_epoch(config)
                if progress.get('checkpoint'):
                    finish_checkpoint()
                if config['watchState']:
                    phase('discover', lambda: worker.command([str(ROOT / 'scripts/worker.py'),
                        '--state', str(self.state / 'receiving'), '--clerk-state', config['clerkState'],
                        'discover', '--watch-state', config['watchState'], '--limit', str(limit)], remaining(), memory_mib))
                receiving = self.receiving(config, memory_mib)
                phase('receive', lambda: receiving.run(limit=limit, deadline_seconds=remaining(),
                                                       max_attempts=max_attempts, allow_publication=False))
                self.check_epoch(config)
                if config.get('relayPrincipal'):
                    relay = message_relay.MessageRelay(self.state / 'messages', config['database'],
                        config['relayPrincipal'], profile=config['profile'], memory_mib=memory_mib)
                    phase('localMessages', lambda: relay.run(limit=min(limit, 16),
                        deadline_seconds=remaining(), max_attempts=max_attempts))
                queue = self.compiler(config, memory_mib)
                def enqueue_compilers():
                    snapshot = self._snapshot(config, deadline)
                    jobs, errors, examined = [], [], 0
                    candidates = [(name, root) for name, root in sorted(snapshot['objects'].items())
                                  if desk.is_source_desk_protocol(root['protocol'])
                                  and desk.candidate_state(root).get('status') == 'pending']
                    cursor = progress.get('compilerCursor', '')
                    candidates = [item for item in candidates if item[0] > cursor] + [item for item in candidates if item[0] <= cursor]
                    for name, root in candidates:
                        remaining()
                        if examined >= limit:
                            break
                        examined += 1
                        progress['compilerCursor'] = name
                        save(progress_path, progress)
                        intent = 'service-compile:' + digest([config['epochId'], name, root])
                        try:
                            jobs.append(queue.enqueue(name, config['compilerPrincipal'], intent, root,
                                                      deadline_seconds=remaining()))
                        except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                            errors.append({'object': name, 'root': digest(root), 'error': str(error)[:2000]})
                    return {'jobs': jobs, 'errors': errors, 'examined': examined, 'pendingCandidates': len(candidates)}
                phase('enqueueCompilers', enqueue_compilers)
                phase('compile', lambda: queue.run(limit=limit, deadline_seconds=remaining(), max_attempts=max_attempts))
                def reconcile():
                    identities = {item['job'] for item in report['phases']['enqueueCompilers']['jobs']}
                    identities.update(item['job'] for item in report['phases']['compile']['processed'])
                    results = []
                    for identity in sorted(identities):
                        remaining()
                        status = queue.inspect(identity)
                        receipt = status.get('receipt', {})
                        data = receipt.get('data')
                        results.append({'job': identity, 'phase': status['phase'], 'kind': receipt.get('kind'),
                            'candidateStatus': data.get('root', {}).get('state', {}).get('status') if isinstance(data, dict) else None,
                            'detail': data if isinstance(data, str) else None})
                    return {'compiler': results,
                            'refused': [item['job'] for item in results if item['kind'] == 'refused']}
                phase('reconcile', reconcile)
                self.check_epoch(config)
                # Worker and compiler returned only after reconciling their own
                # stable attempt identities. Preserve a frozen continuation plan.
                plan = phase('capture', lambda: self._plan(config, progress, deadline))
                if plan:
                    progress['checkpoint'] = plan
                    save(progress_path, progress)
                    finish_checkpoint()
                report['continuation'] = progress.get('continuation')
                failures = [name for name, result in report['phases'].items() if isinstance(result, dict)
                            and (result.get('errors') or result.get('blocked') or result.get('refused'))]
                report['status'] = 'needs-attention' if failures else 'prepared-offline'
                report['attentionPhases'] = failures
                report['deadlineReached'] = any(isinstance(result, dict) and result.get('deadlineReached')
                                                 for result in report['phases'].values())
            except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as error:
                report['errors'].append({'phase': report.get('phase', 'epoch'), 'error': str(error)[:2000]})
                report['deadlineReached'] = isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) or time.monotonic() >= deadline
                report['status'] = 'deadline' if report['deadlineReached'] else 'blocked'
                report['continuation'] = progress.get('continuation')
            save(self.state / 'status.json', report)
            return report

    def status(self):
        path = self.state / 'status.json'
        if path.exists():
            result = loads(path.read_bytes())
            if result.get('status') == 'running':
                result['status'] = 'unfinished'
                result['summary'] = 'Last tick has no terminal report; its saved phase can be resumed.'
            return result
        return {'format': FORMAT, 'status': 'configured', 'epoch': self.config()['epochId'], 'publication': 'paused'}


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '_checkpoint':
        app = Service(sys.argv[2])
        config = app.config()
        app.check_epoch(config)
        print(canonical(checkpoint(config, sys.argv[3])).decode())
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--clerk-state', type=Path, required=True)
    init.add_argument('--world', type=Path, required=True)
    init.add_argument('--genesis', required=True)
    init.add_argument('--compiler-principal', required=True)
    init.add_argument('--watch-state', type=Path)
    init.add_argument('--relay-principal', help='explicit local message delivery principal; requires initialized native messages')
    enqueue = commands.add_parser('enqueue')
    enqueue.add_argument('uri')
    enqueue.add_argument('--cid', required=True)
    tick = commands.add_parser('tick')
    tick.add_argument('--limit', type=int, default=10)
    tick.add_argument('--deadline-seconds', type=float, default=60)
    tick.add_argument('--max-attempts', type=int, default=3)
    tick.add_argument('--memory-mib', type=int, default=2048)
    commands.add_parser('status')
    args = parser.parse_args()
    try:
        app = Service(args.state)
        if args.command == 'init':
            result = app.initialize(args.world, args.clerk_state, args.compiler_principal,
                public_genesis=args.genesis, watch_state=args.watch_state, relay_principal=args.relay_principal)
        elif args.command == 'enqueue':
            result = app.enqueue(args.uri, args.cid)
        elif args.command == 'tick':
            result = app.tick(limit=args.limit, deadline_seconds=args.deadline_seconds,
                              max_attempts=args.max_attempts, memory_mib=args.memory_mib)
        else:
            result = app.status()
        print(canonical(result).decode())
        return 1 if result.get('status') in ('blocked', 'deadline', 'needs-attention') else 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print('service: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
