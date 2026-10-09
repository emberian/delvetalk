"""Retained portal authoring; source custody and explicit Lean requests only."""
import re
import secrets

import desk
import compiler_queue
import submission
from delve import save

canonical, loads, digest = desk.canonical, desk.loads, desk.digest
HEX = re.compile(r'[0-9a-f]{64}\Z')
MAX_SOURCE = 524288
MAX_UPLOAD = 7 * 1048576


def exact(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError('Missing or unknown authoring fields')


def identity(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError('Invalid authoring reference')
    return value


class Authoring:
    def __init__(self, portal):
        self.portal = portal
        self.state = portal.state / 'authoring'
        self.artifacts = portal.directory / 'artifacts'
        (self.state / 'drafts').mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.state / 'results').mkdir(exist_ok=True, mode=0o700)

    def source(self, payload):
        import source_store
        exact(payload, ('text',), ('kind',))
        if not isinstance(payload['text'], str):
            raise ValueError('Source text must be UTF-8 text')
        kind = payload.get('kind', 'source')
        ref = source_store.store_bytes(self.artifacts, payload['text'].encode('utf-8'), kind=kind)
        return {'source': ref['sha256'], 'bytes': ref['bytes'], 'ref': ref}

    def read_source(self, source, kind='source'):
        import source_store
        ref = source_store.ref_for(self.artifacts, identity(source), kind=kind)
        raw = source_store.read_bytes(self.artifacts, ref, kind=kind)
        return {'source': source, 'bytes': len(raw), 'ref': ref, 'text': raw.decode('utf-8')}

    def catalog(self, snapshot):
        registry = loads((desk.ROOT / 'syntaxes/registry.json').read_bytes())
        return {'syntaxes': sorted(registry['syntaxes']),
                'candidates': [name for name, root in snapshot['objects'].items()
                               if root['protocol'].get('name') == 'source-desk-v1'],
                'maxSourceBytes': MAX_SOURCE,
                'links': {'prepare': '/api/authoring/prepare', 'source': '/api/authoring/source'}}

    def _read(self, key):
        value = loads((self.state / 'drafts' / (identity(key) + '.json')).read_bytes())
        if digest(value) != key:
            raise ValueError('Saved authoring draft identity mismatch')
        return value

    def _result(self, key):
        path = self.state / 'results' / (identity(key) + '.json')
        return loads(path.read_bytes()) if path.exists() else {}

    def prepare(self, payload):
        operation = payload.get('operation') if isinstance(payload, dict) else None
        fields = {'submit': ('candidate', 'target', 'syntax', 'source', 'scenarios', 'migrationJson'),
                  'compile': ('candidate',), 'adopt': ('candidate', 'target')}
        if operation not in fields:
            raise ValueError('Unknown authoring operation')
        exact(payload, ('operation', *fields[operation]))
        roots = self.portal.snapshot()['objects']
        candidate = payload['candidate']
        if not isinstance(candidate, str) or candidate not in roots:
            raise ValueError('Unknown candidate object')
        expected = roots[candidate]
        principal = self.portal.principal or 'portal-preview'
        intent = 'portal-authoring:' + secrets.token_hex(16)
        request = None
        target = payload.get('target')
        if operation == 'submit':
            import source_store
            if not isinstance(target, str) or target not in roots:
                raise ValueError('Unknown target object')
            migration = loads(payload['migrationJson'])
            if not isinstance(migration, dict):
                raise ValueError('Migration must be a complete state object')
            proposal = source_store.prepare_proposal(self.artifacts, payload['syntax'],
                self.read_source(payload['source'])['text'].encode('utf-8'),
                self.read_source(payload['scenarios'], 'scenarios')['text'].encode('utf-8'))
            request = {'op': 'invoke', 'object': candidate, 'principal': principal, 'intent': intent,
                       'expected': expected, 'command': 'submit',
                       'input': {'proposal': proposal, 'migration': migration, 'target': target}}
        elif operation == 'adopt':
            if not isinstance(target, str) or target not in roots or target == candidate:
                raise ValueError('Adoption requires a distinct existing target')
            request = {'op': 'transaction', 'principal': principal, 'intent': intent,
                       'reads': {candidate: expected, target: roots[target]},
                       'calls': [{'object': candidate, 'command': 'adopt', 'input': {'target': target}},
                                 {'op': 'reprogram', 'object': target, 'inputFrom': 0}]}
        if request is not None and len(canonical(request)) > 65536:
            raise ValueError('Exact request exceeds the 65536-byte host envelope')
        draft = {'format': 'delvetalk-authoring-draft-v1', 'operation': operation,
                 'candidate': candidate, 'target': target, 'principal': principal, 'intent': intent,
                 'expected': expected, 'request': request, 'runtime': self.portal.runtime,
                 'localPrincipal': self.portal.principal}
        key = digest(draft)
        with self.portal.custody_lock(self.state / 'prepare.lock'):
            if sum(1 for _ in (self.state / 'drafts').glob('*.json')) >= 4096:
                raise ValueError('Authoring custody is full')
            if canonical(desk.immutable(self.state / 'drafts' / (key + '.json'), draft)) != canonical(draft):
                raise ValueError('Authoring identity collision')
        return self.draft(key)

    def _allowed(self, saved):
        return self.portal.interactive and saved['localPrincipal'] == self.portal.principal

    def draft(self, key):
        saved, result = self._read(key), self._result(key)
        request = saved['request']
        wire = ({k: v for k, v in request.items() if k not in ('principal', 'intent')}
                if request else {'operation': 'compile', 'candidate': saved['candidate'], 'expected': saved['expected']})
        return {'draft': key, 'operation': saved['operation'], 'candidate': saved['candidate'],
                'target': saved['target'], 'principal': saved['principal'],
                'summary': {'submit': 'Submit retained source proposal', 'compile': 'Compile captured candidate',
                            'adopt': 'Adopt into the captured target root'}[saved['operation']],
                'canExecute': self._allowed(saved), 'wireJson': canonical(wire).decode(),
                'requestJson': canonical(request).decode(), 'job': result.get('job'),
                'outcome': result.get('receipt', {}).get('kind'),
                'links': {'self': '/api/authoring/draft?draft=' + key,
                          'status': '/api/authoring/status?draft=' + key,
                          'execute': '/api/authoring/execute', 'run': '/api/authoring/run'}}

    def _authorize(self, saved):
        if not self._allowed(saved) or saved['principal'] != self.portal.principal:
            raise PermissionError('Execution requires this draft’s explicitly configured local principal')

    def _queue(self, key):
        return compiler_queue.CompilerQueue(self.state / 'queues' / key, self.portal.database,
                                            self.artifacts, profile=self.portal.profile)

    def execute(self, payload):
        exact(payload, ('draft',))
        key = identity(payload['draft'])
        with self.portal.custody_lock(self.state / 'execute.lock'):
            saved, result = self._read(key), self._result(key)
            self._authorize(saved)
            if saved['operation'] == 'compile':
                if not result.get('job'):
                    queue = self._queue(key)
                    # An enqueue reply can be lost after immutable job publication.
                    # enqueue validates and recovers that same intent before pins.
                    if not any((queue.state / 'jobs').glob('*.json')):
                        self._pins(saved)
                    job = queue.enqueue(saved['candidate'], saved['principal'], saved['intent'], saved['expected'])
                    result = {'job': job['job']}
                    save(self.state / 'results' / (key + '.json'), result)
            else:
                reply, error = submission.execute(self.portal, saved, result.get('receipt'), self.state, self._pins)
                if error:
                    return {'kind': 'uncertain', 'draft': key,
                            'summary': 'Retry this saved draft to recover its exact receipt.', 'detail': error}
                save(self.state / 'results' / (key + '.json'), {'receipt': reply})
        return self.status(key)

    def _pins(self, saved):
        if canonical(self.portal.current_runtime()) != canonical(saved['runtime']):
            raise ValueError('Runtime pins changed; retain this pending draft')

    def run(self, payload):
        exact(payload, ('draft',))
        key = identity(payload['draft'])
        saved = self._read(key)
        self._authorize(saved)
        if saved['operation'] != 'compile' or not self._result(key).get('job'):
            raise ValueError('Enqueue this compile draft before running it')
        queue = self._queue(key)
        job = self._result(key)['job']
        if queue.inspect(job).get('attempts', 0) >= 3:
            queue.retry(job)  # A new explicit Run grants a new bounded attempt, preserving the job.
        queue.run(limit=1, deadline_seconds=30)
        return self.status(key)

    def status(self, key):
        saved, result = self._read(key), self._result(key)
        status = {'draft': key, 'operation': saved['operation'], 'job': result.get('job'),
                  'phase': 'finished' if result.get('receipt') else 'prepared',
                  'receipt': result.get('receipt'), 'diagnostics': [], 'errors': [], 'artifact': None,
                  'canExecute': self._allowed(saved)}
        if result.get('job'):
            job = self._queue(key).inspect(result['job'])
            status.update(phase=job['phase'], receipt=job.get('receipt'), errors=job.get('errors', []), artifact=job.get('artifact'))
            if status['artifact']:
                try:
                    artifact = desk.load_artifact(self.artifacts, status['artifact'])
                    status['diagnostics'] = artifact.get('diagnostics', [])
                except (ValueError, OSError) as error:
                    if status['receipt'] is None:
                        raise
                    # Artifact availability cannot invalidate historical admission.
                    status['artifactStatus'] = 'unavailable'
                    status['artifactError'] = type(error).__name__
                else:
                    status['artifactStatus'] = 'available'
        status['exactJson'] = canonical(status).decode()
        return status
