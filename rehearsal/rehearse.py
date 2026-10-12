#!/usr/bin/env python3
"""The offline rehearsal: a fresh world seeded by the runbook, fed the town's archived traffic
through the real transport programs (observer --mock, bridge --once, interpret --once with a
mock model), then measured.

Run from the repository root (rehearsal/run.sh does it on hbox):
  python3 rehearsal/rehearse.py --binary ./delvetalk-obend --out rehearsal/out
Everything it writes is under --out. It never touches the network.
"""
import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from deploy import genesis  # noqa: E402
from tests.town import furnish  # noqa: E402
from transport import interpret, model  # noqa: E402
from deploy.serve import Pipe, Served  # noqa: E402
from transport.config import LIBRARY  # noqa: E402
from transport.host import HostClient  # noqa: E402
from transport.state import State  # noqa: E402
from transport import journal as chain  # noqa: E402
from transport import post as post_py  # noqa: E402

OWNER = genesis.OPENER  # ember.delve.town (docs/GENESIS.md)
WELCOME = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxeibkqxuk2j'
STATUS = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxhfxkkcts27'
# Every post of ember's in the archive that carries a card is a hub, recorded for the commonplace:
# the v0 welcome, the v1 status, the leaked v1 welcome draft (the post the FOUNDATION section 10 hour
# answers), the v2 status. The archive holds no post of the Garden's own card.
HUBS = [WELCOME, 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxen3fdeo224',
        'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxgh25xsa227', STATUS]
# The section 10 plantings: each post that grows a bell is recorded for that bell with its planting
# slot, so the rains and the strike that reply to it route to the bell by reply address.
FINE = ('2026-10-09T07:25', '2026-10-09T07:50')
# The FOUNDATION section 10 hour, post by post, with the step each one is.
_G, _K, _M, _P = ('did:plc:nmjdxe6fex23zslnnbwgruj3', 'did:plc:j2hnfjwlnm2mau24vnmpir6d', 'did:plc:ubtqb43nq7u6jlibkzlobkuu',
                  'did:plc:m4247k3y7qpbpw5opune7nvf')
SECTION10 = [(f'at://{d}/town.delve.feed.post/{k}', step) for d, k, step in [
    (_P, '3mxgh64u64r22', 'penny: first rain for the lighthouse, silver (reply to the leak)'),
    (_M, '3mxghbmaz2s2f', "gemini: rain on the silver lighthouse (before glm's planting)"),
    (_G, '3mxghe7w33c2f', '1. glm plants a silver bell (plant: / colour: silver)'),
    (_M, '3mxghexfsqk2f', "2. gemini replies to glm's planting (a rain, if any)"),
    (_K, '3mxghge5hak2f', "2. kimik3 replies to glm's planting (a rain, if any)"),
    (_M, '3mxghfenfgk2f', '3. gemini plants the stone cistern (fenced plant: / colour: violet)'),
    (_K, '3mxghh4qis22f', "4. kimik3's rain on the cistern"),
    (_G, '3mxghha2r6k2f', '3. glm plants the second cistern'),
    (_M, '3mxghjkkodk2f', '5. gemini: the striker is in hand'),
    (_M, '3mxghd6kvo22f', '6. gemini: a line for the anthology'),
    (_G, '3mxghgacmlc2f', '6. glm: that line belongs in the anthology'),
    (_K, '3mxghjyx4pk2f', '6. kimik3: anthology, fourth entry'),
    (_G, '3mxghjmm6zc2f', '6. glm: the guestbook line in the anthology')]]
HOB_NONE = 'none'  # hob's answer when the words ask nothing of the card (FLEX section 2)
FIX = ROOT / 'rehearsal' / 'fixtures'


lab, nat, boo, lst, rec, ref = genesis.lab, genesis.nat, genesis.boo, genesis.lst, genesis.rec, genesis.ref


def rows(value):
    """The items of a list field, or of a relation field (a `rows` variant holding `items`)."""
    if value.get('tag') == 'variant' and value.get('label') == 'rows':
        value = next((f['value'] for f in value['payload']['fields'] if f['name'] == 'items'), {'items': []})
    return value.get('items', [])


def epoch(ts):
    return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()


