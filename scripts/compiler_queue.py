#!/usr/bin/env python3
"""Restartable local source-desk compiler custody; no adoption authority."""
import argparse
import hashlib
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk
import worker

ROOT = Path(__file__).resolve().parents[1]
canonical, loads, digest = desk.canonical, desk.loads, desk.digest
save = worker.clerk.save


def compiler_pins(profile, expected):
    """Reviewed runtime plus the selected registered compiler dependency closure."""
    files = desk.execution_profile(profile)['files']
    registry = loads((ROOT / 'syntaxes/registry.json').read_bytes())
    adapter = registry['syntaxes'].get(expected['state']['proposal']['syntax'], {})
    validator = registry['targets'].get(adapter.get('target'), {})
    paths = {'scripts/compiler_queue.py', 'scripts/worker.py', 'scripts/clerk.py',
             'scripts/propose.py', 'scripts/translate.py', 'syntaxes/registry.json',
             *registry['closure'], *adapter.get('closure', []), *validator.get('closure', [])}
    if adapter.get('module') == 'syntaxes/spween.py':
        paths.add('scene/spween-bridge/target/debug/delvetalk-spween')
    if adapter.get('target') == 'spween-protocol-bundle-v1':
        paths.add('scene/room.py')
    for name in sorted(paths):
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('compiler dependency escapes repository')
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'profile': profile, 'python': list(sys.version_info[:3]), 'files': files}


def load_job(path):
    value = loads(Path(path).read_bytes())
    if value.get('format') != 'delvetalk-compiler-job-v1' or digest(value) != Path(path).stem:
        raise ValueError('compiler job identity mismatch')
    return value


def execute_job(path):
    """Only called in worker.command's bounded process group, including locks."""
    job = load_job(path)
    client = desk.Desk(job['database'], job['artifacts'], profile=job['profile'])
    inputs = job['inputs']
    compiled = Path(path).parent.parent / 'compiled' / (Path(path).stem + '.json')
    memo = client.artifact_store / 'attempts' / (digest([inputs['principal'], inputs['intent']]) + '.json')
    if memo.exists():
        attempt = loads(memo.read_bytes())
        if canonical(attempt['inputs']) != canonical(inputs):
            raise ValueError('compiler intent already bound to another candidate/root')
        request = attempt['request']
        if (set(request) != {'op', 'object', 'principal', 'intent', 'expected', 'command', 'input'}
                or request['op'] != 'invoke' or request['command'] not in ('compiled', 'failed')
                or any(canonical(request[key]) != canonical(value) for key, value in inputs.items())):
            raise ValueError('compiler attempt is not the exact queued completion request')
        retained = client.retained_reply(request)
        if retained is not None:
            return {'receipt': retained, 'artifact': attempt['request']['input']['artifact']}
        if (not compiled.exists() or loads(compiled.read_bytes())['artifact']
                != attempt['request']['input']['artifact']):
            raise ValueError('pending desk attempt lacks this queued compiler provenance')

    def check_pins():
        if canonical(compiler_pins(job['profile'], inputs['expected'])) != canonical(job['runtime']):
            raise ValueError('queued compiler runtime changed')

    check_pins()  # Requires the built host binary; never falls back to Lean builds.
    if canonical(client.inspect(inputs['object'])) != canonical(inputs['expected']):
        raise ValueError('queued candidate changed; retain this job and enqueue a fresh intent')

    def saved_build():
        artifact = desk.load_artifact(client.artifact_store, loads(compiled.read_bytes())['artifact'])
        if (artifact.get('format') != 'delvetalk-desk-build-v1'
                or artifact.get('candidateRootSha256') != digest(inputs['expected'])):
            raise ValueError('saved compiler artifact does not match queued candidate')
        return artifact

    if memo.exists():
        saved_build()

    def compile_in_group(root, *, profile):
        # Reuse the trusted compiler API without desk.bounded_compile's nested
        # session: all scenario descendants remain in worker.command's kill group.
        if compiled.exists():
            return saved_build()
        artifact = desk.compile_proposal({'root': root, 'profile': profile})
        check_pins()  # Refuse changed compiler bytes before publishing an admission.
        identity = desk.store_artifact(client.artifact_store, artifact)
        recorded = desk.immutable(compiled, {'artifact': identity})
        if recorded != {'artifact': identity}:
            raise ValueError('compiler build provenance mismatch')
        return artifact

    desk.bounded_compile = compile_in_group
    exchange = client.exchange

    def pinned_exchange(request):
        check_pins()
        return exchange(request)

    client.exchange = pinned_exchange
    receipt = client.check(inputs['object'], inputs['principal'], inputs['intent'], inputs['expected'])
    attempt = loads(memo.read_bytes())
    return {'receipt': receipt, 'artifact': attempt['request']['input']['artifact']}


