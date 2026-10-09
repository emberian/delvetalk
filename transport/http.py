#!/usr/bin/env python3
"""Run as `python3 -m transport.http` (never as a script: this file would shadow stdlib http).

HTTP front on the world host: /AGENTS.md for agents, / and /o/<object> for humans.
Carries bytes and a verified principal; it validates nothing but size and JSON
well-formedness. Host replies pass through verbatim.
"""
import argparse
import collections
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from transport import pages
from transport.delve import Client, canonical, http_transport
from transport.identity import Identity, IdentityError, ORIGIN

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / 'docs' / 'AGENTS-API.md'
STATIC = Path(__file__).resolve().parent / 'static'
BINARY = os.environ.get('DELVETALK_OBEND', '/Users/ember/dev/delvetalk2/.lake/build/bin/delvetalk-obend')
MAX_BODY, MAX_SOURCE, MAX_MODULES = 64 * 1024, 8 * 1024, 16
RATE, OPEN_RATE, WINDOW, HOST_TIMEOUT, DELIVER_LIMIT, POOL = 32, 16, 60, 120, 16, 8
PREFIX, COOKIE = '/AGENTS.md', 'dt_credential'
CREATE_KEYS = ('object', 'modules', 'source', 'package', 'entry', 'seed', 'law')


class HostDied(Exception):
    pass