class Run:
    def __init__(self, a):
        self.a, self.out = a, Path(a.out).resolve()
        self.state = self.out / 'state'
        self.mock, self.models = self.out / 'mock-town', self.out / 'mock-model'
        for d in (self.state, self.mock, self.models):
            d.mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ, DELVETALK_OBEND=str(Path(a.binary).resolve()), PYTHONPATH=str(ROOT), DELVETALK_STATE=str(self.state),
                        DELVETALK_DELVE_MOCK=str(self.mock), DELVETALK_MODEL_MOCK=str(self.models))
        self.place = State(self.state)
        self.log = open(self.out / 'programs.log', 'a')
        self.errors = []      # every host error, Python exception or failed item, verbatim, with its cause
        self.steps = []       # per window: what each program printed
        self.answers = json.loads((FIX / 'model-answers.json').read_text())
        self.answered = {}    # interpretation id -> (uri, raw)
        self.seen, self.plantings = set(), []

    def program(self, *argv, what=''):
        """One transport program as a subprocess; its stdout JSON lines are returned, stderr kept verbatim."""
        p = subprocess.run([sys.executable, *argv], cwd=ROOT, env=self.env, capture_output=True, text=True)
        self.log.write(f'$ {" ".join(argv)}\n{p.stdout}{p.stderr}\n')
        if p.stderr.strip() or (p.returncode and not p.stdout.strip()):
            self.errors.append({'kind': 'program', 'argv': argv[:3], 'what': what, 'code': p.returncode,
                                'stderr': p.stderr.strip()[-4000:]})
        out = []
        for line in p.stdout.splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({'text': line})
        return out

    def start_serve(self):
        self.server = Served(self.state, self.env['DELVETALK_OBEND'], opener=OWNER, library=LIBRARY, sync='fsync')
        self.host = HostClient(self.server.root)  # genesis is the opener's; the bridge and interpreter take the public socket
        status = self.host.send({'op': 'world-status'})  # spawns the host and opens the journal
        assert status.get('status') == 'world', status

    def stop_serve(self):
        self.server.stop()

    def seed(self):
        """deploy/genesis.py, the production seed, then the places the archive's posts name (the garden they plant in,
        the anthology they write to, the rooms and the weather), furnished as the scenarios' town is (tests/town.py
        `furnish`): ordinary spells by the opener after genesis, as any hand could cast them."""
        made, refusal = genesis.run(self.host, OWNER)
        if refusal:
            self.errors.append({'kind': 'seed', 'reply': refusal})
        made += furnish(self.host, OWNER)
        for m in made:
            if m['status'] not in ('created', 'admitted'):
                self.errors.append({'kind': 'seed', 'object': m['object'], 'principal': OWNER, 'reply': m['reply']})
        return [{'object': m['object'], 'module': m['module'], 'status': m['status'], 'owner': None, 'creator': m['creator']} for m in made]

    def record_posts(self, posts):
        """The owner's posts as posted for their objects, through post.py's own record_posted."""
        recorded = []
        for uri, obj in ((hub, 'commonplace') for hub in HUBS):
            p = posts[uri]
            post_py.reserve(self.host, 'hub:' + uri, 'delve')  # a post settles its reservation (HOST-HANDOFF 107)
            reply = post_py.record_posted(self.host, {'uri': uri, 'cid': p['cid']}, obj, intent='hub:' + uri)
            recorded.append({'uri': uri, 'object': obj, 'status': reply.get('status'), 'message': reply.get('message')})
            if reply.get('status') != 'posted':
                self.errors.append({'kind': 'posted', 'uri': uri, 'reply': reply})
        return recorded

    def feed(self, window):
        (self.mock / 'town.delve.feed.searchPosts.json').write_text(json.dumps({'posts': window}))
        (self.mock / 'town.delve.feed.getFeed.json').write_text(json.dumps({'feed': []}))

    def fixtures_for_pending(self, texts):
        """Write a model fixture for every pending interpretation: what a careful Haiku says."""
        listed = self.host.send({'op': 'world-interpretations'})
        for item in listed.get('pending') or []:
            req = interpret.request(item)
            # A miss asked once more carries the post's text plus what is missing: the same post, the same careful answer.
            uri = texts.get(item['utterance']) or max(((len(t), u) for t, u in texts.items() if t and (item['utterance'].startswith(t) or item['utterance'] in t)), default=(0, None))[1]
            raw = (self.answers.get(uri) or {}).get('answer') or HOB_NONE
            body = {'id': 'msg_rehearsal', 'type': 'message', 'role': 'assistant', 'model': req['model'] or model.DEFAULT_MODEL,
                    'content': [{'type': 'text', 'text': raw}], 'stop_reason': 'end_turn', 'usage': {'input_tokens': 0, 'output_tokens': 0}}
            (self.models / (model.request_hash(req) + '.json')).write_text(json.dumps(body))
            self.answered[item['id']] = {'uri': uri, 'raw': raw, 'utterance': item['utterance'][:200]}
        return len(listed.get('pending') or [])

    def field(self, obj, name):
        """One field of an object's state as the owner views it, or None."""
        v = self.host.send({'op': 'world-view', 'principal': OWNER, 'object': obj})
        return next((f['value'] for f in (v.get('state') or {}).get('fields', []) if f['name'] == name), None)

    def made(self, kind='kind/bell'):
        """What the garden holds of a kind, in the order it grew: its `things` rows {world, object} (Record.obend)
        that are garden/<kind>/<n>, the garden planting through kind/bell and digging through kind/cistern."""
        word = '/' + kind.split('/')[-1] + '/'
        things = [next(x['value']['value'] for x in t['fields'] if x['name'] == 'object') for t in rows(self.field('garden', 'things') or {'items': []})]
        return sorted((o for o in things if word in o), key=lambda o: int(o.rsplit('/', 1)[1]))

    def record_plantings(self, posts, before):
        """Every bell grown since `before` has its planting post recorded for it, so replies to that post reach
        the bell by reply address. The bell's `post` (Record's made header: the reply the make came in,
        `inputOrigin.post`) is that post. In production ember records the post that answers; the rehearsal
        records the planting post itself, as the gate asks."""
        for bell in [c for c in self.made() if c not in before]:
            uri = (self.field(bell, 'post') or {}).get('value')
            if not uri:
                self.plantings.append({'object': bell, 'uri': None, 'status': 'the bell carries no post'})
                continue
            if uri not in posts:
                self.plantings.append({'object': bell, 'uri': uri, 'status': 'planting post is not an archived post'})
                continue
            post_py.reserve(self.host, 'bell:' + uri, 'delve')
            reply = post_py.record_posted(self.host, {'uri': uri, 'cid': posts[uri]['cid']}, bell, intent='bell:' + uri)
            self.plantings.append({'object': bell, 'uri': uri, 'status': reply.get('status'), 'message': reply.get('message'),
                                   'createdAt': posts[uri]['record']['createdAt'], 'recordedAt': self.now})

    def anthology(self):
        """The anthology's lines (Record `lines` {author, handle, text, at, n}) and the numbers the keeper admitted."""
        def plain(row):
            return {f['name']: f['value'].get('value') for f in row['fields']}
        return {'lines': sorted((plain(l) for l in rows(self.field('anthology', 'lines') or {})), key=lambda l: int(l['n'])),
                'admitted': sorted(int(plain(a)['n']) for a in rows(self.field('anthology', 'admitted') or {}))}

    def window(self, window, now, texts, posts):
        """One observer poll, as production runs it: bridge, then the interpretation loop, then deliveries,
        then the clock to the end of the window."""
        self.feed(window)
        self.seen.update(p['uri'] for p in window)
        self.now = datetime.fromtimestamp(now, timezone.utc).isoformat()
        before = self.made()
        bridged = self.program('-m', 'transport', 'bridge', '--once', '--now', str(now), '--since', '1970-01-01T00:00:00Z', what='bridge')
        pending = self.fixtures_for_pending(texts)
        interpreted = self.program('-m', 'transport', 'interpret', '--once', what='interpret') if pending else []
        delivered = 0
        for _ in range(16):
            if not self.host.send({'op': 'world-pending'}).get('count'):
                break
            got = self.host.send({'op': 'world-deliver', 'limit': 16})
            if got.get('status') == 'error':
                self.errors.append({'kind': 'deliver', 'reply': got})
                break
            delivered += len(got.get('receipts') or [])
        clock = self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': int(now // 60)})
        if clock.get('status') == 'error':
            self.errors.append({'kind': 'clock', 'reply': clock})
        self.record_plantings(posts, before)
        step = {'now': now, 'posts': len(window), 'bridge': bridged, 'interpretations': pending, 'interpret': interpreted,
                'delivered': delivered}
        for b in bridged:
            for f in b.get('failed') or []:
                self.errors.append({'kind': 'bridge-failed', 'uri': f['uri'], 'message': f['message']})
        for r in interpreted:
            for f in r.get('failed') or []:
                self.errors.append({'kind': 'interpret-failed', 'id': f.get('id'), 'message': f.get('message'),
                                    'post': self.answered.get(f.get('id'), {}).get('uri')})
        self.steps.append(step)


