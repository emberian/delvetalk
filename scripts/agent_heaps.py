"""Authenticated realm selection and bounded native custody; Lean owns behavior.

Identity arguments come only from IdentityStore.authenticate, never request JSON.
One manager owns a private root. Its one worker owns all SQLite connections and
serializes bounded native evaluations; an LRU bounds persistent receiver count.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import base64
import fcntl
import hashlib
import hmac
import importlib.util
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import world
import resident_store
import process_custody
import package_session
import desk
import runtime_profile

ACCOUNT = re.compile(r'[0-9a-f]{32}\Z')
MAX_REQUEST = 256 * 1024
MAX_EVALUATION = 512 * 1024
RESERVED = 'account-bootstrap:'
DEFAULT_RESIDENT_MEMORY = process_custody.NATIVE_MEMORY_BYTES


def encoded(value):
    return desk.canonical(value)


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class HeapLimit(ValueError):
    pass


class QuotaResident(resident_store.Resident):
    """Physical journal bounds before durable commit, not admission decisions."""
    def __init__(self, *args, max_entries, journal_bytes, **kwargs):
        self.max_entries, self.journal_bytes = max_entries, journal_bytes
        super().__init__(*args, **kwargs)

    def _persist(self, entry):
        size = len(encoded(entry))
        count, used = self.connection.execute('SELECT count(*), coalesce(sum(length(frame)),0) FROM entries').fetchone()
        if count >= self.max_entries or size > MAX_EVALUATION or used + size > self.journal_bytes:
            raise HeapLimit('private heap journal quota reached')
        super()._persist(entry)


class HeapManager:
    def __init__(self, root, shared_database, *, shared_profile='compiled', shared_world='shared',
                 max_accounts=64, max_active=4, max_entries=1024, journal_bytes=16*1024*1024,
                 operation_bytes=16*1024*1024, artifact_bytes=256*1024*1024,
                 max_pending=4, timeout=10, welcome=None, model_provider=None,
                 resident_memory_bytes=DEFAULT_RESIDENT_MEMORY):
        if (any(type(value) is not int or value <= 0 for value in
                (max_accounts, max_active, max_entries, journal_bytes, operation_bytes, artifact_bytes, max_pending))
                or max_active > max_accounts or not math.isfinite(timeout) or not 0 < timeout <= 30):
            raise ValueError('invalid heap custody limits')
        if shared_profile not in world.PROFILES or not isinstance(shared_world, str) or not shared_world:
            raise ValueError('explicit shared profile and world identity required')
        if welcome is not None and (not isinstance(welcome, dict) or set(welcome) != {'object', 'principal'}
                or any(not isinstance(v, str) or not v or len(v.encode()) > 256 for v in welcome.values())
                or shared_profile != 'compiled'):
            raise ValueError('welcome requires explicit compiled object and service principal')
        self.welcome_config = None if welcome is None else dict(welcome)
        if model_provider is not None and not callable(model_provider):
            raise ValueError('explicit model provider must be callable')
        if resident_memory_bytes is not None and (type(resident_memory_bytes) is not int
                or resident_memory_bytes <= 0 or not sys.platform.startswith('linux')):
            raise ValueError('explicit resident memory bound requires Linux and positive bytes')
        self.model_provider, self.resident_memory_bytes = model_provider, resident_memory_bytes
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.lock = (self.root / 'manager.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise ValueError('private heap custody already has a manager') from None
        keyfile = self.root / 'identity.key'
        try:
            if keyfile.is_symlink(): raise ValueError('invalid private custody key')
            if not keyfile.exists():
                with keyfile.open('xb') as stream:
                    os.chmod(keyfile, 0o600)
                    stream.write(secrets.token_bytes(32)); stream.flush(); os.fsync(stream.fileno())
                fd = os.open(self.root, os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
            self.secret = keyfile.read_bytes()
            if len(self.secret) != 32:
                raise ValueError('private heap custody identity is invalid')
            self.shared_database, self.shared_profile, self.shared_world = Path(shared_database).resolve(), shared_profile, shared_world
            binding = {'format': 'delvetalk-account-realms-v1', 'sharedDatabase': str(self.shared_database),
                       'sharedWorld': shared_world, 'sharedProfile': shared_profile}
            realm_file = self.root / 'realms.json'
            if realm_file.exists():
                if encoded(world.wire_loads(realm_file.read_bytes())) != encoded(binding):
                    raise ValueError('account custody belongs to another shared realm')
            else:
                self._write(realm_file, binding)
            self.max_accounts, self.max_active = max_accounts, max_active
            self.max_entries, self.journal_bytes, self.operation_bytes = max_entries, journal_bytes, operation_bytes
            self.artifact_bytes = artifact_bytes
            self.timeout = timeout
            self.active = OrderedDict()
            self._protocols = None
            self._package_session = package_session.PackageSession(
                [ROOT / '.lake/build/bin/delvetalk-obend'], cwd=ROOT,
                stdout_limit=MAX_EVALUATION, stderr_limit=64*1024)
            self.pending = threading.BoundedSemaphore(max_pending)
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='native-heaps')
            self.closed = False
        except BaseException:
            self.lock.close()
            raise

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def close(self):
        if self.closed: return
        self.closed = True
        def stop():
            self._package_session.close()
            for resident in self.active.values(): resident.close()
            self.active.clear()
        self.executor.submit(stop).result()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.lock.close()

    def _call(self, function, *arguments):
        if self.closed: raise ValueError('heap custody is closed')
        if not self.pending.acquire(blocking=False): raise HeapLimit('heap receiver is busy; retry later')
        try:
            future = self.executor.submit(self._guarded, function, arguments)
        except BaseException:
            self.pending.release()
            raise
        future.add_done_callback(lambda _: self.pending.release())
        try:
            return future.result(timeout=self.timeout * 4 + 5)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError('heap request deadline reached; retry the same intent') from None

    def _guarded(self, function, arguments):
        try:
            return function(*arguments)
        finally:
            for key, resident in list(self.active.items()):
                if resident.uncertain is not None or resident.process is None:
                    self.active.pop(key).close()

    def _identity(self, identity):
        if (not isinstance(identity, dict) or set(identity) != {'accountId', 'did'}
                or not isinstance(identity['accountId'], str) or not ACCOUNT.fullmatch(identity['accountId'])
                or not isinstance(identity['did'], str) or not identity['did'].startswith('did:')
                or len(identity['did'].encode()) > 256):
            raise ValueError('verified account identity required')
        key = hmac.new(self.secret, identity['accountId'].encode(), hashlib.sha256).hexdigest()
        return dict(identity), key

    def shared_create_prefix(self, identity):
        identity, _ = self._identity(identity)
        return 'agent:' + identity['accountId'] + ':'

    def _directory(self, identity, key):
        directory = self.root / key
        if directory.is_symlink(): raise ValueError('invalid private custody directory')
        if not directory.exists():
            if sum(path.is_dir() for path in self.root.iterdir()) >= self.max_accounts:
                raise HeapLimit('account heap quota reached')
            directory.mkdir(mode=0o700)
        metadata = directory / 'identity.json'
        if metadata.exists():
            if world.wire_loads(metadata.read_bytes()) != identity:
                raise ValueError('private account binding differs')
        else:
            self._write(metadata, identity)
        return directory

    def _write(self, path, value):
        raw = encoded(value)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(path.name + '.pending')
        with temporary.open('wb') as stream:
            os.chmod(temporary, 0o600)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def _save_encounter(self, path, value):
        files = list(path.parent.parent.glob('*/*.json'))
        used = sum(item.stat().st_size for item in files if item != path)
        if ((not path.exists() and len(files) >= self.max_entries)
                or used + len(encoded(value)) > self.operation_bytes):
            raise HeapLimit('account encounter custody quota reached')
        self._write(path, value)

    def _operation(self, directory, realm, intent, value=None):
        folder = directory / 'operations'
        path = folder / (digest([realm, intent]) + '.json')
        if value is not None:
            raw = encoded(value)
            files = list(folder.glob('*.json')) if folder.exists() else []
            size = sum(item.stat().st_size for item in files if item != path)
            if len(raw) > 2 * MAX_EVALUATION or size + len(raw) > self.operation_bytes:
                raise HeapLimit('private operation custody quota reached')
            if not path.exists() and len(files) >= self.max_entries:
                raise HeapLimit('private operation count quota reached')
            self._write(path, value)
        return world.wire_loads(path.read_bytes()) if path.exists() else None

    def _seed_protocols(self):
        if self._protocols is None:
            notebook = _module('account_notebook_source', 'protocols/account-heap/generate.py').notebook()
            candidate = _module('account_source_candidate', 'protocols/editor/generate.py').candidate(editor_mode=False)
            self._protocols = [('notebook', notebook), ('source-desk', candidate)]
        return self._protocols

    def _seed_requests(self, identity, key, directory, resident):
        path = directory / 'seed.json'
        binding = {'format': 'delvetalk-account-seed-v1', 'identity': identity,
                   'world': 'urn:delvetalk:heap:' + key}
        if path.exists():
            saved = world.wire_loads(path.read_bytes())
            if (not isinstance(saved, dict) or set(saved) != set(binding) | {'requests', 'sha256'}
                    or encoded({name: saved[name] for name in binding}) != encoded(binding)
                    or digest(saved['requests']) != saved['sha256']):
                raise ValueError('private seed custody binding differs')
            requests = saved['requests']
            if (not isinstance(requests, list) or len(requests) != 3
                    or requests[0] != {'op': 'messages-init', 'principal': identity['did'],
                        'intent': RESERVED + 'messages', 'lineage': binding['world'], 'pendingLimit': 128}):
                raise ValueError('private seed custody schema differs')
            for request, object_id in zip(requests[1:], ('notebook', 'source-desk')):
                if (not isinstance(request, dict)
                        or set(request) != {'op', 'object', 'principal', 'intent', 'protocol', 'law'}
                        or encoded({k: v for k, v in request.items() if k != 'protocol'}) != encoded({
                            'op': 'create', 'object': object_id, 'principal': identity['did'],
                            'intent': RESERVED + object_id, 'law': [identity['did']]})):
                    raise ValueError('private seed request binding differs')
            return requests
        if resident.sequence:
            raise ValueError('nonempty private heap has no original seed custody; implicit reseeding is forbidden')
        requests = [{'op': 'messages-init', 'principal': identity['did'],
            'intent': RESERVED + 'messages', 'lineage': binding['world'], 'pendingLimit': 128}]
        requests.extend({'op': 'create', 'object': object_id, 'principal': identity['did'],
            'intent': RESERVED + object_id, 'protocol': protocol, 'law': [identity['did']]}
            for object_id, protocol in self._seed_protocols())
        # All descriptors are durable before even the first bootstrap admission.
        self._write(path, {**binding, 'requests': requests, 'sha256': digest(requests)})
        return requests

    def _resident(self, identity, key, directory):
        if key in self.active:
            resident = self.active.pop(key)
            self.active[key] = resident
            return resident
        if len(self.active) >= self.max_active:
            _, old = self.active.popitem(last=False)
            old.close()
        resident = QuotaResident(directory / 'heap.sqlite3', profile='compiled', timeout=self.timeout,
                                 max_entries=self.max_entries, journal_bytes=self.journal_bytes,
                                 **({'memory_bytes': self.resident_memory_bytes} if self.resident_memory_bytes is not None else {}))
        try:
            for request in self._seed_requests(identity, key, directory, resident):
                reply = resident.exchange(request)
                if reply.get('kind') != 'committed': raise ValueError('private source bootstrap refused')
        except BaseException:
            resident.close()
            raise
        self.active[key] = resident
        return resident

    def _context(self, identity, realm):
        identity, key = self._identity(identity)
        if realm not in ('private', 'shared'): raise ValueError('unknown account realm')
        directory = self._directory(identity, key)
        resident = self._resident(identity, key, directory) if realm == 'private' else None
        return identity, key, directory, resident

    def _exchange(self, resident, request):
        return (resident.exchange(request) if resident else
                world.exchange(self.shared_database, request, profile=self.shared_profile, timeout=self.timeout))

    def _lookup(self, resident, request):
        return (resident.retained_reply(request) if resident else
                world.retained_reply(self.shared_database, request, timeout=self.timeout))

    def _request(self, identity, request):
        if not isinstance(request, dict) or 'principal' in request:
            raise ValueError('account requests must omit principal')
        intent = request.get('intent')
        if (not isinstance(intent, str) or not intent or len(intent.encode()) > 256 or intent.startswith(RESERVED)):
            raise ValueError('explicit nonreserved intent required')
        if len(encoded(request)) > MAX_REQUEST: raise HeapLimit('account request exceeds 256 KiB')
        return {**request, 'principal': identity['did']}

    def turn(self, identity, realm, request):
        return self._call(self._turn, identity, realm, request)

    def _turn(self, identity, realm, request):
        identity, key, directory, resident = self._context(identity, realm)
        request = self._request(identity, request)
        if (realm == 'shared' and request.get('op') == 'create'
                and (not isinstance(request.get('object'), str)
                     or not request['object'].startswith(self.shared_create_prefix(identity)))):
            raise ValueError('shared account creations require the assigned agent namespace')
        operation = {'kind': 'turn', 'request': request}
        prior = self._operation(directory, realm, request['intent'])
        if prior is not None and encoded(prior) != encoded(operation):
            raise ValueError('intent already belongs to a different account operation')
        if prior is None: self._operation(directory, realm, request['intent'], operation)
        try:
            return self._exchange(resident, request)
        except BaseException:
            if resident:
                self.active.pop(key, None)
                resident.close()
            raise

    def catalogue(self, identity, realm='private', *, cursor=None, limit=32):
        return self._call(self._catalogue, identity, realm, cursor, limit)

    def _catalogue(self, identity, realm, cursor, limit):
        identity, key, directory, resident = self._context(identity, realm)
        page = world.catalogue_page(None if resident else self.shared_database,
            principal=identity['did'], cursor=cursor, limit=limit,
            profile='compiled' if resident else self.shared_profile,
            timeout=self.timeout, receiver=resident)
        return {'realm': realm, 'world': 'urn:delvetalk:heap:' + key if resident else self.shared_world,
                'sharedCreatePrefix': self.shared_create_prefix(identity),
                'defaultObject': 'notebook' if resident else None,
                'residentMemoryBytes': self.resident_memory_bytes if resident else None,
                'objects': page['objects'], 'nextCursor': page['nextCursor'],
                'head': {'sequence': page['sequence'], 'head': page['head']}}

    def inspect(self, identity, realm, object_id):
        return self._call(self._inspect, identity, realm, object_id)

    def _inspect(self, identity, realm, object_id):
        identity, _, _, resident = self._context(identity, realm)
        if not isinstance(object_id, str) or not object_id or len(object_id.encode()) > 256:
            raise ValueError('object identity required')
        return self._exchange(resident, {'op': 'inspect', 'object': object_id, 'principal': identity['did']})

    def receipt(self, identity, realm, intent):
        return self._call(self._receipt, identity, realm, intent)

    def _receipt(self, identity, realm, intent):
        identity, _, directory, resident = self._context(identity, realm)
        if not isinstance(intent, str) or not intent or len(intent.encode()) > 256:
            raise ValueError('intent required')
        operation = self._operation(directory, realm, intent)
        if operation is None or 'request' not in operation: return None
        if operation['request'].get('principal') != identity['did']:
            raise ValueError('receipt account binding differs')
        return self._lookup(resident, operation['request'])

    def repl(self, identity, realm, intent, specification):
        return self._call(self._repl, identity, realm, intent, specification)

    def _evaluate(self, specification):
        limits = {'ticks': '100000', 'heap': '100000', 'stack': '10000', 'typeFuel': '16384'}
        runner = ROOT / '.lake/build/bin/delvetalk-obend'
        def evaluation_pins():
            return {**runtime_profile.file_hashes('compiled'), **runtime_profile.hash_paths(
                ('scripts/package_session.py', 'spec/PackageMain.lean'))}
        pins = evaluation_pins()
        runner_hash = hashlib.sha256(runner.read_bytes()).hexdigest()
        def native(request):
            try:
                raw = self._package_session.exchange(encoded(request) + b'\n',
                    timeout=min(10, self.timeout), identity=(pins, runner_hash))
            except (subprocess.TimeoutExpired, process_custody.OutputLimitExceeded):
                return {'status': 'failed', 'message': 'native evaluation exceeded custody limits'}
            except (OSError, RuntimeError):
                return {'status': 'failed', 'message': 'native evaluation failed within custody limits'}
            try: return world.wire_loads(raw)
            except (ValueError, UnicodeError):
                self._package_session.close()
                raise ValueError('native evaluation returned invalid framing') from None
        compiled = native({'op': 'compile', 'modules': specification['modules'],
                           'entry': specification['entry'], 'limits': limits})
        result = compiled if compiled.get('status') != 'compiled' else native({
            'op': 'run-data-v1', 'artifact': compiled['artifact'],
            'arguments': specification['arguments'], 'limits': limits})
        if pins != evaluation_pins() or runner_hash != hashlib.sha256(runner.read_bytes()).hexdigest():
            self._package_session.close()
            raise ValueError('native evaluation runtime changed; no result admitted')
        return {**result, 'runtime': {'profile': 'compiled', 'files': pins, 'packageBinarySha256': runner_hash}}

    def _repl(self, identity, realm, intent, specification):
        if realm != 'private': raise ValueError('evaluation notebooks are private; publish through an explicit shared turn')
        identity, _, directory, resident = self._context(identity, realm)
        self._request(identity, {'intent': intent})
        if (not isinstance(specification, dict) or set(specification) != {'modules', 'entry', 'arguments'}
                or not isinstance(specification['modules'], list) or not 1 <= len(specification['modules']) <= 16
                or any(not isinstance(m, dict) or set(m) != {'name', 'source'}
                       or not isinstance(m['name'], str) or not isinstance(m['source'], str)
                       for m in specification['modules'])
                or not isinstance(specification['entry'], str) or not isinstance(specification['arguments'], list)
                or len(encoded(specification)) > 64*1024):
            raise ValueError('evaluation requires a sealed bounded source module table, entry and DataWire arguments')
        operation = self._operation(directory, realm, intent)
        if operation is not None:
            if operation.get('kind') != 'repl' or encoded(operation.get('specification')) != encoded(specification):
                raise ValueError('intent already belongs to a different account operation')
        else:
            operation = {'kind': 'repl', 'specification': specification,
                         'expected': resident.exchange({'op': 'inspect', 'object': 'notebook', 'principal': identity['did']})}
            self._operation(directory, realm, intent, operation)
        if 'request' not in operation:
            evaluation = operation.get('evaluation')
            if evaluation is None:
                evaluation = self._evaluate(specification)
            operation = {**operation, 'evaluation': evaluation, 'request': {
                'op': 'invoke', 'object': 'notebook', 'principal': identity['did'], 'intent': intent,
                'expected': operation['expected'], 'command': 'record',
                'input': {'source': encoded(specification).decode(), 'result': encoded(evaluation).decode()}}}
            self._operation(directory, realm, intent, operation)
        reply = self._lookup(resident, operation['request'])
        if reply is None: reply = resident.exchange(operation['request'])
        return {'evaluation': operation['evaluation'], 'receipt': reply}

    def check(self, identity, realm, object_id, intent, expected):
        return self._call(self._check, identity, realm, object_id, intent, expected)

    def _check(self, identity, realm, object_id, intent, expected):
        if realm != 'private': raise ValueError('private compiler checks require the private realm')
        identity, _, directory, resident = self._context(identity, realm)
        self._request(identity, {'intent': intent})
        operation = {'kind': 'check', 'object': object_id, 'expected': expected}
        prior = self._operation(directory, realm, intent)
        if prior is not None and encoded({key: prior.get(key) for key in operation}) != encoded(operation):
            raise ValueError('intent already belongs to a different account operation')
        if prior is None: self._operation(directory, realm, intent, operation)
        class NativeDesk(desk.Desk):
            def exchange(self, request): return resident.exchange(request)
            def retained_reply(self, request): return resident.retained_reply(request)
        compiler = NativeDesk(directory / 'world.json', directory / 'artifacts', profile='compiled')
        inputs = {'object': object_id, 'principal': identity['did'], 'intent': intent, 'expected': expected}
        prepared = compiler.check_attempt(inputs)
        if prepared is None:
            profile = desk.execution_profile('compiled')
            build = desk.bounded_compile(expected, profile='compiled', artifact_store=compiler.artifact_store,
                                         timeout=self.timeout)
            self._reserve_artifact(compiler.artifact_store, build)
            prepared = compiler.prepare_check(inputs, build, profile)
        self._operation(directory, realm, intent, {**operation, 'request': prepared['request']})
        retained = resident.retained_reply(prepared['request'])
        if retained is not None: return retained
        self._reserve_artifact(compiler.artifact_store,
                               desk.load_artifact(compiler.artifact_store, prepared['request']['input']['artifact']))
        return compiler.admit_check(prepared)

    def _reserve_artifact(self, store, build):
        """Reserve bounded build/attempt bytes and exact missing dependency sizes."""
        import history
        if len(encoded(build)) > MAX_EVALUATION:
            raise HeapLimit('private compiler artifact exceeds 512 KiB')
        used = sum(path.stat().st_size for path in store.rglob('*') if path.is_file()) if store.exists() else 0
        missing = {}
        for name, sha in history.declared_files(build).items():
            if not (store / 'pins/blobs' / sha).exists():
                source = (ROOT / name).resolve()
                if not source.is_relative_to(ROOT): raise ValueError('compiler dependency escapes installation')
                missing[sha] = source.stat().st_size
        # Build + optional room envelope + attempt (captured root, request and
        # runtime pins) all derive from this bounded build and bounded request.
        reserve = sum(missing.values()) + 4 * MAX_EVALUATION
        if used + reserve > self.artifact_bytes:
            raise HeapLimit('private compiler artifact custody quota reached')

    def _portal(self, identity, realm):
        """Reuse authored encounters and native preparation with isolated custody."""
        import portal
        import bootstrap
        manager = self
        identity, key, directory, resident = self._context(identity, realm)
        class AccountPortal(portal.Portal):
            def __init__(self):
                self.directory = directory if resident else manager.shared_database.parent
                # Existing source-offer code supports expanded captured roots with
                # no live database. Its pure native preparation never refreshes them.
                self.database = None
                self.profile = 'compiled' if resident else manager.shared_profile
                self.runtime = bootstrap.history.runtime(self.profile)
                self.metadata = {'format': 'delvetalk-workspace-v1',
                    'worldId': 'urn:delvetalk:heap:' + key if resident else manager.shared_world,
                    'title': 'Private heap' if resident else 'Shared world',
                    'defaultObject': 'notebook', 'entryObjects': ['notebook']}
                self.public, self.interactive, self.proposer = False, True, None
                self.public_origin, self.principal, self.csrf = None, identity['did'], None
                self.state = directory / 'encounters' / realm
                for name in ('cards', 'drafts', 'interpretations', 'preparations'):
                    (self.state / name).mkdir(parents=True, exist_ok=True, mode=0o700)

            def snapshot(self):
                return resident.export_world() if resident else world.snapshot(manager.shared_database, timeout=manager.timeout)

            def capture_roots(self, objects, *, expected=None):
                return world.capture_roots(None if resident else manager.shared_database, objects,
                    principal=identity['did'], profile=self.profile, timeout=manager.timeout,
                    expected=expected, receiver=resident)

            def authorize_reads(self, objects):
                request = {'op': 'authorize-reads', 'principal': identity['did'], 'objects': objects}
                return (resident.query(request) if resident else world.query(manager.shared_database,
                    request, profile=self.profile, timeout=manager.timeout))

            def history_page(self, object_id, before, *, offset=0):
                request = {'op': 'object-history', 'principal': identity['did'],
                    'object': object_id, 'before': before, 'offset': offset, 'limit': 32}
                return (resident.query(request) if resident else world.query(manager.shared_database,
                    request, profile=self.profile, timeout=manager.timeout))

            def prepare_invitation(self, invitation, principal, intent, fields):
                import source_offers
                return source_offers.prepare(invitation, principal, intent, fields,
                    database=None if resident else manager.shared_database, receiver=resident)

            def _store(self, category, value):
                token = portal.identifier()
                manager._save_encounter(self.state / category / (token + '.json'), value)
                return token

            def _retained(self, request):
                if request.get('principal') != identity['did']:
                    raise ValueError('receipt account binding differs')
                return manager._lookup(resident, request)

            def draft(self, token):
                saved = self._read('drafts', token)
                # The native receipt owns the outcome; a presentation quota must
                # never prevent recovery of a durably admitted request.
                reply = self._retained(saved['request'])
                self.authorize_saved_request(saved)
                if saved.get('interpretation'):
                    return {'draft': token, 'intent': saved['request']['intent'],
                        'interpretation': saved['interpretation'], 'object': saved['object'],
                        'version': saved['version'], 'summary': saved['summary'],
                        'command': saved['command'], 'fields': {}, 'canExecute': True,
                        'wire': saved['wire'], 'wireJson': encoded(saved['wire']).decode(),
                        'outcome': reply['kind'] if reply is not None else None,
                        'links': {'self': '/api/draft?draft=' + token, 'execute': '/api/execute'}}
                result = super().draft(token)
                result['intent'] = saved['request']['intent']
                result['outcome'] = reply['kind'] if reply is not None else None
                return result

            def execute(self, payload):
                portal.exact(payload, ('draft',))
                saved = self._read('drafts', payload['draft'])
                request = saved['request']
                if request['principal'] != identity['did'] or saved['localPrincipal'] != identity['did']:
                    raise ValueError('draft account binding differs')
                reply = self._retained(request)
                if reply is None:
                    self._pins(saved)
                    reply = manager._turn(identity, realm, {k: v for k, v in request.items() if k != 'principal'})
                return {'kind': reply['kind'], 'draft': payload['draft'], 'intent': request['intent'],
                        'reply': reply, 'children': self.child_links(reply),
                        'summary': 'Action committed.' if reply['kind'] == 'committed' else str(reply.get('data'))}
        return AccountPortal()

    def encounter(self, identity, realm, object_id, panel='main'):
        return self._call(lambda: self._portal(identity, realm).object(object_id, panel))

    def prepare(self, identity, realm, payload):
        return self._call(lambda: self._portal(identity, realm).prepare(payload))

    def execute(self, identity, realm, payload):
        return self._call(lambda: self._portal(identity, realm).execute(payload))

    def child(self, identity, realm, card, key):
        return self._call(lambda: self._portal(identity, realm).child(card, key))

    def interpretation(self, identity, realm, payload):
        return self._call(self._interpretation, identity, realm, payload)

    def _interpretation(self, identity, realm, payload):
        import account_interpretation
        return account_interpretation.run(self, identity, realm, payload)

    def reading(self, identity, realm, kind, reference):
        if kind == 'interpretation':
            return self._call(lambda: {**self._portal(identity, realm)._read('interpretations', reference),
                                      'interpretation': reference})
        if kind not in ('card', 'draft', 'preparation', 'detail'):
            raise ValueError('unknown saved account encounter')
        return self._call(lambda: getattr(self._portal(identity, realm), kind)(reference))

    def welcome(self, identity, proof):
        """Trusted verification hook, never an account-selected service identity."""
        return self._call(self._welcome, identity, proof)

    def _welcome(self, identity, proof):
        if self.welcome_config is None:
            return {'status': 'unconfigured'}
        identity, key = self._identity(identity)
        if (not isinstance(proof, dict) or set(proof) != {'uri', 'cid', 'basis'}
                or any(not isinstance(v, str) or not v or len(v.encode()) > 2048 for v in proof.values())):
            raise ValueError('trusted verification evidence required')
        directory = self._directory(identity, key)
        retained = directory / 'welcome-proof.json'
        if retained.exists():
            proof = world.wire_loads(retained.read_bytes())
        else:
            self._write(retained, proof)
        service = _module('account_membership_service', 'protocols/membership/service.py')
        return service.enroll(self.shared_database, self.welcome_config['object'],
            self.welcome_config['principal'], identity['did'], proof, 'account-welcome:' + key,
            profile=self.shared_profile, custody=directory / 'welcome', timeout=self.timeout)

    def checkpoint(self, identity):
        """Operator/internal API only; HTTP does not expose physical exports."""
        return self._call(self._checkpoint, identity)

    def _checkpoint(self, identity):
        _, _, _, resident = self._context(identity, 'private')
        return resident.checkpoint()
