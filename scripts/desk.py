#!/usr/bin/env python3
"""World-owned source proposals, bounded compiler custody, explicit atomic adoption."""
import argparse
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import shutil
import stat
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
source_store = module('desk_source_store', 'scripts/source_store.py')
history = module('desk_history', 'scripts/history.py')
adoption = module('desk_adoption', 'scripts/adoption.py')
canonical, loads = translate.canonical, translate.load_json
SOURCE_DESK_PROTOCOL_PATHS = (
    'protocols/source-desk/protocol.json',
    'protocols/town-forge/source-desk.json',
)


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_source_desk_protocol(protocol):
    """Recognize only reviewed complete bodies; this selection grants no authority."""
    expected = canonical(protocol)
    return any(expected == canonical(loads((ROOT / path).read_bytes()))
               for path in SOURCE_DESK_PROTOCOL_PATHS)


def execution_profile(profile='transactions'):
    return {'profile': profile, 'files': {
        **runtime_profile.file_hashes(profile),
        **{path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
           for path in SOURCE_DESK_PROTOCOL_PATHS},
        'scripts/desk.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scripts/adoption.py': hashlib.sha256((ROOT / 'scripts/adoption.py').read_bytes()).hexdigest(),
        'scripts/history.py': hashlib.sha256((ROOT / 'scripts/history.py').read_bytes()).hexdigest(),
        'scripts/source_store.py': hashlib.sha256((ROOT / 'scripts/source_store.py').read_bytes()).hexdigest()}}


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


def preserve_build_dependencies(directory, artifact):
    """Retain exact declared compiler inputs before publishing their admission."""
    custody = Path(directory) / 'pins'
    def regular(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        stream = os.fdopen(descriptor, 'rb')
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            stream.close()
            raise ValueError('build dependency must be a regular file')
        return stream
    for name, sha in history.declared_files(artifact).items():
        target = history.blob_path(custody, sha)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with regular(target) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != sha:
                    raise ValueError('retained build dependency digest mismatch: ' + name)
            continue
        except FileNotFoundError:
            pass
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT):
            raise ValueError('build dependency escapes repository: ' + name)
        temporary = None
        try:
            with regular(source) as original, tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as copied:
                temporary = Path(copied.name)
                shutil.copyfileobj(original, copied)
                copied.flush()
                os.fsync(copied.fileno())
            with regular(temporary) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != sha:
                    raise ValueError('original build dependency missing or changed: ' + name)
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
            with regular(target) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != sha:
                    raise ValueError('retained build dependency digest mismatch: ' + name)
            descriptor = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink()


def proposal_material(proposal, artifact_store=None):
    """Resolve exact bytes only from the explicitly selected local source store."""
    if isinstance(proposal, dict) and proposal.get('format') == source_store.PROPOSAL:
        if artifact_store is None:
            raise ValueError('source reference proposal requires an explicit artifact store')
        source, scenarios = source_store.validate_proposal(artifact_store, proposal)
        bindings = {key: proposal[key] for key in ('syntax', 'sourceRef', 'scenariosRef', 'adapterPin')}
    else:
        if not isinstance(proposal, dict) or set(proposal) != {'syntax', 'source', 'scenarios'}:
            raise ValueError('proposal requires inline syntax/source/scenarios or explicit source references')
        source, scenarios = proposal['source'].encode('utf-8'), proposal['scenarios'].encode('utf-8')
        bindings = {'syntax': proposal['syntax'],
                    'sourceRef': {k: v for k, v in source_store.reference(source).items() if k != 'format'},
                    'scenariosRef': {k: v for k, v in source_store.reference(scenarios, kind='scenarios').items() if k != 'format'}}
        try:
            bindings['adapterPin'] = source_store.adapter_pin(proposal['syntax'])
        except ValueError:
            bindings['adapterPin'] = None  # The compiler retains the unknown-syntax refusal.
    return source, scenarios, bindings


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
        raw_source, raw_scenarios, bindings = proposal_material(source, payload.get('artifactStore'))
        artifact['sourceBindings'] = bindings
        # Local build custody retains originals even when compilation fails.
        artifact['sourceMaterial'] = {'source': raw_source.decode('utf-8'), 'scenarios': raw_scenarios.decode('utf-8')}
        if not isinstance(state['migration'], dict):
            raise ValueError('migration must be a complete state object')
        report = proposal.propose(source['syntax'], raw_source, raw_scenarios, profile=profile)
        if (bindings['adapterPin'] is not None
                and canonical(report['candidate']['artifact']['translation']) != canonical(bindings['adapterPin'])):
            raise ValueError('source adapter changed during compilation')
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


