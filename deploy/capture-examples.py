#!/usr/bin/env python3
"""Regenerate docs/AGENTS-EXAMPLES.md from a real stack.

Starts a throwaway `delvetalk-obend serve` (opener named, library sealed), seeds the town's objects as docs/GENESIS.md does, starts
the HTTP front with a mocked account host, then runs four sessions (a resident at the porch, a maker of a sealed kind, a forger, a stranger by the controls) as
literal requests and writes down the replies. Nothing is edited by hand: the page is whatever this prints.

  DELVETALK_OBEND=/path/to/delvetalk-obend python3 deploy/capture-examples.py [--out docs/AGENTS-EXAMPLES.md]

Not real: the account host (a challenge text is "posted" by writing it where the mocked PDS serves it) and the town's
interpreter (its one answer is written here). Credentials, hashes and heights come from the run.
"""
import argparse
import datetime
import http.client
import json
import re
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deploy import genesis  # noqa: E402
from transport import delve, identity  # noqa: E402
from deploy.serve import Served  # noqa: E402
from transport.config import LIBRARY, Config  # noqa: E402
from transport.host import HostClient  # noqa: E402
from transport.http import Front  # noqa: E402
from tests.test_hypermedia import walk  # noqa: E402

CUT = 2400
OPENER = 'did:plc:6amo7col5h4ciq2gpm5eur7b'
PEOPLE = {'moth.delve.town': 'did:plc:uwsco4yctpvu5ki7tiob73s6', 'owl.delve.town': 'did:plc:32ecuw7tqlouxhk3uxtftip2',
          'smith.delve.town': 'did:plc:tindgd5cosetdn7f7hnr6lda', 'wren.delve.town': 'did:plc:wrenwrenwrenwrenwrenwren',
          'fern.delve.town': 'did:plc:fernfernfernfernfernfern'}
NOW = 1791591368.0
TALLY = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Text.obend as Text
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {count: add 1n}
  state.count + 1n
def lend(state: State, input: {to: String}, context: Abi.Context) -> Activity<String>:
  match world.grant({to: input.to, object: Plans.self(context), method: "bump", until: 100n}):
    case granted(g): g.id
    case refused(r): r.clause
def methods() -> Lists.List<String>:
  Text.words("bump lend")
'''
SEALED = ('delvetalk kinds make / name: sealed / of: record / form: text: text 1..80 / head: what {maker} sealed, stays sealed'
          ' / law: law maker "only its maker writes": request.subject == new.maker')
FLIP = 'edition ObjectiveBend 1\nsum Light:\n  on: {}\n  off: {}\ndef flip(l: Light) -> Nat:\n  match l:\n    on(_) -> 1n\n    off(_) -> 0n\n'
HEAD = '''# DelveTalk: four worked sessions

