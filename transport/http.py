#!/usr/bin/env python3
"""Run as `python3 -m transport.http` (never as a script: this file would shadow stdlib http).

HTTP front on the world host: /AGENTS.md for agents, / and /o/<object> for humans.
Carries bytes and a verified principal; it validates nothing but size and JSON
well-formedness. Host replies pass through verbatim.
"""
import argparse
import hashlib
import html
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from transport import bridge, hand, oauth, pages, post
from transport.hostd import CLOCK
from transport.hostproc import HOST_TIMEOUT, HostClient, RemoteHeaps, add_host_args
from transport.delve import Client, canonical, http_transport
from transport.identity import Identity, IdentityError, ORIGIN
from transport.repo import Repo

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / 'docs' / 'AGENTS-API.md'
STATIC = Path(__file__).resolve().parent / 'static'
MAX_BODY, MAX_SOURCE, MAX_MODULES = 64 * 1024, 16 * 1024, 16
WAIT_MAX, WAIT_STEP = 30, 1  # seconds an offers long poll may hold a request, and how often it re-asks the host
RATE, OPEN_RATE, WINDOW, DELIVER_LIMIT = 32, 16, 60, 16
SLUG = re.compile(r'(?:[bdfghjklmnprstvz][aiou][bdfghjklmnprstvz][aiou][bdfghjklmnprstvz])(?:-[bdfghjklmnprstvz][aiou][bdfghjklmnprstvz][aiou][bdfghjklmnprstvz])+')
PREFIX, COOKIE = '/AGENTS.md', 'dt_credential'
CREATE_KEYS = ('object', 'modules', 'source', 'package', 'entry', 'seed', 'law')
EXAMPLES = ROOT / 'docs' / 'AGENTS-EXAMPLES.md'
REQUEST_TIMEOUT, MAX_REPLY, MAX_DEPTH = 30, 8 * 1024 * 1024, 256  # seconds to send a request; bytes of a reply; JSON nesting of a body
WORKERS = 48  # requests served at once (the container allows 64 tasks); one more is told `busy`
ROUTES = {('GET', 'receipt', True): 'receipt', ('GET', 'offers', False): 'offers', ('GET', 'pending', False): 'pending',
          ('POST', 'deliver', False): 'deliver', ('POST', 'objects', False): 'create', ('POST', 'repl', False): 'repl',
          ('POST', 'check', False): 'check', ('GET', 'me', False): 'me', ('POST', 'revoke', False): 'revoke'}
TOP_ONLY = ('repl', 'check', 'me', 'revoke')
ROUTE_HINT = 'GET /AGENTS.md/api lists every route; OPTIONS on a path answers its entries'
FIXED = {('GET', ()): 'guide', ('GET', ('api',)): 'api', ('GET', ('examples',)): 'examples',
         ('POST', ('challenge',)): 'challenge', ('POST', ('verify',)): 'verify'}


def resolve(method, path):
    """-> (catalogue name, parameters) or (None, None). The one router: requests are answered and OPTIONS described by it."""
    parts = [urllib.parse.unquote(p) for p in path.split('/')[1:]]
    if parts[:1] == ['AGENTS.md']:
        rest = parts[1:]
        if (method, tuple(rest)) in FIXED:
            return FIXED[method, tuple(rest)], {}
        heap = rest[:1] == ['heap']
        rest = rest[1:] if heap else rest
        head, obj, tail = (rest[0] if rest else ''), '/'.join(rest[1:]), ''
        if head == 'world':  # an object id may hold slashes: the last segment names the method, or card/source
            if method == 'POST' or (len(rest) > 2 and rest[-1] in ('card', 'source')):
                obj, tail = '/'.join(rest[1:-1]), rest[-1]
            name = 'action' if method == 'POST' else tail or ('object' if obj else 'world')
            name = name if (obj or name == 'world') and method in ('GET', 'POST') else None
        else:
            name = ROUTES.get((method, head, bool(obj)))
            name = None if name in (('create',) if not heap else TOP_ONLY) else name
        return (name, {'heap': heap, 'object': obj, 'method': tail}) if name else (None, None)
    if parts[:1] == ['xrpc'] and len(parts) == 2:
        return 'xrpc', {'nsid': parts[1]}  # the repository answers every method (405 for a write)
    get = {('',): 'home', ('o',): 'find', ('.well-known', 'did.json'): 'did', ('style', ''): 'specimen', ('style',): 'specimen'}.get(tuple(parts))
    if method == 'GET' and get:
        return get, {}
    if method == 'GET' and parts[:1] == ['static'] and len(parts) == 2 and parts[1] in ('style.css', 'theme.js'):
        return 'static', {'file': parts[1]}
    if parts[:1] == ['play'] and method in ('GET', 'POST'):
        return ('play' if method == 'GET' else 'reply'), {'object': '/'.join(parts[1:])}
    if parts[:1] == ['o'] and len(parts) == 2 and method == 'GET':
        return 'page', {'object': parts[1]}
    return None, None



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
        return typed({'text': data['spell'], 'post': ''})
    return typed(data['fields']) if isinstance(data.get('fields'), dict) else data.get('argument', {'tag': 'record', 'fields': []})


# Keys whose values are content ids, digests or chain links: the default rendering omits them; ?full=1 shows them.
HASHY = {'pin', 'compiled', 'library', 'cid', 'previous', 'request', 'turnRequest', 'binary', 'packet', 'digest', 'packetSha256',
         'rootsDigest', 'newPin', 'oldPin', 'head'}


def terse(value, keep=(), root=True, own=False):
    """A reply without its hashes. The root receipt's own `hash` (the entry CID) stays, as does any key named in `keep`."""
    if isinstance(value, list):
        return [terse(v, keep, False) for v in value]
    if not isinstance(value, dict):
        return value
    return {k: terse(v, keep, False, root and k == 'receipt') for k, v in value.items()
            if k in keep or (k not in HASHY and (k != 'hash' or own))}


def brief(value):
    """A checkpoint's tokens and a suspended receipt's blocks (tens of KiB) as their count."""
    if isinstance(value, dict):
        return {k: {'elided': len(v)} if k in ('tokens', 'blocks') and isinstance(v, (list, dict)) else brief(v) for k, v in value.items()}
    return [brief(v) for v in value] if isinstance(value, list) else value