class Host:
    """One host subprocess, one request at a time; respawned and reopened if it dies.
    With journal=None it is a stateless compile/run process."""

    def __init__(self, journal, binary=BINARY):
        self.journal, self.binary, self.proc = journal, binary, None
        self.lock = threading.Lock()

    def _spawn(self):
        self.proc = subprocess.Popen([self.binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if self.journal:
            reply = self._exchange({'op': 'world-open', 'path': self.journal})
            if reply.get('status') != 'opened':
                raise HostDied('world-open refused: ' + json.dumps(reply))

    def _exchange(self, request):
        watchdog = threading.Timer(HOST_TIMEOUT, self.proc.kill)
        watchdog.start()
        try:
            self.proc.stdin.write(json.dumps(request) + '\n')
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        except (BrokenPipeError, OSError, ValueError):
            line = ''
        finally:
            watchdog.cancel()
        if not line:
            raise HostDied('host closed its output')
        return json.loads(line)

    def send(self, request):
        """A turn is retried once after a restart: the host answers a repeated identity with the original receipt."""
        with self.lock:
            for attempt in (0, 1):
                try:
                    if self.proc is None or self.proc.poll() is not None:
                        self.close()
                        self._spawn()
                    return self._exchange(request)
                except (HostDied, ValueError):
                    self.close()
                    if attempt:
                        return {'status': 'error', 'message': 'host unavailable'}

    def close(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.wait()
            for s in (self.proc.stdin, self.proc.stdout):
                s.close()
            self.proc = None


class Heaps:
    """Per-principal journals, each in its own host process; least recently used evicted.
    A heap is reopened by the host's replay, so eviction loses nothing."""

    def __init__(self, directory, size=POOL, binary=BINARY):
        self.dir, self.size, self.binary = Path(directory), size, binary
        self.pool = collections.OrderedDict()

    def journal(self, did):
        return self.dir / f'{did}.journal'

    def get(self, did, create=True):
        if did in self.pool:
            self.pool.move_to_end(did)
            return self.pool[did]
        if not create and not self.journal(did).exists():
            return None
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        while len(self.pool) >= self.size:
            self.pool.popitem(last=False)[1].close()
        self.pool[did] = Host(str(self.journal(did)), self.binary)
        return self.pool[did]

    def close(self):
        for h in self.pool.values():
            h.close()
        self.pool.clear()


class Front(HTTPServer):
    def __init__(self, address, host, identity, origin=ORIGIN, clock=time.time, heaps=None, repl=None, trust_proxy=False):
        super().__init__(address, Handler)
        self.host, self.identity, self.origin, self.clock = host, identity, origin, clock
        self.heaps, self.repl, self.trust_proxy = heaps, repl or Host(None), trust_proxy
        self.hits, self.cards, self.nonce = {}, {}, secrets.token_hex(4)

    def used(self, credential):
        now = self.clock()
        return [t for t in self.hits.get(credential, []) if now - t < WINDOW]

    def limited(self, key, rate=RATE):
        hits = self.used(key)
        self.hits[key] = hits + [self.clock()]
        return len(hits) >= rate

    def guide(self):
        return GUIDE.read_text().replace('{{origin}}', self.origin)


class Handler(BaseHTTPRequestHandler):
    server_version = 'DelveTalk'

    def log_message(self, *args):
        pass

    def reply(self, code, body, ctype='application/json', headers=()):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype + ('' if ctype.startswith('image') else '; charset=utf-8'))
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def fail(self, code, message):
        self.reply(code, canonical({'status': 'error', 'message': message}))

    def body(self):
        """-> dict, or None after replying with the refusal. JSON, or a urlencoded form."""
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            n = -1
        if n < 0:
            return self.fail(400, 'bad Content-Length')
        if n > MAX_BODY:
            return self.fail(413, f'body exceeds {MAX_BODY} bytes')
        raw = self.rfile.read(n)
        if (self.headers.get('Content-Type') or '').startswith('application/x-www-form-urlencoded'):
            return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors='replace')).items()}
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            return self.fail(400, 'body is not valid JSON')
        return data if isinstance(data, dict) else self.fail(400, 'body must be a JSON object')

    def answer(self, reply):
        status = reply.get('status')
        self.reply(400 if status == 'error' else 404 if status == 'unknown' else 200, canonical(reply))

    def cookie(self):
        for part in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == COOKIE:
                return v
        return ''

    def login_cookie(self, credential):
        return [('Set-Cookie', f'{COOKIE}={credential}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000')]

    def principal(self, credential):
        try:
            return self.server.identity.authenticate(credential)
        except IdentityError:
            return None

    def do_GET(self):
        self.route('GET')

    def do_POST(self):
        self.route('POST')

    def route(self, method):
        path = urllib.parse.urlsplit(self.path).path
        parts = [urllib.parse.unquote(p) for p in path.split('/')[1:]]
        if method == 'GET' and path == PREFIX:
            return self.reply(200, self.server.guide(), 'text/plain')
        if method == 'GET' and parts[:1] == ['static'] and len(parts) == 2 and parts[1] in ('style.css', 'theme.js'):
            return self.reply(200, (STATIC / parts[1]).read_bytes(), 'text/css' if parts[1].endswith('css') else 'text/javascript')
        if parts[:1] == ['AGENTS.md']:
            return self.agents(method, parts[1:])
        if method == 'GET' and path == '/':
            return self.home()
        if method == 'GET' and parts == ['o']:
            name = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('object', [''])[0]
            return self.reply(302, '', 'text/plain', [('Location', '/o/' + urllib.parse.quote(name, safe=''))])
        if parts[:1] == ['o'] and method == 'GET' and len(parts) == 2:
            return self.object_page(parts[1])
        if parts[:1] == ['o'] and method == 'POST' and len(parts) == 3 and parts[2] == 'spell':
            return self.object_page(parts[1], spell=True)
        self.fail(404, f'unknown route; read {self.server.origin}{PREFIX}')

    # ---- agents

    def agents(self, method, rest):
        if method == 'POST' and rest in (['challenge'], ['verify']):
            return self.identify(rest[0])
        kind = {('GET', 'world', 2): 'view', ('POST', 'world', 3): 'turn', ('GET', 'receipt', 2): 'receipt',
                ('POST', 'deliver', 1): 'deliver', ('GET', 'pending', 1): 'pending', ('POST', 'repl', 1): 'repl',
                ('GET', 'me', 1): 'me', ('POST', 'revoke', 1): 'revoke'}.get((method, rest[0] if rest else '', len(rest)))
        heap = rest[:1] == ['heap']
        if heap:
            rest = rest[1:]
            kind = {('POST', 'objects', 1): 'create', ('GET', 'world', 2): 'view', ('POST', 'world', 3): 'turn',
                    ('GET', 'receipt', 2): 'receipt', ('POST', 'deliver', 1): 'deliver',
                    ('GET', 'pending', 1): 'pending'}.get((method, rest[0] if rest else '', len(rest)))
        if kind is None:
            return self.fail(404, f'unknown route; read {self.server.origin}{PREFIX}')
        auth = self.headers.get('Authorization') or ''
        credential = auth[7:] if auth.startswith('Bearer ') else ''
        who = self.principal(credential)
        if who is None:
            return self.fail(401, 'missing, unverified or revoked credential')
        if self.server.limited(credential):
            return self.fail(429, f'more than {RATE} requests per {WINDOW} seconds')
        if kind == 'me':
            return self.me(credential, who)
        if kind == 'revoke':
            self.server.identity.revoke(credential)
            return self.reply(200, canonical({'status': 'revoked'}), headers=[('Set-Cookie', f'{COOKIE}=; Path=/; Max-Age=0')])
        if kind == 'repl':
            return self.run_repl(who['did'])
        if heap:
            host = self.server.heaps.get(who['did'])
        else:
            host = self.server.host
        principal = who['did']  # the principal the host sees; the handle is display only
        send = lambda req: self.answer(host.send(req))
        if kind == 'view':
            return send({'op': 'world-view', 'principal': principal, 'object': rest[1]})
        if kind == 'receipt':
            return send({'op': 'world-receipt', 'principal': principal, 'identity': rest[1]})
        if kind == 'pending':
            return send({'op': 'world-pending'})
        data = self.body()
        if data is None:
            return
        if kind == 'deliver':
            return send({'op': 'world-deliver', 'limit': DELIVER_LIMIT})
        if kind == 'create':
            made = {k: data[k] for k in CREATE_KEYS if k in data}
            return send({'op': 'world-create', 'principal': principal, 'identity': data.get('intent'), **made})
        send({'op': 'world-turn', 'principal': principal, 'object': rest[1], 'method': rest[2],
              'argument': data.get('argument', {'tag': 'record', 'fields': []}), 'identity': data.get('intent')})

    def client_ip(self):
        forwarded = (self.headers.get('X-Forwarded-For') or '').split(',')[-1].strip()
        return forwarded if self.server.trust_proxy and forwarded else self.client_address[0]

    def identify(self, which):
        if self.server.limited('ip:' + self.client_ip(), OPEN_RATE):
            return self.fail(429, f'more than {OPEN_RATE} requests per {WINDOW} seconds')
        data = self.body()
        if data is None:
            return
        try:
            if which == 'challenge':
                out = self.server.identity.challenge(data.get('handle'))
                return self.reply(200, canonical(out), headers=self.login_cookie(out['credential']))
            out = self.server.identity.verify(data.get('handle'), data.get('uri'))
        except IdentityError as err:
            return self.fail(400, err.code)
        mine = self.principal(self.cookie())  # a browser that asked for the challenge holds its credential
        self.reply(200, canonical(out), headers=self.login_cookie(self.cookie()) if mine and mine['did'] == out['did'] else ())

    def me(self, credential, who):
        heap = self.server.heaps.get(who['did'], create=False)
        count = heap.send({'op': 'world-status'}).get('objects') if heap else 0
        self.reply(200, canonical({'principal': who['did'], 'handle': who['handle'], 'did': who['did'], 'verified': who['verified'],
                                   'rateLimit': {'limit': RATE, 'windowSeconds': WINDOW, 'remaining': max(0, RATE - len(self.server.used(credential)))},
                                   'heapObjects': count}))

    def run_repl(self, principal):
        data = self.body()
        if data is None:
            return
        modules = data.get('modules')
        if not isinstance(modules, list) or len(modules) > MAX_MODULES:
            return self.fail(400, f'modules must be a list of at most {MAX_MODULES}')
        for m in modules:
            if not isinstance(m, dict) or len(str(m.get('source', '')).encode()) > MAX_SOURCE:
                return self.fail(413, f'module source exceeds {MAX_SOURCE} bytes')
        repl = self.server.repl
        compiled = repl.send({'op': 'compile', 'modules': modules, 'entry': data.get('entry')})
        if compiled.get('status') != 'compiled':
            return self.answer(compiled)
        extra = {k: data[k] for k in ('limits', 'object', 'intent', 'roots') if k in data}
        if data.get('turn') or 'checkpoint' in data:
            extra['principal'] = principal  # a checkpoint is bound to the credential's principal, never the body's
        if 'checkpoint' in data:
            req = {'op': 'turn-resume', 'checkpoint': data['checkpoint'], 'response': data.get('response'), **extra}
        else:
            req = {'op': 'turn-start' if data.get('turn') else 'run', 'arguments': data.get('arguments', []), **extra}
        self.answer(repl.send({**req, 'artifact': compiled['artifact']}))

    # ---- humans

    def html(self, code, body, headers=()):
        self.reply(code, body, 'text/html', headers)

    def home(self):
        who = self.principal(self.cookie())
        self.html(200, pages.home(self.server.host.send({'op': 'world-status'}), who and who['handle']))

    def object_page(self, name, spell=False):
        credential = self.cookie()
        who = self.principal(credential)
        handle = who['handle'] if who else None
        principal = who['did'] if who else None
        result = None
        if spell:
            data = self.body()
            if data is None:
                return
            if who is None:
                return self.html(401, pages.page('log in', None, '<h1>Log in first</h1><p><a href="/">home</a></p>'))
            if self.server.limited(credential):
                return self.html(429, pages.page('slow down', handle, '<h1>Too many requests</h1>'))
            stamp = f'web:{principal}:{self.server.nonce}:{int(self.server.clock() * 1000)}:{secrets.token_hex(3)}'
            field = lambda k, v: {'name': k, 'value': {'tag': 'label', 'value': v}}
            result = self.server.host.send({'op': 'world-turn', 'principal': principal, 'object': name, 'method': 'receive',
                                            'argument': {'tag': 'record', 'fields': [field('text', data.get('text', '')), field('post', stamp)]},
                                            'identity': stamp})
        host = self.server.host
        view = host.send({'op': 'world-view', 'principal': principal or 'anonymous', 'object': name})
        if view.get('status') != 'viewed':
            return self.html(404, pages.missing(name, handle, view))
        card = self.card(host, principal, name, view['version']) if principal else None
        self.html(200, pages.obj(name, handle, view, card, self.history(host, name), result))

    def card(self, host, principal, name, version):
        """The object's own card: an offer from present/describe, cached because a retried identity returns no offers."""
        key = (principal, name, version)
        if key not in self.server.cards:
            text = None
            for method in ('present', 'describe'):
                r = host.send({'op': 'world-turn', 'principal': principal, 'object': name, 'method': method,
                               'argument': {'tag': 'record', 'fields': []},
                               'identity': f'page:{name}:{method}:{version}:{self.server.nonce}'})
                if r.get('offers'):
                    text = '\n'.join(o['text'] for o in r['offers'])
                    break
            self.server.cards[key] = text
        return self.server.cards[key]

    def history(self, host, name):
        entries, after = [], None
        for _ in range(50):
            req = {'op': 'world-history', 'object': name, 'limit': 100}
            if after is not None:
                req['after'] = after
            page = host.send(req)
            entries += page.get('entries') or []
            if not page.get('more') or not page.get('entries'):
                break
            after = page['entries'][-1]['height']
        return entries[-20:][::-1]


def main(argv=None):
    ap = argparse.ArgumentParser(prog='http.py')
    ap.add_argument('--state', required=True)
    ap.add_argument('--journal', required=True)
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--bind', default='127.0.0.1')
    ap.add_argument('--origin', default=ORIGIN)
    ap.add_argument('--trust-proxy', action='store_true', help='key the unauthenticated limits on the last X-Forwarded-For entry')
    a = ap.parse_args(argv)
    front = Front((a.bind, a.port), Host(a.journal), Identity(a.state, Client(http_transport), a.origin), a.origin,
                  heaps=Heaps(Path(a.state) / 'heaps'), trust_proxy=a.trust_proxy)
    try:
        front.serve_forever()
    finally:
        front.host.close()
        front.heaps.close()
        front.repl.close()


if __name__ == '__main__':
    sys.exit(main())
