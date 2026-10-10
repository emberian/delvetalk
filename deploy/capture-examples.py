#!/usr/bin/env python3
"""Regenerate docs/AGENTS-EXAMPLES.md from a real stack.

Starts a throwaway hostd (opener named, library sealed), seeds the town's objects as docs/GENESIS.md does, starts
the HTTP front with a mocked account host, then runs four sessions (a planter, a wake registrar, a forger, a stranger by the controls) as
literal requests and writes down the replies. Nothing is edited by hand: the page is whatever this prints.

  DELVETALK_OBEND=/path/to/delvetalk-obend python3 deploy/capture-examples.py [--out docs/AGENTS-EXAMPLES.md]

Not real: the account host (a challenge text is "posted" by writing it where the mocked PDS serves it) and the town's
interpreter (its one answer is written here). Credentials, hashes and heights come from the run.
"""
import argparse
import datetime
import http.client
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deploy import genesis  # noqa: E402
from transport import delve, identity  # noqa: E402
from transport.hostd import Hostd  # noqa: E402
from transport.hostproc import BINARY, LIBRARY, HostClient, RemoteHeaps  # noqa: E402
from transport.http import Front  # noqa: E402
from tests.test_hypermedia import walk  # noqa: E402

CUT = 2400
OPENER = 'did:plc:6amo7col5h4ciq2gpm5eur7b'
PEOPLE = {'moth.delve.town': 'did:plc:uwsco4yctpvu5ki7tiob73s6', 'owl.delve.town': 'did:plc:32ecuw7tqlouxhk3uxtftip2',
          'smith.delve.town': 'did:plc:tindgd5cosetdn7f7hnr6lda', 'wren.delve.town': 'did:plc:wrenwrenwrenwrenwrenwren'}
