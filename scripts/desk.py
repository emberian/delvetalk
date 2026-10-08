#!/usr/bin/env python3
"""World-owned source proposals, bounded compiler custody, explicit atomic adoption."""
import argparse
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


translate = module('desk_translate', 'scripts/translate.py')
world = module('desk_world', 'scripts/world.py')
runtime_profile = module('desk_runtime_profile', 'scripts/runtime_profile.py')
canonical, loads = translate.canonical, translate.load_json


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def execution_profile(profile='transactions'):
    return {'profile': profile, 'files': {
        **runtime_profile.file_hashes(profile),
        'scripts/desk.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}


def immutable(path, value):
    """Publish complete immutable bytes without exposing a partially written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except FileExistsError:
            pass
        return loads(path.read_bytes())
    finally:
        if temporary is not None:
            temporary.unlink()


def store_artifact(directory, artifact):
    identity = digest(artifact)
    stored = immutable(Path(directory) / 'builds' / (identity + '.json'), artifact)
    if digest(stored) != identity:
        raise ValueError('artifact store content does not match its identity')
    return identity


def load_artifact(directory, identity):
    if not isinstance(identity, str) or len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
        raise ValueError('invalid build artifact identity')
    artifact = loads((Path(directory) / 'builds' / (identity + '.json')).read_bytes())
    if digest(artifact) != identity:
        raise ValueError('artifact store content does not match its identity')
    return artifact


def compile_proposal(payload):
    """Trusted worker computation only; all world transitions happen elsewhere."""
    proposal = module('desk_proposal', 'scripts/propose.py')
    profile = payload.get('profile', 'transactions')
    state = payload['root']['state']
    source = state['proposal']
    artifact = {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(payload['root']),
                'proposal': source, 'migration': state['migration'], 'target': state['target'], 'admissionProfile': profile,
                'worker': {'scripts/desk.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    try:
        if not isinstance(source, dict) or set(source) != {'syntax', 'source', 'scenarios'}:
            raise ValueError('proposal requires exactly syntax, source and scenarios')
        if not isinstance(state['migration'], dict):
            raise ValueError('migration must be a complete state object')
        report = proposal.propose(source['syntax'], source['source'].encode('utf-8'),
                                  source['scenarios'].encode('utf-8'), profile=profile)
        artifact['report'] = report
        if not report['passed']:
            artifact.update(passed=False, diagnostics=[{'kind': 'scenario-failure', 'report': report['id']}])
            return artifact
        translated = report['candidate']['artifact']
        if translated['target'] == 'local-protocol-v1':
            protocol = translated['lowered']
            artifact['roomArtifact'] = None
        else:
            room = module('desk_room', 'scene/room.py')
            wrapped = room.wrap_bundle(translated['lowered'])
            artifact['roomArtifact'] = wrapped
            protocol = wrapped['protocol']
        artifact.update(passed=True, diagnostics=[], protocol=protocol)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, RecursionError, AttributeError) as error:
        artifact.update(passed=False, diagnostics=[{'kind': 'compile-error', 'message': str(error)}])
    return artifact


def bounded_compile(root, *, timeout=45, profile='transactions'):
    """Run the trusted compiler with wall/CPU/file bounds; never execute source text."""
    def limits():
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_worker'],
                                   stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                   start_new_session=True, preexec_fn=limits)
        def terminate_group():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if process.stdin is not None:
                process.stdin.close()
        try:
            process.communicate(canonical({'root': root, 'profile': profile}), timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_group()
            return {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(root),
                    'passed': False, 'diagnostics': [{'kind': 'worker-timeout', 'seconds': timeout}]}
        except BaseException:
            terminate_group()
            raise
        output.seek(0)
        raw = output.read(8 * 1024 * 1024 + 1)
        if process.returncode or len(raw) > 8 * 1024 * 1024:
            terminate_group()
            return {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(root),
                    'passed': False, 'diagnostics': [{'kind': 'worker-failure', 'exit': process.returncode}]}
        try:
            return loads(raw)
        except (ValueError, UnicodeError):
            return {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(root),
                    'passed': False, 'diagnostics': [{'kind': 'worker-malformed-output'}]}


class Desk:
    def __init__(self, database, artifact_store, *, profile='transactions'):
        if profile not in world.PROFILES:
            raise ValueError('unknown local host profile: ' + str(profile))
        self.database, self.artifact_store = Path(database), Path(artifact_store)
        self.profile = profile

    def exchange(self, request):
        return world.exchange(self.database, request, profile=self.profile)

    def retained_reply(self, request):
        """Read an exact historical receipt without running a replacement engine."""
        with open(str(self.database.resolve()) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.database.exists():
                for entry in loads(self.database.read_bytes())['receipts']:
                    if canonical(entry['request']) == canonical(request):
                        return entry['receipt']
        return None

    def inspect(self, object_id):
        return self.exchange({'op': 'inspect', 'object': object_id, 'principal': 'source-desk-reader'})

    def create(self, object_id, principal, intent, law):
        return self.exchange({'op': 'create', 'object': object_id, 'principal': principal, 'intent': intent,
                              'protocol': loads((ROOT / 'protocols/source-desk/protocol.json').read_bytes()), 'law': law})

    def submit(self, object_id, principal, intent, expected, syntax, source, scenarios, migration, target):
        request = {'op': 'invoke', 'object': object_id, 'principal': principal, 'intent': intent,
                   'expected': expected, 'command': 'submit', 'input': {
                       'proposal': {'syntax': syntax, 'source': source.decode('utf-8'), 'scenarios': scenarios.decode('utf-8')},
                       'migration': migration, 'target': target}}
        return self.exchange(request)

    def check(self, object_id, principal, intent, expected):
        # This memo preserves only the compiler-produced request across uncertainty.
        # Lean's world retains the actual lifecycle and all success/refusal receipts.
        inputs = {'object': object_id, 'principal': principal, 'intent': intent, 'expected': expected}
        path = self.artifact_store / 'attempts' / (digest([principal, intent]) + '.json')
        if path.exists():
            entry = loads(path.read_bytes())
        else:
            profile = execution_profile(self.profile)
            build = bounded_compile(expected, profile=self.profile)
            identity = store_artifact(self.artifact_store, build)
            if build['passed']:
                room_id = None
                if build.get('roomArtifact') is not None:
                    room = module('desk_room_store', 'scene/room.py')
                    room_id = room.store_artifact(self.artifact_store / 'rooms', build['roomArtifact'])
                command, payload = 'compiled', {'artifact': identity, 'protocol': build['protocol'], 'roomArtifact': room_id}
            else:
                command, payload = 'failed', {'artifact': identity, 'diagnostics': build['diagnostics']}
            request = {'op': 'invoke', **inputs, 'command': command, 'input': payload}
            if execution_profile(self.profile) != profile:
                raise ValueError('desk admission runtime changed during compilation')
            entry = immutable(path, {'inputs': inputs, 'request': request, 'executionProfile': profile})
        if canonical(entry['inputs']) != canonical(inputs):
            raise ValueError('compiler intent already bound to another candidate/root')
        retained = self.retained_reply(entry['request'])
        if retained is not None:
            return retained
        if entry.get('executionProfile') != execution_profile(self.profile):
            raise ValueError('pending desk admission runtime pins changed or missing')
        # Detect corruption without repeating translation or adopting a new artifact.
        load_artifact(self.artifact_store, entry['request']['input']['artifact'])
        return self.exchange(entry['request'])

    def adopt(self, object_id, target, principal, intent, expected_candidate, expected_target):
        if object_id == target and canonical(expected_candidate) != canonical(expected_target):
            raise ValueError('one object cannot have two different read roots')
        return self.exchange({'op': 'transaction', 'principal': principal, 'intent': intent,
                              'reads': {object_id: expected_candidate, target: expected_target}, 'calls': [
                                  {'object': object_id, 'command': 'adopt', 'input': {'target': target}},
                                  {'op': 'reprogram', 'object': target, 'inputFrom': 0}]})


def main():
    if len(sys.argv) == 2 and sys.argv[1] == '_worker':
        sys.stdout.buffer.write(canonical(compile_proposal(loads(sys.stdin.buffer.read()))) + b'\n')
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--artifacts', required=True, type=Path)
    parser.add_argument('--profile', choices=world.PROFILES, default='transactions', help='operator-selected admission and compiler-scenario host')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create')
    create.add_argument('--law', required=True, type=Path)
    submit = commands.add_parser('submit')
    submit.add_argument('--syntax', required=True)
    submit.add_argument('--source', required=True, type=Path)
    submit.add_argument('--scenarios', required=True, type=Path)
    submit.add_argument('--migration', required=True, type=Path)
    submit.add_argument('--target', required=True)
    check = commands.add_parser('check')
    adopt = commands.add_parser('adopt')
    adopt.add_argument('--target', required=True)
    adopt.add_argument('--target-root', required=True, type=Path)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--object', required=True)
    for command in (create, submit, check, adopt):
        command.add_argument('--object', required=True)
        command.add_argument('--principal', required=True)
        command.add_argument('--intent', required=True)
        if command is not create:
            command.add_argument('--expected-root', required=True, type=Path)
    args = parser.parse_args()
    desk = Desk(args.database, args.artifacts, profile=args.profile)
    try:
        if args.command == 'inspect':
            result = desk.inspect(args.object)
        elif args.command == 'create':
            result = desk.create(args.object, args.principal, args.intent, loads(args.law.read_bytes()))
        else:
            expected = loads(args.expected_root.read_bytes())
            if args.command == 'submit':
                result = desk.submit(args.object, args.principal, args.intent, expected, args.syntax,
                                     args.source.read_bytes(), args.scenarios.read_bytes(),
                                     loads(args.migration.read_bytes()), args.target)
            elif args.command == 'check':
                result = desk.check(args.object, args.principal, args.intent, expected)
            else:
                result = desk.adopt(args.object, args.target, args.principal, args.intent, expected,
                                   loads(args.target_root.read_bytes()))
        sys.stdout.buffer.write(canonical(result) + b'\n')
        return 1 if result.get('kind') == 'refused' else 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        print('desk: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
