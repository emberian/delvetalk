#!/usr/bin/env python3
"""Run as `python3 -m transport.http` (never as a script: this file would shadow stdlib http).

HTTP front on the world host: /AGENTS.md for agents, / and /o/<object> for humans.
Carries bytes and a verified principal; it validates nothing but size and JSON
well-formedness. Host replies pass through verbatim.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from transport import pages
from transport.hostd import CLOCK
from transport.hostproc import LIBRARY, HostClient, RemoteHeaps, add_host_args
from transport.delve import Client, canonical, http_transport
from transport.identity import Identity, IdentityError, ORIGIN

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / 'docs' / 'AGENTS-API.md'
STATIC = Path(__file__).resolve().parent / 'static'
MAX_BODY, MAX_SOURCE, MAX_MODULES = 64 * 1024, 16 * 1024, 16
WAIT_MAX, WAIT_STEP = 30, 1  # seconds an offers long poll may hold a request, and how often it re-asks the host
RATE, OPEN_RATE, WINDOW, DELIVER_LIMIT = 32, 16, 60, 16
PREFIX, COOKIE = '/AGENTS.md', 'dt_credential'
CREATE_KEYS = ('object', 'modules', 'source', 'package', 'entry', 'seed', 'law')
EXAMPLES = ROOT / 'docs' / 'AGENTS-EXAMPLES.md'
UNKNOWN_OP = 'unknown world operation'
IMPORT = re.compile(r'^import \./(\w+)\.obend', re.M)
ROUTES = {('GET', 'receipt', True): 'receipt', ('GET', 'offers', False): 'offers', ('GET', 'pending', False): 'pending',
          ('POST', 'deliver', False): 'deliver', ('POST', 'objects', False): 'create', ('POST', 'repl', False): 'repl',
          ('POST', 'check', False): 'check', ('GET', 'me', False): 'me', ('POST', 'revoke', False): 'revoke'}
TOP_ONLY = ('repl', 'check', 'me', 'revoke')
ROUTE_HINT = ('GET world, world/<object>, world/<object>/card, world/<object>/source, receipt/<intent>, offers, pending, me, examples; '
              'POST world/<object>/<method>, repl, check, deliver, revoke, heap/objects; heap/ before world, receipt, offers, pending, deliver')


def plain(data):
    """Typed data as plain JSON, for reading only (a form's fields); never sent back to the host."""
    tag = data.get('tag') if isinstance(data, dict) else None
    if tag == 'record':
        return {f['name']: plain(f['value']) for f in data['fields']}
    if tag == 'list':
        return [plain(i) for i in data['items']]
    if tag == 'variant':
        inner = plain(data['payload'])
        return {'tag': data['label'], **inner} if isinstance(inner, dict) else {'tag': data['label'], 'value': inner}
    return int(data['value']) if tag == 'natural' else data.get('value') if tag else data


def typed(value):
    """Plain JSON as the host's typed data: text is a label, an integer a natural, an object a record."""
    if isinstance(value, dict):
        return value if 'tag' in value else {'tag': 'record', 'fields': [{'name': k, 'value': typed(v)} for k, v in value.items()]}
    if isinstance(value, list):
        return {'tag': 'list', 'items': [typed(v) for v in value]}
    if isinstance(value, bool):
        return {'tag': 'boolean', 'value': value}
    return {'tag': 'natural', 'value': str(value)} if isinstance(value, int) else {'tag': 'label', 'value': str(value)}


def argument(data):
    """A turn's argument: `spell` is a reply's text as a card hears it, `fields` a plain record, else `argument` typed."""
    if 'spell' in data:
        return typed({'text': data['spell'], 'post': '', 'slot': ''})
    return typed(data['fields']) if isinstance(data.get('fields'), dict) else data.get('argument', {'tag': 'record', 'fields': []})


def brief(value):
    """A checkpoint's tokens (hundreds of KiB for a suspended turn) as their count."""
    if isinstance(value, dict):
        return {k: {'elided': len(v)} if k == 'tokens' and isinstance(v, list) else brief(v) for k, v in value.items()}
    return [brief(v) for v in value] if isinstance(value, list) else value


def compact(reply):
    """A turn reply cut to what an agent reads: the status, the outcome, the offered texts and where the receipt sits."""
    receipt = reply['receipt']
    root = (receipt.get('roots') or [{}])[0]
    return {'status': reply.get('status'), 'outcome': receipt.get('outcome'),
            'offers': [o['text'] for o in reply.get('offers') or []],
            'receipt': {'object': root.get('object'), 'version': root.get('version'), 'height': receipt.get('height')}}


def compact_offers(reply):
    """An offers reply cut to the texts, and the height of the newest (pass it as `after`)."""
    offers = reply.get('offers') or []
    return {'status': reply['status'], 'offers': [o['text'] for o in offers], **({'height': offers[-1]['height']} if offers else {})}


def library(modules):
    """The modules, after the world/lib modules they import and did not supply (imports first): the bytes hostd seals."""
    found = {p.stem: p for p in sorted(LIBRARY.rglob('*.obend'))}
    have, out = {m.get('name') for m in modules}, []

    def visit(name):
        if name not in have and name in found:
            have.add(name)
            source = found[name].read_text()
            for dep in IMPORT.findall(source):
                visit(dep)
            out.append({'name': name, 'source': source})
    for m in modules:
        for dep in IMPORT.findall(str(m.get('source', ''))):
            visit(dep)
    return out + modules


class Front(ThreadingHTTPServer):  # threaded so a long poll holds one thread, not the front
    daemon_threads = True
    request_queue_size = 128  # the default backlog of 5 resets connections when a burst arrives faster than accept() runs

    def __init__(self, address, host, identity, origin=ORIGIN, clock=time.time, heaps=None, repl=None, trust_proxy=False, sleep=time.sleep):
        super().__init__(address, Handler)
        self.host, self.identity, self.origin, self.clock = host, identity, origin, clock
        self.heaps, self.repl, self.trust_proxy, self.sleep = heaps, repl, trust_proxy, sleep
        self.hits, self.nonce, self.hits_lock = {}, secrets.token_hex(4), threading.Lock()
        # The bytes this front runs as its host, so an operator can compare them with the build's pin.
        self.host_sha256 = (hashlib.sha256(Path(host.binary).read_bytes()).hexdigest() if hasattr(host, 'binary')
                            else host.send({'op': 'hostd-info'}).get('hostSha256', 'unknown'))

    def used(self, credential):
        now = self.clock()
        with self.hits_lock:
            return [t for t in self.hits.get(credential, []) if now - t < WINDOW]

    def limited(self, key, rate=RATE):
        with self.hits_lock:  # read, test and append as one step
            now = self.clock()
            hits = [t for t in self.hits.get(key, []) if now - t < WINDOW]
            self.hits[key] = hits + [now]
        return len(hits) >= rate

    def record_handle(self, did, handle):
        """Tell the host a verified account has arrived (the clock principal alone may), so cards name them by handle.
        Idempotent at the host; a refusal leaves the verification standing."""
        return self.host.send({'op': 'world-arrive', 'principal': CLOCK, 'did': did, 'handle': handle})

    def guide(self, path=GUIDE):
        return path.read_text().replace('{{origin}}', self.origin)


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

    def fail(self, code, message, hint=None):
        self.reply(code, canonical({'status': 'error', 'message': message, **({'hint': hint} if hint else {})}))

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
        # curl -d labels JSON as a form; a browser's form body never starts with '{'
        if (self.headers.get('Content-Type') or '').startswith('application/x-www-form-urlencoded') and not raw.lstrip().startswith(b'{'):
            return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors='replace')).items()}
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            return self.fail(400, 'body is not valid JSON')
        return data if isinstance(data, dict) else self.fail(400, 'body must be a JSON object')

    def answer(self, reply):
        """The host's reply, rendered: a diagnostic carried as JSON text in `message` is lifted, its `hint` with it,
        and a checkpoint's tokens are counted, not shown (?full=1 shows them)."""
        status = reply.get('status')
        try:
            inner = json.loads(reply['message']) if status == 'error' else None
        except (KeyError, TypeError, ValueError):
            inner = None
        reply = {**inner, 'status': 'error'} if isinstance(inner, dict) else reply
        if isinstance(reply.get('diagnostic'), dict) and 'hint' in reply['diagnostic']:
            reply = {**reply, 'hint': reply['diagnostic']['hint']}
        full = 'full' in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        self.reply(400 if status == 'error' else 404 if status == 'unknown' else 200, canonical(reply if full else brief(reply)))

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
            return self.reply(200, self.server.guide(), 'text/plain', [('X-DelveTalk-Host-Sha256', self.server.host_sha256)])
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
        if method == 'GET' and rest == ['examples']:
            return self.reply(200, self.server.guide(EXAMPLES), 'text/plain')
        heap = rest[:1] == ['heap']
        rest = rest[1:] if heap else rest
        head, obj, tail = (rest[0] if rest else ''), '/'.join(rest[1:]), ''
        if head == 'world':  # an object id may hold slashes: the last segment names the method, or card/source
            if method == 'POST' or (len(rest) > 2 and rest[-1] in ('card', 'source')):
                obj, tail = '/'.join(rest[1:-1]), rest[-1]
            kind = 'turn' if method == 'POST' else tail or ('view' if obj else 'objects')
            kind = kind if obj or kind == 'objects' else None
        else:
            kind = ROUTES.get((method, head, bool(obj)))
            kind = None if kind in (('create',) if not heap else TOP_ONLY) else kind
        if kind is None:
            return self.fail(404, f'unknown route; read {self.server.origin}{PREFIX}', ROUTE_HINT)
        auth = self.headers.get('Authorization') or ''
        credential = auth[7:] if auth.startswith('Bearer ') else ''
        who = self.principal(credential)
        if who is None:
            return self.fail(401, 'missing, unverified or revoked credential', 'POST /AGENTS.md/challenge, post its text, POST /AGENTS.md/verify; then send Authorization: Bearer <credential>')
        if self.server.limited(credential):
            return self.fail(429, f'more than {RATE} requests per {WINDOW} seconds')
        if kind == 'me':
            return self.me(credential, who)
        if kind == 'revoke':
            self.server.identity.revoke(credential)
            return self.reply(200, canonical({'status': 'revoked'}), headers=[('Set-Cookie', f'{COOKIE}=; Path=/; Max-Age=0')])
        if kind in ('repl', 'check'):
            return self.run_repl(who['did'], kind)
        host = self.server.heaps.get(who['did']) if heap else self.server.host
        principal = who['did']  # the principal the host sees; the handle is display only
        send = lambda req: self.answer(host.send(req))
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        after = {'after': int(q['after']) if q['after'].isdigit() else q['after']} if 'after' in q else {}
        if kind == 'objects':
            return send({'op': 'world-objects', 'principal': principal, **{k: q[k] for k in ('prefix', 'after') if k in q}})
        if kind == 'view':
            return send({'op': 'world-view', 'principal': principal, 'object': obj})
        if kind in ('card', 'source'):
            r = host.send({'op': 'world-card' if kind == 'card' else 'world-inspect', 'principal': principal, 'object': obj})
            if 'full' not in q:  # the readable part; ?full=1 is the host's reply verbatim
                r = {k: plain(v) if k == 'forms' else v for k, v in r.items() if k not in ('document', 'methods')}
            return self.answer(r)
        if kind == 'receipt':
            return send({'op': 'world-receipt', 'principal': principal, 'identity': obj})
        if kind == 'offers':
            wait = min(int(q['wait']), WAIT_MAX) if q.get('wait', '').isdigit() else 0
            for waited in range(0, wait + 1, WAIT_STEP):
                reply = host.send({'op': 'world-offers', 'principal': principal, **after})
                if reply.get('status') != 'offers' or reply.get('offers') or waited + WAIT_STEP > wait:
                    break
                self.server.sleep(WAIT_STEP)
            return self.answer(compact_offers(reply) if q.get('compact') == '1' and reply.get('status') == 'offers' else reply)
        if kind == 'pending':
            return send({'op': 'world-pending'})
        data = self.body()
        if data is None:
            return
        if kind == 'deliver':
            return send({'op': 'world-deliver', 'limit': DELIVER_LIMIT})
        if kind == 'create':
            made = {k: typed(data[k]) if k == 'seed' else data[k] for k in CREATE_KEYS if k in data}
            return send({'op': 'world-create', 'principal': principal, 'identity': data.get('intent'), **made})
        reply = host.send({'op': 'world-turn', 'principal': principal, 'object': obj, 'method': tail,
                           'argument': argument(data), 'identity': data.get('intent')})
        self.answer(compact(reply) if q.get('compact') == '1' and 'receipt' in reply else reply)

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
        self.server.record_handle(out['did'], out['handle'])
        mine = self.principal(self.cookie())  # a browser that asked for the challenge holds its credential
        self.reply(200, canonical(out), headers=self.login_cookie(self.cookie()) if mine and mine['did'] == out['did'] else ())

    def me(self, credential, who):
        heap = self.server.heaps.get(who['did'], create=False)
        count = heap.send({'op': 'world-status'}).get('objects') if heap else 0
        self.reply(200, canonical({'principal': who['did'], 'handle': who['handle'], 'did': who['did'], 'verified': who['verified'],
                                   'rateLimit': {'limit': RATE, 'windowSeconds': WINDOW, 'remaining': max(0, RATE - len(self.server.used(credential)))},
                                   'heapObjects': count}))

    def run_repl(self, principal, kind='repl'):
        data = self.body()
        if data is None:
            return
        modules = data['modules'] if 'modules' in data else [{'name': 'Package', 'source': data.get('source', '')}]
        if not isinstance(modules, list) or len(modules) > MAX_MODULES:
            return self.fail(400, f'modules must be a list of at most {MAX_MODULES}')
        for m in modules:
            if not isinstance(m, dict) or len(str(m.get('source', '')).encode()) > MAX_SOURCE:
                return self.fail(413, f'module source exceeds {MAX_SOURCE} bytes', 'import the library by name (./Plan.obend); it is not sent')
        if kind == 'check':  # the verdict, against the world's sealed library; ?full=1 adds the compiled artifact
            checked = self.server.host.send({'op': 'world-check', 'principal': principal, 'modules': modules, 'entry': data.get('entry')})
            if UNKNOWN_OP in str(checked.get('message')):
                # TODO(world-check): delete this fallback, which reads world/lib from disk, once every host answers world-check.
                checked = self.server.repl.send({'op': 'check-package', 'modules': library(modules), 'entry': data.get('entry')})
            return self.answer(checked if 'full=1' in self.path else {k: v for k, v in checked.items() if k != 'artifact'})
        repl, modules = self.server.repl, library(modules)
        compiled = repl.send({'op': 'compile', 'modules': modules, 'entry': data.get('entry')})
        if compiled.get('status') != 'compiled':
            return self.answer(compiled)
        ty = compiled['artifact'].get('type') or {}
        while ty.get('tag') == 'arrow':
            ty = ty.get('codomain') or {}
        activity = ty.get('tag') == 'computation'  # an Activity entry starts a turn; anything else runs
        extra = {k: data[k] for k in ('limits', 'object', 'intent', 'roots') if k in data}
        if activity or 'checkpoint' in data:
            extra['principal'] = principal  # a checkpoint is bound to the credential's principal, never the body's
        if 'checkpoint' in data:
            req = {'op': 'turn-resume', 'checkpoint': data['checkpoint'], 'response': data.get('response'), **extra}
        else:
            req = {'op': 'turn-start' if activity else 'run', 'arguments': data.get('arguments', []), **extra}
        reply = repl.send({**req, 'artifact': compiled['artifact']})
        return self.answer(reply) if reply.get('status') == 'error' else self.reply(200, canonical(reply))  # a checkpoint goes back whole

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
                                            'argument': {'tag': 'record', 'fields': [field('text', data.get('text', '')), field('post', stamp), field('slot', '')]},
                                            'identity': stamp})
        host = self.server.host
        view = host.send({'op': 'world-view', 'principal': principal or 'anonymous', 'object': name})
        if view.get('status') != 'viewed':
            return self.html(404, pages.missing(name, handle, view))
        card = self.card(host, principal, name) if principal else None
        self.html(200, pages.obj(name, handle, view, card, self.history(host, name, principal), result))

    def card(self, host, principal, name):
        """The object's card as this reader sees it, from the host's world-card (no journaled turn)."""
        r = host.send({'op': 'world-card', 'principal': principal or 'anonymous', 'object': name})
        return r.get('text') if r.get('status') == 'card' else None

    def history(self, host, name, principal=''):
        """The newest 20 entries touching the object, newest first, read from the tail of the journal under the reader's authority."""
        height = host.send({'op': 'world-status'}).get('height') or 0
        window = 20
        while True:
            after, entries = max(0, height - window), []
            for _ in range(50):
                req = {'op': 'world-history', 'principal': principal or '', 'object': name, 'limit': 100}
                if after:
                    req['after'] = after
                page = host.send(req)
                entries += page.get('entries') or []
                if not page.get('more') or not page.get('entries'):
                    break
                after = page['entries'][-1]['height']
            if len(entries) >= 20 or window >= height:
                return entries[-20:][::-1]
            window *= 4


def main(argv=None):
    ap = argparse.ArgumentParser(prog='http.py')
    ap.add_argument('--state', required=True)
    add_host_args(ap)
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--bind', default='127.0.0.1')
    ap.add_argument('--origin', default=ORIGIN)
    ap.add_argument('--trust-proxy', action='store_true', help='key the unauthenticated limits on the last X-Forwarded-For entry')
    a = ap.parse_args(argv)
    sock = a.host_socket or Path(a.state) / 'host.sock'
    host, heaps, repl = HostClient(sock), RemoteHeaps(sock, Path(a.state) / 'heaps'), HostClient(sock, stateless=True)
    front = Front((a.bind, a.port), host, Identity(a.state, Client(http_transport), a.origin), a.origin,
                  heaps=heaps, repl=repl, trust_proxy=a.trust_proxy)
    try:
        front.serve_forever()
    finally:
        front.host.close()
        front.heaps.close()
        front.repl.close()


if __name__ == '__main__':
    sys.exit(main())
