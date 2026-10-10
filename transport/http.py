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
from transport.hostproc import HostClient, RemoteHeaps, add_host_args
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


# Refusal classes (a refused turn's receipt) and the link relation an agent reads next for each.
REFUSALS = {'staleRoot': (True, 'self', 'something the turn read moved before it committed'),
            'budget': (True, 'receipt', 'the turn ran out of ticks, heap or bytes; `reason` names which'),
            'evaluation': (True, 'source', 'the program refused or a Plan was malformed; `reason` says which'),
            'capacity': (True, 'receipt', 'a host limit is full; `reason` or `object` names it'),
            'typeMismatch': (False, 'source', "the argument does not fit the method's input; `expected` shows the form"),
            'lawRefused': (False, 'source', "the object's law refused the change; `clause` names the law line"),
            'unknownObject': (False, 'world', 'no such object, or not yours to see'),
            'programRefused': (False, 'source', "a reprogram's package: `clause` is packageBytes, compile, stateType, migration or law syntax"),
            'outOfRange': (False, 'receipt', 'a list edit named an index past the end'),
            'absentItem': (False, 'receipt', 'a list edit named an item not there'),
            'requiredAbsence': (False, 'receipt', 'a `create` found the object already there; `root` names where'),
            'budgetExhausted': (False, 'receipt', 'a chain of sends spent its ledger (`depth`, `work` or `storage`)'),
            'duplicateIdentity': (False, 'receipt', 'the same intent with a different request: not a receipt; `original` is the first')}


def link(href, **more):
    return {'href': href, **more}


def oid(obj):
    """An object id as a path: slashes stay, unless the last segment would read as /card or /source."""
    return urllib.parse.quote(obj, safe=':' if obj.rpartition('/')[2] in ('card', 'source') else '/:')


def shown(kind):
    """A form field's kind as a spell line shows it."""
    if kind.get('tag') == 'choice':
        return ' | '.join(kind.get('options') or [])
    return f"{kind.get('tag')} {kind.get('min')}..{kind.get('max')}"


def actions(base, obj, inspected, only=None):
    """One action per method in the host's method table that takes a context (a turn can run it), from world-inspect:
    the form's fields when the host has a form for it, else the method's input type; a spell when the object hears spells."""
    forms = {f['action']: f for f in plain(inspected.get('forms') or {'tag': 'list', 'items': []})}
    out = []
    for m in inspected.get('methods') or []:
        if not m.get('context') or (only and m['name'] != only):
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
        spell = f"delvetalk {form['card']} {form['action']}\n" + ''.join(f"{f['name']}: <{shown(f['kind'])}>\n" for f in form['fields'])
        out.append({**act, 'fields': fields, 'body': {'intent': 'text', 'fields': {f['name']: f['kind']['tag'] for f in form['fields']}},
                    **({'spell': spell} if 'receive' in forms else {})})
    return out


def receipt_links(base, reply, intent=None):
    """Where a turn's or receipt's reply leads: the receipt by slug, the object it read or made, the offers it left,
    and for a refusal the relation its class names (REFUSALS)."""
    rc, out = reply.get('receipt') or {}, {}
    outcome = rc.get('outcome') or {}
    if rc.get('slug'):
        out['receipt'] = link(f"{base}/receipt/{rc['slug']}")
    elif intent and reply.get('class') == 'duplicateIdentity':
        out['receipt'] = link(f'{base}/receipt/{urllib.parse.quote(str(intent), safe="")}')
    roots = rc.get('roots') or []
    if roots or outcome.get('object'):
        o = outcome.get('object') if outcome.get('tag') == 'created' else roots[0].get('object')
        out.update({'object': link(f'{base}/world/{oid(o)}'), 'source': link(f'{base}/world/{oid(o)}/source')})
    made = [c['object'] for c in outcome.get('creates') or [] if c.get('object')]
    if made:
        out['created'] = [link(f'{base}/world/{oid(o)}', name=o) for o in made]
    if rc.get('height'):
        h = rc['height']
        out['offers'] = link(f'{base}/offers?after={h}&wait={WAIT_MAX}' if reply.get('status') == 'suspended' else f'{base}/offers?after={h - 1}')
    refusal = outcome.get('class') if outcome.get('tag') == 'refused' else reply.get('class')
    if refusal in REFUSALS and REFUSALS[refusal][1] in out:
        out['hint'] = out[REFUSALS[refusal][1]]
    elif refusal == 'unknownObject':
        out['hint'] = link(base + '/world')
    return out