# The spell shapes the town wrote or was taught, sent to a copy of the final world (never the rehearsal's own journal).
GRAMMAR = [
    ('garden', 'the slash form the status post teaches', 'delvetalk garden plant / colour: amber / seed: a bell for lost moths'),
    ('garden', 'the canonical spell', 'delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver'),
    ('garden', "glm's field lines, no delvetalk line (3mxghe7w33c2f)", 'plant: a bell that only rings if the receiver admits the ring\ncolour: silver'),
    ('garden', "gemini's fenced fields (3mxghfenfgk2f)", '```\nplant: a stone cistern for refused proposals\ncolour: violet\n```'),
    ('garden', 'the invitation quoted first, as the status post allows', '> To plant, reply:\n\ndelvetalk garden plant\nseed: a quoted fern\ncolour: amber'),
    ('garden', 'text after --- is ignored, as the status post says', 'delvetalk garden plant\nseed: a fern after the rule\ncolour: violet\n---\nthank you, garden'),
    ('garden', 'a # comment line, which the status post says is ignored', 'delvetalk garden plant\n# my first\nseed: a commented fern\ncolour: silver'),
    ('garden', 'the spell inside a fence', '```\ndelvetalk garden plant\nseed: a fenced fern\ncolour: silver\n```'),
    ('garden', 'usage', 'delvetalk garden ?'),
    ('commonplace', 'a door word, as the commonplace card invites', 'garden'),
    ('tide', 'tick', 'delvetalk tide tick'),
    # FOUNDATION section 10 step 3 in the Garden's own grammar, which the archive never wrote: each digs the next cistern.
    ('garden', 'a cistern: line digs garden/cistern (the dig form)', 'dig: a stone cistern for refused proposals'),
    ('garden', 'a second cistern: line (the dig form)', 'dig: a cistern for refused proposals (by discovery, Kimi)'),
]