class CompilerQueue:
    def __init__(self, state, database, artifacts, *, profile='transactions', memory_mib=2048):
        if profile not in desk.world.PROFILES:
            raise ValueError('unknown local host profile')
        if not 64 <= memory_mib <= 8192:
            raise ValueError('memory bound must be 64..8192 MiB')
        self.state, self.database, self.artifacts = (Path(p).expanduser().resolve() for p in (state, database, artifacts))
        self.profile, self.memory_mib = profile, memory_mib

    def bind(self):
        config = {'format': 'delvetalk-compiler-queue-v1', 'database': str(self.database),
                  'artifacts': str(self.artifacts), 'profile': self.profile}
        if desk.immutable(self.state / 'queue.json', config) != config:
            raise ValueError('compiler queue belongs to another world, artifact store or profile')

    def lock(self, deadline):
        return worker.bounded_lock(self.state / '.compiler.lock', deadline, time.monotonic)

    def job_path(self, identity):
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('invalid compiler job identity')
        return self.state / 'jobs' / (identity + '.json')

    def status_path(self, identity):
        self.job_path(identity)
        return self.state / 'status' / (identity + '.json')

    def status(self, identity):
        path = self.status_path(identity)
        return loads(path.read_bytes()) if path.exists() else {'phase': 'queued', 'attempts': 0, 'errors': []}

    def enqueue(self, object_id, principal, intent, expected, *, deadline_seconds=10):
        if not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 300:
            raise ValueError('deadline must be finite and in (0,300]')
        if any(not isinstance(x, str) or not x for x in (object_id, principal, intent)):
            raise ValueError('object, principal and intent must be nonempty strings')
        inputs = {'object': object_id, 'principal': principal, 'intent': intent, 'expected': expected}
        deadline = time.monotonic() + deadline_seconds
        with self.lock(deadline) as acquired:
            if not acquired:
                raise TimeoutError('compiler queue lock deadline reached')
            self.bind()
            # Scan immutable jobs so interruption cannot orphan an intent binding.
            paths = sorted((self.state / 'jobs').glob('*.json'))
            for path in paths:
                if time.monotonic() >= deadline:
                    raise TimeoutError('compiler enqueue deadline reached')
                job = load_job(path)
                prior = job['inputs']
                if (prior['principal'], prior['intent']) == (principal, intent):
                    if canonical(prior) != canonical(inputs):
                        raise ValueError('compiler intent already bound to another candidate/root')
                    return {'job': path.stem, 'status': 'already-queued', **self.status(path.stem)}
            if len(paths) >= 10000:
                raise ValueError('compiler queue retention bound reached (10000 jobs)')
            if expected['state']['status'] != 'pending':
                raise ValueError('compiler queue requires an exact pending source-desk root')
            runtime = compiler_pins(self.profile, expected)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('compiler enqueue deadline reached')
            observed = worker.command([str(ROOT / 'scripts/desk.py'), '--database', str(self.database),
                                       '--artifacts', str(self.artifacts), '--profile', self.profile,
                                       'inspect', '--object', object_id], remaining, self.memory_mib)
            if canonical(observed) != canonical(expected):
                raise ValueError('queued candidate changed')
            if canonical(compiler_pins(self.profile, expected)) != canonical(runtime):
                raise ValueError('compiler runtime changed during enqueue')
            job = {'format': 'delvetalk-compiler-job-v1', 'database': str(self.database),
                   'artifacts': str(self.artifacts), 'profile': self.profile, 'inputs': inputs, 'runtime': runtime}
            identity = digest(job)
            if canonical(desk.immutable(self.job_path(identity), job)) != canonical(job):
                raise ValueError('compiler job store mismatch')
            return {'job': identity, 'status': 'queued'}

    def inspect(self, identity):
        job = load_job(self.job_path(identity))
        return {'job': identity, 'candidate': job['inputs']['object'], **self.status(identity)}

    def retry(self, identity, *, deadline_seconds=10):
        if not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 300:
            raise ValueError('deadline must be finite and in (0,300]')
        with self.lock(time.monotonic() + deadline_seconds) as acquired:
            if not acquired:
                raise TimeoutError('compiler queue lock deadline reached')
            self.bind()
            load_job(self.job_path(identity))
            status = self.status(identity)
            status['attempts'] = 0
            save(self.status_path(identity), status)
            return {'job': identity, 'phase': status['phase'], 'status': 'retry-enabled'}

    def run(self, *, limit=10, deadline_seconds=60, max_attempts=3):
        if (not 1 <= limit <= 100 or not math.isfinite(deadline_seconds)
                or not 0 < deadline_seconds <= 300 or not 1 <= max_attempts <= 20):
            raise ValueError('bounds: limit 1..100, finite deadline (0,300], attempts 1..20')
        deadline = time.monotonic() + deadline_seconds
        report = {'format': 'delvetalk-compiler-run-v1', 'processed': [], 'errors': [], 'blocked': [],
                  'deadlineReached': False}
        with self.lock(deadline) as acquired:
            if not acquired:
                report.update(deadlineReached=True, lockTimedOut=True)
                return report
            self.bind()
            for path in sorted((self.state / 'jobs').glob('*.json')):
                if time.monotonic() >= deadline:
                    report['deadlineReached'] = True
                    break
                identity = path.stem
                status = self.status(identity)
                if status['phase'] == 'finished':
                    continue
                if len(report['processed']) >= limit:
                    break
                if status['attempts'] >= max_attempts:
                    report['blocked'].append({'job': identity, 'error': status['errors'][-1] if status['errors'] else 'interrupted attempt'})
                    continue
                status.update(phase='running', attempts=status['attempts'] + 1)
                save(self.status_path(identity), status)  # Durable before starting, safe to repeat after loss.
                try:
                    result = worker.command([str(Path(__file__).resolve()), '_check', str(path)],
                                            max(0.001, deadline - time.monotonic()), self.memory_mib)
                    if result['receipt'].get('kind') not in ('committed', 'refused'):
                        raise ValueError('invalid compiler admission receipt')
                    status.update(phase='finished', **result)
                except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    message = str(error)[:2000]
                    status['errors'] = (status['errors'] + [message])[-20:]
                    status['phase'] = 'queued'
                    report['errors'].append({'job': identity, 'error': message})
                save(self.status_path(identity), status)
                report['processed'].append({'job': identity, 'phase': status['phase']})
        report['deadlineReached'] |= time.monotonic() >= deadline
        return report


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '_check':
        print(desk.world.wire_dumps(execute_job(sys.argv[2])))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--profile', choices=desk.world.PROFILES, default='transactions')
    parser.add_argument('--memory-mib', type=int, default=2048)
    commands = parser.add_subparsers(dest='op', required=True)
    enqueue = commands.add_parser('enqueue')
    for flag in ('object', 'principal', 'intent'):
        enqueue.add_argument('--' + flag, required=True)
    enqueue.add_argument('--expected-root', type=Path, required=True)
    for name in ('inspect', 'retry'):
        commands.add_parser(name).add_argument('job')
    run = commands.add_parser('run')
    run.add_argument('--limit', type=int, default=10)
    run.add_argument('--deadline-seconds', type=float, default=60)
    run.add_argument('--max-attempts', type=int, default=3)
    parser.add_argument('--json', action='store_true', help='complete machine-readable custody result')
    args = parser.parse_args()
    try:
        queue = CompilerQueue(args.state, args.database, args.artifacts, profile=args.profile, memory_mib=args.memory_mib)
        if args.op == 'enqueue':
            result = queue.enqueue(args.object, args.principal, args.intent, loads(args.expected_root.read_bytes()))
        elif args.op == 'run':
            result = queue.run(limit=args.limit, deadline_seconds=args.deadline_seconds, max_attempts=args.max_attempts)
        else:
            result = getattr(queue, args.op)(args.job)
        if args.json:
            print(desk.world.wire_dumps(result))
        elif args.op == 'run':
            print(f"Compiler queue: {len(result['processed'])} processed, {len(result['errors'])} errors, {len(result['blocked'])} blocked.")
        else:
            print(f"Compiler job {result['job'][:12]}: {result.get('status', result.get('phase'))}.")
        return 1 if result.get('errors') or result.get('blocked') or result.get('deadlineReached') else 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print('compiler queue: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