def compact(reply):
    """A turn reply cut to what an agent reads: the status, the outcome, the offered texts and where the receipt sits."""
    receipt = reply['receipt']
    root = (receipt.get('roots') or [{}])[0]
    return {'status': reply.get('status'), 'outcome': receipt.get('outcome'),
            'offers': [o['text'] for o in reply.get('offers') or []],
            'receipt': {'object': root.get('object'), 'version': root.get('version'), 'height': receipt.get('height')}}


def turn_view(reply):
    """A turn reply's default rendering: the turn line with its stamp, the offered texts and where the receipt sits. The whole
    receipt is `?full=1` and `GET /receipt/<slug>`."""
    rc = reply['receipt']
    line = turn_line(reply)
    if rc.get('slug'):
        line = line.removesuffix(f", receipt {rc['slug']}")
    outcome = rc.get('outcome') or {}
    cls = reply.get('class') or outcome.get('class')
    return {'status': reply.get('status'), **({'class': cls} if cls and reply.get('status') == 'refused' else {}),
            'line': f"{pages.stamp(reply.get('status'), word=False)} {line}",
            'offers': [o['text'] for o in reply.get('offers') or []],
            'receipt': {'slug': rc.get('slug'), 'height': rc.get('height')}}


def compact_offers(reply):
    """An offers reply cut to the texts, and the height of the newest (pass it as `after`)."""
    offers = reply.get('offers') or []
    return {'status': reply['status'], 'offers': [o['text'] for o in offers], **({'height': offers[-1]['height']} if offers else {})}



# The catalogue's text, loaded once: routes, conventions, the envelope, the error, XRPC error and refusal classes.
API = json.loads((STATIC / 'catalogue.json').read_text())
CATALOGUE, ERRORS, REFUSALS = API['routes'], API['errors'], API['refusals']


CLAIM_LINES = {'no_post_yet': 'No post with that word from {handle} yet. Post it, then press I posted it.',
               'posts_hidden': 'We cannot see the newest posts of {handle}. Make them public, then press I posted it.',
               'challenge_expired': 'That word is older than 15 minutes. Ask for a new one.',
               'handle_unresolved': '{handle} is not a handle this town knows. Check the spelling.',
               'invalid_handle': '{handle} is not a handle this town knows. Check the spelling.'}


def turn_line(r):
    """A turn's receipt in one line: `admitted garden v3 at height 9, receipt <slug>`, `refused owner: <reading>`, `suspended at height 9`."""
    rc = r.get('receipt') or {}
    out = rc.get('outcome') or {}
    if r.get('status') == 'admitted':
        w = (out.get('writes') or [None])[0]
        return f"admitted {w['object']} v{w.get('version')} at height {rc.get('height')}, receipt {rc.get('slug')}" if w else \
            f"admitted at height {rc.get('height')}, receipt {rc.get('slug')}"
    if r.get('status') == 'refused':
        line = bridge.refusal_line(out, r.get('class'))
        return line + (f"\nnext at {out['next']}" if 'next' in out else '')
    return f"suspended at height {rc.get('height')}" if r.get('status') == 'suspended' else f"{r.get('status')}: {r.get('message', '')}"


def door_rows(view):
    """The doors in an object's state, in menu order: a list, or a relation (`rows {items}`) ordered by each row's place."""
    state = plain(view.get('state') or {})
    doors = (state.get('doors') if isinstance(state, dict) else None) or []
    doors = sorted(doors.get('items') or [], key=lambda d: d.get('place', 0)) if isinstance(doors, dict) else doors
    return [d for d in doors if isinstance(d, dict) and (d.get('to') or {}).get('object')]


def digits(text):
    return text.isascii() and text.isdigit()


def depth(value):
    """How deep a JSON value nests, counted without recursion; stops past MAX_DEPTH."""
    stack, deepest = [(value, 1)], 0
    while stack and deepest <= MAX_DEPTH:
        v, d = stack.pop()
        deepest = max(deepest, d)
        stack += [(x, d + 1) for x in (v.values() if isinstance(v, dict) else v if isinstance(v, list) else ())]
    return deepest


def link(href, **more):
    return {'href': href, **more}


def oid(obj):
    """An object id as a path: slashes stay, unless the last segment would read as /card or /source."""
    return urllib.parse.quote(obj, safe=':' if obj.rpartition('/')[2] in ('card', 'source') else '/:')


def shown(kind):
    """A form field's kind as a spell line shows its value: a choice names its options, the rest their bounds."""
    if kind.get('tag') == 'choice':
        return 'one of ' + ', '.join(kind.get('options') or [])
    return f"<{kind.get('tag')} {kind.get('min')}..{kind.get('max')}>"


def actions(base, obj, inspected, only=None):
    """One action per method in the host's method table that takes a context (a turn can run it), from world-inspect:
    the form's fields when the host has a form for it, else the method's input type; a spell when the object hears spells."""
    forms = {f['action']: f for f in plain(inspected.get('forms') or {'tag': 'list', 'items': []})}
    out = []
    for m in inspected.get('methods') or []:
        if not m.get('context') or (only and m['name'] != only) or m.get('admits', True) is not True:  # `admits`: host op wanted
            continue
        act = {'name': m['name'], 'method': 'POST', 'href': f"{base}/world/{oid(obj)}/{urllib.parse.quote(m['name'], safe='')}"}
        form = forms.get(m['name'])
        if form is None:
            out.append({**act, 'input': m.get('input'), 'body': {'intent': 'text', 'argument': 'typed data of type `input`'}})
            continue
        fields = [{'name': f['name'], 'kind': f['kind']['tag'], 'bounds': {k: v for k, v in f['kind'].items() if k != 'tag'}}
                  for f in form['fields']]
        if m['name'] == 'receive':
            out.append({**act, 'fields': fields, 'body': {'intent': 'text', 'spell': "text: any action's spell, or prose"}})
            continue
        spell = f"delvetalk {form['card']} {form['action']}\n" + ''.join(f"{f['name']}: {shown(f['kind'])}\n" for f in form['fields'])
        out.append({**act, 'fields': fields, 'body': {'intent': 'text', 'fields': {f['name']: f['kind']['tag'] for f in form['fields']}},
                    'spell': spell})
    return out


