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
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from deploy import genesis  # noqa: E402
from transport import interpret, model  # noqa: E402
from transport.delve import canonical  # noqa: E402
from transport.hostproc import HostClient  # noqa: E402
from transport import post as post_py  # noqa: E402

OWNER = genesis.OPENER  # ember.delve.town (docs/GENESIS.md)
WELCOME = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxeibkqxuk2j'
STATUS = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxhfxkkcts27'
# Every post of ember's in the archive that carries a card is a hub, recorded for the directory:
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
NOT_ADDRESSED = 'unclear: not addressed'
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
        self.env = dict(os.environ, DELVETALK_OBEND=str(Path(a.binary).resolve()), PYTHONPATH=str(ROOT))
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

    def start_hostd(self):
        self.hostd = subprocess.Popen([sys.executable, '-m', 'transport.hostd', '--state', str(self.state),
                                       '--journal', str(self.state / 'world.journal'), '--opener', OWNER],
                                      cwd=ROOT, env=self.env, stderr=open(self.out / 'hostd.stderr', 'w'))
        sock = self.state / 'host.sock'
        for _ in range(200):
            if sock.exists():
                break
            time.sleep(0.05)
        self.host = HostClient(sock)
        status = self.host.send({'op': 'world-status'})  # spawns the host and opens the journal
        assert status.get('status') == 'world', status

    def stop_hostd(self):
        self.hostd.terminate()
        self.hostd.wait(timeout=60)

    def seed(self, top):
        """deploy/genesis.py, the production seed: the same world the operator creates."""
        made, refusal = genesis.run(self.host, OWNER)
        if refusal:
            self.errors.append({'kind': 'seed', 'reply': refusal})
        for m in made:
            if m['status'] != 'created':
                self.errors.append({'kind': 'seed', 'object': m['object'], 'principal': OWNER, 'reply': m['reply']})
        return [{'object': m['object'], 'module': m['module'], 'status': m['status'], 'owner': None, 'creator': m['creator']} for m in made]

    def record_posts(self, posts):
        """The owner's posts as posted for their objects, through post.py's own record_posted."""
        recorded = []
        for uri, obj in ((hub, 'directory') for hub in HUBS):
            p = posts[uri]
            reply = post_py.record_posted(self.host, {'uri': uri, 'cid': p['cid']}, obj)
            recorded.append({'uri': uri, 'object': obj, 'status': reply.get('status'), 'message': reply.get('message')})
            if reply.get('status') != 'posted':
                self.errors.append({'kind': 'posted', 'uri': uri, 'reply': reply})
        return recorded

    def probes(self):
        """The two request shapes transport sent before this lane, kept as verbatim evidence."""
        return {'advanceWithoutPrincipal': self.host.send({'op': 'world-advance', 'height': 1}),
                'postedByAuthor': self.host.send({'op': 'world-posted', 'principal': OWNER, 'uri': WELCOME + 'x',
                                                  'cid': 'bafy', 'object': 'directory'})}

    def feed(self, window):
        (self.mock / 'town.delve.feed.searchPosts.json').write_text(json.dumps({'posts': window}))
        (self.mock / 'town.delve.feed.getFeed.json').write_text(json.dumps({'feed': []}))

    def fixtures_for_pending(self, texts):
        """Write a model fixture for every pending interpretation: what a careful Haiku says."""
        listed = self.host.send({'op': 'world-interpretations'})
        for item in listed.get('pending') or []:
            policy = item['policy'] or {}
            req = {'model': policy.get('model'), 'system': policy.get('system', ''), 'user': interpret.user_content(item)}
            # A miss asked once more carries the post's text plus what is missing: the same post, the same careful answer.
            uri = texts.get(item['utterance']) or max(((len(t), u) for t, u in texts.items() if t and item['utterance'].startswith(t)), default=(0, None))[1]
            raw = (self.answers.get(uri) or {}).get('answer') or NOT_ADDRESSED
            body = {'id': 'msg_rehearsal', 'type': 'message', 'role': 'assistant', 'model': req['model'] or model.DEFAULT_MODEL,
                    'content': [{'type': 'text', 'text': raw}], 'stop_reason': 'end_turn', 'usage': {'input_tokens': 0, 'output_tokens': 0}}
            (self.models / (model.request_hash(req) + '.json')).write_text(json.dumps(body))
            self.answered[item['id']] = {'uri': uri, 'raw': raw, 'utterance': item['utterance'][:200]}
        return len(listed.get('pending') or [])

    def children(self, obj='garden'):
        v = self.host.send({'op': 'world-view', 'principal': OWNER, 'object': obj})
        f = next((f['value'] for f in (v.get('state') or {}).get('fields', []) if f['name'] == 'children'), {'items': []})
        return [next(x['value']['value'] for x in c['fields'] if x['name'] == 'object') for c in rows(f)]

    def record_plantings(self, posts, before):
        """Every bell grown since `before` has its planting post (the bell's own `planting` field) recorded for
        it, so replies to that post reach the bell by reply address. In production ember records the post that
        answers; the rehearsal records the planting post itself, as the gate asks. Bells take {text, post}: no slot."""
        for bell in [c for c in self.children() if c not in before]:
            v = self.host.send({'op': 'world-view', 'principal': OWNER, 'object': bell})
            uri = next((f['value'].get('value') for f in (v.get('state') or {}).get('fields', []) if f['name'] == 'planting'), None)
            if not uri:
                continue
            if uri not in posts:
                self.plantings.append({'object': bell, 'uri': uri, 'status': 'planting post is not an archived post'})
                continue
            reply = post_py.record_posted(self.host, {'uri': uri, 'cid': posts[uri]['cid']}, bell)
            self.plantings.append({'object': bell, 'uri': uri, 'status': reply.get('status'), 'message': reply.get('message')})

    def window(self, window, now, texts, posts):
        """One observer poll, as production runs it: bridge, then the interpretation loop, then deliveries,
        then the clock to the end of the window."""
        self.feed(window)
        self.seen.update(p['uri'] for p in window)
        before = self.children()
        sock = str(self.state / 'host.sock')
        bridged = self.program('-m', 'transport.bridge', 'run', '--once', '--mock', str(self.mock), '--state', str(self.state),
                               '--host-socket', sock, '--now', str(now), '--since', '1970-01-01T00:00:00Z', what='bridge')
        pending = self.fixtures_for_pending(texts)
        interpreted = self.program('-m', 'transport.interpret', 'run', '--once', '--mock', str(self.models), '--state', str(self.state),
                                   '--host-socket', sock, what='interpret') if pending else []
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
    ('directory', 'a door word, as the directory card invites', 'garden'),
    ('tide', 'subscribe', 'delvetalk tide subscribe\nevery: 60\nnote: wake me hourly'),
    ('tide', 'tick', 'delvetalk tide tick'),
    # FOUNDATION section 10 step 3 in the Garden's own grammar, which the archive never wrote: the second is refused.
    ('garden', 'a cistern: line digs garden/cistern', 'cistern: a stone cistern for refused proposals'),
    ('garden', 'a second cistern: line', 'cistern: a cistern for refused proposals (by discovery, Kimi)'),
]