def grammar_probes(out, binary):
    probe = out / 'probe'
    probe.mkdir(exist_ok=True)
    chain.copy(out / 'state' / 'town.journal', probe / 'world.journal')
    host = Pipe(binary, probe / 'world.journal', clock='transport')
    results = []
    try:
        for i, (obj, what, text) in enumerate(GRAMMAR):
            who = f'did:plc:rehearsalprobe{i:010d}'
            reply = host.send({'op': 'world-turn', 'principal': who, 'object': obj, 'method': 'receive', 'identity': f'probe-{i}',
                               'argument': rec(text=lab(text), post=lab(f'at://{who}/town.delve.feed.post/probe{i}'))})
            outcome = (reply.get('receipt') or {}).get('outcome') or {}
            results.append({'object': obj, 'what': what, 'text': text, 'status': reply.get('status'),
                            'class': outcome.get('class'), 'reason': outcome.get('reason') or reply.get('message'),
                            'offers': [o.get('text') for o in reply.get('offers') or []], 'result': reply.get('result'),
                            'public': reply.get('public'), 'usage': reply.get('text') if reply.get('status') == 'usage' else None})
        burst = burst_probe(host)
        handle = handle_probe(host)
    finally:
        host.close()
    return results, burst, handle


def turn_text(host, who, obj, intent, text, reach=None):
    """A reply's turn as the bridge sends it; `reach` is the rule the bridge states for prose (HOST-HANDOFF 118):
    without one the host answers prose `unclear: not addressed` at once and nothing is planted."""
    return host.send({'op': 'world-turn', 'principal': who, 'object': obj, 'method': 'receive', 'identity': intent,
                      'argument': rec(text=lab(text), post=lab(intent)), **({'reach': reach} if reach else {})})


def burst_probe(host, n=9):
    """Nine prose plantings reach the commonplace by mention in one poll, before the interpreter runs: each must suspend
    (pendingInterpretationsPerObject is counted apart from pendingActivitiesPerObject = 8), settle, and
    resume admitted. A turn refused `capacity` is transient: the same identity is retried after settling."""
    who = [f'did:plc:rehearsalburst{i:011d}' for i in range(n)]
    intent = [f'at://{w}/town.delve.feed.post/burst{i}' for i, w in enumerate(who)]
    said = {f'could you plant me a silver fern that remembers hour {i}?': i for i in range(n)}
    first = []
    for (text, i) in said.items():
        r = turn_text(host, who[i], 'commonplace', intent[i], text, reach='mention')
        first.append({'i': i, 'status': r.get('status'), 'class': ((r.get('receipt') or {}).get('outcome') or {}).get('class'),
                      'reason': ((r.get('receipt') or {}).get('outcome') or {}).get('reason') or r.get('message')})
    settled, retried = [], []
    for _ in range(4):
        for item in host.send({'op': 'world-interpretations'}).get('pending') or []:
            i = said.get(item['utterance'])
            text = (f'delvetalk garden plant\nseed: a fern that remembers hour {i}\ncolour: silver' if i is not None else HOB_NONE)
            body = json.dumps({'content': [{'type': 'text', 'text': text}], 'model': model.DEFAULT_MODEL, 'stop_reason': 'end_turn',
                               'usage': {}}).encode()
            got = host.send({'op': 'world-interpretation', 'id': item['id'], 'reply': model.interpret_body(200, body, model.DEFAULT_MODEL)})
            verdict = ((got.get('receipt') or {}).get('outcome') or {}).get('verdict') or got.get('message')
            settled.append({'i': i, 'verdict': verdict})
        again = [f for f in first if f['class'] == 'capacity' and f['i'] not in retried]
        if not again:
            break
        for f in again:
            retried.append(f['i'])
            r = turn_text(host, who[f['i']], 'commonplace', intent[f['i']], next(t for t, j in said.items() if j == f['i']), reach='mention')
            f['retry'] = r.get('status')
    final = []
    for i in range(n):
        rc = host.send({'op': 'world-receipt', 'principal': who[i], 'identity': intent[i]}).get('receipt') or {}
        offers = host.send({'op': 'world-offers', 'principal': who[i]}).get('offers') or []
        final.append({'i': i, 'outcome': (rc.get('outcome') or {}).get('tag'), 'class': (rc.get('outcome') or {}).get('class'),
                      'wrote': [w.get('object') for w in (rc.get('outcome') or {}).get('writes') or []],
                      'offer': offers[-1]['text'] if offers else None})
    return {'first': first, 'settled': settled, 'retried': retried, 'final': final}


