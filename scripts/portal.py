#!/usr/bin/env python3
"""Loopback portal: saved affordances, explicit drafts, existing Lean admission."""
import argparse
import base64
import copy
from collections import OrderedDict
from contextlib import contextmanager
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
import affordances
import interpret
import submission
from delve import save

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'portal/static'
IDENTITY = re.compile(r'[a-z2-7]{12}\Z')
MAX_BODY = 65536
MAX_SAVED = 4096
LOCK_TIMEOUT = 10
PUBLIC_CACHE_TTL = 900
PUBLIC_CACHE_ENTRIES = 256
PUBLIC_CACHE_BYTES = 8 * 1024 * 1024
loads, canonical = bootstrap.history.loads, bootstrap.history.canonical


@contextmanager
def bounded_lock(path):
    with open(path, 'a') as stream:
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('World custody is busy; retry the same request shortly')
                time.sleep(min(0.02, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def identifier():
    return base64.b32encode(secrets.token_bytes(8)).decode().lower()[:12]


def exact(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError('Missing or unknown request fields')


def validate_public_origin(value):
    """Require an exact HTTPS origin, without proxy-header interpretation."""
    if not isinstance(value, str):
        raise ValueError('Public origin must be an exact HTTPS origin')
    parsed = urlsplit(value)
    if (value != 'https://' + parsed.netloc or parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query
            or parsed.fragment or parsed.username is not None or parsed.password is not None
            or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', parsed.hostname)
            or parsed.netloc != parsed.hostname + (':' + str(parsed.port) if parsed.port is not None else '')
            or parsed.port == 0):
        raise ValueError('Public origin must be an exact HTTPS origin with no path or credentials')
    return value


class PreviewCache:
    """Bounded serialized snapshots; aliases expire and confer no durable identity."""
    def __init__(self):
        self.records = OrderedDict()
        self.bytes = 0

    def prune(self):
        now = time.monotonic()
        for key, (expires, raw) in list(self.records.items()):
            if expires <= now:
                del self.records[key]
                self.bytes -= len(raw)

    def store(self, category, value):
        raw = canonical(value)
        if len(raw) > PUBLIC_CACHE_BYTES:
            raise ValueError('This preview exceeds the public cache byte bound')
        self.prune()
        while self.records and (len(self.records) >= PUBLIC_CACHE_ENTRIES
                                or self.bytes + len(raw) > PUBLIC_CACHE_BYTES):
            _, (_, prior) = self.records.popitem(last=False)
            self.bytes -= len(prior)
        for _ in range(5):
            identity = identifier()
            if (category, identity) not in self.records:
                self.records[(category, identity)] = (time.monotonic() + PUBLIC_CACHE_TTL, raw)
                self.bytes += len(raw)
                return identity
        raise RuntimeError('Could not allocate a preview reference')

    def read(self, category, identity):
        self.prune()
        entry = self.records.get((category, identity))
        if entry is None:
            raise ValueError('Preview reference expired or is unknown; read the object again')
        return loads(entry[1])

    def lifetime(self, category, identity):
        self.read(category, identity)
        return max(0, int(self.records[(category, identity)][0] - time.monotonic()))


class Portal:
    def __init__(self, directory, *, state=None, principal=None, allow_local_actions=False, proposer=None,
                 public_origin=None):
        self.public_origin = validate_public_origin(public_origin) if public_origin is not None else None
        self.public = self.public_origin is not None
        if self.public and (principal is not None or allow_local_actions or proposer is not None or state is not None):
            raise ValueError('Public previews cannot configure a principal, local actions, language model or custody directory')
        if self.public:
            # Lazy projection/request imports must not create bytecode on a
            # remotely triggered read, even outside a read-only service mount.
            sys.dont_write_bytecode = True
        self.directory = Path(directory).resolve()
        self.database = self.directory / 'world.json'
        self.metadata = loads((self.directory / 'manifest.json').read_bytes())
        if not self.database.is_file():
            raise ValueError('World database is missing')
        self.runtime = self.metadata.get('runtime')
        if not isinstance(self.runtime, dict):
            raise ValueError('Portal requires an explicitly pinned bootstrap world')
        self.profile = self.runtime['name']
        if allow_local_actions != bool(principal):
            raise ValueError('Local interaction requires both --principal and --allow-local-actions')
        if principal is not None and (not isinstance(principal, str) or not principal or len(principal) > 256):
            raise ValueError('Invalid configured local principal')
        self.principal = principal
        self.interactive = allow_local_actions
        self.proposer = proposer
        self.csrf = secrets.token_urlsafe(32)
        self.state = Path(state).resolve() if state else self.directory / 'portal-custody'
        if self.public:
            self.preview = PreviewCache()
            return
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        binding = {'format': 'delvetalk-portal-custody-v1', 'database': str(self.database), 'runtime': self.runtime}
        stored = bootstrap.desk_module.immutable(self.state / 'binding.json', binding)
        if canonical(stored) != canonical(binding):
            raise ValueError('Portal custody belongs to a different world/runtime')
        for name in ('cards', 'drafts', 'interpretations'):
            (self.state / name).mkdir(exist_ok=True, mode=0o700)

    custody_lock = staticmethod(bounded_lock)

    def current_runtime(self):
        return bootstrap.history.runtime(self.profile)

    @property
    def authoring(self):
        if self.public:
            raise PermissionError('Authoring is unavailable on a public preview')
        from authoring import Authoring
        return Authoring(self)

    def snapshot(self):
        if self.public:
            # world.exchange atomically replaces this file. Inspection needs
            # one complete snapshot, not a newly created/writable lock file.
            return loads(self.database.read_bytes())
        with bounded_lock(str(self.database) + '.lock'):
            return loads(self.database.read_bytes())

    def world(self):
        snapshot = self.snapshot()
        return {'title': self.metadata.get('title', 'DelveTalk · a shared workbench'),
                'mode': 'public-preview' if self.public else 'local-interactive' if self.interactive else 'read-only',
                'principal': self.principal, 'csrf': self.csrf,
                'custody': ({'kind': 'ephemeral', 'ttlSeconds': PUBLIC_CACHE_TTL,
                             'maxEntries': PUBLIC_CACHE_ENTRIES, 'maxBytes': PUBLIC_CACHE_BYTES}
                            if self.public else {'kind': 'durable'}),
                'capabilities': {'execute': self.interactive, 'authoring': not self.public,
                                 'repository': not self.public},
                'worldId': bootstrap.world_id(self.metadata),
                'interpretation': 'model-assisted' if self.proposer else 'copyable-tokens',
                'defaultObject': bootstrap.default_object(self.metadata),
                'authoring': None if self.public else self.authoring.catalog(snapshot),
                'objects': [{'id': name, 'title': name, 'version': root['version'],
                             'href': '/api/object?object=' + quote(name, safe='')}
                            for name, root in snapshot['objects'].items()],
                'scope': ('Public inspection and request export. Preview aliases expire; no action is submitted.'
                          if self.public else 'Local custody. Delve identity and publication are separate.')}

    def _read(self, category, identity):
        if not isinstance(identity, str) or not IDENTITY.fullmatch(identity):
            raise ValueError('Invalid saved reference')
        if self.public:
            return self.preview.read(category, identity)
        path = self.state / category / (identity + '.json')
        if not path.is_file():
            raise ValueError('Unknown saved reference; obtain a card from this portal')
        return loads(path.read_bytes())

    def _store(self, category, value):
        if self.public:
            return self.preview.store(category, value)
        with bounded_lock(self.state / (category + '.lock')):
            if sum(1 for _ in (self.state / category).glob('*.json')) >= MAX_SAVED:
                raise ValueError('Portal custody is full; preserve it and choose a new custody directory')
            for _ in range(5):
                identity = identifier()
                path = self.state / category / (identity + '.json')
                if not path.exists():
                    stored = bootstrap.desk_module.immutable(path, value)
                    if canonical(stored) == canonical(value):
                        return identity
            raise RuntimeError('Could not allocate a saved reference')

    def _view(self, root, object_id, panel):
        artifact = None
        if 'roomArtifact' in root['protocol']:
            binding = root['protocol']['roomArtifact']
            if (not isinstance(binding, dict) or set(binding) != {'format', 'contentSha256'}
                    or binding['format'] != bootstrap.room.FORMAT
                    or not isinstance(binding['contentSha256'], str)
                    or not re.fullmatch(r'[0-9a-f]{64}', binding['contentSha256'])):
                raise ValueError('Invalid admitted room artifact binding')
            admitted_protocol = canonical(root['protocol'])
            # A declaration selects a candidate, never authenticates it. Unrelated
            # damaged files must not prevent reading this admitted room; validate
            # byte identity and the complete contract only for matching candidates.
            for path in sorted((self.directory / 'artifacts/rooms').glob('*.json')):
                try:
                    envelope = loads(path.read_bytes())
                except (OSError, ValueError, UnicodeError):
                    continue
                if not isinstance(envelope, dict) or not isinstance(envelope.get('protocol'), dict):
                    continue
                if envelope['protocol'].get('roomArtifact') != binding:
                    continue
                if canonical(envelope['protocol']) != admitted_protocol:
                    continue
                candidate = bootstrap.room.load_artifact(path.parent, path.stem)
                if canonical(candidate['protocol']) != admitted_protocol:
                    raise ValueError('Bound room artifact protocol differs from the admitted program')
                artifact = candidate
            if artifact is None:
                raise ValueError('Exact bound room artifact is unavailable')
        return bootstrap.room.inspect_object(root, object_id, artifact, panel=panel,
                                             expected_runtime=self.runtime)

    def object(self, object_id=None, panel='main'):
        if not isinstance(panel, str) or len(panel) > 128:
            raise ValueError('Invalid view panel')
        object_id = object_id or bootstrap.default_object(self.metadata)
        snapshot = self.snapshot()
        if object_id not in snapshot['objects']:
            raise ValueError('Unknown object')
        view = self._view(snapshot['objects'][object_id], object_id, panel)
        try:
            card = affordances.card(view)
        except affordances.AffordanceError as error:
            card = {'format': affordances.FORMAT, 'object': object_id,
                    'version': view['root']['version'], 'mode': view['mode'],
                    'title': object_id, 'prose': 'Action metadata is unsupported. Exact source, state and law remain available in Look inside.',
                    'actions': [], 'unsupported': str(error)}
        identity = self._store('cards', {'view': view, 'card': card,
            'historyLength': len(snapshot['receipts']), 'runtime': self.runtime})
        return self.card(identity)

    def object_ref(self, object_id):
        namespace = bootstrap.world_id(self.metadata)
        if namespace is None:
            return {}
        from references import object_reference
        try:
            return {'objectRef': object_reference(namespace, object_id)}
        except ValueError:
            return {'referenceStatus': 'This local object ID cannot be represented by the portable reference format.'}

    def child_links(self, receipt):
        return [{**child, **self.object_ref(child['object']),
                 'href': '/?object=' + quote(child['object'], safe='')}
                for child in affordances.allocated_refs(receipt)]

    def card(self, identity):
        saved = self._read('cards', identity)
        card = copy.deepcopy(saved['card'])
        card.update(self.object_ref(card['object']))
        card.update(card=identity, links={'self': '/api/card?card=' + identity,
            'details': '/api/detail?card=' + identity,
            'refresh': '/api/object?object=' + quote(card['object'], safe=''),
            'prepare': '/api/prepare', 'interpret': '/api/interpret'})
        for action in card['actions']:
            action['token'] = 'do ' + identity + ' ' + action['id']
        if self.public:
            card.update(ephemeral=True, expiresInSeconds=self.preview.lifetime('cards', identity))
        return card

    def detail(self, identity):
        saved = self._read('cards', identity)
        view = saved['view']
        snapshot = self.snapshot()
        def affects(request):
            return (request.get('object') == view['object'] or view['object'] in request.get('reads', {})
                    or view['object'] in request.get('absent', []))
        records = [entry for entry in snapshot['receipts'][:saved['historyLength']] if affects(entry['request'])]
        detail = {'object': view['object'], 'source': bootstrap.room.source_document(view),
                'state': view['root']['state'], 'law': view['root']['law'], 'root': view['root'],
                'history': records, 'runtime': saved['runtime'],
                'scope': 'Exact captured view and retained local admissions; no remote authorship claim.'}
        detail['exact'] = {key: canonical(detail[key]).decode()
                           for key in ('source', 'state', 'law', 'root', 'history', 'runtime')}
        return detail

    def prepare(self, payload):
        exact(payload, ('card', 'action'), ('fields',))
        saved = self._read('cards', payload['card'])
        principal = self.principal or 'portal-preview'
        request = affordances.request(saved['view'], payload['action'], principal,
                    'portal:' + secrets.token_hex(16), payload.get('fields', {}))
        if len(canonical(request)) > MAX_BODY:
            raise ValueError('Exact request exceeds the host envelope; a smaller program/view is required')
        wire = {key: value for key, value in request.items() if key not in ('principal', 'intent')}
        draft = {'card': payload['card'], 'action': payload['action'], 'fields': payload.get('fields', {}),
                 'request': request, 'runtime': saved['runtime'], 'localPrincipal': self.principal,
                 'wire': wire, 'reply': None}
        if self.public:
            # The existing constructor's preview identity is only a framing
            # sentinel. Public custody retains no principal or submission intent.
            action = next(action for action in saved['card']['actions'] if action['id'] == payload['action'])
            draft['request'] = wire
            del draft['localPrincipal']
            draft['presentation'] = {'summary': action['label'],
                                     'token': 'do ' + payload['card'] + ' ' + payload['action']}
        identity = self._store('drafts', draft)
        return self.draft(identity)

    def draft(self, identity):
        saved = self._read('drafts', identity)
        action = ({'label': saved['presentation']['summary'], 'token': saved['presentation']['token']}
                  if self.public else next(a for a in self.card(saved['card'])['actions'] if a['id'] == saved['action']))
        suffix = (' ' + canonical(saved['fields']).decode()) if saved['fields'] else ''
        result = {'draft': identity, 'summary': action['label'], 'command': saved['request']['command'],
                'object': saved['request']['object'], 'version': saved['request']['expected']['version'],
                'canExecute': self.interactive and saved['localPrincipal'] == self.principal,
                'token': action['token'] + suffix, 'wire': saved['wire'],
                'wireJson': canonical(saved['wire']).decode(),
                'links': {'self': '/api/draft?draft=' + identity, 'execute': '/api/execute'},
                'outcome': saved['reply']['kind'] if saved.get('reply') else None,
                'absence': saved['request'].get('absent', []),
                'scope': 'Preparing does not submit. Execute or retry retains this draft’s original intent.'}
        if self.public:
            result.update(ephemeral=True, expiresInSeconds=self.preview.lifetime('drafts', identity),
                          links={'self': '/api/draft?draft=' + identity},
                          scope='Copy the exact request to keep it. Preview aliases may expire or be evicted; no submission identity is retained.')
        return result

    def _retained(self, request):
        for entry in self.snapshot()['receipts']:
            if canonical(entry['request']) == canonical(request):
                return entry['receipt']
        return None

    def _pins(self, saved):
        if canonical(self.current_runtime()) != canonical(saved['runtime']):
            raise ValueError('Runtime pins changed; pending drafts cannot run under a replacement engine')

    def execute(self, payload):
        exact(payload, ('draft',))
        if not self.interactive:
            raise PermissionError('This portal is read-only; export a draft or use an explicitly configured local session')
        identity = payload['draft']
        with bounded_lock(self.state / 'execute.lock'):
            saved = self._read('drafts', identity)
            if saved['localPrincipal'] != self.principal or saved['request']['principal'] != self.principal:
                raise PermissionError('Draft belongs to another configured local principal')
            reply, error = submission.execute(self, saved, saved.get('reply'), self.state, self._pins)
            if error:
                return {'kind': 'uncertain', 'draft': identity,
                        'summary': 'No confirmed outcome. Retry this same draft to recover its receipt.',
                        'detail': error}
            saved['reply'] = reply
            save(self.state / 'drafts' / (identity + '.json'), saved)
            kind = reply['kind']
            return {'kind': kind, 'draft': identity, 'reply': reply,
                    'children': self.child_links(reply),
                    'summary': 'Action committed.' if kind == 'committed' else str(reply.get('data', 'Action refused.')),
                    'links': {'refresh': '/api/object?object=' + quote(saved['request']['object'], safe=''),
                              'retry': '/api/execute'}}

    def repository_prepare(self, payload):
        if self.public:
            raise PermissionError('Repository custody is unavailable on a public preview')
        exact(payload, ('draft',))
        from portal_bridge import Bridge
        prepared = Bridge(self).prepare(payload['draft'])
        return {'draft': payload['draft'], 'recordJson': canonical(prepared['record']).decode(),
                'publicationIntent': prepared['publicationIntent'],
                'scope': 'Prepared locally. No repository publication or admission has occurred.'}

    def interpretation(self, payload):
        exact(payload, ('card', 'text'))
        card = self.card(payload['card'])
        model_card = {key: card[key] for key in ('card', 'object', 'title', 'prose')}
        if 'objectRef' in card:
            model_card['objectRef'] = card['objectRef']
        model_card['actions'] = [{key: action[key] for key in
            ('id', 'label', 'available', 'fields', 'inspectOnly', 'children') if key in action}
            for action in card['actions']]
        result = interpret.interpret(payload['text'], model_card, proposer=self.proposer)
        identity = self._store('interpretations', {'card': payload['card'], 'text': payload['text'], 'result': result})
        return {**result, 'interpretation': identity}


def make_server(portal, port=0):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'DelveTalkPortal/1'

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass  # No utterances, action tokens or credentials in request logs.

        def respond(self, status, value, content_type='application/json; charset=utf-8'):
            raw = value if isinstance(value, bytes) else canonical(value) + b'\n'
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(raw)

        def route(self, method):
            url = urlsplit(self.path)
            if url.scheme or url.netloc or not self.path.startswith('/'):
                raise ValueError('Expected an origin-relative portal path')
            host = self.headers.get('Host')
            expected_host = '127.0.0.1:' + str(self.server.server_port)
            allowed_hosts = ((urlsplit(portal.public_origin).netloc,) if portal.public else
                             (expected_host, 'localhost:' + str(self.server.server_port)))
            if len(self.headers.get_all('Host', [])) != 1 or host not in allowed_hosts:
                raise PermissionError('Unrecognized portal host')
            origin = portal.public_origin if portal.public else 'http://' + host
            if len(self.headers.get_all('Origin', [])) > 1 or self.headers.get('Origin') not in (None, origin):
                raise PermissionError('Cross-origin requests are refused')
            navigation = (portal.public and method == 'GET' and url.path == '/'
                          and self.headers.get('Sec-Fetch-Mode') == 'navigate'
                          and self.headers.get('Sec-Fetch-Dest') == 'document')
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none') and not navigation:
                raise PermissionError('Cross-site requests are refused')
            if portal.public:
                allowed = {'GET': {'/', '/static/app.js', '/static/style.css', '/api/world',
                                   '/api/object', '/api/card', '/api/detail', '/api/draft'},
                           'HEAD': {'/', '/static/app.js', '/static/style.css', '/api/world'},
                           'POST': {'/api/prepare', '/api/interpret'}}
                if url.path not in allowed.get(method, set()):
                    raise PermissionError('This relation is unavailable on a public preview')
            query = parse_qs(url.query, keep_blank_values=True)
            if any(len(value) != 1 for value in query.values()):
                raise ValueError('Repeated query fields')
            q = {key: value[0] for key, value in query.items()}
            if method in ('GET', 'HEAD'):
                if url.path in ('/', '/static/app.js', '/static/style.css'):
                    name = {'/': 'index.html', '/static/app.js': 'app.js', '/static/style.css': 'style.css'}[url.path]
                    mime = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css'}[name]
                    return self.respond(200, (STATIC / name).read_bytes(), mime + '; charset=utf-8')
                if url.path == '/api/world':
                    exact(q, ()); result = portal.world()
                elif url.path == '/api/object':
                    exact(q, (), ('object', 'panel')); result = portal.object(q.get('object'), q.get('panel', 'main'))
                elif url.path == '/api/card':
                    exact(q, ('card',)); result = portal.card(q['card'])
                elif url.path == '/api/detail':
                    exact(q, ('card',)); result = portal.detail(q['card'])
                elif url.path == '/api/authoring/source':
                    exact(q, ('source',), ('kind',)); result = portal.authoring.read_source(q['source'], q.get('kind', 'source'))
                elif url.path == '/api/authoring/draft':
                    exact(q, ('draft',)); result = portal.authoring.draft(q['draft'])
                elif url.path == '/api/authoring/status':
                    exact(q, ('draft',)); result = portal.authoring.status(q['draft'])
                elif url.path == '/api/draft':
                    exact(q, ('draft',)); result = portal.draft(q['draft'])
                else:
                    return self.respond(404, {'error': 'not-found', 'message': 'Unknown portal relation'})
            else:
                if not secrets.compare_digest(self.headers.get('X-Delvetalk-CSRF', ''), portal.csrf):
                    raise PermissionError('Refresh the portal session before submitting')
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Expected application/json')
                if self.headers.get('Transfer-Encoding'):
                    raise ValueError('Chunked request bodies are unsupported')
                length = int(self.headers.get('Content-Length', '0'))
                limit = MAX_BODY
                if not portal.public and url.path == '/api/authoring/source':
                    from authoring import MAX_UPLOAD
                    limit = MAX_UPLOAD
                if not 0 < length <= limit:
                    raise ValueError('Request body exceeds this route’s byte bound')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete request body')
                payload = loads(raw)
                routes = {'/api/prepare': portal.prepare, '/api/interpret': portal.interpretation}
                if not portal.public:
                    routes.update({'/api/execute': portal.execute,
                                   '/api/repository/prepare': portal.repository_prepare,
                                   '/api/authoring/source': portal.authoring.source,
                                   '/api/authoring/prepare': portal.authoring.prepare,
                                   '/api/authoring/execute': portal.authoring.execute,
                                   '/api/authoring/run': portal.authoring.run})
                if url.path not in routes or q:
                    return self.respond(404, {'error': 'not-found', 'message': 'Unknown portal relation'})
                result = routes[url.path](payload)
            self.respond(200, result)

        def handle_request(self, method):
            try:
                self.route(method)
            except PermissionError as error:
                self.respond(403, {'error': 'forbidden', 'message': str(error)})
            except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
                self.respond(400, {'error': 'invalid-request', 'message': str(error)})
            except (OSError, RuntimeError) as error:
                self.respond(503, {'error': 'unavailable', 'message': str(error)})

        def do_GET(self):
            self.handle_request('GET')

        def do_HEAD(self):
            self.handle_request('HEAD')

        def do_POST(self):
            self.handle_request('POST')

    return HTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='existing source-bound bootstrap world')
    parser.add_argument('--state', type=Path, help='private portal custody; defaults inside world directory')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--public-origin', help='exact HTTPS origin for read-only public previews behind a trusted proxy')
    parser.add_argument('--principal', help='trusted local caller identity; never a Delve login')
    parser.add_argument('--allow-local-actions', action='store_true')
    parser.add_argument('--anthropic', action='store_true', help='opt into one paid proposal call per NL interpretation')
    args = parser.parse_args()
    if args.public_origin and (args.principal is not None or args.allow_local_actions or args.anthropic or args.state is not None):
        parser.error('--public-origin cannot combine with --principal, --allow-local-actions, --anthropic or --state')
    proposer = None
    if args.anthropic:
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            parser.error('--anthropic requires ANTHROPIC_API_KEY')
        proposer = interpret.AnthropicProposer(key)
    portal = Portal(args.directory, state=args.state, principal=args.principal,
                    allow_local_actions=args.allow_local_actions, proposer=proposer,
                    public_origin=args.public_origin)
    server = make_server(portal, args.port)
    print('DelveTalk portal: ' + (portal.public_origin or 'http://127.0.0.1:' + str(server.server_port)), flush=True)
    print('Local interaction as ' + args.principal if portal.interactive else 'Inspection and draft preparation only.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
