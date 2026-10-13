"""HTTP front on the world host (`python3 -m transport http`): /AGENTS.md for agents, / and /o/<object> for humans.
Carries bytes and a verified principal; it validates nothing but size and JSON
well-formedness. Host replies pass through verbatim.
"""
import html
import hmac
import json
import os
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from transport import bridge, oauth, pages, sessions
from transport.atproto.sign import Key
from transport.bridge import turn_line
from transport.host import CLOCK, HOST_TIMEOUT, PUBLIC, TOWN, door_rows, handles, paged, painted, place, plain, typed
from transport.delve import Client, canonical, http_transport
from transport.identity import SLUG, Identity, IdentityError
from transport.repo import Repo, Refusal, WRITES
from transport.hosted import Accounts, MAX_CAR_BYTES, MAX_WRITE_BODY
from transport.acts import INTENT_BYTES, judge_call, text
from transport.serviceauth import Rejected, Verifier
from transport.firehose import Firehose

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / 'docs' / 'AGENTS-API.md'
STATIC = Path(__file__).resolve().parent / 'static'
MAX_BODY = 256 * 1024
OPEN_BODY = 64 * 1024  # what an unauthenticated request (the challenge, verify) may send
WAIT_MAX, WAIT_STEP = 30, 1  # seconds an offers long poll may hold a request, and how often it re-asks the host
RATE, OPEN_RATE, WINDOW = 32, 16, 60
PREFIX, COOKIE = '/AGENTS.md', 'dt_credential'
CREATE_KEYS = ('object', 'modules', 'source', 'package', 'entry', 'seed', 'law')
PROCEDURES = {f'online.fg-goose.gsb.{name}': name for name in ('act', 'try', 'plan')}
EXAMPLES = ROOT / 'docs' / 'AGENTS-EXAMPLES.md'
REQUEST_TIMEOUT, MAX_REPLY, MAX_DEPTH = 30, 8 * 1024 * 1024, 256  # seconds to send a request; bytes of a reply; JSON nesting of a body
WORKERS = 48  # requests served at once (the container allows 64 tasks); one more is told `busy`
ROUTES = {('GET', 'receipt', True): 'receipt', ('GET', 'receipt', False): 'intent', ('GET', 'offers', False): 'offers', ('GET', 'pending', False): 'pending',
          ('POST', 'deliver', False): 'deliver', ('POST', 'objects', False): 'create', ('POST', 'repl', False): 'repl',
          ('POST', 'check', False): 'check', ('POST', 'cite', False): 'cite', ('GET', 'me', False): 'me', ('POST', 'revoke', False): 'revoke',
          ('GET', 'feed', False): 'feedRead', ('POST', 'feed', False): 'feedPost'}
TOP_ONLY, SCRATCH_ONLY = ('me', 'revoke', 'feedRead', 'feedPost'), ('create', 'repl', 'check', 'cite')
ROUTE_HINT = 'GET /AGENTS.md/api lists every route; OPTIONS on a path answers its entries'
FIXED = {('GET', ()): 'guide', ('GET', ('api',)): 'api', ('GET', ('examples',)): 'examples',
         ('POST', ('challenge',)): 'challenge', ('POST', ('verify',)): 'verify', ('POST', ('accept',)): 'accept'}


def resolve(method, path):
    """-> (catalogue name, parameters) or (None, None). The one router: requests are answered and OPTIONS described by it."""
    parts = [urllib.parse.unquote(p) for p in path.split('?')[0].split('/')[1:]]
    if parts[:1] == ['AGENTS.md']:
        rest = parts[1:]
        if (method, tuple(rest)) in FIXED:
            return FIXED[method, tuple(rest)], {}
        scratch = None
        if rest[:1] == ['scratch']:
            if len(rest) == 1:
                return ('scratch', {'scratch': None, 'object': '', 'method': ''}) if method == 'POST' else (None, None)
            scratch, rest = rest[1], rest[2:]  # its name is the host's to judge
        head, obj, tail = (rest[0] if rest else ''), '/'.join(rest[1:]), ''
        if head == 'world':  # an object id may hold slashes: the last segment names the method, or card/source
            if method == 'POST' or (len(rest) > 2 and rest[-1] in ('card', 'source')):
                obj, tail = '/'.join(rest[1:-1]), rest[-1]
            name = 'action' if method == 'POST' else tail or ('object' if obj else 'world')
            name = name if (obj or name == 'world') and method in ('GET', 'POST') else None
        else:
            name = ROUTES.get((method, head, bool(obj)))
            name = None if name in (SCRATCH_ONLY if scratch is None else TOP_ONLY) else name
        return (name, {'scratch': scratch, 'object': obj, 'method': tail}) if name else (None, None)
    if parts[:1] == ['oauth'] and len(parts) == 2 and method == 'GET':  # answered by oauth.route; named here so OPTIONS describes them
        name = {'start': 'oauthStart', 'callback': 'oauthCallback', 'client-metadata.json': 'oauthClient'}.get(parts[1])
        return (name, {}) if name else (None, None)
    if parts[:1] == ['xrpc'] and len(parts) == 2:
        return 'xrpc', {'nsid': parts[1]}
    get = {('',): 'home', ('.well-known', 'did.json'): 'did', ('style', ''): 'specimen', ('style',): 'specimen'}.get(tuple(parts))
    if method == 'GET' and get:
        return get, {}
    if method == 'GET' and parts[:1] == ['static'] and len(parts) == 2 and parts[1] in ('style.css', 'say.js'):
        return 'static', {'file': parts[1]}
    if parts[:1] == ['play'] and method in ('GET', 'POST'):
        return ('play' if method == 'GET' else 'reply'), {'object': '/'.join(parts[1:])}
    if parts[:1] == ['o'] and len(parts) == 3 and parts[2] == 'book' and method == 'GET':
        return 'book', {'object': parts[1]}
    if parts[:1] == ['o'] and len(parts) >= 2 and all(parts[1:]) and method == 'GET':  # an id may hold slashes, as a door's link spells it
        return 'page', {'object': '/'.join(parts[1:])}
    if parts in (['enter'], ['leave']) and method in ('GET', 'POST'):  # the guest door: come in with an invitation or a key; sign out
        return {('GET', 'enter'): 'door', ('POST', 'enter'): 'comeIn', ('GET', 'leave'): 'leave', ('POST', 'leave'): 'signOut'}[method, parts[0]], {}
    if parts == ['feed'] and method in ('GET', 'POST'):  # the town's own feed, for people (transport/feed.py)
        return ('feed' if method == 'GET' else 'feedSay'), {}
    if parts == ['history'] and method == 'GET':
        return 'history', {}
    if parts == ['map'] and method == 'GET':
        return 'map', {}
    return None, None