def receipt_links(base, reply, intent=None):
    """Where a turn's or receipt's reply leads: the receipt by slug, the object it read or made, the offers it left,
    and for a refusal the relation its class names (REFUSALS)."""
    rc, out = reply.get('receipt') or {}, {}
    # Someone else's refusal is the host's public projection, flat: {status: refused, class, root, slug}.
    outcome = rc.get('outcome') or ({'tag': 'refused', 'class': rc.get('class')} if rc.get('status') == 'refused' else {})
    if rc.get('slug'):
        out['receipt'] = link(f"{base}/receipt/{rc['slug']}")
    elif intent and reply.get('class') == 'duplicateIdentity':
        out['receipt'] = link(f'{base}/receipt/{urllib.parse.quote(str(intent), safe="")}')
    roots = rc.get('roots') or ([rc['root']] if isinstance(rc.get('root'), dict) else [])
    o = outcome.get('object') if outcome.get('tag') == 'created' or not roots else roots[0].get('object')  # a refusal may name no root
    if o:
        out.update({'object': link(f'{base}/world/{oid(o)}'), 'source': link(f'{base}/world/{oid(o)}/source')})
    made = [c['object'] for c in outcome.get('creates') or [] if c.get('object')]
    if made:
        out['created'] = [link(f'{base}/world/{oid(o)}', name=o) for o in made]
    if rc.get('height'):
        h = rc['height']
        out['offers'] = link(f'{base}/offers?after={h}&wait={WAIT_MAX}' if reply.get('status') == 'suspended' else f'{base}/offers?after={h - 1}')
    refusal = outcome.get('class') if outcome.get('tag') == 'refused' else reply.get('class')
    if refusal in REFUSALS and REFUSALS[refusal]['hint'] in out:
        out['hint'] = out[REFUSALS[refusal]['hint']]
    elif refusal == 'unknownObject':
        out['hint'] = link(base + '/world')
    return out


_busy = canonical({'status': 'error', 'class': 'busy', 'message': API['errors']['busy']['when']}).encode()
BUSY = (b'HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json; charset=utf-8\r\nRetry-After: 1\r\n'
        b'Connection: close\r\nContent-Length: %d\r\n\r\n' % len(_busy)) + _busy


class AccessLog:
    """One line per request: time, method, path (no query), status, bytes sent, the principal's DID or `-`. Never a credential
    or a body. Rotated by size: past `limit` bytes the file becomes `<name>.1` (the previous one is dropped)."""
    LIMIT = 16 * 1024 * 1024

    def __init__(self, path, limit=LIMIT):
        self.path, self.limit, self.lock = Path(path), limit, threading.Lock()

    def write(self, when, method, path, status, sent, did):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(when))} {method} {path} {status} {sent} {did or '-'}\n"
        with self.lock:
            try:
                if self.path.exists() and self.path.stat().st_size + len(line) > self.limit:
                    os.replace(self.path, self.path.with_name(self.path.name + '.1'))
                with open(self.path, 'a') as f:
                    f.write(line)
            except OSError:
                pass  # the log is not the front's to fail on


class Front(ThreadingHTTPServer):  # threaded so a long poll holds one thread, not the front
    daemon_threads = True
    request_queue_size = 128  # the default backlog of 5 resets connections when a burst arrives faster than accept() runs

    def __init__(self, address, host, identity, origin=ORIGIN, clock=time.time, heaps=None, repl=None, trust_proxy=False, sleep=time.sleep, hand=None, access=None, workers=WORKERS):
        super().__init__(address, Handler)
        self.slots, self.receiving, self.receiving_lock = threading.BoundedSemaphore(workers), {}, threading.Lock()
        threading.Thread(target=self.reap, daemon=True).start()
        self.access = access
        self.host, self.identity, self.origin, self.clock = host, identity, origin, clock
        self.heaps, self.repl, self.trust_proxy, self.sleep, self.hand = heaps, repl, trust_proxy, sleep, hand
        self.repo = Repo(origin)  # the journal as AT Protocol records, read only
        self.oauth = oauth.OAuth(origin)  # log in with delve.town (transport/oauth.py)
        self.hits, self.nonce, self.hits_lock = {}, secrets.token_hex(4), threading.Lock()
        self.request_timeout = REQUEST_TIMEOUT
        # The bytes this front runs as its host, so an operator can compare them with the build's pin.
        info = {} if hasattr(host, 'binary') else host.send({'op': 'hostd-info'})
        self.host_sha256 = hashlib.sha256(Path(host.binary).read_bytes()).hexdigest() if hasattr(host, 'binary') else info.get('hostSha256', 'unknown')
        self.host_timeout = getattr(host, "timeout", HOST_TIMEOUT + 30)
        self.library, self.hostd_pid = info.get('library'), info.get('pid')  # the pin of the library hostd sealed; the REPL compiles against it by name

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):  # every worker is taken: say so at once rather than queue behind them
            try:
                request.settimeout(1)
                request.sendall(BUSY)
            except OSError:
                pass
            return self.shutdown_request(request)
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def reap(self):
        """The absolute deadline: a request not received `request_timeout` seconds after its connection opened has its
        reading side shut, however steadily its bytes trickle in (a reply already under way is unaffected)."""
        while self.socket.fileno() != -1:
            time.sleep(0.25)
            with self.receiving_lock:
                late = [c for c, t in self.receiving.items() if time.monotonic() - t > self.request_timeout]
            for c in late:
                try:
                    c.shutdown(socket.SHUT_RD)
                except OSError:
                    pass

    def sync_library(self, force=False):
        """Re-read hostd-info when hostd's pid changed (it restarted, maybe with a new library), or when forced."""
        if hasattr(self.host, 'binary'):
            return
        info = self.host.send({'op': 'hostd-info'})
        if force or info.get('pid') != self.hostd_pid:
            self.library, self.hostd_pid = info.get('library'), info.get('pid')

    def used(self, credential):
        now = self.clock()
        with self.hits_lock:
            return [t for t in self.hits.get(credential, []) if now - t < WINDOW]

    def limited(self, key, rate=RATE):
        """0 when under the limit, else the seconds until the oldest counted request leaves the window."""
        with self.hits_lock:  # read, test and append as one step
            now = self.clock()
            hits = [t for t in self.hits.get(key, []) if now - t < WINDOW]
            self.hits[key] = hits + [now]
        return max(1, int(hits[-rate] + WINDOW - now + 0.999)) if len(hits) >= rate else 0

    def record_handle(self, did, handle):
        """Tell the host a verified account has arrived (the clock principal alone may), so cards name them by handle.
        Idempotent at the host; a refusal leaves the verification standing."""
        return self.host.send({'op': 'world-arrive', 'principal': CLOCK, 'did': did, 'handle': handle})

    def catalogue(self, here):
        """Every route, the error envelope, the error and refusal classes (static/catalogue.json) and the limits, as data."""
        return {'status': 'catalogue', 'origin': self.origin, **API,
                'limits': {'bodyBytes': MAX_BODY, 'moduleBytes': MAX_SOURCE, 'modules': MAX_MODULES, 'bodyDepth': MAX_DEPTH,
                           'replyBytes': MAX_REPLY, 'requestSeconds': REQUEST_TIMEOUT, 'workers': WORKERS, 'hostSeconds': self.host_timeout,
                           'requestLineBytes': 65536, 'headerLineBytes': 65536, 'headers': 100, 'offersWaitSeconds': WAIT_MAX,
                           'ratePerCredential': [RATE, WINDOW], 'ratePerAddressOnChallengeAndVerify': [OPEN_RATE, WINDOW],
                           'ratePerAddressOnXrpcWithoutCredential': [RATE, WINDOW], 'ratePerAddressOnPagesWithoutLogin': [RATE, WINDOW], 'idsPerPage': 64, 'deliverPerCall': DELIVER_LIMIT},
                '_links': {'self': link(here), 'guide': link(PREFIX), 'examples': link(PREFIX + '/examples'),
                           'challenge': link(PREFIX + '/challenge')}}

    def guide(self, path=GUIDE):
        return path.read_text().replace('{{origin}}', self.origin)