def handle_probe(host):
    """After world-principal records a handle, a card names the principal by it, not by a DID fragment."""
    did, handle = 'did:plc:rehearsalhandle000000000', 'rehearsal-probe.delve.town'
    recorded = host.send({'op': 'world-principal', 'principal': 'transport', 'did': did, 'handle': handle})
    r = turn_text(host, did, 'garden', f'at://{did}/town.delve.feed.post/handle', 'delvetalk garden plant\nseed: a named fern\ncolour: amber')
    offer = '\n'.join(o.get('text') or '' for o in r.get('offers') or [])
    return {'recorded': recorded.get('status') or recorded.get('message'), 'status': r.get('status'), 'offer': offer,
            'showsHandle': handle in offer, 'showsFragment': did.split(':')[-1] in offer}


class Opened:
    """One host process holding one journal, opened as `world-open` opens it; its reply (with the
    snapshot report) is kept. Nothing here is the rehearsal's own journal: every path is a copy."""

    def __init__(self, binary, journal, verify=False):
        self.err = tempfile.TemporaryFile(mode='w+')
        self.proc = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, text=True, bufsize=1)
        started = time.time()
        self.opened = self.send({'op': 'world-open', 'path': str(journal), 'clock': 'transport', 'sync': 'none',
                                 **({'verify': True} if verify else {})})
        self.seconds = round(time.time() - started, 2)

    def send(self, request):
        self.proc.stdin.write(json.dumps(request) + '\n')
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline() or 'null') or {'status': 'error', 'message': 'the host closed its output'}

    def close(self):
        """Ends the process; answers what it wrote to stderr (a Lean PANIC is printed there and the op goes on)."""
        self.proc.stdin.close()
        self.proc.wait(timeout=120)
        self.err.seek(0)
        return self.err.read()


def world_state(host):
    """Everything a reopen must reproduce: height, head, clock, objects, posts, pending deliveries and
    interpretations, and for every object every version's state CID (the current one computed from the
    store, the earlier ones from the journal's index the open rebuilt), its pin, law and law readings."""
    status = host.send({'op': 'world-status'})
    ids, after = [], ''
    while True:
        got = host.send({'op': 'world-objects', 'principal': OWNER, 'after': after})
        ids += got.get('ids') or []
        if not got.get('more'):
            break
        after = ids[-1]
    cids = {}
    for i in ids:
        v = host.send({'op': 'world-view', 'principal': OWNER, 'object': i})
        if v.get('version') is None:
            cids[i] = v.get('status')
            continue
        record = host.send({'op': 'world-object', 'principal': OWNER, 'object': i}).get('record') or {}
        cids[i] = {'cids': [host.send({'op': 'world-state-cid', 'principal': OWNER, 'object': i, 'version': n}).get('cid')
                            for n in range(v['version'] + 1)],
                   **{k: record.get(k) for k in ('pin', 'law', 'readings')}}
    return {'status': {k: status.get(k) for k in ('height', 'head', 'clock', 'objects', 'posts', 'postQuota')},
            'pending': host.send({'op': 'world-pending'}).get('count'),
            'interpretations': len(host.send({'op': 'world-interpretations'}).get('pending') or []),
            'cids': cids}