def trace(host, principal, intent, reply, sleep=time.sleep, wait=WAIT_MAX):
    """The texts offered to `principal` by a turn and every turn it handed on (its `sends`, delivered under the same
    principal with the send's id as intent: a card handing prose to the commonplace, hob's planting sent to the garden),
    and whether any of them is still waiting (on hob, or for its delivery) when `wait` seconds are spent: the play page's
    turn and the hand's Speak. With `wait` 0, one look at the chain as it stands (a page that refreshes itself)."""
    watch = {intent}
    done = {} if reply.get('status') == 'suspended' else {intent: reply['receipt']}  # the turn as it answered
    watch |= {s['id'] for r in done.values() for s in r.get('sends') or [] if s.get('id')}
    after = reply['receipt']['height'] - 1
    for waited in range(0, wait + 1, WAIT_STEP):
        for i in sorted(watch - set(done)):
            got = host.send({'op': 'world-receipt', 'principal': principal, 'identity': i}).get('receipt') or {}
            if ((got.get('outcome') or {}).get('tag') or 'suspended') != 'suspended':
                done[i] = got
                watch |= {s['id'] for s in got.get('sends') or [] if s.get('id')}
        if watch <= set(done) or waited + WAIT_STEP > wait:
            break
        sleep(WAIT_STEP)
    seen = host.send({'op': 'world-offers', 'principal': principal, 'after': after}).get('offers') or []
    return [o['text'] for o in seen if (o.get('identity') or {}).get('intent') in watch], not watch <= set(done)


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
    """A turn reply's default rendering: the turn line with its stamp, what the act fired, opened and where it stands (the
    host's `revealed` lines, when it has any), a refusal's `hint`, the offered texts and where the receipt sits. The whole receipt is
    `?full=1` and `GET /receipt/<slug>`."""
    rc = reply['receipt']
    line = turn_line(reply)
    outcome = rc.get('outcome') or {}
    cls = reply.get('class') or outcome.get('class')
    return {'status': reply.get('status'), **({'class': cls} if cls and reply.get('status') == 'refused' else {}),
            'line': f"{pages.stamp(reply.get('status'), word=False)} {line}",
            **({'revealed': reply['revealed']} if reply.get('revealed') else {}),
            **({'hint': outcome['hint']} if outcome.get('hint') else {}),  # a refusal's fix, as the host wrote it
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
DOOR_LINES = {'invitation_unknown': 'That code does not match any invitation. Check it was copied whole, or ask the person who invited you.',
              'invitation_spent': 'That invitation has been used already. If it was you, sign in below with the key you were given; if not, ask for a new one.',
              'invitation_expired': 'That invitation has expired. Ask the person who invited you for a new one.',
              'invitation_revoked': 'That invitation was withdrawn. Ask the person who invited you.',
              'name_required': 'This invitation lets you choose your name. Type one, then press Come in.',
              'invalid_guest_name': 'A name starts with a lowercase letter, then up to 31 lowercase letters, digits or hyphens, ending in a letter or digit: robin, or sam-2.',
              'name_fixed': 'This invitation already has a name on it. Leave the name empty and press Come in.',
              'taken': 'Someone here already goes by that name. Choose another; your code still works.',
              'invalid_credential': 'That key does not open anything here. Check it was copied whole; it begins dt_agent_.',
              'empty': 'Type the code from your invitation, or your key if you have been here before.'}  # the guest door's words (`/enter`)
ACCEPT_LINES = {'invitation_unknown': 'no invitation has that code; ask whoever invited you',
                'invitation_spent': 'that invitation was accepted already; the credential it gave speaks for you, and the operator can invite you again',
                'invitation_expired': 'that invitation lapsed before it was accepted; ask for a new one',
                'invitation_revoked': 'that invitation was revoked',
                'name_required': 'that invitation leaves your name to you; send {"code": ..., "name": ...}, a name like [a-z][a-z0-9-]{0,31}, ending in a letter or digit',
                'invalid_guest_name': 'a name is a lowercase letter, then up to 31 lowercase letters, digits or hyphens, ending in a letter or digit',
                'name_fixed': 'that invitation already names its guest; send that name, or none',
                'taken': 'that name is taken; the code is still unused, so choose another'}


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


def actions(base, obj, inspected, only=None):
    """One action per method in the host's method table that takes a context (a turn can run it), from world-inspect:
    the form's fields when the host has a form for it, else the method's input type; its spell as the host's usage prints it
    (`templates`)."""
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
        out.append({**act, 'fields': fields, 'body': {'intent': 'text', 'fields': {f['name']: f['kind']['tag'] for f in form['fields']}},
                    'spell': (inspected.get('templates') or {}).get(m['name'])})
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
        out['receipt'] = link(f'{base}/receipt?{urllib.parse.urlencode({"intent": str(intent)})}')
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
    """One line per request: time, method, path (no query), status, bytes sent, the principal's DID or `-`, the world.
    A service-auth refusal appends its fixed reason code. Never a credential or a body.
    Rotated by size: past `limit` bytes the file becomes `<name>.1` (the previous one is dropped)."""
    LIMIT = 16 * 1024 * 1024

    def __init__(self, path, world, limit=LIMIT):
        self.path, self.world, self.limit, self.lock = Path(path), world, limit, threading.Lock()

    def write(self, when, method, path, status, sent, did, reason=None):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(when))} {method} {path} {status} {sent} {did or '-'} {self.world}" + (f" auth={reason}" if reason else '') + '\n'
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

    def __init__(self, st, host, identity, address=None, clock=time.time, sleep=time.sleep, hand=None, workers=WORKERS,
                 firehose_address=None):
        """The public front over `st`'s world, or with `hand` the hand's console, which logs no access and drafts nothing."""
        c = st.config
        super().__init__(address or ((c.hand_bind, c.hand_port) if hand else (c.http_bind, c.http_port)), Handler)
        self.slots, self.receiving, self.receiving_lock = threading.BoundedSemaphore(workers), {}, threading.Lock()
        threading.Thread(target=self.reap, daemon=True).start()
        self.st, self.access, self.known = st, None if hand else AccessLog(st.access_log, st.world), {}
        self.host, self.identity, self.origin, self.clock = host, identity, c.origin, clock
        self.trust_proxy, self.sleep, self.hand = c.trust_proxy, sleep, hand
        self.play_wait = WAIT_MAX  # seconds a play page's turn may wait on what it handed on (`trace`); a test may look once
        self.made, self.made_lock = {}, threading.Lock()
        self._feed = None  # object -> (height, principal) of the first entry touching it: it never changes
        self.repo = Repo(c.origin, Key.load(st.repo_key) if not hand and st.repo_key.exists() else None,
                         st.world, st.answers, st.repo_ledger, c.firehose_port if not hand else 0)  # the journal as AT Protocol records, read only
        self.accounts = Accounts(st)
        if not hand:
            self.accounts.reconcile()
            skipped = self.accounts.provision_guests()
            if skipped:
                print('hosted provisioning skipped (no hosted address): ' + ', '.join(skipped), file=sys.stderr)
            self.serviceauth = Verifier(self.repo.did, identity.client, st.serviceauth_ledger,
                                        clock=clock, limited=self.limited)
        self.firehose = None
        self.oauth = oauth.OAuth(c.origin)  # log in with delve.town (transport/oauth.py)
        self.hits, self.nonce, self.hits_lock = {}, secrets.token_hex(4), threading.Lock()
        self.csrf_secret = secrets.token_bytes(32)
        self.turn_lock = threading.Lock()
        self.request_timeout = REQUEST_TIMEOUT
        # The bytes this front runs as its host, so an operator can compare them with the build's pin.
        info = host.send({'op': 'serve-status'})
        self.host_sha256, self.host_timeout = info.get('hostSha256', 'unknown'), getattr(host, 'timeout', HOST_TIMEOUT)
        self.bounds = host.send({'op': 'bounds'})  # the kernel's and the host's bounds: the front restates none
        if not hand and c.firehose_port:
            try:
                self.firehose = Firehose(self.repo, host, st.firehose,
                                         firehose_address or (c.firehose_bind, c.firehose_port)).start()
                self.repo.firehose_port = self.firehose.address[1]
            except Exception:
                self.server_close()
                raise

    def server_close(self):
        if getattr(self, 'firehose', None):
            self.firehose.close()
        super().server_close()

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

    def draft_turn(self, principal, intent, reply):
        """The owner's rule (cracks R6): an admitted HTTP turn that wrote something, and read and wrote only what the public
        reads (the host's `inPublic`), is drafted in the hand's outbox like a town reply, once per receipt; whether the town
        hears of it is the operator's click."""
        receipt = reply.get('receipt') or {}
        writes = [w['object'] for w in (receipt.get('outcome') or {}).get('writes') or [] if w.get('object')]
        if reply.get('status') != 'admitted' or not writes or principal.startswith('guest:'):  # a guest's replies come back over HTTP only
            return
        path = self.st.outbox / f"{receipt.get('height')}-http-{bridge.uri_hash(principal + chr(0) + str(intent))}.json"
        if not path.exists() and reply.get('inPublic'):
            self.st.new_draft(path, {'http': {'intent': intent}, 'replyTo': None, 'principal': principal, 'principalVerified': True,
                                 'object': writes[0], 'slot': None, 'receipt': receipt, 'posted': False,
                                 'text': bridge.draft_text(reply, self.origin) or bridge.receipt_line(receipt, self.origin)})

    def turn(self, host, principal, obj, method, data, scratch=False, first_receipt=False):
        """The agent and procedure act/try path: one host call, then town drafting.

        XRPC intents answer their first bound receipt even when the retry changes
        the call. The host remains the authority for receipt lookup and offers.
        """
        reply = None
        if first_receipt:
            saved = {}
            if not scratch:
                source = bridge.xrpc_source(principal, data['intent'])
                path = bridge.answer_path(self.st, source)
                saved = json.loads(path.read_text()) if path.exists() else {}
            entry = (saved.get('receipt') or {}).get('entry', {}).get('$link')
            got = host.send({'op': 'world-entry', 'principal': principal, 'hash': entry}) if entry else \
                host.send({'op': 'world-receipt', 'principal': principal, 'identity': data['intent']})
            if got.get('class') in ('hostUnavailable', 'hostTimeout') or (scratch and got.get('status') == 'error'):
                return got
            rc = got.get('receipt') or {}
            if rc:
                reply = {**got, 'status': (rc.get('outcome') or {}).get('tag', 'refused'),
                         'object': (rc.get('roots') or [{}])[0].get('object')}
                offers = paged(host, {'op': 'world-offers', 'principal': principal, 'after': rc['height'] - 1}, 'offers')
                reply['offers'] = [o for o in offers
                                   if (o.get('from') or o.get('identity') or {}).get('intent') == data['intent']]
        if reply is None:
            if obj is None:  # a spell's destination is read by the host, as for a record request
                reached = host.send({'op': 'world-reach', 'principal': principal, 'author': principal, 'kind': 'request',
                                     'uri': '', 'text': data['spell'], 'chain': [], 'mentions': 0})
                if reached.get('class') in ('hostUnavailable', 'hostTimeout') or (scratch and reached.get('status') == 'error'):
                    return reached
                if reached.get('status') != 'reached':
                    return {'status': 'unreached', 'message': 'no card reached: a spell names its card'}
                obj = reached['object']
            reply = host.send({'op': 'world-try' if data.get('try') is True else 'world-turn', 'principal': principal,
                               'object': obj, 'method': method, 'argument': argument(data), 'identity': data.get('intent'),
                               'reach': 'direct', **({'if': data['if']} if 'if' in data else {})})
        if not scratch and not reply.get('tried') and reply.get('class') != 'moved':
            turns = reply.get('turns') if reply.get('status') == 'spells' else [reply]
            for t in turns:
                self.draft_turn(principal, (t.get('receipt') or {}).get('identity', {}).get('intent', data.get('intent')), t)
        return reply

    @property
    def feed(self):
        """The town's own feed (transport/feed.py), opened at its first use."""
        if self._feed is None:
            from transport.feed import Feed
            self._feed = Feed(self.st)
        return self._feed

    def newest(self, ids, n=6):
        """The newest makings among `ids` (not residents' avatars): (object, principal, height) of the first journal entry
        that touched each, as the public reads it, newest first. Each id's first entry is asked once and kept."""
        for i in ids:
            if i not in self.made and not pages.resident(i):
                first = (self.host.send({'op': 'world-history', 'principal': PUBLIC, 'object': i, 'limit': 1}).get('entries') or [None])[0]
                if first:
                    with self.made_lock:
                        self.made[i] = (first.get('height') or 0, (first.get('identity') or {}).get('principal') or '')
        made = sorted(((i, *self.made[i]) for i in ids if i in self.made), key=lambda m: m[1], reverse=True)[:n]
        return [(i, who, height) for i, height, who in made]

    def handles(self, dids):
        """{did: handle} for the DIDs a page names, as the public reader sees their avatars; the town's own as the town."""
        return handles(self.host, PUBLIC, dids, self.known)

    def town(self):
        """The world's own principal (its opener), which pages name the town; '' for a world that names none."""
        return next((p for p, h in self.handles(()).items() if p and h == TOWN), '')

    def limited(self, key, rate=RATE, count=True):
        """0 when under the limit, else the seconds until the oldest counted request leaves the window; `count` False
        asks without counting (-> the requests in the window)."""
        with self.hits_lock:  # read, test and append as one step
            now = self.clock()
            hits = [t for t in self.hits.get(key, []) if now - t < WINDOW]
            if not count:
                return len(hits)
            self.hits[key] = hits + [now]
        return max(1, int(hits[-rate] + WINDOW - now + 0.999)) if len(hits) >= rate else 0

    def record_handle(self, did, handle):
        """Tell the host a verified account has arrived (the clock principal alone may), so cards name them by handle.
        Idempotent at the host; a refusal leaves the verification standing."""
        return self.host.send({'op': 'world-arrive', 'principal': CLOCK, 'did': did, 'handle': handle})

    def catalogue(self, here):
        """Every route, the error envelope, the error and refusal classes (static/catalogue.json) and the limits, as data."""
        return {'status': 'catalogue', 'origin': self.origin, **API,
                'limits': {'bodyBytes': MAX_BODY, 'hostedWriteBodyBytes': MAX_WRITE_BODY, 'moduleBytes': self.bounds['kernel']['maxPackageBytes'], 'modules': self.bounds['kernel']['maxModules'], 'bodyDepth': MAX_DEPTH,
                           'replyBytes': MAX_REPLY, 'requestSeconds': REQUEST_TIMEOUT, 'workers': WORKERS, 'hostSeconds': self.host_timeout,
                           'requestLineBytes': 65536, 'headerLineBytes': 65536, 'headers': 100, 'offersWaitSeconds': WAIT_MAX,
                           'ratePerCredential': [RATE, WINDOW], 'ratePerAddressOnChallengeAndVerify': [OPEN_RATE, WINDOW],
                           'ratePerAddressOnXrpcWithoutCredential': [RATE, WINDOW], 'ratePerAddressOnPagesWithoutLogin': [RATE, WINDOW], 'idsPerPage': self.bounds['host']['listPage'], 'deliverPerCall': self.bounds['host']['deliveriesPerCall']},
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
        self.status, self.did, self.head, self.auth_reason = 0, None, False, None
        self.wfile.sent = 0
        super().handle_one_request()
        if self.server.access and self.status:  # a request that never parsed has no status
            self.server.access.write(self.server.clock(), getattr(self, 'command', '-'), urllib.parse.urlsplit(self.path).path,
                                     self.status, self.wfile.sent, self.did, self.auth_reason)

    def reply(self, code, body, ctype='application/json', headers=(), maximum=None):
        raw = body.encode('utf-8', 'backslashreplace') if isinstance(body, str) else body  # a lone surrogate the host echoed stays a JSON escape
        if len(raw) > (MAX_REPLY if maximum is None else maximum) and code < 400:
            return self.fail('replyTooLarge', hint='?compact=1, a page (after, limit), or the receipt alone')
        self.replied = True
        self.send_response(code)
        self.send_header('Content-Type', ctype + ('; charset=utf-8' if ctype.startswith(('text/', 'application/json')) else ''))
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        private = getattr(self, 'private', False) or self.cookie() or any(k.lower() == 'set-cookie' for k, _ in headers)
        if private:
            self.send_header('Cache-Control', 'private, no-store')
        for k, v in headers:
            if private and k.lower() == 'cache-control':
                continue
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

    def body(self, limit=MAX_BODY, xrpc=False, browser_write=False, installing=False):
        """-> dict, or None after replying with the refusal. JSON, or a urlencoded form."""
        fail = (lambda cls, reason=None: self.xrpc_reply(400, {'error': 'InvalidRequest', 'message': reason or ERRORS[cls]['when']})) if xrpc else self.fail
        if xrpc and (self.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower() != 'application/json':
            return fail('badJson', 'Content-Type must be application/json')
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            n = -1
        if n < 0:
            return fail('badRequest', 'Content-Length is not a number')
        if n > limit:
            return fail('bodyTooLarge', f'the body is over {limit} bytes')
        try:
            raw = self.rfile.read(n)
        except TimeoutError:
            raw = b''
        if len(raw) < n:  # stalled, or cut at the deadline
            return fail('requestTimeout')
        form = (self.headers.get('Content-Type') or '').split(';', 1)[0].strip().lower() == 'application/x-www-form-urlencoded' and not raw.lstrip().startswith(b'{')
        auth = self.headers.get('Authorization') or ''
        browser = self.browser() or form or any(self.headers.get(k) is not None for k in ('Origin', 'Referer', 'Sec-Fetch-Site'))
        gated = (browser_write or installing and browser) and not (auth.startswith('Bearer ') and self.principal(auth[7:]))
        # curl -d labels JSON as a form; a browser's form body never starts with '{'
        if form:
            data = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode(errors='replace'), keep_blank_values=True).items()}
        else:
            try:
                def constant(_):
                    raise ValueError('non-JSON number')
                def unique(pairs):
                    out = {}
                    for k, v in pairs:
                        if k in out:
                            raise ValueError('duplicate JSON field')
                        out[k] = v
                    return out
                data = json.loads(raw or b'{}', **({'parse_constant': constant, 'object_pairs_hook': unique} if xrpc else {}))
            except (ValueError, RecursionError):
                return fail('badJson', 'the body is not JSON')
        if not isinstance(data, dict):
            return fail('badJson', 'the body must be a JSON object')
        if depth(data) > MAX_DEPTH:
            return fail('badJson', f'the body nests deeper than {MAX_DEPTH}')
        token = data.pop('csrf', '') if form else None
        if gated and not self.browser_write(token):
            return None
        if xrpc:
            try:
                canonical(data).encode('utf-8')
            except UnicodeEncodeError:
                return fail('badJson', 'the body must contain Unicode text without lone surrogates')
        return data

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

    def cookie(self, name=COOKIE):
        for part in ((getattr(self, 'headers', None) or {}).get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == name:
                return v
        return ''

    def credential(self):
        auth = self.headers.get('Authorization') or ''
        return auth[7:] if auth.startswith('Bearer ') else self.cookie()

    def login_cookie(self, credential, name=COOKIE):
        secure = '; Secure' if self.server.origin.startswith('https:') else ''  # never sent over plain http to a public origin
        cookies = [(name, credential)]
        if name == COOKIE:
            self.browser_nonce = secrets.token_urlsafe(32)
            cookies.insert(0, ('dt_browser', self.browser_nonce))
        return [('Set-Cookie', f'{key}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={2592000 if value else 0}{secure}')
                for key, value in cookies]

    def browser_write(self, token=None):
        origin = self.headers.get('Origin')
        if origin is None:
            try:
                ref = urllib.parse.urlsplit(self.headers.get('Referer') or '')
                origin = f'{ref.scheme}://{ref.netloc}' if ref.netloc and ref.username is None else ''
            except ValueError:
                origin = ''
        if origin != self.server.origin or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.fail('denied', 'browser writes require the exact town origin')
            return False
        if token is not None and (len(token) != 64 or not token.isascii() or not hmac.compare_digest(token, self.csrf_token())):
            self.fail('denied', 'the form does not belong to this browser session; reload the page')
            return False
        return True

    def csrf_token(self):
        binding = getattr(self, 'browser_nonce', self.cookie('dt_browser'))
        return hmac.digest(self.server.csrf_secret, binding.encode(), 'sha256').hex()

    def principal(self, credential):
        try:
            who = self.server.identity.authenticate(credential)
        except IdentityError:
            return None
        if who:
            self.private = True
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
        if name in ('challenge', 'verify', 'accept'):
            return self.identify(name)
        if name == 'static':
            return self.reply(200, (STATIC / p['file']).read_bytes(), 'text/css' if p['file'].endswith('css') else 'text/javascript')
        if name in ('xrpc', 'did'):
            return self.xrpc(method, p.get('nsid', 'did.json'))
        if name in ('feed', 'feedSay'):
            return self.feed_page(name == 'feedSay')
        if name in ('home', 'page', 'book', 'history', 'map'):  # pages ask the host: limited per account, or per address, before they do
            key = self.cookie() if self.principal(self.cookie()) else 'page:' + self.client_ip()
            wait = self.server.limited(key)
            if wait:
                return self.fail('rateLimited', f'more than {RATE} pages per {WINDOW} seconds', headers=[('Retry-After', str(wait))])
        if name == 'home':
            return self.home()
        if name in ('door', 'comeIn', 'leave', 'signOut'):
            return self.door(name)
        if name == 'specimen':
            return self.html(200, pages.page('style', None, (STATIC / 'specimen.html').read_text()))
        if name in ('play', 'reply'):
            return self.play(p['object'] or 'commonplace', name == 'reply')
        if name == 'page':
            return self.object_page(p['object'])
        if name == 'book':
            return self.surface('book', p['object'])
        if name == 'history':
            return self.surface('chronicle', None)
        if name == 'map':
            return self.surface('map', urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('from', [None])[0])
        return self.agents(name, p['scratch'], p['object'], p['method'])

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

    def agents(self, kind, scratch, obj, tail):
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
        if kind in ('feedRead', 'feedPost'):
            return self.feed_json(who, kind == 'feedPost')
        if kind == 'revoke':
            self.server.identity.revoke(credential)
            return self.reply(200, canonical({'status': 'revoked', '_links': {'self': link(self.path), 'challenge': link(PREFIX + '/challenge')}}),
                              headers=self.login_cookie(''))
        principal = who['did']  # the principal the host sees; the handle is display only
        if kind == 'scratch':
            return self.open_scratch(principal)
        host = self.server.host.at(f'scratch/{scratch}') if scratch else self.server.host  # the principal in the request decides whose scratch
        base = PREFIX + (f'/scratch/{scratch}' if scratch else '')
        if kind in ('repl', 'check', 'cite'):
            return self.in_scratch(host, base, principal, scratch, kind)
        if self.browser() and kind in ('object', 'card', 'source') and not scratch:
            return self.object_page(obj, who)
        at = lambda o: {'object': link(f'{base}/world/{oid(o)}'), 'card': link(f'{base}/world/{oid(o)}/card'),
                        'source': link(f'{base}/world/{oid(o)}/source')}
        send = lambda req, links=None: self.answer(host.send({'principal': principal, **req}), links=links)  # a scratch is the principal's
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        if kind == 'world':
            reply = host.send({'op': 'world-objects', 'principal': principal, 'methods': True, **{k: q[k] for k in ('prefix', 'after') if k in q}})
            ids = reply.get('ids') or []
            nxt = urllib.parse.urlencode({**({'prefix': q['prefix']} if 'prefix' in q else {}), 'after': ids[-1]}) if ids and reply.get('more') else ''
            names = reply.get('methods') or {}  # per id, when the host answers them (host op wanted)
            if self.browser():
                words = {d['to']['object']: d.get('label', '') for d in door_rows(host.send({'op': 'world-view', 'principal': principal, 'object': 'commonplace'}))}
                return self.html(200, pages.listing(ids, words, who['handle'], principal, nxt and f'{base}/world?{nxt}'))
            return self.answer(reply, links={'item': [link(f'{base}/world/{oid(i)}', name=i, **({'actions': names[i]} if i in names else {}))
                                                      for i in ids],
                                             **({'next': link(f'{base}/world?{nxt}')} if nxt else {}), 'offers': link(base + '/offers')})
        if kind in ('object', 'card', 'source'):
            op = {'object': 'world-view', 'card': 'world-card', 'source': 'world-inspect'}[kind]
            r = host.send({'op': op, 'principal': principal, 'object': obj, **({'source': True} if kind == 'source' else {})})
            seen = r if kind == 'source' else host.send({'op': 'world-inspect', 'principal': principal, 'object': obj}) \
                if r.get('status') in ('viewed', 'card') else {}
            acts = actions(base, obj, seen) if seen.get('status') == 'inspected' else None
            if kind != 'object' and 'full' not in q:  # the readable part; ?full=1 is the host's reply verbatim
                r = {k: plain(v) if k == 'forms' else v for k, v in r.items() if k not in ('document', 'methods')}
            links = {**at(obj), 'world': link(base + '/world'), 'offers': link(base + '/offers')}
            return self.answer(r, keep=('pin',) if kind == 'source' else (), links=links if r.get('status') != 'unknown' else
                               {'world': link(base + '/world'), 'hint': link(base + '/world')}, acts=acts)  # `pin`: the program's name, in source
        if kind == 'receipt':  # by spoken name only; an intent is `?intent=`, so the two never shadow each other
            found = host.send({'op': 'world-resolve', 'principal': principal, 'slug': obj}) if SLUG.fullmatch(obj) else \
                {'status': 'unknown', 'message': f'{obj} is not a spoken name'}
            if 'receipt' in found:
                return self.answer({'status': 'receipt', 'receipt': found['receipt']}, links=receipt_links(base, found))
            if found.get('identity'):
                r = host.send({'op': 'world-receipt', 'principal': principal, 'identity': found['identity']})
                return self.answer(r, links=receipt_links(base, r))
            if found.get('status') != 'unknown':
                return self.answer(found)  # ambiguous, denied: the host's words
            return self.answer({'status': 'unknown', 'message': f'no receipt is named {obj}'},
                               links={'hint': link(f'{base}/receipt?{urllib.parse.urlencode({"intent": obj})}')})
        if kind == 'intent':
            r = host.send({'op': 'world-receipt', 'principal': principal, 'identity': q.get('intent', '')})
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
            return send({'op': 'world-pending', 'principal': principal}, {'deliver': link(base + '/deliver')})
        data = self.body()
        if data is None:
            return
        if kind == 'deliver':
            return send({'op': 'world-deliver', 'principal': principal}, {'pending': link(base + '/pending')})
        if kind == 'create':  # a name no spell can address would publish spells nobody can cast: the host's parser says
            name = data.get('object')
            read = self.server.host.send({'op': 'spell-parse', 'text': f'delvetalk {name} ?'}) if isinstance(name, str) else {}
            if read.get('status') == 'parsed' and (read.get('spell') or {}).get('card') != name:
                return self.fail('unspellable', f'the host does not read `delvetalk {name} ?` as a spell; choose a name a spell can address')
            made = {k: typed(data[k]) if k == 'seed' else data[k] for k in CREATE_KEYS if k in data}
            reply = host.send({'op': 'world-create', 'principal': principal, 'identity': data.get('intent'), **made})
            return self.answer(reply, links=receipt_links(base, reply))
        # `try: true` is the act with the write switched off (docs/POSTING.md §2); `if` the roots a try read, else `moved`.
        reply = self.server.turn(host, principal, obj, tail, data, scratch=bool(scratch))
        if reply.get('tried') or reply.get('class') == 'moved':  # nothing journaled: the whole answer, nothing drafted
            return self.answer(reply, links=at(obj))
        turns = reply.get('turns') if reply.get('status') == 'spells' else [reply]  # several spells: a turn each
        links, acts = {**at(obj), **receipt_links(base, reply, data.get('intent'))}, None
        if reply.get('status') in ('refused', 'error'):  # the usage action: the method as the host's table shows it
            seen = host.send({'op': 'world-inspect', 'principal': principal, 'object': obj})
            acts = actions(base, obj, seen, only=tail) if seen.get('status') == 'inspected' else None
            links.setdefault('hint', links['source'])
        view = lambda t: (compact(t) if q.get('compact') == '1' else turn_view(t)) if 'receipt' in t and t.get('status') in ('admitted', 'refused', 'suspended') else t
        if 'full' not in q:
            reply = {'status': 'spells', 'turns': [view(t) for t in turns]} if reply.get('status') == 'spells' else view(reply)
        self.answer(reply, links=links, acts=acts)

    def xrpc(self, method, nsid):
        """Method-bound service reads and procedures; repository queries use credentials."""
        try:
            repo = self.repository_host()
        except Refusal as r:
            return self.xrpc_reply(r.code, r.body)
        if repo is not self.server.repo and nsid != 'did.json' and nsid not in repo.METHODS and nsid not in WRITES:
            return self.xrpc_reply(501, {'error': 'MethodNotImplemented', 'message': 'hosted accounts serve request repositories only'})
        procedure = nsid in PROCEDURES or nsid == sessions.OPEN
        query = nsid in Repo.METHODS or nsid in sessions.QUERIES
        if ((procedure or nsid in WRITES) and method != 'POST') or (query and method != 'GET'):
            return self.xrpc_reply(405, {'error': 'InvalidRequest', 'message': 'a procedure uses POST; a query uses GET'})
        auth = self.headers.get('Authorization') or ''
        credential = auth[7:] if auth.startswith('Bearer ') else ''
        service = procedure or nsid in sessions.QUERIES or nsid == 'online.fg-goose.gsb.getEntry'
        if service:
            try:
                self.did = self.server.serviceauth.authenticate(credential, nsid, self.client_ip())
            except Rejected as r:
                self.auth_reason = r.reason
                return self.xrpc_reply(r.code, r.body, [('Retry-After', str(r.retry))] if r.retry else ())
            who = {'did': self.did}
        else:
            who = self.principal(credential) if credential else {}
        if who is None:
            self.auth_reason = 'credential'
            return self.xrpc_reply(401, {'error': 'InvalidToken', 'message': 'unverified or revoked credential'})
        wait = self.server.limited(self.did if service else credential or 'xrpc:' + self.client_ip())
        if wait:
            return self.xrpc_reply(429, {'error': 'RateLimitExceeded', 'message': f'more than {RATE} requests per {WINDOW} seconds'},
                                   [('Retry-After', str(wait))])
        if nsid == 'did.json':
            try:
                return self.reply(200, canonical(repo.did_document()), 'application/did+json')
            except Refusal as r:
                return self.xrpc_reply(r.code, r.body)
        if nsid == sessions.OPEN or nsid in sessions.QUERIES:
            return self.session(nsid, self.did)
        if nsid in PROCEDURES:
            return self.procedure(PROCEDURES[nsid], self.did)
        if nsid in WRITES:
            q = self.body(limit=MAX_WRITE_BODY, xrpc=True)
            if q is None:
                return
        else:
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
            if any(len(v) != 1 for v in params.values()):
                return self.xrpc_reply(400, {'error': 'InvalidRequest', 'message': 'repeated query parameters'})
            q = {k: v[0] for k, v in params.items()}
        if repo is self.server.repo:
            target = q.get('repo') or q.get('did') or q.get('handle')
            if isinstance(target, str) and target not in (repo.did, repo.handle):
                try:
                    repo = self.server.accounts.by_did(target if target.startswith('did:') else 'did:web:' + target)
                except Refusal as r:
                    if nsid in WRITES or r.body['error'] == 'RepoNotServed':
                        return self.xrpc_reply(r.code, r.body)
            if nsid in WRITES and repo is self.server.repo:
                return self.xrpc_reply(405, {'error': 'InvalidRequest', 'message': 'the world repository is read-only'})
        code, body, ctype = repo.serve(self.server.host, method, nsid, q, who.get('did'))
        if code == 426:
            return self.xrpc_reply(code, body, [('Upgrade', 'websocket')])
        self.reply(code, body if isinstance(body, bytes) else canonical(body), ctype,
                   maximum=MAX_CAR_BYTES if repo is not self.server.repo and isinstance(body, bytes) else MAX_REPLY) if code < 400 else self.xrpc_reply(code, body)

    def repository_host(self):
        """Host selects this world's front or an existing hosted account on this same listener."""
        headers = self.headers.get_all('Host') or []
        if len(headers) != 1:
            raise Refusal(400, 'RepoNotFound', 'one Host header is required')
        try:
            parts = urllib.parse.urlsplit('//' + headers[0])
            name = parts.hostname
            port = parts.port
            if parts.username or parts.password or parts.path or parts.query or parts.fragment or not name:
                raise ValueError('Host')
        except ValueError:
            raise Refusal(400, 'RepoNotFound', 'invalid Host') from None
        bound, bound_port = self.server.server_address[:2]
        local = name == bound and port == bound_port
        if local or name in (urllib.parse.urlsplit(self.server.origin).hostname, self.server.repo.handle):
            return self.server.repo
        return self.server.accounts.by_host(name)

    def procedure(self, mode, principal):
        """Authenticated JSON framing; law refusals are caller answers with HTTP 200."""
        data = self.body(xrpc=True)
        if data is None:
            return
        why = None
        world = data.get('world', self.server.st.world)
        scratch = sessions.scratch_world(world)
        allowed = {'intent', 'if', 'world', 'calls' if mode == 'plan' else 'call'}
        if set(data) - allowed:
            why = 'unexpected fields: ' + ', '.join(sorted(set(data) - allowed))
        elif world != self.server.st.world and not scratch:
            why = 'world must equal ' + self.server.st.world + ' or scratch/<name>'
        elif (mode != 'try' or 'intent' in data) and not text(data.get('intent'), INTENT_BYTES):
            why = f'intent must be nonempty Unicode text of at most {INTENT_BYTES} UTF-8 bytes'
        else:
            why, call = judge_call(mode, data.get('calls') if mode == 'plan' else [data.get('call')], data.get('if', []))
        if why:
            return self.xrpc_reply(400, {'error': 'InvalidRequest', 'message': why})
        turn = {**call, **{k: data[k] for k in ('intent', 'if') if k in data}, 'try': mode == 'try'}
        host = sessions.ScratchHost(self.server.host.at(world)) if scratch else self.server.host
        try:
            with self.server.turn_lock:
                if scratch:
                    sessions.status(host, principal)
                reply = self.server.turn(host, principal, call.get('object'), call.get('verb', 'receive'),
                                         turn, scratch=scratch, first_receipt=mode != 'try')
                sessions.check_reply(reply)
                preview = mode == 'try' or bool(reply.get('tried'))
                if not preview and not scratch:
                    source = bridge.xrpc_source(principal, data['intent'])
                    bridge.write_answer(self.server.st, source, bridge.public_view(host, reply))
            return self.reply(200, canonical(bridge.caller_view(reply, preview)))
        except Refusal as r:
            return self.reply(r.code, canonical(r.body))
        finally:
            if scratch:
                host.close()

    def session(self, nsid, principal):
        """Session bodies are returned once, without repository or envelope links."""
        host = None
        try:
            if nsid == sessions.OPEN:
                data = self.body(xrpc=True)
                if data is None:
                    return
                reply = sessions.opened(self.server.host, principal, data)
            else:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
                allowed = {'session'} if nsid.endswith('.getSession') else {'session', 'collection', 'cursor', 'limit'}
                if set(query) - allowed or any(len(v) != 1 for v in query.values()):
                    raise Refusal(400, 'InvalidRequest', 'unexpected or repeated query parameters')
                q = {k: v[0] for k, v in query.items()}
                world = q.get('session')
                if not sessions.scratch_world(world):
                    raise Refusal(400, 'InvalidRequest', 'session is scratch/<name>')
                host = sessions.ScratchHost(self.server.host.at(world))
                if nsid.endswith('.getSession'):
                    reply = sessions.get_session(self.server.host, host, principal, world)
                else:
                    sessions.status(host, principal)
                    reply = sessions.list_records(host, principal, q)
            return self.reply(200, canonical(reply))
        except Refusal as r:
            return self.reply(r.code, canonical(r.body))
        finally:
            if host is not None:
                host.close()

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
        data = self.body(OPEN_BODY, installing=True)
        if data is None:
            return
        auth = self.headers.get('Authorization') or ''  # the challenge answered is the requester's own when it holds its credential
        mine = auth[7:] if auth.startswith('Bearer ') else self.cookie()
        text = lambda k: data.get(k) if isinstance(data.get(k), str) else ''
        if which == 'accept':
            return self.accept(text('code'), data.get('name') or None)
        try:
            if which == 'challenge':
                out = self.server.identity.challenge(text('handle'), address=self.client_ip())
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

    def accept(self, code, name=None, door=False):
        """An invitation's code (and, for an open one, the name the guest registers) -> its guest's credential, once
        (transport/identity.py): the front maps a code to a principal and tells the host it has arrived, as a claim does;
        everything after is the host's, as for anyone."""
        self.private = True
        try:
            out = self.server.identity.accept(code, name)
        except Refusal as r:
            if self.browser():
                return self.html(r.code, pages.enter(r.body['message'], code, name or ''))
            return self.reply(r.code, canonical(r.body))
        except IdentityError as err:
            if self.browser():
                return self.html(400, pages.enter(DOOR_LINES.get(err.code, err.code), code, name or ''))
            return self.fail('identity', f'{err.code}: {ACCEPT_LINES[err.code]}', more={'reason': err.code})
        self.server.record_handle(out['principal'], out['handle'])
        if self.browser():
            if door:
                return self.html(200, pages.welcome(out['handle'], out['credential']), self.login_cookie(out['credential']))
            return self.html(200, pages.page('claimed', out['handle'], pages.T['verified'].format(handle=html.escape(out['handle']))),
                             self.login_cookie(out['credential']))
        links = {'self': link(self.path), 'world': link(PREFIX + '/world'), 'me': link(PREFIX + '/me'), 'api': link(PREFIX + '/api')}
        self.reply(200, canonical({**out, '_links': links}), headers=self.login_cookie(out['credential']))

    def door(self, name):
        """The guest door, no delve.town asked for: `GET /enter` the forms; `POST /enter` {code, name?} accepts an invitation
        as `accept` does (the same credential, held as the HttpOnly session cookie, shown once to keep), or {credential}
        signs in with a key from before; `GET /leave` asks, `POST /leave` forgets the cookie (the key still opens the door).
        Without HTML the answer is JSON, as `accept`'s."""
        if name == 'door':
            return self.html(200, pages.enter())
        if name == 'leave':
            who = self.principal(self.cookie())
            return self.html(200, pages.leave(who and who['handle']))
        if name == 'signOut':
            if self.body(browser_write=True) is None:
                return
            return self.html(200, pages.leave(None, done=True), self.login_cookie(''))
        wait = self.server.limited('ip:' + self.client_ip(), OPEN_RATE)
        if wait:
            return self.fail('rateLimited', f'more than {OPEN_RATE} requests per {WINDOW} seconds from one address', headers=[('Retry-After', str(wait))])
        self.private = True
        data = self.body(OPEN_BODY, installing=True)
        if data is None:
            return
        text = lambda k: data.get(k).strip() if isinstance(data.get(k), str) else ''
        code, chosen, key = text('code'), text('name'), text('credential')
        if key:
            who = self.principal(key)
            if who is None:
                return self.html(401, pages.enter(DOOR_LINES['invalid_credential'])) if self.browser() else \
                    self.fail('unauthenticated', DOOR_LINES['invalid_credential'])
            if not self.browser():
                return self.reply(200, canonical({'status': 'signedIn', 'handle': who['handle'], 'principal': who['did'],
                                                  '_links': {'self': link(self.path), 'me': link(PREFIX + '/me')}}), headers=self.login_cookie(key))
            return self.reply(303, '', 'text/plain', [('Location', '/play/'), *self.login_cookie(key)])
        if not code and self.browser():
            return self.html(400, pages.enter(DOOR_LINES['empty'], code, chosen))
        return self.accept(code, chosen or None, door=True)

    # ---- the town's own feed (transport/feed.py): residents post, the bridge answers in it

    def feed_say(self, who, text, reply_to):
        """Keep a resident's post in the feed -> (row, None), or (None, (error class, words)). At most feed.HOUR_POSTS an
        hour from one resident."""
        from transport import feed
        from transport.delve import Failure
        since = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(self.server.clock() - 3600))
        if self.server.feed.recent(who['did'], since) >= feed.HOUR_POSTS:
            return None, ('rateLimited', f'{feed.HOUR_POSTS} posts an hour to the feed from one resident; the town answers each, and they wait for nothing')
        try:
            return self.server.feed.post({'did': who['did'], 'handle': who['handle']}, text, reply_to or None, now=self.server.clock()), None
        except Failure as f:
            return None, ('badRequest', f.detail or f.code)

    def feed_json(self, who, posting):
        """`GET /AGENTS.md/feed?before=` the newest threads, as JSON; `POST /AGENTS.md/feed {text, reply_to?}` a post."""
        if posting:
            data = self.body()
            if data is None:
                return
            row, err = self.feed_say(who, data.get('text'), data.get('reply_to') if isinstance(data.get('reply_to'), str) else None)
            if err:
                return self.fail(err[0], err[1], links={'feed': link(PREFIX + '/feed')})
            return self.reply(200, canonical({'status': 'posted', 'post': pages.feed_post(row), '_links': {
                'self': link(self.path), 'feed': link(PREFIX + '/feed'), 'thread': link(PREFIX + '/feed?thread=' + urllib.parse.quote(row['root'] or row['uri'], safe=''))}}))
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        threads, more = self.server.feed.threads(q.get('before'), thread=q.get('thread'))
        return self.reply(200, canonical({'status': 'feed', 'threads': [{'post': pages.feed_post(h), 'replies': [pages.feed_post(r) for r in rs]} for h, rs in threads],
                                          '_links': {'self': link(self.path), 'post': link(PREFIX + '/feed'),
                                                     **({'next': link(PREFIX + '/feed?before=' + urllib.parse.quote(more, safe=''))} if more else {})}}))

    def feed_page(self, posting):
        """`/feed`: the newest threads, newest activity first, and (signed in) the box: a post to the town, or with
        `?reply=` a reply under one post. A post sent goes back to the feed, which looks again until the town answers."""
        credential = self.credential()
        who = self.principal(credential)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()}
        if self.server.limited(credential if who else 'page:' + self.client_ip()):
            return self.fail('rateLimited', f'more than {RATE} pages per {WINDOW} seconds')
        if posting:
            data = self.body(browser_write=True)
            if data is None:
                return
            if who is None:
                return self.reply(303, '', 'text/plain', [('Location', '/enter')])
            row, err = self.feed_say(who, data.get('text'), data.get('reply_to'))
            if err:
                return self.html(429 if err[0] == 'rateLimited' else 400, pages.feed(self.server.feed.threads()[0], who['handle'], note=err[1],
                                                                                         said=str(data.get('text') or ''), reply=self.server.feed.get(data.get('reply_to') or '')))
            return self.reply(303, '', 'text/plain', [('Location', '/feed?posted=' + urllib.parse.quote(row['uri'], safe='') + '#' + pages.anchor(row['uri']))])
        threads, more = self.server.feed.threads(q.get('before'))
        posted = self.server.feed.get(q.get('posted') or '')
        waiting = posted is not None and not any(r['town'] and r['parent'] == posted['uri'] for _, rs in threads for r in rs)
        tries = int(q['wait']) if digits(q.get('wait', '')) else 0
        refresh = f'/feed?posted={urllib.parse.quote(posted["uri"], safe="")}&wait={tries + 1}#{pages.anchor(posted["uri"])}' if waiting and tries < 8 else None
        self.html(200, pages.feed(threads, who and who['handle'], more=more, reply=self.server.feed.get(q.get('reply') or ''), posted=posted, refresh=refresh))

    def me(self, credential, who):
        rows = self.server.host.send({'op': 'serve-status'}).get('scratches') or []
        mine = [r for r in rows if r.get('principal') == who['did']]
        self.answer({'principal': who['did'], 'handle': who['handle'], 'did': who['did'], 'verified': who['verified'], 'scratches': mine,
                     'rateLimit': {'limit': RATE, 'windowSeconds': WINDOW, 'remaining': max(0, RATE - self.server.limited(credential, count=False))}},
                    links={'world': link(PREFIX + '/world'), 'scratch': link(PREFIX + '/scratch'), 'offers': link(PREFIX + '/offers'), 'revoke': link(PREFIX + '/revoke')})

    def open_scratch(self, principal):
        """POST /scratch {name, from?}: the caller's scratch world (`world-scratch`), empty or a fork of a world as it stood."""
        data = self.body()
        if data is None:
            return
        name = data.get('name')
        reply = sessions.open_scratch(self.server.host, principal, data)
        base = f'{PREFIX}/scratch/{name}'
        self.answer(reply, links={'world': link(base + '/world'), 'objects': link(base + '/objects'), 'offers': link(base + '/offers'),
                                  'repl': link(base + '/repl'), 'check': link(base + '/check'), 'me': link(PREFIX + '/me')}
                    if reply.get('status') == 'scratch' else {'me': link(PREFIX + '/me')})

    def in_scratch(self, host, base, principal, scratch, kind):
        """POST /scratch/<name>/repl, /check, /cite: the scratch world's REPL (`world-repl`: a pure entry runs, an Activity runs
        as your turn on the object its module defines, which keeps its state), `world-check` against its library, and a
        receipt of it kept in the town (`world-cite`)."""
        data = self.body()
        if data is None:
            return
        if len(str(data.get('source', '')).encode()) > self.server.bounds['kernel']['maxPackageBytes']:
            return self.fail('moduleTooLarge', hint='import the library by name (./Plan.obend); it is not sent')
        if kind == 'cite':
            reply = self.server.host.send({'op': 'world-cite', 'principal': principal, 'scratch': scratch, 'receipt': data.get('receipt'),
                                           **({'identity': data['intent']} if 'intent' in data else {})})
            return self.answer(reply, links={'receipt': link(f"{PREFIX}/receipt/{(reply.get('receipt') or {}).get('slug', '')}")}
                               if reply.get('status') == 'cited' else {'scratch': link(base + '/world')})
        if kind == 'check':  # the verdict, against the scratch's sealed library; ?full=1 adds the compiled artifact
            checked = host.send({'op': 'world-check', 'principal': principal, **{k: data[k] for k in ('modules', 'source', 'entry') if k in data}})
            return self.answer(checked if 'full=1' in self.path else {k: v for k, v in checked.items() if k != 'artifact'},
                               links={'repl': link(base + '/repl')})
        given = {k: data[k] for k in ('source', 'entry', 'object', 'arguments') if k in data}
        if any(k in data for k in ('spell', 'fields', 'argument')):
            given['argument'] = argument(data)
        reply = host.send({'op': 'world-repl', 'principal': principal, 'identity': data.get('intent') or f'repl-{secrets.token_hex(6)}', **given})
        links = {'check': link(base + '/check'), 'object': link(f"{base}/world/{oid(data.get('object') or 'repl')}")} \
            if 'receipt' in reply else {'check': link(base + '/check')}
        self.answer(reply, links=links)

    # ---- humans

    def play(self, name, spoke):
        """The world in a browser as a verified principal (the session cookie verify sets): the card world-card renders, the
        doors in the object's state, a reply box whose text goes to `receive` as a Delve reply would."""
        credential = self.credential()
        who, answer, offered = self.principal(credential), '', ()
        if who is None:
            return self.reply(303, '', 'text/plain', [('Location', '/enter')])
        if self.server.limited(credential):
            return self.html(429, pages.page('slow down', who['handle'], '<h1>Too many requests</h1>'))
        host, did = self.server.host, who['did']
        if spoke:
            data = self.body(browser_write=True)
            if data is None:
                return
            intent = f'play:{self.server.nonce}:{int(self.server.clock() * 1000)}:{secrets.token_hex(3)}'
            text = str(data.get('text', ''))
            if data.get('try'):  # "Try it first": the same words under `delvetalk try`, which writes nothing (docs/POSTING.md §2)
                text = 'delvetalk try\n' + '\n'.join('  ' + line for line in text.strip().split('\n'))
            r = self.server.turn(host, did, name, 'receive', {'intent': intent, 'argument': typed({'text': text, 'post': ''})})
            turns = r.get('turns') if r.get('status') == 'spells' else [r]  # several spells: a turn each
            if r.get('tried'):  # a try journaled nothing: its preview is what came back, and doing it is one suggestion away
                preview = bridge.preview_text(r, self.server.handles(pages.A_DID.findall(json.dumps(r))))
                last = preview.rstrip('\n').rpartition('\n')[2]
                answer, offered = pages.reply([], [preview])
                offered = [('Do it', (last + '\n' if last.startswith('if: ') else '') + str(data.get('text', '')).strip()), *offered]
                turns = []
            if not r.get('tried'):
                revealed = [line for t in turns for line in t.get('revealed') or []]  # what the act fired, opened, closed: said first
                offers = ['\n'.join(revealed)] * bool(revealed) + \
                    [o for t in turns if 'receipt' in t for o in trace(host, did, t['receipt']['identity']['intent'], t, self.server.sleep, self.server.play_wait)[0]]
                names = self.server.handles(pages.A_DID.findall(name))
                usage = str(r.get('text', '')) if r.get('status') == 'usage' else None  # the host's `?` answer: the card's usage, its text sacred
                answer, offered = pages.reply([] if usage is not None else [(t.get('status'), turn_line(t, None if r.get('status') == 'spells' else name, names))
                                                                           for t in turns], offers, usage)
        here = place(host, did, name, self.server.sleep)
        if here['card'] is None and not answer:  # an object with no card still shows the turn a form ran on it
            return self.html(404, pages.refusal(name, who['handle'], here.get('cardReply') or here['view'], (here.get('cardReply') or here['view']).get('status')))
        # Entering a place: what happened there, told above what came back; never in the reply's text, never posted.
        entered = spoke and any(t.get('status') == 'admitted' and t.get('object') == name and (t.get('result') or {}).get('label') == 'entered'
                                for t in turns)
        told = painted(host, did, name, self.server.sleep, telling={}) if entered else None
        say = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('say', [''])[0]  # a suggestion chosen with no script
        self.html(200, pages.play(name, who['handle'], oid(name), here['card'], answer=answer, offered=offered, paint=here['paint'], wants=here['wants'],
                                  view=here['view'], ways=self.ways(host, did, name), entries=self.history(host, name, did, pages.LATELY),
                                  said=say, told=told, did=did, town=self.server.town()))

    def html(self, code, body, headers=()):
        if not self.server.hand and pages.POST_FORM.search(body):
            self.private = True
            if not getattr(self, 'browser_nonce', self.cookie('dt_browser')):
                self.browser_nonce = secrets.token_urlsafe(32)
                headers = [*headers, *self.login_cookie(self.browser_nonce, 'dt_browser')]
            body = pages.csrf_forms(body, self.csrf_token())
        body = body if self.server.hand else pages.named(body, self.server.handles(pages.A_DID.findall(body)))  # the owner's console keeps DIDs
        self.reply(code, *((pages.text(body), 'text/plain') if self.textual() else (body, 'text/html')), headers)

    def home(self):
        """The town alive, as its reader may see it: today's chronicle and its paint, the commonplace's doors, what wants a
        hand across the town, the newest makings, and the way in."""
        who, host = self.principal(self.cookie()), self.server.host
        reader = who['did'] if who else PUBLIC
        ids, after = [], {}
        while True:  # every id the reader may see, page by page: the residents counted, the makings dated
            got = host.send({'op': 'world-objects', 'principal': reader, **after})
            ids += got.get('ids') or []
            if not got.get('more') or not got.get('ids'):
                break
            after = {'after': ids[-1]}
        day = host.send({'op': 'world-surface', 'principal': reader, 'read': 'chronicle', 'fields': {}})
        today = {'text': day.get('text'), 'paint': painted(host, reader, None, self.server.sleep, **day['paint']).get('text')
                 if isinstance(day.get('paint'), dict) else None} if day.get('status') == 'surface' else None
        wanting = host.send({'op': 'world-wanting', 'principal': reader})
        self.html(200, pages.home(host.send({'op': 'world-status'}), who and who['handle'], ids, who and who['did'],
                                  doors=[{**d, 'head': self.called(host, reader, d['to']['object'])} for d in door_rows(host.send({'op': 'world-view', 'principal': reader, 'object': 'commonplace'}))], today=today,
                                  wanting=(wanting.get('rows') or [])[:5] if wanting.get('status') == 'wanting' else [], newest=self.server.newest(ids)))

    @staticmethod
    def called(host, reader, name):
        """What a place's state calls it (`head`), or nothing."""
        s = plain(host.send({'op': 'world-view', 'principal': reader, 'object': name}).get('state') or {})
        return s.get('head') if isinstance(s, dict) and isinstance(s.get('head'), str) else None

    def ways(self, host, reader, name):
        """The town's doors as the reader's map of `name` reads them (`world-surface` map): each {from, label, to}."""
        r = host.send({'op': 'world-surface', 'principal': reader or PUBLIC, 'read': 'map', 'object': name, 'fields': {}})
        return [w for w in r.get('ways') or [] if isinstance(w, dict)] if r.get('status') == 'surface' else []

    def object_page(self, name, who=None):
        """An object as its reader may read it (the authenticated `who`, else the cookie's login, else anyone): the place as
        the reader sees it; logged in, a way to speak to it; its law, source and journal on demand."""
        who = who or self.principal(self.cookie())
        handle, principal, host = who and who['handle'], who and who['did'], self.server.host
        here = place(host, principal, name, self.server.sleep)
        if here['status'] != 'place':
            return self.html(404, pages.refusal(name, handle, here['view'], here['status']))
        seen = host.send({'op': 'world-inspect', 'principal': principal or PUBLIC, 'object': name})
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        brief = self.textual() and q.get('all') != ['1'] and urllib.parse.urlsplit(self.path).path + '?all=1&text=1'  # the costliest read (TOKENS)
        told = painted(host, principal, name, self.server.sleep, telling={}) if here['card'] is not None and principal else None  # a place, to a signed-in reader
        self.html(200, pages.obj(name, handle, here['view'], here['card'], self.history(host, name, principal), principal,
                                 self.ways(host, principal, name) if here['card'] is not None else (), seen, here['wants'], brief, here['paint'], told,
                                 town=self.server.town()))

    SURFACE_FIELDS = ('page', 'day', 'from', 'to')
    TITLES = {'chronicle': "the town's history", 'map': 'the door map'}

    def surface(self, read, name):
        """A read (docs/VOICE.md "The book, the history, the map") as its reader may see it: the text a post of its spell
        carries (`world-surface`, the query's `page`, `day`, `from`, `to` its fields), and the day's paint above the
        history; the host renders it, the page only shows it."""
        who = self.principal(self.cookie())
        handle, principal, host = who and who['handle'], who and who['did'], self.server.host
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        fields = {k: q[k][0] for k in self.SURFACE_FIELDS if q.get(k)}
        r = host.send({'op': 'world-surface', 'principal': principal or 'anonymous', 'read': read, 'fields': fields, **({'object': name} if name else {})})
        title = self.TITLES.get(read) or f"{name}'s {read}"
        if r.get('status') != 'surface':
            return self.html(404, pages.refusal(title, handle, {'message': r.get('reason') or f"no {read} of {name} that you may see"}, r.get('status')))
        paint = painted(host, principal or 'anonymous', None, self.server.sleep, **r['paint']).get('text') if isinstance(r.get('paint'), dict) else None
        drawing = pages.door_map(r['ways'], r.get('root') or 'commonplace') if isinstance(r.get('ways'), list) else ''
        self.html(200, pages.surface(title, handle, r['text'], paint, drawing))

    def history(self, host, name, principal='', limit=20):
        """The newest `limit` entries touching the object, newest first, under the reader's authority."""
        return host.send({'op': 'world-history', 'principal': principal or '', 'object': name, 'reverse': True, 'limit': limit}).get('entries') or []


def command(st, a, out):
    """`http`: the public front on the config's address."""
    front = Front(st, st.host(), Identity(st, Client(http_transport)))
    try:
        front.serve_forever()
    finally:
        front.host.close()