class Counted:
    """The reply socket's file, counting what is written."""
    def __init__(self, f):
        self.f, self.sent = f, 0

    def write(self, data):
        self.sent += len(data)
        return self.f.write(data)

    def __getattr__(self, name):
        return getattr(self.f, name)


class Handler(BaseHTTPRequestHandler):
    server_version = 'DelveTalk'

    def log_message(self, *args):
        pass

    def setup(self):
        self.timeout = self.server.request_timeout  # a client that stalls sending its request is dropped after this
        with self.server.receiving_lock:
            self.server.receiving[self.request] = time.monotonic()  # and one that trickles, by the reaper
        super().setup()
        self.wfile = Counted(self.wfile)

    def finish(self):
        with self.server.receiving_lock:
            self.server.receiving.pop(self.request, None)
        super().finish()

    def send_response(self, code, message=None):
        self.status = code
        super().send_response(code, message)

    def handle_one_request(self):
        self.status, self.did, self.head = 0, None, False
        self.wfile.sent = 0
        super().handle_one_request()
        if self.server.access and self.status:  # a request that never parsed has no status
            self.server.access.write(self.server.clock(), getattr(self, 'command', '-'), urllib.parse.urlsplit(self.path).path,
                                     self.status, self.wfile.sent, self.did)

    def reply(self, code, body, ctype='application/json', headers=()):
        raw = body.encode('utf-8', 'backslashreplace') if isinstance(body, str) else body  # a lone surrogate the host echoed stays a JSON escape
        if len(raw) > MAX_REPLY and code < 400:
            return self.fail('replyTooLarge', hint='?compact=1, a page (after, limit), or the receipt alone')
        self.replied = True
        self.send_response(code)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype.startswith(('text/', 'application/json')) else ''))
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if not getattr(self, 'head', False):
            self.wfile.write(raw)

    def fail(self, cls, message=None, hint=None, links=None, more=None, acts=None, headers=()):
        """The one error envelope: {status, class, message, hint?, _links} over the host's own fields, if any (`more`)."""
        code, status, when = ERRORS[cls]['code'], ERRORS[cls]['status'], ERRORS[cls]['when']
        body = {**(more or {}), 'status': status, 'class': cls, 'message': message or when, **({'hint': hint} if hint else {}),
                '_links': {'self': link(self.path), 'api': link(PREFIX + '/api'), **(links or {})}, **({'_actions': acts} if acts else {})}
        if self.browser():  # the same envelope, as a page: a person reads a refusal as easily as a card
            return self.html(code, pages.refusal(f'{code} {cls}', None, body), headers)
        self.reply(code, canonical(body), headers=headers)

    def browser(self):
        return 'text/html' in (getattr(self, 'headers', None) or {}).get('Accept', '') or self.textual()

    def textual(self):
        """?text=1, or Accept: text/plain without HTML or JSON: the page as plain text, read off the page's own markup."""
        accept = (getattr(self, 'headers', None) or {}).get('Accept', '')
        return urllib.parse.parse_qs(urllib.parse.urlsplit(getattr(self, 'path', '')).query).get('text') == ['1'] or \
            ('text/plain' in accept and 'text/html' not in accept and 'application/json' not in accept)

    def send_error(self, code, message=None, explain=None):
        """http.server's own refusals (a bad request line, a long URI or header, an unknown method), in the envelope."""
        self.close_connection = True
        cls = {408: 'requestTimeout', 414: 'uriTooLong', 431: 'headersTooLarge', 501: 'notImplemented', 505: 'httpVersion'}.get(code, 'badRequest')
        if not hasattr(self, 'path'):  # the request line did not parse
            self.path = ''
        if self.request_version == 'HTTP/0.9':  # unparsed: answer with a status line all the same
            self.request_version = 'HTTP/1.0'
        self.fail(cls, message)

    def body(self):
        """-> dict, or None after replying with the refusal. JSON, or a urlencoded form."""
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            n = -1
        if n < 0:
            return self.fail('badRequest', 'Content-Length is not a number')
        if n > MAX_BODY:
            return self.fail('bodyTooLarge')
        try:
            raw = self.rfile.read(n)
        except TimeoutError:
            raw = b''
        if len(raw) < n:  # stalled, or cut at the deadline
            return self.fail('requestTimeout')
        # curl -d labels JSON as a form; a browser's form body never starts with '{'
        if (self.headers.get('Content-Type') or '').startswith('application/x-www-form-urlencoded') and not raw.lstrip().startswith(b'{'):
            return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors='replace'), keep_blank_values=True).items()}  # a blank field is a value
        try:
            data = json.loads(raw or b'{}')
        except (ValueError, RecursionError):
            return self.fail('badJson', 'the body is not JSON')
        if not isinstance(data, dict):
            return self.fail('badJson', 'the body must be a JSON object')
        return data if depth(data) <= MAX_DEPTH else self.fail('badJson', f'the body nests deeper than {MAX_DEPTH}')

    def answer(self, reply, keep=(), links=None, acts=None):
        """The host's reply, rendered, with its controls: a diagnostic carried as JSON text in `message` is lifted, its `hint`
        with it, and a checkpoint's tokens are counted, not shown (?full=1 shows them)."""
        status = reply.get('status')
        try:
            inner = json.loads(reply['message']) if status == 'error' else None
        except (KeyError, TypeError, ValueError):
            inner = None
        reply = {**inner, 'status': 'error'} if isinstance(inner, dict) else reply
        if isinstance(reply.get('diagnostic'), dict) and 'hint' in reply['diagnostic']:
            reply = {**reply, 'hint': reply['diagnostic']['hint']}
        full = 'full' in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        acts = {a['name']: a['spell'] for a in acts or () if a.get('spell')}  # the spell templates; fields and hrefs follow the catalogue's rule
        body = reply if full else brief(terse(reply, keep))
        cls = reply.get('class') if reply.get('class') in ('hostUnavailable', 'hostTimeout') else \
            {'error': 'hostRequest', 'unknown': 'unknown', 'denied': 'denied', 'ambiguous': 'ambiguous'}.get(status)
        if cls:  # the host said no, or was not there: the envelope, over the host's own words
            return self.fail(cls, reply.get('message'), reply.get('hint'), links, body, acts)
        if self.browser():
            return self.html(200, pages.rendered(getattr(self, 'kind', 'reply'), body, links or {}, *((self.who['handle'], self.who['did']) if getattr(self, 'who', None) else (None,))))
        self.reply(200, canonical({**body, '_links': {'self': link(self.path), **(links or {})}, **({'_actions': acts} if acts else {})}))

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
            who = self.server.identity.authenticate(credential)
        except IdentityError:
            return None
        self.did = (who or {}).get('did') or self.did
        return who

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = lambda self: self.dispatch(self.command)

    def do_HEAD(self):
        """Answers as GET does, headers only."""
        self.head = True
        self.dispatch('GET')

    def dispatch(self, method):
        """Route, and turn whatever escapes into a named envelope: a client gone is dropped, anything else is `internal`."""
        self.replied = False
        try:
            self.route(method) if method != 'OPTIONS' else self.options()
        except (ConnectionError, TimeoutError):
            self.close_connection = True
        except Exception:
            traceback.print_exc()
            if not self.replied:
                self.fail('internal')

    def route(self, method):
        path = urllib.parse.urlsplit(self.path).path
        if self.server.hand:  # the owner's console, on its own loopback listener and nothing else there; never in the catalogue
            if path.split('/')[1:2] != ['hand']:
                return self.fail('unknownRoute', f'no route at {path}')
            form = self.body() if method == 'POST' else None
            if method == 'POST' and form is None:
                return
            code, body, headers = self.server.hand.handle(method, self.path, self.headers.get('Cookie') or '', form)
            return self.html(code, body, headers)
        if path.split('/')[1:2] == ['oauth']:
            return oauth.route(self, method, path)
        name, p = resolve(method, path)
        if name is None:
            allow = [m for m in ('GET', 'POST') if resolve(m, path)[0]]
            if allow:
                return self.fail('methodNotAllowed', f'{path} takes {" and ".join(allow)}', headers=[('Allow', ', '.join(allow + ['OPTIONS']))])
            return self.fail('unknownRoute', f'no route at {path}', ROUTE_HINT)
        if name == 'guide' and 'application/json' not in (self.headers.get('Accept') or ''):
            return self.reply(200, self.server.guide(), 'text/plain', [('X-DelveTalk-Host-Sha256', self.server.host_sha256)])
        if name == 'api' and self.browser():
            return self.html(200, pages.catalogue(self.server.catalogue(self.path), None))
        if name in ('guide', 'api'):
            return self.reply(200, canonical(self.server.catalogue(self.path)), headers=[('X-DelveTalk-Host-Sha256', self.server.host_sha256)])
        if name == 'examples':
            return self.reply(200, self.server.guide(EXAMPLES), 'text/plain')
        if name in ('challenge', 'verify'):
            return self.identify(name)
        if name == 'static':
            return self.reply(200, (STATIC / p['file']).read_bytes(), 'text/css' if p['file'].endswith('css') else 'text/javascript')
        if name in ('xrpc', 'did'):
            return self.xrpc(method, p.get('nsid', 'did.json'))
        if name in ('home', 'page'):  # pages ask the host: limited per account, or per address, before they do
            key = self.cookie() if self.principal(self.cookie()) else 'page:' + self.client_ip()
            wait = self.server.limited(key)
            if wait:
                return self.fail('rateLimited', f'more than {RATE} pages per {WINDOW} seconds', headers=[('Retry-After', str(wait))])
        if name == 'home':
            return self.home()
        if name == 'specimen':
            return self.html(200, pages.page('style', None, (STATIC / 'specimen.html').read_text()))
        if name == 'find':
            found = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('object', [''])[0]
            return self.reply(302, '', 'text/plain', [('Location', '/o/' + urllib.parse.quote(found, safe=''))])
        if name in ('play', 'reply'):
            return self.play(p['object'] or 'directory', name == 'reply')
        if name == 'page':
            return self.object_page(p['object'])
        return self.agents(name, p['heap'], p['object'], p['method'])

    def options(self):
        """The catalogue entries of the routes at this path, one per method."""
        path = urllib.parse.urlsplit(self.path).path
        names = [n for n in (resolve(m, path)[0] for m in ('GET', 'POST')) if n]
        if not names:
            return self.fail('unknownRoute', f'no route at {path}', ROUTE_HINT)
        entries = [e for n in names for e in CATALOGUE if e['name'] == n]
        allow = ', '.join(sorted({e['method'] for e in entries}) + ['OPTIONS'])
        self.reply(200, canonical({'status': 'route', 'routes': entries, '_links': {'self': link(self.path), 'api': link(PREFIX + '/api')}}),
                   headers=[('Allow', allow)])

    # ---- agents

    def agents(self, kind, heap, obj, tail):
        auth = self.headers.get('Authorization') or ''
        credential = auth[7:] if auth.startswith('Bearer ') else self.cookie() if self.browser() and self.command == 'GET' else ''
        who = self.principal(credential)
        if who is None:
            return self.fail('unauthenticated', hint='POST /AGENTS.md/challenge, post its text, POST /AGENTS.md/verify; then send Authorization: Bearer <credential>',
                             links={'hint': link(PREFIX + '/challenge')})
        wait, self.kind, self.who = self.server.limited(credential), kind, who
        if wait:
            return self.fail('rateLimited', f'more than {RATE} requests per {WINDOW} seconds', links={'hint': link(PREFIX + '/me')},
                             headers=[('Retry-After', str(wait))])
        if kind == 'me':
            return self.me(credential, who)
        if kind == 'revoke':
            self.server.identity.revoke(credential)
            return self.reply(200, canonical({'status': 'revoked', '_links': {'self': link(self.path), 'challenge': link(PREFIX + '/challenge')}}),
                              headers=[('Set-Cookie', f'{COOKIE}=; Path=/; Max-Age=0')])
        if kind in ('repl', 'check'):
            return self.run_repl(who['did'], kind)
        host = self.server.heaps.get(who['did']) if heap else self.server.host
        principal = who['did']  # the principal the host sees; the handle is display only
        base = PREFIX + ('/heap' if heap else '')
        if self.browser() and kind in ('object', 'card', 'source') and not heap:
            return self.object_page(obj, who)
        at = lambda o: {'object': link(f'{base}/world/{oid(o)}'), 'card': link(f'{base}/world/{oid(o)}/card'),
                        'source': link(f'{base}/world/{oid(o)}/source')}
        send = lambda req, links=None: self.answer(host.send(req), links=links)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        if kind == 'world':
            reply = host.send({'op': 'world-objects', 'principal': principal, 'methods': True, **{k: q[k] for k in ('prefix', 'after') if k in q}})
            ids = reply.get('ids') or []
            nxt = urllib.parse.urlencode({**({'prefix': q['prefix']} if 'prefix' in q else {}), 'after': ids[-1]}) if ids and reply.get('more') else ''
            names = reply.get('methods') or {}  # per id, when the host answers them (host op wanted)
            if self.browser():
                words = {d['to']['object']: d.get('label', '') for d in door_rows(host.send({'op': 'world-view', 'principal': principal, 'object': 'directory'}))}
                return self.html(200, pages.listing(ids, words, who['handle'], principal, nxt and f'{base}/world?{nxt}'))
            return self.answer(reply, links={'item': [link(f'{base}/world/{oid(i)}', name=i, **({'actions': names[i]} if i in names else {}))
                                                      for i in ids],
                                             **({'next': link(f'{base}/world?{nxt}')} if nxt else {}), 'offers': link(base + '/offers')})
        if kind in ('object', 'card', 'source'):
            op = {'object': 'world-view', 'card': 'world-card', 'source': 'world-inspect'}[kind]
            r = host.send({'op': op, 'principal': principal, 'object': obj})
            seen = r if kind == 'source' else host.send({'op': 'world-inspect', 'principal': principal, 'object': obj}) \
                if r.get('status') in ('viewed', 'card') else {}
            acts = actions(base, obj, seen) if seen.get('status') == 'inspected' else None
            if kind != 'object' and 'full' not in q:  # the readable part; ?full=1 is the host's reply verbatim
                r = {k: plain(v) if k == 'forms' else v for k, v in r.items() if k not in ('document', 'methods')}
            links = {**at(obj), 'world': link(base + '/world'), 'offers': link(base + '/offers')}
            return self.answer(r, keep=('pin',) if kind == 'source' else (), links=links if r.get('status') != 'unknown' else
                               {'world': link(base + '/world'), 'hint': link(base + '/world')}, acts=acts)  # `pin`: the program's name, in source
        if kind == 'receipt':
            if SLUG.fullmatch(obj):  # a proquint slug names a receipt; any other text is the intent
                found = host.send({'op': 'world-resolve', 'principal': principal, 'slug': obj})
                if 'receipt' in found:
                    return self.answer({'status': 'receipt', 'receipt': found['receipt']}, links=receipt_links(base, found))
                if found.get('identity'):
                    r = host.send({'op': 'world-receipt', 'principal': principal, 'identity': found['identity']})
                    return self.answer(r, links=receipt_links(base, r))
                if 'unknown' not in str(found.get('message')):
                    return self.answer(found)
            r = host.send({'op': 'world-receipt', 'principal': principal, 'identity': obj})
            return self.answer(r, links=receipt_links(base, r))
        if kind == 'offers':
            wait, after = min(int(q['wait']), WAIT_MAX) if digits(q.get('wait', '')) else 0, {'after': q['after']} if 'after' in q else {}
            after = {'after': int(q['after'])} if digits(after.get('after', '')) else after
            for waited in range(0, wait + 1, WAIT_STEP):
                reply = host.send({'op': 'world-offers', 'principal': principal, **after})
                if reply.get('status') != 'offers' or reply.get('offers') or waited + WAIT_STEP > wait:
                    break
                self.server.sleep(WAIT_STEP)
            newest = (reply.get('offers') or [{}])[-1].get('height', after.get('after', ''))
            links = {'next': link(f'{base}/offers?after={newest}&wait={WAIT_MAX}'), 'world': link(base + '/world')}
            return self.answer(compact_offers(reply) if q.get('compact') == '1' and reply.get('status') == 'offers' else reply, links=links)
        if kind == 'pending':
            return send({'op': 'world-pending'}, {'deliver': link(base + '/deliver')})
        data = self.body()
        if data is None:
            return
        if kind == 'deliver':
            return send({'op': 'world-deliver', 'limit': DELIVER_LIMIT}, {'pending': link(base + '/pending')})
        if kind == 'create':  # a name no spell can address would publish spells nobody can cast: the host's parser says
            name = data.get('object')
            read = host.send({'op': 'spell-parse', 'text': f'delvetalk {name} ?'}) if isinstance(name, str) else {}
            if read.get('status') == 'parsed' and (read.get('spell') or {}).get('card') != name:
                return self.fail('unspellable', f'the host does not read `delvetalk {name} ?` as a spell; choose a name a spell can address')
            made = {k: typed(data[k]) if k == 'seed' else data[k] for k in CREATE_KEYS if k in data}
            reply = host.send({'op': 'world-create', 'principal': principal, 'identity': data.get('intent'), **made})
            return self.answer(reply, links=receipt_links(base, reply))
        reply = host.send({'op': 'world-turn', 'principal': principal, 'object': obj, 'method': tail,
                           'argument': argument(data), 'identity': data.get('intent')})
        links, acts = {**at(obj), **receipt_links(base, reply, data.get('intent'))}, None
        if reply.get('status') in ('refused', 'error'):  # the usage action: the method as the host's table shows it
            seen = host.send({'op': 'world-inspect', 'principal': principal, 'object': obj})
            acts = actions(base, obj, seen, only=tail) if seen.get('status') == 'inspected' else None
            links.setdefault('hint', links['source'])
        if 'receipt' in reply and reply.get('status') in ('admitted', 'refused', 'suspended') and 'full' not in q:
            reply = compact(reply) if q.get('compact') == '1' else turn_view(reply)
        self.answer(reply, links=links, acts=acts)

    def xrpc(self, method, nsid):
        """The read-only repository (transport/repo.py): no credential reads as the public reader, a bearer as its principal."""
        auth = self.headers.get('Authorization') or ''
        credential = auth[7:] if auth.startswith('Bearer ') else ''
        who = self.principal(credential) if credential else {}
        if who is None:
            return self.xrpc_reply(401, {'error': 'InvalidToken', 'message': 'unverified or revoked credential'})
        wait = self.server.limited(credential or 'xrpc:' + self.client_ip())
        if wait:
            return self.xrpc_reply(429, {'error': 'RateLimitExceeded', 'message': f'more than {RATE} requests per {WINDOW} seconds'},
                                   [('Retry-After', str(wait))])
        if nsid == 'did.json':
            return self.reply(200, canonical(self.server.repo.did_document()), 'application/did+json')
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        code, body, ctype = self.server.repo.serve(self.server.host, method, nsid, q, who.get('did'))
        self.reply(code, body if isinstance(body, bytes) else canonical(body), ctype) if code < 400 else self.xrpc_reply(code, body)

    def xrpc_reply(self, code, body, headers=()):
        """XRPC's {error, message}, with the envelope's status, class and links beside it. A record or a page is the
        AT Protocol's shape, verbatim: its `cursor` is its control."""
        error = {'status': 'refused' if code == 403 else 'error', 'class': body['error'],
                 '_links': {'self': link(self.path), 'api': link(PREFIX + '/api')}}
        if self.browser():
            return self.html(code, pages.refusal(f"{code} {body['error']}", None, {**body, **error}), headers)
        self.reply(code, canonical({**body, **error}), headers=headers)

    def client_ip(self):
        forwarded = (self.headers.get('X-Forwarded-For') or '').split(',')[-1].strip()
        return forwarded if self.server.trust_proxy and forwarded else self.client_address[0]

    def identify(self, which):
        wait = self.server.limited('ip:' + self.client_ip(), OPEN_RATE)
        if wait:
            return self.fail('rateLimited', f'more than {OPEN_RATE} requests per {WINDOW} seconds from one address', headers=[('Retry-After', str(wait))])
        data = self.body()
        if data is None:
            return
        auth = self.headers.get('Authorization') or ''  # the challenge answered is the requester's own when it holds its credential
        mine = auth[7:] if auth.startswith('Bearer ') else self.cookie()
        try:
            text = lambda k: data.get(k) if isinstance(data.get(k), str) else ''
            if which == 'challenge':
                out = self.server.identity.challenge(text('handle'))
                if self.browser():
                    return self.html(200, pages.challenged(out['handle'], out['text']), self.login_cookie(out['credential']))
                return self.reply(200, canonical({**out, '_links': {'self': link(self.path), 'verify': link(PREFIX + '/verify')}}),
                                  headers=self.login_cookie(out['credential']))
            # An agent that has the post's URI gives it; a person presses "I posted it" and the account's newest posts are read.
            ident = self.server.identity
            out = ident.verify(text('handle'), text('uri'), mine) if text('uri') else ident.claim(text('handle'), mine)
        except IdentityError as err:
            line = CLAIM_LINES.get(err.code)
            waiting = self.server.identity.pending(text('handle'), mine) if err.code in ('no_post_yet', 'posts_hidden') else None
            if self.browser() and waiting:  # the word is still good: show it again with what went wrong
                return self.html(200, pages.challenged(text('handle'), waiting['text'], line.format(handle=text('handle'))))
            return self.fail('identity', line.format(handle=text('handle')) if line else err.code, links={'hint': link(PREFIX + '/challenge')})
        self.server.record_handle(out['did'], out['handle'])
        mine = self.principal(self.cookie())  # a browser that asked for the challenge holds its credential
        links = {'self': link(self.path), 'world': link(PREFIX + '/world'), 'me': link(PREFIX + '/me'), 'api': link(PREFIX + '/api')}
        keep = self.login_cookie(self.cookie()) if mine and mine['did'] == out['did'] else ()
        if self.browser():
            return self.html(200, pages.page('claimed', out['handle'], pages.T['verified'].format(handle=html.escape(out['handle']))), keep)
        self.reply(200, canonical({**terse(out), '_links': links}), headers=keep)

    def me(self, credential, who):
        heap = self.server.heaps.get(who['did'], create=False)
        count = heap.send({'op': 'world-status'}).get('objects') if heap else 0
        self.answer({'principal': who['did'], 'handle': who['handle'], 'did': who['did'], 'verified': who['verified'], 'heapObjects': count,
                     'rateLimit': {'limit': RATE, 'windowSeconds': WINDOW, 'remaining': max(0, RATE - len(self.server.used(credential)))}},
                    links={'world': link(PREFIX + '/world'), 'heap': link(PREFIX + '/heap/world'), 'offers': link(PREFIX + '/offers'), 'revoke': link(PREFIX + '/revoke')})

    def run_repl(self, principal, kind='repl'):
        data = self.body()
        if data is None:
            return
        modules = data['modules'] if 'modules' in data else [{'name': 'Package', 'source': data.get('source', '')}]
        if not isinstance(modules, list) or len(modules) > MAX_MODULES:
            return self.fail('badModules')
        for m in modules:
            if not isinstance(m, dict) or len(str(m.get('source', '')).encode()) > MAX_SOURCE:
                return self.fail('moduleTooLarge' if isinstance(m, dict) else 'badModules', hint='import the library by name (./Plan.obend); it is not sent')
        if kind == 'check':  # the verdict, against the world's sealed library; ?full=1 adds the compiled artifact
            checked = self.server.host.send({'op': 'world-check', 'principal': principal, 'modules': modules, 'entry': data.get('entry')})
            return self.answer(checked if 'full=1' in self.path else {k: v for k, v in checked.items() if k != 'artifact'},
                               links={'repl': link(PREFIX + '/repl')})
        repl = self.server.repl
        for retry in (False, True):  # once per request: an unknown pin means hostd restarted with another library
            self.server.sync_library(force=retry)
            pin = {'library': self.server.library} if self.server.library else {}
            compiled = repl.send({'op': 'compile', 'modules': modules, 'entry': data.get('entry'), **pin})
            if retry or 'unknown library pin' not in str(compiled.get('message')):
                break
        if compiled.get('status') != 'compiled':
            return self.answer(compiled, links={'check': link(PREFIX + '/check')})
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
        if reply.get('status') == 'error':
            return self.answer(reply, links={'check': link(PREFIX + '/check')})
        # The default rendering omits hashes like every other reply; only the checkpoint, which the client sends back, stays whole.
        body = reply if 'full=1' in self.path else {**terse({k: v for k, v in reply.items() if k != 'checkpoint'}), **({'checkpoint': reply['checkpoint']} if 'checkpoint' in reply else {})}
        self.reply(200, canonical({**body, '_links': {'self': link(self.path)}}))

    # ---- humans

    def play(self, name, spoke):
        """The world in a browser as a verified principal (the session cookie verify sets): the card world-card renders, the
        doors in the object's state, a reply box whose text goes to `receive` as a Delve reply would."""
        credential = self.cookie()
        who, said = self.principal(credential), ''
        if who is None:
            return self.reply(303, '', 'text/plain', [('Location', '/')])
        if self.server.limited(credential):
            return self.html(429, pages.page('slow down', who['handle'], '<h1>Too many requests</h1>'))
        host, did = self.server.host, who['did']
        if spoke:
            data = self.body()
            if data is None:
                return
            intent = f'play:{self.server.nonce}:{int(self.server.clock() * 1000)}:{secrets.token_hex(3)}'
            kinds = {'n:': lambda v: int(v) if digits(v) else v, 'c:': lambda v: {'tag': 'variant', 'label': v, 'payload': {'tag': 'record', 'fields': []}}}
            fields = {k[2:] if k[:2] in kinds else k: kinds[k[:2]](v) if k[:2] in kinds else v for k, v in data.items() if k != 'method'}
            r = host.send({'op': 'world-turn', 'principal': did, 'object': name, 'method': data.get('method') or 'receive', 'identity': intent,
                           'argument': typed(fields if data.get('method') else {'text': str(data.get('text', '')), 'post': ''})})
            offers = [o['text'] for o in r.get('offers') or []]
            for _ in range(WAIT_MAX if r.get('status') == 'suspended' else 0):  # the interpreter answers as an offer to this intent
                seen = host.send({'op': 'world-offers', 'principal': did, 'after': r['receipt']['height']}).get('offers') or []
                offers = [o['text'] for o in seen if (o.get('identity') or {}).get('intent') == intent]
                if offers:
                    break
                self.server.sleep(WAIT_STEP)
            if r.get('status') == 'usage':  # the host's `?` answer: the card's usage, its text sacred
                said = pages.T['usage'].format(text=html.escape(str(r.get('text', ''))))
            else:
                said = pages.T['said'].format(cls=html.escape(str(r.get('status'))), icon=pages.stamp(r.get('status'), word=False), line=html.escape(turn_line(r)),
                                              offers=''.join(pages.T['offer'].format(text=html.escape(t)) for t in offers) or pages.T['quiet'])
        card, view = (host.send({'op': op, 'principal': did, 'object': name}) for op in ('world-card', 'world-view'))
        if card.get('status') != 'card' and not said:  # an object with no card still shows the turn a form ran on it
            return self.html(404, pages.refusal(name, who['handle'], card, card.get('status')))
        self.html(200, pages.page(name, who['handle'], pages.T['page'].format(
            name=html.escape(name), path=html.escape(oid(name)), said=said, card=html.escape(card.get('text', '')), doors=pages.door_nav(door_rows(view)))))

    def html(self, code, body, headers=()):
        self.reply(code, *((pages.text(body), 'text/plain') if self.textual() else (body, 'text/html')), headers)

    def home(self):
        who, host = self.principal(self.cookie()), self.server.host
        ids = host.send({'op': 'world-objects', 'principal': who['did'] if who else 'anonymous'}).get('ids') or []
        self.html(200, pages.home(host.send({'op': 'world-status'}), who and who['handle'], ids, who and who['did']))

    def object_page(self, name, who=None):
        """An object as its reader may read it (the authenticated `who`, else the cookie's login, else anyone): its card as
        the reader sees it, its ledger; logged in, a link to play it."""
        who = who or self.principal(self.cookie())
        handle, principal, host = who and who['handle'], who and who['did'], self.server.host
        view = host.send({'op': 'world-view', 'principal': principal or 'anonymous', 'object': name})
        if view.get('status') != 'viewed':
            return self.html(404, pages.refusal(name, handle, view, view.get('status')))
        card, seen = (host.send({'op': op, 'principal': principal or 'anonymous', 'object': name}) for op in ('world-card', 'world-inspect'))
        acts = actions('', name, seen) if principal and seen.get('status') == 'inspected' else ()
        self.html(200, pages.obj(name, handle, view, card.get('text') if card.get('status') == 'card' else None,
                                 self.history(host, name, principal), principal, door_rows(view), seen, acts))

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
    ap.add_argument('--hand-token', metavar='SECRET', help='serve the owner\'s console at /hand/ (needs the token once) on --hand-bind:--hand-port only')
    ap.add_argument('--hand-bind', default='127.0.0.1', help='the hand\'s listener: loopback, reached by an ssh forward')
    ap.add_argument('--hand-port', type=int, default=8766)
    ap.add_argument('--credentials', default=post.CREDENTIALS, help='the Delve credentials file the hand posts with')
    ap.add_argument('--trust-proxy', action='store_true', help='key the unauthenticated limits on the last X-Forwarded-For entry')
    a = ap.parse_args(argv)
    sock = a.host_socket or Path(a.state) / 'host.sock'
    host, heaps, repl = HostClient(sock), RemoteHeaps(sock, Path(a.state) / 'heaps'), HostClient(sock, stateless=True)
    ident = Identity(a.state, Client(http_transport), a.origin)
    front = Front((a.bind, a.port), host, ident, a.origin, heaps=heaps, repl=repl, trust_proxy=a.trust_proxy, access=AccessLog(Path(a.state) / 'access.log'))
    if a.hand_token:  # never on the public port: its own listener, which serves /hand/ and nothing else
        console = Front((a.hand_bind, a.hand_port), host, ident, a.origin, hand=hand.Hand(a.state, host, a.hand_token, a.credentials))
        threading.Thread(target=console.serve_forever, daemon=True).start()
    try:
        front.serve_forever()
    finally:
        front.host.close()
        front.heaps.close()
        front.repl.close()

if __name__ == '__main__':
    sys.exit(main())
