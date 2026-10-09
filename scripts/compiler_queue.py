#!/usr/bin/env python3
"""Restartable local source-desk compiler custody; no adoption authority."""
import argparse
import math
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk
import worker
import process_custody

ROOT = Path(__file__).resolve().parents[1]
canonical, loads, digest = desk.canonical, desk.loads, desk.digest
save = worker.clerk.save


def syntax_pins(profile, syntax):
    """Physical runtime identity for one explicitly registered syntax."""
    proposal = desk.module('queue_proposal', 'scripts/propose.py')
    registry = loads((ROOT / 'syntaxes/registry.json').read_bytes())
    adapter = registry['syntaxes'].get(syntax, {})
    validator = registry['targets'].get(adapter.get('target'), {})
    paths = {'scripts/compiler_queue.py', 'scripts/worker.py', 'scripts/clerk.py',
             'scripts/translate.py', 'syntaxes/registry.json',
             *desk.execution_paths(profile), *proposal.execution_paths(profile),
             *desk.translate.closure_paths(registry, adapter, validator)}
    if adapter.get('module') == 'syntaxes/spween.py':
        paths.add('scene/spween-bridge/target/debug/delvetalk-spween')
    if adapter.get('target') == 'spween-protocol-bundle-v1':
        paths.add('scene/room.py')
    files = desk.runtime_profile.hash_paths(paths, root=ROOT)
    return {'profile': profile, 'python': list(sys.version_info[:3]), 'files': files}


def compiler_pins(profile, expected, work):
    """Pins for already captured work; root identity is bound by its job."""
    return syntax_pins(profile, work['proposal']['syntax'])


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
    attempt = client.check_attempt(inputs)
    if attempt is not None:
        retained = client.retained_reply(attempt['request'])
        if retained is not None:
            return {'receipt': retained, 'artifact': attempt['request']['input']['artifact']}
        if (not compiled.exists() or loads(compiled.read_bytes())['artifact']
                != attempt['request']['input']['artifact']):
            raise ValueError('pending desk attempt lacks this queued compiler provenance')

    def check_pins():
        if canonical(compiler_pins(job['profile'], inputs['expected'], job['work'])) != canonical(job['runtime']):
            raise ValueError('queued compiler runtime changed')

    check_pins()  # Requires the built host binary; never falls back to Lean builds.
    material = desk.proposal_material(job['work']['proposal'], client.artifact_store)[2]
    if 'sourceBindings' in job and canonical(material) != canonical(job['sourceBindings']):
        raise ValueError('queued source bindings changed')
    if canonical(client.inspect(inputs['object'], principal=inputs['principal'])) != canonical(inputs['expected']):
        raise ValueError('queued candidate changed; retain this job and enqueue a fresh intent')

    profile = desk.execution_profile(job['profile'])
    if compiled.exists():
        artifact = desk.load_artifact(client.artifact_store, loads(compiled.read_bytes())['artifact'])
        if (artifact.get('format') != 'delvetalk-desk-build-v1'
                or artifact.get('candidateRootSha256') != digest(inputs['expected'])
                or canonical(artifact.get('compilerWork')) != canonical(job['work'])):
            raise ValueError('saved compiler artifact does not match queued candidate')
        if 'sourceBindings' in job and canonical(artifact.get('sourceBindings')) != canonical(job['sourceBindings']):
            raise ValueError('saved compiler artifact does not match queued source bindings')
    else:
        # Already inside worker.command's kill group; no nested compiler session.
        artifact = desk.compile_proposal({'root': inputs['expected'], 'work': job['work'], 'profile': job['profile'],
                                         'artifactStore': str(client.artifact_store)})
        check_pins()
        identity = desk.store_artifact(client.artifact_store, artifact)
        if desk.immutable(compiled, {'artifact': identity}) != {'artifact': identity}:
            raise ValueError('compiler build provenance mismatch')
    if attempt is None:
        attempt = client.prepare_check(inputs, artifact, profile)
    receipt = client.admit_check(attempt, before_exchange=check_pins)
    return {'receipt': receipt, 'artifact': attempt['request']['input']['artifact']}


class CompilerQueue:
    def __init__(self, state, database, artifacts, *, profile='compiled', memory_mib=process_custody.NATIVE_MEMORY_MIB):
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

    def enqueue(self, object_id, principal, intent, expected, *, work=None, deadline_seconds=10):
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
                    if work is not None and canonical(work) != canonical(job['work']):
                        raise ValueError('compiler intent already bound to another source work request')
                    return {'job': path.stem, 'status': 'already-queued', **self.status(path.stem)}
            if len(paths) >= 10000:
                raise ValueError('compiler queue retention bound reached (10000 jobs)')
            offered = desk.compiler_work(expected, object_id, principal, self.database)
            if offered is None or offered['intent'] != intent or (work is not None and canonical(work) != canonical(offered)):
                raise ValueError('compiler work was not offered under this intent/root')
            work = offered
            material = desk.proposal_material(work['proposal'], self.artifacts)[2]
            runtime = compiler_pins(self.profile, expected, work)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('compiler enqueue deadline reached')
            observed = worker.command([str(ROOT / 'scripts/desk.py'), '--database', str(self.database),
                                       '--artifacts', str(self.artifacts), '--profile', self.profile,
                                       'inspect', '--object', object_id, '--principal', principal], remaining, self.memory_mib)
            if canonical(observed) != canonical(expected):
                raise ValueError('queued candidate changed')
            if canonical(compiler_pins(self.profile, expected, work)) != canonical(runtime):
                raise ValueError('compiler runtime changed during enqueue')
            job = {'format': 'delvetalk-compiler-job-v1', 'database': str(self.database),
                   'artifacts': str(self.artifacts), 'profile': self.profile, 'inputs': inputs, 'work': work, 'runtime': runtime,
                   'sourceBindings': material}
            identity = digest(job)
            if canonical(desk.immutable(self.job_path(identity), job)) != canonical(job):
                raise ValueError('compiler job store mismatch')
            return {'job': identity, 'status': 'queued'}

    def enqueue_offered(self, object_id, principal, *, expected=None, deadline_seconds=10):
        """Carry the Candidate's source-authored physical compiler request.

        Source chooses readiness and intent. This custodian acquires the exact
        root, preserves it and binds the existing bounded compiler queue to it.
        """
        client = desk.Desk(self.database, self.artifacts, profile=self.profile)
        # A service-held catalogue root can advertise absence of work without
        # acquiring private state under the compiler principal. Actual offered
        # work still requires the current native read below and preparation.
        if expected is not None:
            view = desk.projection.project(expected, object_id)
            if 'compile' not in desk.projection.invitations(view):
                return None
        root = client.inspect(object_id, principal=principal)
        if expected is not None and canonical(root) != canonical(expected):
            raise ValueError('source compiler request differs from captured candidate')
        request = desk.compiler_work(root, object_id, principal, self.database)
        if request is None:
            return None
        return self.enqueue(object_id, principal, request['intent'], root, work=request,
                            deadline_seconds=deadline_seconds)

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
    parser.add_argument('--profile', choices=desk.world.PROFILES, default='compiled')
    parser.add_argument('--memory-mib', type=int, default=process_custody.NATIVE_MEMORY_MIB)
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