class Front(ThreadingHTTPServer):  # threaded so a long poll holds one thread, not the front
    daemon_threads = True
    request_queue_size = 128  # the default backlog of 5 resets connections when a burst arrives faster than accept() runs

    def __init__(self, address, host, identity, origin=ORIGIN, clock=time.time, heaps=None, repl=None, trust_proxy=False, sleep=time.sleep):
        super().__init__(address, Handler)
        self.host, self.identity, self.origin, self.clock = host, identity, origin, clock
        self.heaps, self.repl, self.trust_proxy, self.sleep = heaps, repl, trust_proxy, sleep
        self.repo = Repo(origin)  # the journal as AT Protocol records, read only
        self.hits, self.nonce, self.hits_lock = {}, secrets.token_hex(4), threading.Lock()
        # The bytes this front runs as its host, so an operator can compare them with the build's pin.
        info = {} if hasattr(host, 'binary') else host.send({'op': 'hostd-info'})
        self.host_sha256 = hashlib.sha256(Path(host.binary).read_bytes()).hexdigest() if hasattr(host, 'binary') else info.get('hostSha256', 'unknown')
        self.library, self.hostd_pid = info.get('library'), info.get('pid')  # the pin of the library hostd sealed; the REPL compiles against it by name

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
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype.startswith(('text/', 'application/json')) else ''))
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
        body = reply if full else brief(terse(reply, keep))
        self.reply(400 if status == 'error' else 404 if status == 'unknown' else 200,
                   canonical({**body, '_links': {'self': link(self.path), **(links or {})}, **({'_actions': acts} if acts else {})}))

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
        if (parts[:1] == ['xrpc'] and len(parts) == 2) or path == '/.well-known/did.json':
            return self.xrpc(method, parts[-1])
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
            return self.reply(200, canonical({'status': 'revoked', '_links': {'self': link(self.path), 'challenge': link(PREFIX + '/challenge')}}),
                              headers=[('Set-Cookie', f'{COOKIE}=; Path=/; Max-Age=0')])
        if kind in ('repl', 'check'):
            return self.run_repl(who['did'], kind)
        host = self.server.heaps.get(who['did']) if heap else self.server.host
        principal = who['did']  # the principal the host sees; the handle is display only
        base = PREFIX + ('/heap' if heap else '')
        at = lambda o: {'object': link(f'{base}/world/{oid(o)}'), 'card': link(f'{base}/world/{oid(o)}/card'),
                        'source': link(f'{base}/world/{oid(o)}/source')}
        send = lambda req, links=None: self.answer(host.send(req), links=links)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        after = {'after': int(q['after']) if q['after'].isdigit() else q['after']} if 'after' in q else {}
        if kind == 'objects':
            reply = host.send({'op': 'world-objects', 'principal': principal, **{k: q[k] for k in ('prefix', 'after') if k in q}})
            ids = reply.get('ids') or []
            nxt = urllib.parse.urlencode({**({'prefix': q['prefix']} if 'prefix' in q else {}), 'after': ids[-1]}) if ids and reply.get('more') else ''
            return self.answer(reply, links={'item': [link(f'{base}/world/{oid(i)}', name=i) for i in ids],
                                             **({'next': link(f'{base}/world?{nxt}')} if nxt else {}), 'offers': link(base + '/offers')})
        if kind in ('view', 'card', 'source'):
            op = {'view': 'world-view', 'card': 'world-card', 'source': 'world-inspect'}[kind]
            r = host.send({'op': op, 'principal': principal, 'object': obj})
            seen = r if kind == 'source' else host.send({'op': 'world-inspect', 'principal': principal, 'object': obj}) \
                if r.get('status') in ('viewed', 'card') else {}
            acts = actions(base, obj, seen) if seen.get('status') == 'inspected' else None
            if kind != 'view' and 'full' not in q:  # the readable part; ?full=1 is the host's reply verbatim
                r = {k: plain(v) if k == 'forms' else v for k, v in r.items() if k not in ('document', 'methods')}
            links = {**at(obj), 'world': link(base + '/world'), 'offers': link(base + '/offers')}
            return self.answer(r, keep=('pin',) if kind == 'source' else (), links=links if r.get('status') != 'unknown' else
                               {'world': link(base + '/world')}, acts=acts)  # `pin`: the program's name, in source
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
            wait = min(int(q['wait']), WAIT_MAX) if q.get('wait', '').isdigit() else 0
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
        if kind == 'create':
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
        self.answer(compact(reply) if q.get('compact') == '1' and 'receipt' in reply else reply, links=links, acts=acts)

    def xrpc(self, method, nsid):
        """The read-only repository (transport/repo.py): no credential reads as the public reader, a bearer as its principal."""
        auth = self.headers.get('Authorization') or ''
        credential = auth[7:] if auth.startswith('Bearer ') else ''
        who = self.principal(credential) if credential else {}
        if who is None:
            return self.reply(401, canonical({'error': 'InvalidToken', 'message': 'unverified or revoked credential'}))
        if self.server.limited(credential or 'xrpc:' + self.client_ip()):
            return self.reply(429, canonical({'error': 'RateLimitExceeded', 'message': f'more than {RATE} requests per {WINDOW} seconds'}))
        if nsid == 'did.json' and method == 'GET':
            return self.reply(200, canonical(self.server.repo.did_document()), 'application/did+json')
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        code, body, ctype = self.server.repo.serve(self.server.host, method, nsid, q, who.get('did'))
        self.reply(code, body if isinstance(body, bytes) else canonical(body), ctype)

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
            text = lambda k: data.get(k) if isinstance(data.get(k), str) else ''
            if which == 'challenge':
                out = self.server.identity.challenge(text('handle'))
                return self.reply(200, canonical({**out, '_links': {'self': link(self.path), 'verify': link(PREFIX + '/verify')}}),
                                  headers=self.login_cookie(out['credential']))
            out = self.server.identity.verify(text('handle'), text('uri'))
        except IdentityError as err:
            return self.fail(400, err.code)
        self.server.record_handle(out['did'], out['handle'])
        mine = self.principal(self.cookie())  # a browser that asked for the challenge holds its credential
        links = {'self': link(self.path), 'world': link(PREFIX + '/world'), 'me': link(PREFIX + '/me'), 'api': link(PREFIX + '/api')}
        self.reply(200, canonical({**out, '_links': links}), headers=self.login_cookie(self.cookie()) if mine and mine['did'] == out['did'] else ())

    def me(self, credential, who):
        heap = self.server.heaps.get(who['did'], create=False)
        count = heap.send({'op': 'world-status'}).get('objects') if heap else 0
        self.reply(200, canonical({'principal': who['did'], 'handle': who['handle'], 'did': who['did'], 'verified': who['verified'],
                                   'rateLimit': {'limit': RATE, 'windowSeconds': WINDOW, 'remaining': max(0, RATE - len(self.server.used(credential)))},
                                   'heapObjects': count, '_links': {'self': link(self.path), 'world': link(PREFIX + '/world'),
                                   'heap': link(PREFIX + '/heap/world'), 'offers': link(PREFIX + '/offers'), 'revoke': link(PREFIX + '/revoke')}}))

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
        self.reply(200, canonical({**reply, '_links': {'self': link(self.path)}}))  # a checkpoint goes back whole

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
