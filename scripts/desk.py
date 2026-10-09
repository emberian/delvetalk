#!/usr/bin/env python3
"""World-owned source proposals, bounded compiler custody, explicit atomic adoption."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
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
process_custody = module('desk_process_custody', 'scripts/process_custody.py')
source_object = module('desk_source_object', 'scripts/source_object.py')
history = module('desk_history', 'scripts/history.py')
source_offers = module('desk_source_offers', 'scripts/source_offers.py')
projection = module('desk_projection', 'scene/projection.py')
canonical, loads = translate.canonical, translate.load_json
SOURCE_CANDIDATE_FILES = ('protocols/editor/generate.py', 'protocols/editor/Candidate.obend',
                          'world/lib/prelude/List.obend', 'world/lib/prelude/Preparation.obend', 'world/lib/prelude/Abi.obend',
                          'protocols/contract-workshop/generate.py',
                          'protocols/contract-workshop/Workshop.obend',
                          'protocols/contract-workshop/ContractCandidate.obend')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def candidate_state(root):
    """Project Candidate custody data without replacing its exact native root."""
    model = source_object.state_data(root)
    if (not isinstance(model, dict) or set(model) != {'tag', 'fields'}
            or model['tag'] != 'record' or not isinstance(model['fields'], list)):
        raise ValueError('typed candidate state requires a DataWire record')
    fields = {}
    for field in model['fields']:
        if (not isinstance(field, dict) or set(field) != {'name', 'value'}
                or not isinstance(field['name'], str) or field['name'] in fields):
            raise ValueError('typed candidate state requires distinct named fields')
        fields[field['name']] = field['value']
    names = ('proposal', 'migration', 'protocol', 'diagnostics', 'roomArtifact')
    decoded = source_object.values('decode', [fields[name] for name in names])
    result = {name: source_object.plain(value) for name, value in fields.items() if name not in names}
    result.update(zip(names, decoded))
    return result


def compiler_work(root, object_id, principal, database, *, receiver=None):
    """Acquire explicit offered compiler consent under the service's current read.

    This DTO describes bounded physical work and report transport, not an
    approved source program. Native preparation checks the exact held root.
    """
    if database is not None and receiver is not None:
        raise ValueError('compiler work selects exactly one native transport')
    references = None
    if receiver is not None:
        captured = world.capture_roots(None, [object_id], principal=principal,
                                       profile='compiled', receiver=receiver)
        pair = captured['roots'][object_id]
        if pair is None or canonical(pair['root']) != canonical(root):
            raise ValueError('compiler work differs from captured current root')
        references = {object_id: pair['reference']}
    view = projection.project(root, object_id)
    offers = source_offers.capture(view, {object_id: root}, database=database,
                                  references=references)
    offer = offers.get('compile')
    if offer is None:
        return None
    outcome = source_offers.prepare(offer, principal, 'inspect-compiler-request', {},
                                   database=database, receiver=receiver)
    if outcome.get('kind') != 'inspection':
        raise ValueError('source compiler offer did not produce an inspection')
    work = outcome.get('value')
    validate_compiler_work(work, root, object_id)
    return work


def validate_compiler_work(work, root, object_id):
    """Check the physical compiler request framing; source owns its workflow."""
    keys = {'format', 'object', 'intent', 'proposal', 'migration', 'target', 'reports'}
    if (not isinstance(work, dict) or set(work) != keys
            or work['format'] != 'delvetalk-compiler-request-v1' or work['object'] != object_id
            or not isinstance(work['intent'], str) or not 0 < len(work['intent'].encode()) <= 512
            or not isinstance(work['proposal'], dict) or not isinstance(work['migration'], dict)
            or not isinstance(work['proposal'].get('syntax'), str)
            or not 0 < len(work['proposal']['syntax'].encode()) <= 128
            or not isinstance(work['target'], str) or not 0 < len(work['target'].encode()) <= 512
            or not isinstance(work['reports'], dict) or set(work['reports']) != {'passed', 'failed'}
            or len(canonical(work)) > 1024 * 1024):
        raise ValueError('source compiler request contract differs')
    commands = root['protocol'].get('commands', {})
    for command in work['reports'].values():
        if not isinstance(command, str) or not command or command not in commands:
            raise ValueError('source compiler report method is not declared')
        transition = commands[command].get('transition', {})
        if (transition.get('profile') != 'delvetalk-source-transition'
                or transition.get('inputCodec') != 'value'):
            raise ValueError('source compiler report method requires the typed Value input contract')
    return work


def execution_paths(profile='compiled'):
    """Return custody dependency names independently from byte hashing."""
    return tuple(sorted(set(runtime_profile.paths(profile))
        | set(SOURCE_CANDIDATE_FILES)
        | set(source_store.adapter_pin('objective-bend-object')['files']) | {
        'scripts/desk.py', 'scripts/source_offers.py', 'scene/projection.py',
        'scripts/affordances.py', 'scripts/references.py', 'scripts/source_packages.py',
        'scripts/history.py', 'scripts/source_store.py',
        'scripts/process_custody.py', 'scripts/source_object.py'}))


def execution_profile(profile='compiled'):
    return {'profile': profile, 'files': runtime_profile.hash_paths(execution_paths(profile), root=ROOT)}


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
    if isinstance(proposal, dict) and proposal.get('format') == source_store.INLINE_MODULE_PROPOSAL:
        if (set(proposal) != {'format', 'syntax', 'modules', 'scenarios'}
                or not isinstance(proposal['syntax'], str) or not isinstance(proposal['scenarios'], str)):
            raise ValueError('inline module proposal requires syntax/modules/scenarios')
        source = source_store.inline_module_material(proposal['modules'], artifact_store)
        scenarios = proposal['scenarios'].encode('utf-8')
        bindings = {'syntax': proposal['syntax'], 'manifest': source['manifest'],
                    'scenariosRef': (source_store.reference(scenarios, kind='scenarios') if artifact_store is None
                                     else source_store.store_bytes(artifact_store, scenarios, kind='scenarios')),
                    'adapterPin': source_store.adapter_pin(proposal['syntax'])}
    elif isinstance(proposal, dict) and proposal.get('format') == source_store.MODULE_PROPOSAL:
        if artifact_store is None:
            raise ValueError('module proposal requires an explicit artifact store')
        source, scenarios = source_store.validate_module_proposal(artifact_store, proposal)
        bindings = {key: proposal[key] for key in ('syntax', 'manifest', 'scenariosRef', 'adapterPin')}
    elif isinstance(proposal, dict) and proposal.get('format') == source_store.PROPOSAL:
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
    profile = payload.get('profile', 'compiled')
    state = payload['work']
    source = state['proposal']
    artifact = {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(payload['root']),
                'compilerWork': state, 'proposal': source, 'migration': state['migration'], 'target': state['target'], 'admissionProfile': profile,
                'worker': {'scripts/desk.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    try:
        raw_source, raw_scenarios, bindings = proposal_material(source, payload.get('artifactStore'))
        artifact['sourceBindings'] = bindings
        # Local build custody retains originals even when compilation fails.
        modules = raw_source if isinstance(raw_source, dict) else None
        artifact['sourceMaterial'] = ({**modules, 'scenarios': raw_scenarios.decode('utf-8')} if modules is not None
                                      else {'source': raw_source.decode('utf-8'), 'scenarios': raw_scenarios.decode('utf-8')})
        if not isinstance(state['migration'], dict):
            raise ValueError('migration must be a complete state object')
        report = proposal.propose(source['syntax'], b'' if modules is not None else raw_source,
                                  raw_scenarios, profile=profile, modules=modules)
        if (bindings['adapterPin'] is not None
                and canonical(report['candidate']['artifact']['translation']) != canonical(bindings['adapterPin'])):
            raise ValueError('source adapter changed during compilation')
        artifact['report'] = report
        if not report['passed']:
            artifact.update(passed=False, diagnostics=[{'kind': 'scenario-failure', 'report': report['id']}])
            return artifact
        translated = report['candidate']['artifact']
        if translated['target'] != 'local-protocol-v1':
            raise ValueError('source authoring requires an ordinary local object protocol')
        protocol = translated['lowered']
        artifact['roomArtifact'] = None
        artifact.update(passed=True, diagnostics=[], protocol=protocol)
        if set(payload['root']['state']) == {'model'}:
            artifact['program'] = source_object.values('digest', [protocol])[0]
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, RecursionError, AttributeError) as error:
        artifact.update(passed=False, diagnostics=[{'kind': 'compile-error', 'message': str(error)}])
    return artifact


def bounded_compile(root, *, work, timeout=45, profile='compiled', artifact_store=None):
    """Run the trusted compiler with wall/CPU/file bounds; never execute source text."""
    failed = {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(root), 'compilerWork': work, 'passed': False}
    state = work
    if isinstance(state.get('proposal'), dict):
        proposed = state['proposal']
        failed['proposal'] = proposed
        if proposed.get('format') == source_store.PROPOSAL:
            failed['sourceBindings'] = {key: proposed[key] for key in ('syntax', 'sourceRef', 'scenariosRef', 'adapterPin')}
        elif proposed.get('format') == source_store.MODULE_PROPOSAL:
            failed['sourceBindings'] = {key: proposed[key] for key in ('syntax', 'manifest', 'scenariosRef', 'adapterPin')}
    try:
        process = process_custody.run([sys.executable, str(Path(__file__).resolve()), '_worker'],
            input=canonical({'root': root, 'work': work, 'profile': profile,
                             'artifactStore': str(Path(artifact_store).resolve()) if artifact_store is not None else None}),
            timeout=timeout, cpu_seconds=30, memory_bytes=process_custody.NATIVE_MEMORY_BYTES,
            stdout_limit=8 * 1024 * 1024,
            stderr_limit=8 * 1024 * 1024, file_limit=8 * 1024 * 1024)
    except subprocess.TimeoutExpired:
        return {**failed, 'diagnostics': [{'kind': 'worker-timeout', 'seconds': timeout}]}
    except process_custody.OutputLimitExceeded:
        return {**failed, 'diagnostics': [{'kind': 'worker-output-limit'}]}
    if process.returncode:
        return {**failed, 'diagnostics': [{'kind': 'worker-failure', 'exit': process.returncode}]}
    try:
        return loads(process.stdout)
    except (ValueError, UnicodeError):
        return {**failed, 'diagnostics': [{'kind': 'worker-malformed-output'}]}


class Desk:
    def __init__(self, database, artifact_store, *, profile='compiled'):
        if profile not in world.PROFILES:
            raise ValueError('unknown local host profile: ' + str(profile))
        self.database, self.artifact_store = Path(database), Path(artifact_store)
        self.profile = profile

    def exchange(self, request):
        return world.exchange(self.database, request, profile=self.profile)

    def retained_reply(self, request):
        """Read an exact historical receipt without running a replacement engine."""
        return world.retained_reply(self.database, request)

    def inspect(self, object_id, *, principal='source-desk-reader'):
        return self.exchange({'op': 'inspect', 'object': object_id, 'principal': principal})

    def create(self, object_id, principal, intent, law):
        if self.profile != 'compiled':
            raise ValueError('source Candidate creation requires the explicitly selected compiled profile')
        protocol = module('desk_candidate_package', 'protocols/editor/generate.py').candidate(editor_mode=False)
        return self.exchange({'op': 'create', 'object': object_id, 'principal': principal, 'intent': intent,
                              'protocol': protocol, 'law': law})

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
        if isinstance(proposal, dict) and proposal.get('format') == source_store.MODULE_PROPOSAL:
            source_store.validate_module_proposal(self.artifact_store, proposal)
        else:
            source_store.validate_proposal(self.artifact_store, proposal)
        source_store.preserve_dependencies(self.artifact_store, proposal)
        return self.exchange(request)

    def check_attempt(self, inputs):
        """Read the existing exact completion request without consulting current pins."""
        path = self.artifact_store / 'attempts' / (digest([inputs['principal'], inputs['intent']]) + '.json')
        if not path.exists():
            return None
        entry = loads(path.read_bytes())
        if canonical(entry['inputs']) != canonical(inputs):
            raise ValueError('compiler intent already bound to another candidate/root')
        validate_compiler_work(entry['work'], inputs['expected'], inputs['object'])
        if entry['work']['intent'] != inputs['intent']:
            raise ValueError('compiler attempt intent differs from source request')
        request = entry['request']
        if (set(request) != {'op', 'object', 'principal', 'intent', 'expected', 'command', 'input'}
                or request['op'] != 'invoke' or request['command'] not in entry['work']['reports'].values()
                or any(canonical(request[key]) != canonical(value) for key, value in inputs.items())):
            raise ValueError('compiler attempt is not the exact captured completion request')
        return entry

    def prepare_check(self, inputs, build, profile):
        """Retain a compiler-produced request; preparing never admits or adopts."""
        entry = self.check_attempt(inputs)
        if entry is not None:
            return entry
        if build.get('candidateRootSha256') != digest(inputs['expected']):
            raise ValueError('compiler build does not match captured candidate')
        validate_compiler_work(build['compilerWork'], inputs['expected'], inputs['object'])
        if build['compilerWork']['intent'] != inputs['intent']:
            raise ValueError('compiler build intent differs from source request')
        identity = store_artifact(self.artifact_store, build)
        if build['passed']:
            room_id = None
            if build.get('roomArtifact') is not None:
                room = module('desk_room_store', 'scene/room.py')
                room_id = room.store_artifact(self.artifact_store / 'rooms', build['roomArtifact'])
            command, payload = build['compilerWork']['reports']['passed'], {'artifact': identity, 'protocol': build['protocol'], 'roomArtifact': room_id}
            if set(inputs['expected']['state']) == {'model'}:
                payload['program'] = build['program']
        else:
            command, payload = build['compilerWork']['reports']['failed'], {'artifact': identity, 'diagnostics': build['diagnostics']}
        if execution_profile(self.profile) != profile:
            raise ValueError('desk admission runtime changed during compilation')
        path = self.artifact_store / 'attempts' / (digest([inputs['principal'], inputs['intent']]) + '.json')
        immutable(path, {'inputs': inputs, 'work': build['compilerWork'], 'request': {'op': 'invoke', **inputs, 'command': command, 'input': payload},
                         'executionProfile': profile})
        return self.check_attempt(inputs)

    def admit_check(self, entry, *, before_exchange=None):
        """Recover first; otherwise verify custody and let Lean decide admission."""
        retained = self.retained_reply(entry['request'])
        if retained is not None:
            return retained
        if entry.get('executionProfile') != execution_profile(self.profile):
            raise ValueError('pending desk admission runtime pins changed or missing')
        proposal = entry['work']['proposal']
        if proposal.get('format') in (source_store.PROPOSAL, source_store.MODULE_PROPOSAL, source_store.INLINE_MODULE_PROPOSAL):
            proposal_material(proposal, self.artifact_store)
        build = load_artifact(self.artifact_store, entry['request']['input']['artifact'])
        if (build.get('candidateRootSha256') != digest(entry['inputs']['expected'])
                or canonical(build.get('compilerWork')) != canonical(entry['work'])):
            raise ValueError('compiler artifact differs from retained work/root')
        preserve_build_dependencies(self.artifact_store, build)
        if before_exchange is not None:
            before_exchange()
        return self.exchange(entry['request'])

    def check(self, object_id, principal, intent, expected):
        inputs = {'object': object_id, 'principal': principal, 'intent': intent, 'expected': expected}
        entry = self.check_attempt(inputs)
        if entry is None:
            profile = execution_profile(self.profile)
            options = {'profile': self.profile}
            work = compiler_work(expected, object_id, principal, self.database)
            if work is None or work['intent'] != intent:
                raise ValueError('compiler work was not offered under this intent')
            proposal = work['proposal']
            if proposal.get('format') in (source_store.PROPOSAL, source_store.MODULE_PROPOSAL, source_store.INLINE_MODULE_PROPOSAL):
                proposal_material(proposal, self.artifact_store)
                options['artifact_store'] = self.artifact_store
            entry = self.prepare_check(inputs, bounded_compile(expected, work=work, **options), profile)
        return self.admit_check(entry)

    def _prepare_release(self, inputs):
        view = projection.project(inputs['expectedCandidate'], inputs['object'])
        roots = {inputs['object']: inputs['expectedCandidate'], inputs['target']: inputs['expectedTarget']}
        invitation = source_offers.capture(view, roots).get('release')
        if invitation is None:
            raise ValueError('this source Candidate does not offer an ordinary release')
        return source_offers.request(invitation, inputs['principal'], inputs['intent'], {})

    def adopt(self, object_id, target, principal, intent, expected_candidate, expected_target):
        inputs = {'object': object_id, 'target': target, 'principal': principal, 'intent': intent,
                  'expectedCandidate': expected_candidate, 'expectedTarget': expected_target}
        path = self.artifact_store / 'releases' / (digest([principal, intent]) + '.json')
        entry = loads(path.read_bytes()) if path.exists() else None
        if entry is not None:
            if (not isinstance(entry, dict) or set(entry) !=
                    {'format', 'inputs', 'runtime', 'request', 'sha256'}
                    or entry['format'] != 'delvetalk-source-release-attempt-v1'
                    or entry['sha256'] != digest({key: value for key, value in entry.items() if key != 'sha256'})):
                raise ValueError('invalid retained source release attempt')
            if canonical(entry['inputs']) != canonical(inputs):
                raise ValueError('release intent already bound to different inputs')
            if any(entry['request'].get(key) != inputs[key] for key in ('principal', 'intent')):
                raise ValueError('release request differs from its retained caller and intent')
            retained = self.retained_reply(entry['request'])
            if retained is not None:
                return retained
            if execution_profile(self.profile) != entry['runtime']:
                raise ValueError('release runtime changed; retain the original pending attempt')
            if canonical(self._prepare_release(inputs)) != canonical(entry['request']):
                raise ValueError('source release differs from its retained preparation')
            if execution_profile(self.profile) != entry['runtime']:
                raise ValueError('release runtime changed during source preparation')
        else:
            profile = execution_profile(self.profile)
            request = self._prepare_release(inputs)
            if execution_profile(self.profile) != profile:
                raise ValueError('release runtime changed during source preparation')
            body = {'format': 'delvetalk-source-release-attempt-v1', 'inputs': inputs,
                    'runtime': profile, 'request': request}
            prepared = {**body, 'sha256': digest(body)}
            entry = immutable(path, prepared)
            if canonical(entry) != canonical(prepared):
                raise ValueError('release intent already bound to another preparation')
        return self.exchange(entry['request'])


def main():
    if len(sys.argv) == 2 and sys.argv[1] == '_worker':
        sys.stdout.buffer.write(canonical(compile_proposal(loads(sys.stdin.buffer.read()))) + b'\n')
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--artifacts', required=True, type=Path)
    parser.add_argument('--profile', choices=world.PROFILES, default='compiled', help='operator-selected admission and compiler-scenario host')
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
    inspect.add_argument('--principal', default='source-desk-reader')
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
            result = desk.inspect(args.object, principal=args.principal)
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
