#!/usr/bin/env python3
"""Regenerate docs/AGENTS-EXAMPLES.md from a real stack.

Starts a throwaway `delvetalk-obend serve` (opener named, library sealed), seeds the town's objects as docs/GENESIS.md does, starts
the HTTP front with a mocked account host, then runs four sessions (a bell-maker, a maker of a sealed kind, a forger, a stranger by the controls) as
literal requests and writes down the replies. Nothing is edited by hand: the page is whatever this prints.

  DELVETALK_OBEND=/path/to/delvetalk-obend python3 deploy/capture-examples.py [--out docs/AGENTS-EXAMPLES.md]

Not real: the account host (a challenge text is "posted" by writing it where the mocked PDS serves it) and the town's
interpreter (its one answer is written here). Credentials, hashes and heights come from the run.
"""
import argparse
import atexit
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
of docs/GENESIS.md (the minimal town: the commonplace, `kinds`, the porch with its two bells), `python3 -m transport http`. Two things were not real: the account host (each challenge text
was "posted" by writing it where a mocked PDS serves it) and the town's interpreter (its one answer is written in
the script). Replies longer than {cut:,} bytes are cut where marked.
The guide is `GET /AGENTS.md`, the catalogue `GET /AGENTS.md/api`; `$T` is the credential from the challenge. Each reply
is shown with its `_links` first and an object's `_actions` last.
'''


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
        self.token = ch['credential']
        self.step('POST', '/verify', {'handle': handle, 'uri': uri})
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


def made(reply):
    """The id of the first thing a turn reply says it created (its `created` link), or ''."""
    return ([c['name'] for c in reply.get('_links', {}).get('created', [])] or [''])[0]


def bell_maker(cap):
    cap.say('## A bell-maker')
    did = cap.login('moth.delve.town')
    cap.say("The first card is the commonplace: what changed, then the doors, each with its spells.")
    cap.step('GET', '/world/commonplace/card')
    cap.step('GET', '/world')
    cap.step('GET', '/world/kind/bell/card')
    cap.say('A spell that leaves out a field is asked for, not refused; nothing of it is kept, so the whole spell is sent again.')
    cap.step('POST', '/world/kind/bell/receive', {'intent': 'bell-0', 'spell': 'delvetalk kind/bell make\ncolour: amber'})
    first = cap.step('POST', '/world/kind/bell/receive', {'intent': 'bell-1', 'spell': 'delvetalk kind/bell make\ncolour: amber\nseed: a bell for lost moths'})
    bell = made(first)
    cap.step('POST', '/world/kind/bell/make', {'intent': 'bell-2', 'fields': {'colour': 'silver', 'seed': 'a fern that remembers yesterday'}})
    cap.say('Prose instead of a spell: the kind asks the interpreter, and the turn waits for it.')
    waiting = cap.step('POST', '/world/kind/bell/receive', {'intent': 'bell-3', 'spell': 'please make me something violet for the owls'})
    cap.interpret('delvetalk kind/bell make\nseed: a bell for the owls\ncolour: violet')
    cap.say("(The town's interpreter answered with a spell; the turn resumed and the kind made the bell at once. The card is in your offers.)")
    cap.step('GET', f'/offers?after={waiting["receipt"]["height"] - 1}')
    cap.step('GET', '/receipt?intent=bell-1')
    cap.step('GET', f'/world/{bell}/card')
    cap.say('Acting grows the bell. A verb nobody gave it, a rule that fires when a write makes its condition true, and a want it poses until it is met:')
    grow = lambda intent, spell: cap.step('POST', f'/world/{bell}/receive', {'intent': intent, 'spell': spell})
    grow('grow-1', f'delvetalk {bell} grow\nname: trim\nreading: the wick trimmed\ntakes: nothing')
    cap.say('The verb is a name and a reading; using it is a turn that waits for hob to answer.')
    grow('grow-2', f'delvetalk {bell} trim')
    grow('verbs-1', f'delvetalk {bell} verbs')
    grow('rule-1', f'delvetalk {bell} rule\nname: heard\nwhen: count(new.lines) >= 3\nthen: delvetalk me note\ntext: {bell} heard thrice')
    grow('want-1', f'delvetalk {bell} want\nname: unheard\nreading: a bell nobody has rained on\nwhen: count(new.lines) == 0\nasks: delvetalk {bell} rain')
    grow('wants-1', f'delvetalk {bell} wants')
    for n in (1, 2, 3):
        cap.step('POST', f'/world/{bell}/rain', {'intent': f'rain-{n}', 'fields': {'text': f'rain number {n}'}})
    cap.say('The third rain made the rule true: it fired at commit, under its writer, and left a note on the avatar, which is the object named by your DID.')
    cap.step('GET', f'/world/{did}/card')
    grow('rules-1', f'delvetalk {bell} rules')
    grow('wants-2', f'delvetalk {bell} wants')


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
    cap.step('POST', '/scratch', {'name': 'try'})
    cap.step('POST', '/scratch/try/check', {'entry': 'flip', 'source': FLIP})
    cap.step('POST', '/scratch/try/check', {'entry': 'bump', 'source': TALLY})
    cap.step('POST', '/scratch/try/objects', {'intent': 'mk-tally', 'object': 'tally', 'modules': [{'name': 'Tally', 'source': TALLY}], 'entry': 'initial', 'seed': {'count': 40}})
    cap.step('POST', '/scratch/try/world/tally/bump', {'intent': 'bump-1'})
    cap.step('GET', '/scratch/try/world/tally')
    cap.step('POST', '/scratch/try/world/tally/lend', {'intent': 'lend-1', 'fields': {'to': 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'}})
    cap.step('POST', '/scratch/try/repl', {'source': TALLY, 'entry': 'bump', 'object': 'counter', 'intent': 'repl-1'})
    cap.step('POST', '/scratch/try/repl', {'entry': 'bump', 'object': 'counter', 'intent': 'repl-2'})
    cap.say("An unclaimed thing on the porch becomes its keeper's by one spell; being its keeper does not make one its owner.")
    cap.step('POST', '/world/porch/ring/receive', {'intent': 'inspirit-1', 'spell': 'delvetalk porch/ring inspirit\nsurrounding: a ring that hums on an anvil'})
    cap.step('GET', '/world/porch/ring/source')
    thing = (ROOT / 'world' / 'objects' / 'Thing.obend').read_text() + '# a ring that hums keeps its hum\n'
    cap.say('A change of its code, proposed through the workshop:')
    cap.step('POST', '/world/workshop/receive', {'intent': 'propose-1', 'spell': f'delvetalk workshop propose\ntarget: porch/ring\nmigration:\n\n```obend\n{thing}```\n'})
    cap.say("The host dry-ran the change against the ring's law before the workshop answered. Only the owner reprograms a thing, so the dry run\n"
            'was refused `owner`; the workshop held the proposal for the owner to adopt. The offer says `refused owner: held as #1 …`,\n'
            "and the receipt is the workshop's own admitted write, the held proposal inserted into its `held` rows.")
    cap.step('GET', '/receipt?intent=propose-1')


def fill(spell):
    """Plain values for a spell template's fields, as any client would read them: a choice's first word, a natural's minimum."""
    values = {}
    for name, shown in re.findall(r'^(\w+): (.+)$', spell.partition('\n')[2], re.M):
        values[name] = re.split(r', ', shown[len('one of '):])[0] if shown.startswith('one of ') else \
            int(re.search(r'(\d+)\.\.', shown)[1]) if shown.startswith('<natural') else f"a {name} for strangers"
    return values


PURE = 'edition ObjectiveBend 1\ndef twice(n: Nat) -> Nat:\n  n + n\n'


def walk(call, handle, prove, module):
    """A stranger with only the catalogue and the controls in replies: challenge, verify, find a kind to make from, make,
    read the receipt by its slug, open a scratch world, make a thing in it and run it, run a REPL entry. `call(method, href,
    body, token)` -> (status, reply); `prove(text)` posts the challenge and returns the post's URI; `module` is the stranger's
    own Bend (a State with a `count` and a `bump` method). -> what it reached."""
    got = {}
    api = call('GET', '/AGENTS.md/api', None, None)[1]
    routes = {r['name']: r for r in api['routes']}
    ch = call('POST', routes['challenge']['href'], {'handle': handle}, None)[1]
    tok = ch['credential']
    v = call('POST', ch['_links']['verify']['href'], {'handle': handle, 'uri': prove(ch['text'])}, tok)[1]
    listing = call('GET', v['_links']['world']['href'], None, tok)[1]
    item = [i for i in listing['_links']['item'] if i['name'] == 'kind/bell'][0]  # the listing names each object's methods
    assert 'make' in item['actions'], item
    spell = call('GET', item['href'], None, tok)[1]['_actions']['make']
    planted = call('POST', f"{item['href']}/make", {'intent': 'stranger-make', 'fields': fill(spell)}, tok)[1]
    got['made'] = (planted['status'], [c['name'] for c in planted['_links'].get('created', [])])
    receipt = call('GET', planted['_links']['receipt']['href'], None, tok)[1]
    got['receipt'] = (receipt['status'], receipt['receipt']['slug'] == planted['receipt']['slug'])
    opened = call('POST', routes['scratch']['href'], {'name': 'try'}, tok)[1]
    made_ = call('POST', opened['_links']['objects']['href'], {'intent': 'stranger-scratch', 'object': 'mine', 'entry': 'initial', 'source': module, 'seed': {}}, tok)[1]
    mine = call('GET', made_['_links']['object']['href'], None, tok)[1]
    assert 'bump' in mine['_actions'], mine
    bumped = call('POST', mine['_links']['object']['href'] + '/bump', {'intent': 'stranger-bump', 'fields': {}}, tok)[1]
    result = call('GET', bumped['_links']['receipt']['href'], None, tok)[1]['receipt']['result']
    got['scratch'] = (made_['status'], bumped['status'], result)
    ran = call('POST', opened['_links']['repl']['href'], {'source': PURE, 'entry': 'twice', 'arguments': [{'tag': 'natural', 'value': '21'}]}, tok)[1]
    got['repl'] = (ran['status'], ran['value'])
    return got


def stranger(cap):
    cap.say('## A stranger, by the controls alone')
    cap.say('Only `GET /AGENTS.md/api` and the `_links` and `_actions` of each reply, as `walk` below follows them:\n'
            'the first object offering `make`, its card for the colours, the receipt by slug, a counter in a scratch world, a REPL entry.')
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
        served = Served(Path(tmp) / 'state', a.binary, opener=OPENER, library=LIBRARY, cleanup=atexit.register)
        sock = served.sock
        seed_town(served.root)
        provider = Provider()
        front = Front(served.place, HostClient(sock), identity.Identity(served.place, delve.Client(provider), clock=lambda: NOW),
                      ('127.0.0.1', 0), clock=lambda: NOW)
        threading.Thread(target=front.serve_forever, daemon=True).start()
        cap = Capture(front.server_address[1], sock, provider, tmp)
        cap.root = served.root
        cap.out = HEAD.format(date=datetime.date.today().isoformat(), cut=CUT).split('\n')
        try:
            for session in (bell_maker, maker, forger, stranger):
                session(cap)
        except BaseException:
            Path('/tmp/ex-partial.md').write_text('\n'.join(cap.out))
            raise
        finally:
            front.shutdown()
            front.server_close()
            served.stop()
    Path(a.out).write_text('\n'.join(cap.out).rstrip('\n') + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