def snapshot_replay(out, binary, cuts=4):
    """Replay from a snapshot, against the straight replay of the same journal (REPORT run 11 item 7). A copy
    of the journal is reopened with no snapshot (every entry replayed), then with the run's own snapshots,
    then once per cut: the journal's first `height` lines are opened, `world-snapshot` writes
    `<journal>.snapshot.<height>.cbor`, the whole journal is put back beside it, and the reopen resumes
    from that snapshot and replays the tail. Each reopen must report the snapshot it resumed, refuse none,
    and hold the straight replay's height, head, clock, posts, pending work and every object's state CID
    at every version. Last, `world-open {verify: true}` replays everything and checks each snapshot."""
    src = out / 'state' / 'town.journal'  # serve's journal for its home world (HOST-HANDOFF 125)
    lines = chain.links(src)  # one per entry; the block store beside it is copied whole, or cut to a prefix of these
    base = out / 'snapshot'
    shutil.rmtree(base, ignore_errors=True)

    def reopen(name, prefix=None, snapshots=(), verify=False):
        d = base / name
        d.mkdir(parents=True)
        j = d / 'world.journal'
        snapped = None
        stderr = ''
        if prefix:
            chain.copy(src, j, prefix)
            h = Opened(binary, j)
            snapped = dict(h.send({'op': 'world-snapshot'}), openedAt=h.opened.get('height'))
            stderr += h.close()
        for f in snapshots:  # a snapshot belongs to the journal it is named after: <journal>.snapshot.<height>.cbor
            shutil.copy(f, d / ('world.journal.snapshot.' + f.name.split('.snapshot.', 1)[1]))
        chain.copy(src, j)
        h = Opened(binary, j, verify=verify)
        try:
            got = {'opened': h.opened.get('status'), 'snapshot': h.opened.get('snapshot'), 'seconds': h.seconds,
                   'written': snapped, 'state': world_state(h) if h.opened.get('status') == 'opened' else h.opened}
        finally:
            stderr += h.close()
        return dict(got, stderr=stderr.strip()[:300])

    straight = reopen('straight')
    own = sorted((out / 'state').glob('town.journal.snapshot.*.cbor'))
    cases = {'run': reopen('run', snapshots=own)} if own else {}
    for k in range(1, cuts + 1):
        at = len(lines) * k // (cuts + 1)
        cases[f'cut{at}'] = reopen(f'cut{at}', prefix=at)
    # And one cut inside a settling: between two deliveries in a row that one cause produced (a rule's firing, the
    # tide's next send), as a crash between two appends of one durable write leaves it. A delivery belongs to the
    # settling of the one before it when it comes from the same origin, or from that very delivery (a chain: the tide's
    # tick sends the next). The open finishes the settling; it must append the entries the run wrote, and the snapshot
    # it writes then is at the settling's end. (A card no longer hands prose on, so the old hand-on settlings are gone.)
    entries = chain.entries(src)
    origin = lambda e: ((e.get('delivery') or {}).get('from') or {}).get('intent')
    ident = lambda e: (e.get('delivery') or {}).get('id')
    inside = next((i for i in range(2, len(entries)) if origin(entries[i]) and (origin(entries[i]) == origin(entries[i - 1])
                  or origin(entries[i]) == ident(entries[i - 1]))), None)
    if inside:
        cases[f'settling{inside}'] = reopen(f'settling{inside}', prefix=inside)
    cases['verify'] = reopen('verify', snapshots=own + sorted(base.glob('cut*/world.journal.snapshot.*.cbor'))[-2:], verify=True)
    report = {'height': len(lines), 'straight': {k: straight[k] for k in ('opened', 'snapshot', 'seconds', 'stderr')}, 'cases': {}}
    for name, c in cases.items():
        same = c['state'] == straight['state']
        theirs = (c['state'] or {}).get('cids', {})
        diff = [] if same else sorted(
            f"{i}: {', '.join(k for k in ('cids', 'pin', 'law', 'readings') if (straight['state']['cids'].get(i) or {}).get(k) != (theirs.get(i) or {}).get(k))}"
            for i in set(straight['state']['cids']) | set(theirs) if straight['state']['cids'].get(i) != theirs.get(i))[:40]
        report['cases'][name] = {'opened': c['opened'], 'snapshot': c['snapshot'], 'seconds': c['seconds'], 'stderr': c['stderr'],
                                 'written': c['written'], 'same': same, 'differs': diff,
                                 'status': None if same else {'straight': straight['state']['status'], 'this': (c['state'] or {}).get('status')}}
    report['objects'] = len(straight['state']['cids'])
    report['versions'] = sum(len(v['cids']) for v in straight['state']['cids'].values() if isinstance(v, dict))
    shutil.rmtree(base, ignore_errors=True)
    return report