Literal requests and replies, captured on {date} by `deploy/capture-examples.py` from a real stack started as
docs/DEPLOY.md says: `serve` over a fresh directory with the opener named and the library sealed, genesis by the seeds
of docs/GENESIS.md (the minimal town: the commonplace, the porch and its bells, the kinds), `python3 -m transport http`. Two things were not real: the account host (each challenge text
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
    def __init__(self, port, socket, provider, tmp):
        self.port, self.sock, self.provider, self.tmp = port, socket, provider, str(tmp)
        self.out, self.token, self.count = [], '', [0, 0, 0]

    def say(self, text=''):
        self.out += [text, '']

    def shown(self, text):
        return re.sub(r'dt_agent_[A-Za-z0-9_-]+', 'dt_agent_…', text.replace(self.tmp, '/data'))  # a throwaway token is not a secret, but the page need not carry it

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
        self.out += ['    $ T=dt_agent_…   # the credential from the challenge', '']
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
    made, refusal = genesis.run(HostClient(sock), OPENER)  # the root socket: the opener speaks there only
    assert refusal is None and all(m['status'] in ('created', 'admitted') for m in made), (refusal, [m for m in made if m['status'] not in ('created', 'admitted')])


def resident(cap):
    cap.say('## A resident at the porch')
    cap.login('moth.delve.town')
    cap.say("The first card is the commonplace: what changed, then the doors, each with its spells.")
    cap.step('GET', '/world/commonplace/card')
    cap.step('GET', '/world')
    cap.step('POST', '/world/porch/receive', {'intent': 'enter-1', 'spell': 'delvetalk porch enter'})
    cap.step('GET', '/world/bell/1/card')
    cap.step('POST', '/world/bell/1/receive', {'intent': 'rain-1', 'spell': 'delvetalk bell/1 rain\ntext: a moth taps the brass'})
    cap.say('A verb the bell lacks, grown by a hand and used at once; the grower is named on the card.')
    cap.step('POST', '/world/bell/1/receive', {'intent': 'grow-1', 'spell': 'delvetalk bell/1 grow\nname: hum\nreading: hummed at by a hand; a line, and the bell is tended\ntakes: text'})
    cap.step('POST', '/world/bell/1/receive', {'intent': 'hum-1', 'spell': 'delvetalk bell/1 hum\ntext: low, for the moths'})
    cap.say('Words instead of a spell: the bell leaves them to hob, and the turn waits for its reading.')
    waiting = cap.step('POST', '/world/bell/1/receive', {'intent': 'hum-2', 'spell': 'hum to it again, for the owls this time'})
    cap.interpret('delvetalk bell/1 hum\ntext: for the owls')
    cap.say("(The town's interpreter answered with the grown verb's spell; the turn resumed and ran it as yours. The card is in your offers.)")
    cap.step('GET', f'/offers?after={waiting["receipt"]["height"] - 1}')
    cap.step('GET', '/receipt?intent=hum-1')
    cap.step('GET', '/world/bell/1/card')
    cap.say('A garden is a kind anyone makes; what it makes, it plants.')
    made = cap.step('POST', '/world/kind/garden/receive', {'intent': 'garden-1', 'spell': 'delvetalk kind/garden make\nname: the moth garden'})
    garden = [c['name'] for c in made['_links'].get('created', [])][0]
    cap.step('GET', f'/world/{garden}/card')
    cap.step('POST', f'/world/{garden}/plant', {'intent': 'plant-1', 'fields': {'colour': 'amber', 'seed': 'a bell for lost moths'}})


def maker(cap):
    cap.say('## A maker')
    cap.say('A kind with a law (the commonplace\'s KINDS door): only its maker writes what it makes.')
    cap.login('fern.delve.town')
    cap.step('POST', '/world/kinds/receive', {'intent': 'kind-sealed', 'spell': SEALED})
    cap.step('GET', '/world/kind/sealed/card')
    cap.step('POST', '/world/kind/sealed/receive', {'intent': 'seal-1', 'spell': 'delvetalk kind/sealed make / text: the first seal'})
    cap.step('POST', '/world/sealed/1/receive', {'intent': 'seal-2', 'spell': 'delvetalk sealed/1 write / text: the first seal, again'})
    cap.say('Someone else writes on it; the law answers by name, and nothing is written:')
    cap.login('moth.delve.town')
    cap.step('POST', '/world/sealed/1/receive', {'intent': 'seal-3', 'spell': 'delvetalk sealed/1 write / text: a moth was here'})
    cap.step('GET', '/receipt?intent=seal-3')
    cap.step('GET', '/world/sealed/1/card')


def forger(cap):
    cap.say('## A forger')
    cap.login('smith.delve.town')
    cap.step('POST', '/check', {'entry': 'flip', 'source': FLIP})
    cap.step('POST', '/check', {'entry': 'bump', 'source': TALLY})
    cap.step('POST', '/scratch', {'name': 'try'})
    cap.step('POST', '/scratch/try/objects', {'intent': 'mk-tally', 'object': 'tally', 'modules': [{'name': 'Tally', 'source': TALLY}], 'entry': 'initial', 'seed': {'count': 40}})
    cap.step('POST', '/scratch/try/world/tally/bump', {'intent': 'bump-1'})
    cap.step('GET', '/scratch/try/world/tally')
    cap.step('POST', '/scratch/try/world/tally/lend', {'intent': 'lend-1', 'fields': {'to': 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'}})
    bind = {'object': 'tally', 'intent': 'repl-1', 'roots': [{'object': 'tally', 'version': 0}]}
    yielded = cap.step('POST', '/repl', {'source': TALLY, 'entry': 'bump', 'arguments': [record(count={'tag': 'natural', 'value': '41'})], **bind})
    cap.step('POST', '/repl', {'source': TALLY, 'entry': 'bump', 'checkpoint': cap.whole(yielded), 'response': {'tag': 'variant', 'label': 'written', 'payload': record()}, **bind})


def stranger(cap):
    cap.say('## A stranger, by the controls alone')
    cap.say('Only `GET /AGENTS.md/api` and the `_links` and `_actions` of each reply, as `tests/test_hypermedia.py` `walk` follows them:\n'
            'the first object offering `plant` (a garden the resident made), its card for the colours, the receipt by slug, a counter in a scratch world, a REPL entry.')
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
    ap.add_argument('--binary', default=Config.load().obend)
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='dt-capture-') as tmp:
        served = Served(Path(tmp) / 'state', a.binary, opener=OPENER, library=LIBRARY)
        sock = served.sock
        seed_town(served.root)
        provider = Provider()
        front = Front(served.place, HostClient(sock), identity.Identity(served.place, delve.Client(provider), clock=lambda: NOW),
                      ('127.0.0.1', 0), clock=lambda: NOW)
        threading.Thread(target=front.serve_forever, daemon=True).start()
        cap = Capture(front.server_address[1], sock, provider, tmp)
        cap.root = served.root
        cap.whole = lambda reply: reply['checkpoint']
        cap.out = HEAD.format(date=datetime.date.today().isoformat(), cut=CUT).split('\n')
        try:
            for session in (resident, maker, forger, stranger):
                session(cap)
        finally:
            front.shutdown()
            front.server_close()
            served.stop()
    Path(a.out).write_text('\n'.join(cap.out).rstrip('\n') + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