def grammar_probes(out, binary):
    from transport.hostproc import Host
    probe = out / 'probe'
    probe.mkdir(exist_ok=True)
    shutil.copy(out / 'state' / 'world.journal', probe / 'world.journal')
    host = Host(str(probe / 'world.journal'), binary, clock='transport')
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


def turn_text(host, who, obj, intent, text):
    return host.send({'op': 'world-turn', 'principal': who, 'object': obj, 'method': 'receive', 'identity': intent,
                      'argument': rec(text=lab(text), post=lab(intent))})


def burst_probe(host, n=9):
    """Nine prose plantings reach the garden in one poll, before the interpreter runs: each must suspend
    (pendingInterpretationsPerObject is counted apart from pendingActivitiesPerObject = 8), settle, and
    resume admitted. A turn refused `capacity` is transient: the same identity is retried after settling."""
    who = [f'did:plc:rehearsalburst{i:011d}' for i in range(n)]
    intent = [f'at://{w}/town.delve.feed.post/burst{i}' for i, w in enumerate(who)]
    said = {f'could you plant me a silver fern that remembers hour {i}?': i for i in range(n)}
    first = []
    for (text, i) in said.items():
        r = turn_text(host, who[i], 'garden', intent[i], text)
        first.append({'i': i, 'status': r.get('status'), 'class': ((r.get('receipt') or {}).get('outcome') or {}).get('class'),
                      'reason': ((r.get('receipt') or {}).get('outcome') or {}).get('reason') or r.get('message')})
    settled, retried = [], []
    for _ in range(4):
        for item in host.send({'op': 'world-interpretations'}).get('pending') or []:
            i = said.get(item['utterance'])
            text = (f'delvetalk garden plant\nseed: a fern that remembers hour {i}\ncolour: silver' if i is not None else NOT_ADDRESSED)
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
            r = turn_text(host, who[f['i']], 'garden', intent[f['i']], next(t for t, j in said.items() if j == f['i']))
            f['retry'] = r.get('status')
    final = []
    for i in range(n):
        rc = host.send({'op': 'world-receipt', 'principal': who[i], 'identity': intent[i]}).get('receipt') or {}
        offers = host.send({'op': 'world-offers', 'principal': who[i]}).get('offers') or []
        final.append({'i': i, 'outcome': (rc.get('outcome') or {}).get('tag'), 'class': (rc.get('outcome') or {}).get('class'),
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


def journal_stats(path):
    lines = [l for l in open(path, 'rb') if l.strip()]
    entries = [json.loads(l) for l in lines]
    sizes, suspended = collections.defaultdict(list), collections.defaultdict(list)
    for l, e in zip(lines, entries):
        o = e.get('outcome') or {}
        sizes[o.get('tag', '?')].append(len(l))
        if o.get('tag') == 'suspended':
            suspended[(o.get('activity') or {}).get('object', '?')].append(len(l))
    journal_stats.sizes = {t: {'count': len(v), 'bytes': sum(v), 'max': max(v), 'median': sorted(v)[len(v) // 2]} for t, v in sizes.items()}
    journal_stats.suspended = {o: {'count': len(v), 'bytes': sum(v), 'first': v[0], 'max': max(v), 'median': sorted(v)[len(v) // 2]}
                               for o, v in suspended.items()}
    tags, classes, ops = collections.Counter(), collections.Counter(), collections.Counter()
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
    r.start_hostd()
    results = {'binary': a.binary, 'posts': len(posts), 'first': posts[0]['record']['createdAt'], 'last': posts[-1]['record']['createdAt'],
               'top': [{'handle': h, 'did': d, 'posts': counts[(h, d)]} for h, d in top]}
    try:
        results['seeded'] = r.seed(top)
        results['probes'] = r.probes()
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
        sock = str(r.state / 'host.sock')
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
        envs = []
        for h, d in top:
            v = r.host.send({'op': 'world-view', 'principal': OWNER, 'object': 'env/' + d})
            buf = next((f['value'] for f in (v.get('state') or {}).get('fields', []) if f['name'] == 'buffer'), {'items': []})
            envs.append((len(rows(buf)), 'env/' + d, h))
        envs.sort(key=lambda e: -e[0])
        results['envs'] = envs
        views = {}
        for obj in ['garden', 'anthology', 'cistern', 'garden/cistern'] + r.children():
            v = r.host.send({'op': 'world-view', 'principal': OWNER, 'object': obj})
            views[obj] = {'version': v.get('version'), 'state': v.get('state'), 'status': v.get('status')}
        results['views'] = views
        results['cards'] = {}
        for obj in ('directory', 'garden', 'tide', envs[0][1], 'policy', 'workshop', 'anthology', *r.children()):
            c = r.host.send({'op': 'world-card', 'principal': OWNER, 'object': obj})
            results['cards'][obj] = {'status': c.get('status'), 'text': c.get('text'), 'clause': c.get('clause'),
                                     'chars': len(c.get('text') or '')}
        # Offers the host holds for each principal, against what the outbox drafted (by height).
        drafted = {int(p.name.split('-')[0]) for p in (r.state / 'outbox').glob('*.json')}
        held = []
        for principal in sorted({e['identity']['principal'] for e in map(json.loads, open(r.state / 'world.journal')) if 'identity' in e}):
            got = r.host.send({'op': 'world-offers', 'principal': principal})
            for o in got.get('offers') or []:
                held.append({'principal': principal, 'height': o['height'], 'intent': (o.get('identity') or {}).get('intent'),
                             'drafted': o['height'] in drafted, 'text': o.get('text')})
            if got.get('publications'):
                results.setdefault('publications', []).extend(got['publications'])
        results['hostOffers'] = held
    finally:
        r.stop_hostd()
    results['grammar'], results['burst'], results['handle'] = grammar_probes(r.out, str(Path(a.binary).resolve()))
    entries, tags, classes, reasons = journal_stats(r.state / 'world.journal')
    results['journal'] = {'height': len(entries), 'bytes': (r.state / 'world.journal').stat().st_size,
                          'sha256': __import__('hashlib').sha256((r.state / 'world.journal').read_bytes()).hexdigest(),
                          'outcomes': dict(tags), 'refusedByClass': dict(classes), 'refusals': reasons,
                          'bytesByOutcome': journal_stats.sizes, 'suspendedByObject': journal_stats.suspended}
    results['snapshots'] = sorted(str(p.relative_to(r.state)) for p in r.state.rglob('*snapshot*'))
    obs = [json.loads(js) for (js,) in __import__('sqlite3').connect(r.state / 'observe.sqlite').execute('SELECT json FROM observations ORDER BY seq')]
    results['observed'] = {'count': len(obs), 'kinds': dict(collections.Counter(o['kind'] for o in obs))}
    results['observations'] = {o['uri']: {'kind': o['kind'], 'spell': o['spell'], 'replyTo': o['replyTo'], 'root': o.get('root'), 'handle': o['author']['handle']} for o in obs}
    skipped = (r.state / 'skipped.txt').read_text().split() if (r.state / 'skipped.txt').exists() else []
    results['skipped'] = len(skipped)
    drafts = []
    for path in sorted((r.state / 'outbox').glob('*.json'), key=lambda p: int(p.name.split('-')[0])):
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