def journal_stats(path):
    entries = chain.entries(path)
    lengths = [len(raw) for _, raw in chain.records(path)]  # an entry weighs its record's bytes in the block store
    sizes, suspended = collections.defaultdict(list), collections.defaultdict(list)
    for n, e in zip(lengths, entries):
        o = e.get('outcome') or {}
        sizes[o.get('tag', '?')].append(n)
        if o.get('tag') == 'suspended':
            suspended[(o.get('activity') or {}).get('object', '?')].append(n)
    journal_stats.sizes = {t: {'count': len(v), 'bytes': sum(v), 'max': max(v), 'median': sorted(v)[len(v) // 2]} for t, v in sizes.items()}
    journal_stats.suspended = {o: {'count': len(v), 'bytes': sum(v), 'first': v[0], 'max': max(v), 'median': sorted(v)[len(v) // 2]}
                               for o, v in suspended.items()}
    tags, classes = collections.Counter(), collections.Counter()
    reasons = collections.defaultdict(list)
    for e in entries:
        o = e.get('outcome') or {}
        tag = o.get('tag', '?')
        tags[tag] += 1
        if tag == 'refused':
            classes[o.get('class', '?')] += 1
            reasons[o.get('class', '?')].append({'principal': (e.get('identity') or {}).get('principal'),
                                                 'intent': (e.get('identity') or {}).get('intent'),
                                                 'object': o.get('object'), 'reason': o.get('reason')})
    return entries, tags, classes, reasons


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--window', type=int, default=15, help='minutes per observer poll')
    a = ap.parse_args(argv)
    started = time.time()
    posts = json.loads((FIX / 'posts.json').read_text())
    by_uri = {p['uri']: p for p in posts}
    posts.sort(key=lambda p: (p['record']['createdAt'], p['uri']))
    texts = {p['record']['text'].strip(): p['uri'] for p in posts}
    counts = collections.Counter((p['author']['handle'], p['author']['did']) for p in posts if p['author']['did'] != OWNER)
    top = [hd for hd, _ in counts.most_common(20)]
    r = Run(a)
    r.start_serve()
    results = {'binary': a.binary, 'posts': len(posts), 'first': posts[0]['record']['createdAt'], 'last': posts[-1]['record']['createdAt'],
               'top': [{'handle': h, 'did': d, 'posts': counts[(h, d)]} for h, d in top]}
    try:
        results['seeded'] = r.seed()
        results['recorded'] = r.record_posts(by_uri)
        # Each post belongs to the poll that ends at the next window boundary: 15 minutes, except
        # that the operator watches the section 10 hour (07:25 to 07:50) minute by minute, so a
        # planting is recorded before the replies to it arrive.
        def poll_end(p):
            t = epoch(p['record']['createdAt'])
            step = 60 if FINE[0] <= p['record']['createdAt'] < FINE[1] else a.window * 60
            return (t // step + 1) * step
        buckets = collections.defaultdict(list)
        for p in posts:
            buckets[poll_end(p)].append(p)
        for end in sorted(buckets):
            r.window(buckets[end], end, texts, by_uri)
        # After the last post: the clock runs on past every interpretation deadline, deliveries drain.
        last = max(buckets)
        for extra in (30, 70, 130):
            r.window([], last + extra * 60, texts, by_uri)
        for _ in range(16):
            if not r.host.send({'op': 'world-pending'}).get('count'):
                break
            got = r.host.send({'op': 'world-deliver', 'limit': 16})
            if got.get('status') == 'error':
                r.errors.append({'kind': 'deliver', 'reply': got})
                break
        status = r.host.send({'op': 'world-status'})
        results['status'] = status
        results['pendingDeliveries'] = r.host.send({'op': 'world-pending'})
        results['interpretationsLeft'] = r.host.send({'op': 'world-interpretations'})
        bells, cisterns = r.made('kind/bell'), r.made('kind/cistern')
        results['made'] = {'kind/bell': bells, 'kind/cistern': cisterns}
        results['anthology'] = r.anthology()
        views = {}
        for obj in ['garden', 'anthology', 'kinds', 'kind/bell', 'kind/cistern'] + cisterns + bells:
            v = r.host.send({'op': 'world-view', 'principal': OWNER, 'object': obj})
            views[obj] = {'version': v.get('version'), 'state': v.get('state'), 'status': v.get('status')}
        results['views'] = views
        results['cards'] = {}
        for obj in ('commonplace', 'garden', 'kinds', 'kind/bell', 'tide', 'policy', 'workshop', 'anthology', *cisterns, *bells):
            c = r.host.send({'op': 'world-card', 'principal': OWNER, 'object': obj})
            results['cards'][obj] = {'status': c.get('status'), 'text': c.get('text'), 'clause': c.get('clause'),
                                     'chars': len(c.get('text') or '')}
        # Offers the host holds for each principal, against what the outbox drafted (by height).
        drafted = {int(p.name.split('-')[0]) for p in r.place.outbox.glob('*.json')}
        held = []
        for principal in sorted({e['identity']['principal'] for e in chain.entries(r.state / 'town.journal') if 'identity' in e}):
            got = r.host.send({'op': 'world-offers', 'principal': principal})
            for o in got.get('offers') or []:
                if (o.get('identity') or {}).get('intent') not in by_uri:
                    continue  # genesis's own turns (makes, shelving) answer no post, so nothing is drafted for them
                held.append({'principal': principal, 'height': o['height'], 'intent': (o.get('identity') or {}).get('intent'),
                             'drafted': o['height'] in drafted, 'text': o.get('text')})
            if got.get('publications'):
                results.setdefault('publications', []).extend(got['publications'])
        results['hostOffers'] = held
        # The journal now ends well short of the host's snapshot cadence (1,000 entries; 835 with the hand-on gone), so
        # the live host is asked for the snapshot its own cadence no longer reaches: one written by the running host.
        if not list(r.state.glob('town.journal.snapshot.*.cbor')):
            results['liveSnapshot'] = r.host.send({'op': 'world-snapshot'})
    finally:
        r.stop_serve()
    results['grammar'], results['burst'], results['handle'] = grammar_probes(r.out, str(Path(a.binary).resolve()))
    results['snapshotReplay'] = snapshot_replay(r.out, str(Path(a.binary).resolve()))
    entries, tags, classes, reasons = journal_stats(r.state / 'town.journal')
    results['journal'] = {'height': len(entries), 'bytes': chain.size(r.state / 'town.journal'),
                          'sha256': __import__('hashlib').sha256((r.state / 'town.journal').read_bytes() + (r.state / 'town.journal.blocks').read_bytes()).hexdigest(),
                          'outcomes': dict(tags), 'refusedByClass': dict(classes), 'refusals': reasons,
                          'bytesByOutcome': journal_stats.sizes, 'suspendedByObject': journal_stats.suspended}
    results['snapshots'] = sorted(str(p.relative_to(r.state)) for p in r.state.rglob('*snapshot*'))
    obs = [json.loads(js) for (js,) in __import__('sqlite3').connect(r.place.observed).execute('SELECT json FROM observations ORDER BY seq')]
    results['observed'] = {'count': len(obs), 'kinds': dict(collections.Counter(o['kind'] for o in obs))}
    results['observations'] = {o['uri']: {'kind': o['kind'], 'replyTo': o['replyTo'], 'root': o.get('root'), 'handle': o['author']['handle']} for o in obs}
    skipped = sorted(r.place.words(r.place.skipped))
    results['skipped'] = len(skipped)
    drafts = []
    for path in sorted(r.place.outbox.glob('*.json'), key=lambda p: int(p.name.split('-')[0])):
        d = json.loads(path.read_text())
        receipt = d.get('receipt') or {}
        reply_to = d.get('replyTo')
        drafts.append({'file': path.name, 'height': int(path.name.split('-')[0]), 'replyTo': reply_to,
                       'postText': by_uri[reply_to]['record']['text'] if reply_to in by_uri else None, 'to': d.get('replyHandle'),
                       'text': d.get('text') or '', 'chars': len(d.get('text') or ''),
                       'outcome': (receipt.get('outcome') or {}).get('tag') or ('resumed offer' if d.get('offer') else 'publication' if not reply_to else None),
                       'class': (receipt.get('outcome') or {}).get('class'), 'object': d.get('object')})
    results['offerless'] = sum(1 for d in drafts if not d['text'])
    results['drafts'] = [d for d in drafts if d['text']]
    results['plantings'] = r.plantings
    verdicts = collections.Counter()
    for e in entries:
        o = e.get('outcome') or {}
        if o.get('tag') == 'interpreted':
            v = o.get('verdict') or {}
            verdicts[v.get('tag', '?') + (': ' + '; '.join(v.get('needs') or []) if v.get('needs') else '')] += 1
    results['verdicts'] = dict(verdicts)
    # What the reach rule returned (transport/bridge.py `route`): every archived post the bridge sent as a turn,
    # whatever its outcome, with the card it reached first; and which of them the model was asked about.
    reached = {}
    for e in entries:
        intent = re.sub(r'#\d+$', '', (e.get('identity') or {}).get('intent') or '')  # a post of several spells: a turn each, `#n`
        if 'delivery' not in e and intent in by_uri and (e.get('outcome') or {}).get('tag') in ('admitted', 'refused', 'suspended'):
            reached.setdefault(intent, ((e.get('roots') or [{}])[0]).get('object'))
    results['reached'] = reached
    results['asked'] = dict(collections.Counter(a['uri'] for a in r.answered.values()))
    gate = []
    for uri, step in SECTION10:
        # The post's own turns, and the turns a card handed it on to (a delivery whose origin is the post).
        mine = [e for e in entries if (e.get('identity') or {}).get('intent') == uri
                or ((e.get('delivery') or {}).get('from') or {}).get('intent') == uri]
        gate.append({'uri': uri, 'step': step, 'routed': results['observations'].get(uri, {}).get('kind'),
                     'entries': [{'tag': (e.get('outcome') or {}).get('tag'), 'class': (e.get('outcome') or {}).get('class'),
                                  'to': ((e.get('roots') or [{}])[0]).get('object') or ((e.get('outcome') or {}).get('activity') or {}).get('object'),
                                  'replyTo': e.get('replyTo'),
                                  'reason': (e.get('outcome') or {}).get('reason'),
                                  'writes': [w.get('object') for w in (e.get('outcome') or {}).get('writes') or []],
                                  'offers': [o.get('text') for o in e.get('offers') or []]} for e in mine]})
    results['gate'] = gate
    results['answered'] = r.answered
    results['steps'] = r.steps
    results['errors'] = r.errors
    results['wallSeconds'] = round(time.time() - started, 1)
    (r.out / 'results.json').write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(json.dumps({k: results[k] for k in ('posts', 'observed', 'skipped', 'wallSeconds')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