def bounded_compile(root, *, timeout=45, profile='transactions', artifact_store=None):
    """Run the trusted compiler with wall/CPU/file bounds; never execute source text."""
    failed = {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(root), 'passed': False}
    if isinstance(root.get('state', {}).get('proposal'), dict):
        proposed = root['state']['proposal']
        failed['proposal'] = proposed
        if proposed.get('format') == source_store.PROPOSAL:
            failed['sourceBindings'] = {key: proposed[key] for key in ('syntax', 'sourceRef', 'scenariosRef', 'adapterPin')}
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
            process.communicate(canonical({'root': root, 'profile': profile,
                                           'artifactStore': str(Path(artifact_store).resolve()) if artifact_store is not None else None}),
                                timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_group()
            return {**failed, 'diagnostics': [{'kind': 'worker-timeout', 'seconds': timeout}]}
        except BaseException:
            terminate_group()
            raise
        output.seek(0)
        raw = output.read(8 * 1024 * 1024 + 1)
        if process.returncode or len(raw) > 8 * 1024 * 1024:
            terminate_group()
            return {**failed, 'diagnostics': [{'kind': 'worker-failure', 'exit': process.returncode}]}
        try:
            return loads(raw)
        except (ValueError, UnicodeError):
            return {**failed, 'diagnostics': [{'kind': 'worker-malformed-output'}]}


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

    def submit_refs(self, object_id, principal, intent, expected, proposal, migration, target):
        request = {'op': 'invoke', 'object': object_id, 'principal': principal, 'intent': intent,
                   'expected': expected, 'command': 'submit',
                   'input': {'proposal': proposal, 'migration': migration, 'target': target}}
        retained = self.retained_reply(request)
        if retained is not None:
            return retained
        source_store.validate_proposal(self.artifact_store, proposal)
        source_store.preserve_dependencies(self.artifact_store, proposal)
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
            if expected['state']['proposal'].get('format') == source_store.PROPOSAL:
                # Custody/runtime errors remain retryable; do not admit source loss as a failed program.
                proposal_material(expected['state']['proposal'], self.artifact_store)
                build = bounded_compile(expected, profile=self.profile, artifact_store=self.artifact_store)
            else:
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
        if expected['state']['proposal'].get('format') == source_store.PROPOSAL:
            proposal_material(expected['state']['proposal'], self.artifact_store)
        # Detect corruption without repeating translation or adopting a new artifact.
        build = load_artifact(self.artifact_store, entry['request']['input']['artifact'])
        preserve_build_dependencies(self.artifact_store, build)
        return self.exchange(entry['request'])

    def adopt(self, object_id, target, principal, intent, expected_candidate, expected_target):
        return self.exchange(adoption.request(object_id, target, principal, intent,
                                              expected_candidate, expected_target))


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
    submit.add_argument('--references', action='store_true', help='store exact source/scenarios locally and submit compact references')
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
                if args.references:
                    proposal = source_store.prepare_proposal(args.artifacts, args.syntax,
                                                             args.source.read_bytes(), args.scenarios.read_bytes())
                    result = desk.submit_refs(args.object, args.principal, args.intent, expected, proposal,
                                              loads(args.migration.read_bytes()), args.target)
                else:
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