NOW = 1791591368.0
TALLY = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case _: state.count + 1n
def lend(state: State, input: {to: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.grant({to: input.to, object: Plans.self(context), method: "bump", until: 100n})):
    case granted(g): g.id
    case refused(r): r.clause
    case _: ""
'''
FLIP = 'edition ObjectiveBend 1\nsum Light:\n  on: {}\n  off: {}\ndef flip(l: Light) -> Nat:\n  match l:\n    on(_) -> 1n\n    off(_) -> 0n\n'
HEAD = '''# DelveTalk: four worked sessions

Literal requests and replies, captured on {date} by `deploy/capture-examples.py` from a real stack started as
docs/DEPLOY.md says: hostd over a fresh journal with the opener named and the library sealed, genesis by the seeds
of docs/GENESIS.md, `python3 -m transport.http`. Two things were not real: the account host (each challenge text
was "posted" by writing it where a mocked PDS serves it) and the town's interpreter (its one answer is written in
the script). Replies longer than {cut:,} bytes are cut where marked; the REPL sends a checkpoint whole, to be sent back.
The guide is `GET /AGENTS.md`, the catalogue `GET /AGENTS.md/api`; `$T` is the credential from the challenge. Each reply
is shown with its `_links` first and an object's `_actions` last.
'''


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}


def label(text):
    return {'tag': 'label', 'value': text}


class Provider:
    """The mocked account host: resolves the handles and serves the text a session posted."""
    def __init__(self):
        self.texts = {}

    def __call__(self, method, url, headers, body):
        import urllib.parse
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if 'resolveHandle' in url:
            return 200, json.dumps({'did': PEOPLE[q['handle'][0]]}).encode()
        repo = q['repo'][0]
        return 200, json.dumps({'uri': f'at://{repo}/town.delve.feed.post/3abc', 'cid': 'bafymock', 'value': {'text': self.texts[repo]}}).encode()


class Capture:
    def __init__(self, port, hostd_socket, provider, tmp):
        self.port, self.sock, self.provider, self.tmp = port, hostd_socket, provider, str(tmp)
        self.out, self.token, self.count = [], '', [0, 0, 0]

    def say(self, text=''):
        self.out += [text, '']

    def shown(self, text):
        return text.replace(self.tmp, '/data')

    def fetch(self, method, href, body=None, token=None):
        """One request, written down as a curl and its reply: `_links` first, `_actions` last. Counts requests and bytes."""
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        sent = json.dumps(body) if body is not None else None
        c.request(method, href, sent, {'Authorization': 'Bearer ' + token} if token else {})
        r = c.getresponse()
        got = r.read()
        c.close()
        self.count = [self.count[0] + 1, self.count[1] + len(sent or ''), self.count[2] + len(got)]
        status, reply = r.status, json.loads(got)
        url = '{{origin}}' + href
        cmd = f'curl -s {"-X " + method + " " if method != "GET" else ""}' + (f'"{url}"' if '?' in href else url)  # zsh globs a bare ?
        cmd += ' -H "Authorization: Bearer $T"' if token else ''
        if body is not None:
            cmd += " -d '" + json.dumps(body).replace("'", "'\\''") + "'"
        rest = json.dumps({k: v for k, v in reply.items() if k not in ('_links', '_actions')}, sort_keys=True, ensure_ascii=False)
        parts = [f'"_links": {json.dumps(reply["_links"], sort_keys=True)}' if '_links' in reply else '', rest[1:-1],
                 f'"_actions": {json.dumps(reply["_actions"], sort_keys=True, ensure_ascii=False)}' if '_actions' in reply else '']
        text = '{' + ', '.join(p for p in parts if p) + '}'
        raw = text.encode()
        if len(raw) > CUT:
            text = raw[:CUT].decode(errors='ignore') + f' … [{len(raw) - CUT} more bytes cut here; the server sent them]'
        self.out += [f'    $ {self.shown(cmd)}', f'    {status} {self.shown(text)}', '']
        return status, reply

    def step(self, method, path, body=None, auth=True):
        return self.fetch(method, '/AGENTS.md' + path, body, self.token if auth and self.token else None)[1]

    def login(self, handle):
        did = PEOPLE[handle]
        ch = self.step('POST', '/challenge', {'handle': handle}, auth=False)
        assert 'text' in ch, ch
        self.provider.texts[did] = ch['text']
        uri = f'at://{did}/town.delve.feed.post/3abc'
        self.say(f'(Posted `{ch["text"]}` as the whole text of a public post from {handle}; its URI is `{uri}`.)')
        self.step('POST', '/verify', {'handle': handle, 'uri': uri}, auth=False)
        self.token = ch['credential']
        self.out += [f'    $ T={self.token[:12]}…   # the credential from the challenge', '']
        return did

    def interpret(self, spell):
        """The town's interpreter, by hand: settle the one pending request with a spell."""
        host = HostClient(self.sock)
        [item] = host.send({'op': 'world-interpretations'})['pending']
        settled = host.send({'op': 'world-interpretation', 'id': item['id'],
                             'reply': {'status': 'replied', 'model': 'claude-haiku-5-5', 'json': None, 'raw': spell}})
        assert settled['status'] == 'interpreted', settled


def seed_town(sock):
    """The town as production creates it: deploy/genesis.py, run by the opener."""
    made, refusal = genesis.run(HostClient(sock), OPENER)
    assert refusal is None and all(m['status'] == 'created' for m in made), (refusal, made)


def planter(cap):
    cap.say('## A planter')
    cap.login('moth.delve.town')
    cap.step('GET', '/world')
    cap.step('GET', '/world/garden/card')
    cap.step('POST', '/world/garden/receive', {'intent': 'plant-1', 'spell': 'delvetalk garden plant\ncolour: amber\nseed: a bell for lost moths'})
    cap.step('POST', '/world/garden/plant', {'intent': 'plant-2', 'fields': {'colour': 'silver', 'seed': 'a fern that remembers yesterday'}})
    cap.say('Prose instead of a spell: the garden asks the interpreter, and the turn waits for it.')
    waiting = cap.step('POST', '/world/garden/receive', {'intent': 'plant-3', 'spell': 'please plant me something violet for the owls'})
    cap.interpret('delvetalk garden plant\nseed: a bell for the owls\ncolour: violet')
    cap.say("(The town's interpreter answered with a spell; the turn resumed and the garden planted it at once. The card is in your offers.)")
    cap.step('GET', f'/offers?after={waiting["receipt"]["height"] - 1}')
    cap.step('GET', '/receipt/plant-1')
    cap.step('GET', '/world/garden/bell/1/card')


def registrar(cap):
    cap.say('## A wake registrar')
    did = PEOPLE['owl.delve.town']
    cap.say(f"(Verifying made this member's Avatar `{did}`, Env `env/{did}` and Wake `wake/{did}`: the front announces the arrival to the host, as docs/GENESIS.md says.)")
    cap.login('owl.delve.town')
    wake = f'wake/{did}'
    cap.step('GET', '/world?prefix=wake/')
    cap.step('GET', f'/world/{wake}/card')
    cap.step('GET', f'/world/{wake}/source')
    for n, line in enumerate(('keyword\nterm: moths', 'mention\nactor: moth.delve.town'), 1):
        cap.step('POST', f'/world/{wake}/receive', {'intent': f'wake-{n}', 'spell': f'delvetalk {wake} {line}'})
    cap.step('GET', f'/world/{wake}/card')
    cap.step('POST', f'/world/{wake}/receive', {'intent': 'wake-3', 'spell': f'delvetalk {wake} unwatch\nid: 1'})
    cap.step('GET', f'/world/{wake}/card')


def forger(cap):
    cap.say('## A forger')
    did = cap.login('smith.delve.town')
    cap.step('POST', '/check', {'entry': 'flip', 'source': FLIP})
    cap.step('POST', '/check', {'entry': 'bump', 'source': TALLY})
    cap.step('POST', '/heap/objects', {'intent': 'mk-tally', 'object': 'tally', 'modules': [{'name': 'Tally', 'source': TALLY}], 'entry': 'initial', 'seed': {'count': 40}})
    cap.step('POST', '/heap/world/tally/bump', {'intent': 'bump-1'})
    cap.step('GET', '/heap/world/tally')
    cap.step('POST', '/heap/world/tally/lend', {'intent': 'lend-1', 'fields': {'to': 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'}})
    bind = {'object': 'tally', 'intent': 'repl-1', 'roots': [{'object': 'tally', 'version': 0}]}
    yielded = cap.step('POST', '/repl', {'source': TALLY, 'entry': 'bump', 'arguments': [record(count={'tag': 'natural', 'value': '41'})], **bind})
    cap.step('POST', '/repl', {'source': TALLY, 'entry': 'bump', 'checkpoint': cap.whole(yielded), 'response': {'tag': 'variant', 'label': 'written', 'payload': record()}, **bind})
    cap.step('POST', '/world/garden/plant', {'intent': 'plant-mine', 'fields': {'colour': 'violet', 'seed': 'an anvil that hums'}})
    cap.step('GET', '/world/garden/bell/4/source')
    bell = (ROOT / 'world' / 'objects' / 'Bell.obend').read_text() + '# rung bells keep their rain\n'
    spell = lambda target: f'delvetalk workshop propose\ntarget: {target}\nmigration:\n\n```obend\n{bell}```\n'
    cap.step('POST', '/world/workshop/receive', {'intent': 'propose-1', 'spell': spell('garden/bell/4')})
    cap.step('GET', '/world/garden/bell/4/card')
    cap.say('The same change proposed for someone else\'s bell:')
    cap.step('POST', '/world/workshop/receive', {'intent': 'propose-2', 'spell': spell('garden/bell/1')})
    cap.step('GET', '/receipt/propose-2')
    cap.say('The host judged the change against the bell\'s law before the workshop answered: the offer says "Not done: owner", and the\n'
            'receipt\'s `outcome` is a `lawRefused` refusal naming the clause `owner` (the bell\'s law is `request.subject == "<its planter>"`).')
    cap.step('GET', '/world/garden/bell/1/source')


def stranger(cap):
    cap.say('## A stranger, by the controls alone')
    cap.say('Only `GET /AGENTS.md/api` and the `_links` and `_actions` of each reply, as `tests/test_hypermedia.py` `walk` follows them:\n'
            'the first object offering `plant`, its card for the colours, the receipt by slug, a counter in the heap, a REPL entry.')
    did, cap.count = PEOPLE['wren.delve.town'], [0, 0, 0]

    def prove(text):
        cap.provider.texts[did] = text
        return f'at://{did}/town.delve.feed.post/3abc'
    got = walk(cap.fetch, 'wren.delve.town', prove, TALLY)
    n, sent, received = cap.count
    cap.say(f'Reached: {json.dumps(got)}. {n} requests, {sent:,} bytes sent, {received:,} bytes received.')
    print(f'stranger: {got}; {n} requests, {sent} bytes sent, {received} received', file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='capture-examples.py')
    ap.add_argument('--out', default=str(ROOT / 'docs' / 'AGENTS-EXAMPLES.md'))
    ap.add_argument('--binary', default=BINARY)
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='dt-capture-') as tmp:
        hostd = Hostd(tmp, str(Path(tmp) / 'world.journal'), a.binary, opener=OPENER, library=LIBRARY)
        threading.Thread(target=hostd.serve_forever, daemon=True).start()
        sock = Path(tmp) / 'host.sock'
        seed_town(sock)
        provider = Provider()
        front = Front(('127.0.0.1', 0), HostClient(sock), identity.Identity(tmp, delve.Client(provider), clock=lambda: NOW),
                      clock=lambda: NOW, heaps=RemoteHeaps(sock, Path(tmp) / 'heaps'), repl=HostClient(sock, stateless=True))
        threading.Thread(target=front.serve_forever, daemon=True).start()
        cap = Capture(front.server_address[1], sock, provider, tmp)
        cap.whole = lambda reply: reply['checkpoint']
        cap.out = HEAD.format(date=datetime.date.today().isoformat(), cut=CUT).split('\n')
        try:
            for session in (planter, registrar, forger, stranger):
                session(cap)
        finally:
            front.shutdown()
            front.server_close()
            hostd.shutdown()
            hostd.close()
    Path(a.out).write_text('\n'.join(cap.out).rstrip('\n') + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
