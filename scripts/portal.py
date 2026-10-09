#!/usr/bin/env python3
"""Loopback portal: saved affordances, explicit drafts, existing Lean admission."""
import argparse
import base64
import copy
from contextlib import contextmanager
import fcntl
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap
import affordances
import interpret
from delve import save

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'portal/static'
IDENTITY = re.compile(r'[a-z2-7]{12}\Z')
MAX_BODY = 65536
MAX_SAVED = 4096
LOCK_TIMEOUT = 10
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


class Portal:
    def __init__(self, directory, *, state=None, principal=None, allow_local_actions=False, proposer=None):
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
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        binding = {'format': 'delvetalk-portal-custody-v1', 'database': str(self.database), 'runtime': self.runtime}
        stored = bootstrap.desk_module.immutable(self.state / 'binding.json', binding)
        if canonical(stored) != canonical(binding):
            raise ValueError('Portal custody belongs to a different world/runtime')
        for name in ('cards', 'drafts', 'interpretations'):
            (self.state / name).mkdir(exist_ok=True, mode=0o700)

    def snapshot(self):
        with bounded_lock(str(self.database) + '.lock'):
            return loads(self.database.read_bytes())

    def world(self):
        snapshot = self.snapshot()
        return {'title': 'DelveTalk · a shared workbench',
                'mode': 'local-interactive' if self.interactive else 'read-only',
                'principal': self.principal, 'csrf': self.csrf,
                'interpretation': 'model-assisted' if self.proposer else 'copyable-tokens',
                'defaultObject': self.metadata['cafe'],
                'objects': [{'id': name, 'title': name, 'version': root['version'],
                             'href': '/api/object?object=' + quote(name, safe='')}
                            for name, root in snapshot['objects'].items()],
                'scope': 'Local custody. Delve identity and publication are separate.'}

    def _read(self, category, identity):
        if not isinstance(identity, str) or not IDENTITY.fullmatch(identity):
            raise ValueError('Invalid saved reference')
        path = self.state / category / (identity + '.json')
        if not path.is_file():
            raise ValueError('Unknown saved reference; obtain a card from this portal')
        return loads(path.read_bytes())

    def _store(self, category, value):
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
            # Resolve the current admitted program, never a stale index's "latest" label.
            for path in sorted((self.directory / 'artifacts/rooms').glob('*.json')):
                candidate = bootstrap.room.load_artifact(path.parent, path.stem)
                if canonical(candidate['protocol']) == canonical(root['protocol']):
                    artifact = candidate
                    break
        return bootstrap.room.inspect_object(root, object_id, artifact, panel=panel)

    def object(self, object_id=None, panel='main'):
        if not isinstance(panel, str) or len(panel) > 128:
            raise ValueError('Invalid view panel')
        object_id = object_id or self.metadata['cafe']
        snapshot = self.snapshot()
        if object_id not in snapshot['objects']:
            raise ValueError('Unknown object')
        view = self._view(snapshot['objects'][object_id], object_id, panel)
        card = affordances.card(view)
        identity = self._store('cards', {'view': view, 'card': card,
            'historyLength': len(snapshot['receipts']), 'runtime': self.runtime})
        return self.card(identity)

    def card(self, identity):
        saved = self._read('cards', identity)
        card = copy.deepcopy(saved['card'])
        card.update(card=identity, links={'self': '/api/card?card=' + identity,
            'details': '/api/detail?card=' + identity,
            'refresh': '/api/object?object=' + quote(card['object'], safe=''),
            'prepare': '/api/prepare', 'interpret': '/api/interpret'})
        for action in card['actions']:
            action['token'] = 'do ' + identity + ' ' + action['id']
        return card

    def detail(self, identity):
        saved = self._read('cards', identity)
        view = saved['view']
        snapshot = self.snapshot()
        def affects(request):
            return request.get('object') == view['object'] or view['object'] in request.get('reads', {})
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
        identity = self._store('drafts', draft)
        return self.draft(identity)

    def draft(self, identity):
        saved = self._read('drafts', identity)
        action = next(a for a in self.card(saved['card'])['actions'] if a['id'] == saved['action'])
        suffix = (' ' + canonical(saved['fields']).decode()) if saved['fields'] else ''
        return {'draft': identity, 'summary': action['label'], 'command': saved['request']['command'],
                'object': saved['request']['object'], 'version': saved['request']['expected']['version'],
                'canExecute': self.interactive and saved['localPrincipal'] == self.principal,
                'token': action['token'] + suffix, 'wire': saved['wire'],
                'wireJson': canonical(saved['wire']).decode(),
                'links': {'self': '/api/draft?draft=' + identity, 'execute': '/api/execute'},
                'outcome': saved['reply']['kind'] if saved.get('reply') else None,
                'scope': 'Preparing does not submit. Execute or retry retains this draft’s original intent.'}

    def _retained(self, request):
        for entry in self.snapshot()['receipts']:
            if canonical(entry['request']) == canonical(request):
                return entry['receipt']
        return None

    def execute(self, payload):
        exact(payload, ('draft',))
        if not self.interactive:
            raise PermissionError('This portal is read-only; export a draft or use an explicitly configured local session')
        identity = payload['draft']
        with bounded_lock(self.state / 'execute.lock'):
            saved = self._read('drafts', identity)
            if saved['localPrincipal'] != self.principal or saved['request']['principal'] != self.principal:
                raise PermissionError('Draft belongs to another configured local principal')
            reply = saved.get('reply') or self._retained(saved['request'])
            if reply is None:
                if canonical(bootstrap.history.runtime(self.profile)) != canonical(saved['runtime']):
                    raise ValueError('Runtime pins changed; pending drafts cannot run under a replacement engine')
                try:
                    # Separate process group permits bounded cancellation; admission/custody
                    # still exclusively belong to world.py and the selected Lean engine.
                    import worker
                    with tempfile.NamedTemporaryFile('wb', dir=self.state, delete=False) as request_file:
                        path = Path(request_file.name)
                        request_file.write(canonical(saved['request']))
                    try:
                        reply = worker.command([str(ROOT / 'scripts/world.py'),
                            '--profile', self.profile, str(self.database), str(path)], 20)
                    finally:
                        path.unlink(missing_ok=True)
                except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
                    return {'kind': 'uncertain', 'draft': identity,
                            'summary': 'No confirmed outcome. Retry this same draft to recover its receipt.',
                            'detail': type(error).__name__}
            saved['reply'] = reply
            save(self.state / 'drafts' / (identity + '.json'), saved)
            kind = reply['kind']
            return {'kind': kind, 'draft': identity, 'reply': reply,
                    'summary': 'Action committed.' if kind == 'committed' else str(reply.get('data', 'Action refused.')),
                    'links': {'refresh': '/api/object?object=' + quote(saved['request']['object'], safe=''),
                              'retry': '/api/execute'}}

    def interpretation(self, payload):
        exact(payload, ('card', 'text'))
        card = self.card(payload['card'])
        model_card = {key: card[key] for key in ('card', 'object', 'title', 'prose')}
        model_card['actions'] = [{key: action[key] for key in
            ('id', 'label', 'available', 'fields', 'inspectOnly') if key in action}
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
            self.wfile.write(raw)

        def route(self, method):
            expected_host = '127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') not in (expected_host, 'localhost:' + str(self.server.server_port)):
                raise PermissionError('Unrecognized portal host')
            if self.headers.get('Origin') not in (None, 'http://' + self.headers['Host']):
                raise PermissionError('Cross-origin requests are refused')
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                raise PermissionError('Cross-site requests are refused')
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            if any(len(value) != 1 for value in query.values()):
                raise ValueError('Repeated query fields')
            q = {key: value[0] for key, value in query.items()}
            if method == 'GET':
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
                elif url.path == '/api/draft':
                    exact(q, ('draft',)); result = portal.draft(q['draft'])
                else:
                    return self.respond(404, {'error': 'not-found', 'message': 'Unknown portal relation'})
            else:
                if self.headers.get('Origin') not in (None, 'http://' + self.headers['Host']):
                    raise PermissionError('Cross-origin requests are refused')
                if not secrets.compare_digest(self.headers.get('X-Delvetalk-CSRF', ''), portal.csrf):
                    raise PermissionError('Refresh the portal session before submitting')
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Expected application/json')
                if self.headers.get('Transfer-Encoding'):
                    raise ValueError('Chunked request bodies are unsupported')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    raise ValueError('Request body must be 1..65536 bytes')
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete request body')
                payload = loads(raw)
                routes = {'/api/prepare': portal.prepare, '/api/execute': portal.execute,
                          '/api/interpret': portal.interpretation}
                if url.path not in routes or q:
                    return self.respond(404, {'error': 'not-found', 'message': 'Unknown portal relation'})
                result = routes[url.path](payload)
            self.respond(200, result)

        def handle_request(self, method):
            try:
                self.route(method)
            except PermissionError as error:
                self.respond(403, {'error': 'forbidden', 'message': str(error)})
            except (ValueError, KeyError, TypeError, UnicodeError) as error:
                self.respond(400, {'error': 'invalid-request', 'message': str(error)})
            except (OSError, RuntimeError) as error:
                self.respond(503, {'error': 'unavailable', 'message': str(error)})

        def do_GET(self):
            self.handle_request('GET')

        def do_POST(self):
            self.handle_request('POST')

    return HTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='existing source-bound bootstrap world')
    parser.add_argument('--state', type=Path, help='private portal custody; defaults inside world directory')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--principal', help='trusted local caller identity; never a Delve login')
    parser.add_argument('--allow-local-actions', action='store_true')
    parser.add_argument('--anthropic', action='store_true', help='opt into one paid proposal call per NL interpretation')
    args = parser.parse_args()
    proposer = None
    if args.anthropic:
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            parser.error('--anthropic requires ANTHROPIC_API_KEY')
        proposer = interpret.AnthropicProposer(key)
    portal = Portal(args.directory, state=args.state, principal=args.principal,
                    allow_local_actions=args.allow_local_actions, proposer=proposer)
    server = make_server(portal, args.port)
    print('DelveTalk portal: http://127.0.0.1:' + str(server.server_port), flush=True)
    print('Local interaction as ' + args.principal if portal.interactive else 'Inspection and draft preparation only.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
