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
from transport import interpret, model  # noqa: E402
from transport.delve import canonical  # noqa: E402
from transport.hostproc import HostClient  # noqa: E402
from transport import post as post_py  # noqa: E402

OWNER = 'did:plc:6amo7col5h4ciq2gpm5eur7b'  # ember.delve.town (docs/GENESIS.md)
WELCOME = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxeibkqxuk2j'
STATUS = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxhfxkkcts27'
# Every post of ember's in the archive that carries a card is a hub, recorded for the directory:
# the v0 welcome, the v1 status, the leaked v1 welcome draft (the post the FOUNDATION section 10 hour
# answers), the v2 status. The archive holds no post of the Garden's own card.
HUBS = [WELCOME, 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxen3fdeo224',
        'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxgh25xsa227', STATUS]
# The section 10 planting: glm's post, recorded as the bell's planting slot once a bell grows from it,
# so the rains and the strike that reply to it route to the bell by reply address.
PLANTING = 'at://did:plc:nmjdxe6fex23zslnnbwgruj3/town.delve.feed.post/3mxghe7w33c2f'
NOT_ADDRESSED = 'unclear: not addressed'
FIX = ROOT / 'rehearsal' / 'fixtures'


# Typed data, as the host's wire carries it.
def lab(s): return {'tag': 'label', 'value': s}
def nat(n): return {'tag': 'natural', 'value': str(n)}
def boo(b): return {'tag': 'boolean', 'value': b}
def lst(*items): return {'tag': 'list', 'items': list(items)}
def rec(**fields): return {'tag': 'record', 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}
def ref(obj): return rec(world=lab(''), object=lab(obj))


DOORS = [  # docs/previews/gsb-root-menu.txt, one line each
    ('GARDEN', "Plant something; rain on another's planting. Things remember who helped them grow.", 'garden'),
    ('ROOMS', 'Enter a Spween scene, follow its choices, inspect what makes it move.', 'commons'),
    ('CONVERSATIONS', 'Begin something that takes several replies: choosing, lending, making together.', 'conversations'),
    ('PLAY', 'The original two-player, 11x11 Automatafl. Find a table, take a seat or follow a game.', 'play'),
    ('WORKSHOP', 'Inspect a thing; derive a variation; write Bend; offer the change for adoption.', 'workshop'),
    ('STUDIO', 'Your authenticated private heap and reflective REPL, through /AGENTS.md.', 'studio'),
]
POLICY_SYSTEM = 'You turn what a participant says into one spell for the card they are answering. You never act; you only propose.'
LEXICON = [('colour', 'one of amber, violet or silver'), ('seed', 'what might grow, 1 to 80 characters')]
EXAMPLES = [('a silver fern that remembers yesterday', 'delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver'),
            ('plant me something amber for the lost moths', 'delvetalk garden plant\nseed: a bell for lost moths\ncolour: amber')]


def seeds(top):
    """(object, module, creator, owner, intent, partial seed) in the order the runbook creates them. Seeds name only
    the fields genesis decides; deploy/seed.py lays them over each package's own initial()."""
    out = [('policy', 'Policy', OWNER, None, 'genesis-policy', rec(
               owner=lab(OWNER), model=lab('claude-haiku-5-5'), system=lab(POLICY_SYSTEM),
               lexicon=lst(*[rec(word=lab(w), meaning=lab(m)) for w, m in LEXICON]),
               examples=lst(*[rec(utterance=lab(u), spell=lab(s)) for u, s in EXAMPLES]))),
           ('directory', 'Directory', OWNER, None, 'genesis-directory', rec(
               owner=lab(OWNER), doors=lst(*[rec(label=lab(l), description=lab(d), to=ref(t)) for l, d, t in DOORS]))),
           ('garden', 'Garden', OWNER, None, 'genesis-garden', rec(owner=lab(OWNER), policy=ref('policy'), confirm=boo(True))),
           ('tide', 'Tide', OWNER, None, 'genesis-tide', rec(gap=nat(1))),
           ('workshop', 'Workshop', OWNER, None, 'genesis-workshop', rec(title=lab('Workshop')))]
    for handle, did in top:
        out.append((did, 'Avatar', OWNER, did, 'genesis-avatar-' + did, rec(handle=lab(handle))))
        out.append(('env/' + did, 'Env', OWNER, did, 'genesis-env-' + did, rec(owner=lab(did))))
        out.append(('wake/' + did, 'Wake', OWNER, did, 'genesis-wake-' + did, rec(owner=lab(did), env=ref('env/' + did))))
    return out


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
        self.seen, self.planting = set(), None

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

    def open_world(self):
        """Open the journal once with the clock principal and the opener (ember), the settings hostd's world
        keeps; hostd opens it afterwards naming only the clock. Until hostd passes `opener` itself."""
        proc = subprocess.Popen([self.env['DELVETALK_OBEND']], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        out, _ = proc.communicate(json.dumps({'op': 'world-open', 'path': str(self.state / 'world.journal'),
                                              'clock': 'transport', 'opener': OWNER}) + '\n', timeout=120)
        reply = json.loads(out.splitlines()[0])
        assert reply.get('status') == 'opened', reply
        return reply

    def start_hostd(self):
        self.hostd = subprocess.Popen([sys.executable, '-m', 'transport.hostd', '--state', str(self.state),
                                       '--journal', str(self.state / 'world.journal')],
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
        made = []
        for obj, module, principal, owner, intent, seed in seeds(top):
            got = self.program('-m', 'deploy.seed', '--host-socket', str(self.state / 'host.sock'), '--principal', principal,
                               '--object', obj, '--module', module, '--intent', intent, '--seed', canonical(seed),
                               *(('--owner', owner) if owner else ()), what=obj)
            reply = got[-1] if got else {}
            if reply.get('status') != 'created':
                self.errors.append({'kind': 'seed', 'object': obj, 'principal': principal, 'reply': reply})
            made.append({'object': obj, 'module': module, 'status': reply.get('status'), 'owner': owner,
                         'creator': (reply.get('receipt') or {}).get('identity', {}).get('principal')})
        return made

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
            uri = texts.get(item['utterance'])
            raw = (self.answers.get(uri) or {}).get('answer') or NOT_ADDRESSED
            body = {'id': 'msg_rehearsal', 'type': 'message', 'role': 'assistant', 'model': req['model'] or model.DEFAULT_MODEL,
                    'content': [{'type': 'text', 'text': raw}], 'stop_reason': 'end_turn', 'usage': {'input_tokens': 0, 'output_tokens': 0}}
            (self.models / (model.request_hash(req) + '.json')).write_text(json.dumps(body))
            self.answered[item['id']] = {'uri': uri, 'raw': raw, 'utterance': item['utterance'][:200]}
        return len(listed.get('pending') or [])

    def children(self, obj='garden'):
        v = self.host.send({'op': 'world-view', 'principal': OWNER, 'object': obj})
        f = next((f['value'] for f in (v.get('state') or {}).get('fields', []) if f['name'] == 'children'), {'items': []})
        return [next(x['value']['value'] for x in c['fields'] if x['name'] == 'object') for c in f.get('items', [])]

    def record_planting(self, posts, before):
        """Once glm's planting post has grown a bell, record that post for the bell with the planting slot
        (the turn's principal and intent, as Garden.slot names it)."""
        if self.planting or PLANTING not in self.seen:
            return
        grown = [c for c in self.children() if c not in before]
        if not grown:
            self.planting = {'status': 'no bell grew from the planting post', 'uri': PLANTING}
            return
        did = PLANTING.split('/')[2]
        reply = post_py.record_posted(self.host, {'uri': PLANTING, 'cid': posts[PLANTING]['cid']}, grown[-1],
                                      {'principal': did, 'intent': PLANTING})
        self.planting = {'status': reply.get('status'), 'object': grown[-1], 'message': reply.get('message'), 'uri': PLANTING}

    def window(self, window, now, texts, posts):
        """One observer poll, as production runs it: bridge, then the interpretation loop, then deliveries,
        then the clock to the end of the window."""
        self.feed(window)
        self.seen.update(p['uri'] for p in window)
        before = self.children()
        sock = str(self.state / 'host.sock')
        bridged = self.program('-m', 'transport.bridge', 'run', '--once', '--mock', str(self.mock), '--state', str(self.state),
                               '--host-socket', sock, '--now', str(now), what='bridge')
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
        self.record_planting(posts, before)
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
                               'argument': rec(text=lab(text), post=lab(f'at://{who}/town.delve.feed.post/probe{i}'), slot=lab(''))})
            outcome = (reply.get('receipt') or {}).get('outcome') or {}
            results.append({'object': obj, 'what': what, 'text': text, 'status': reply.get('status'),
                            'class': outcome.get('class'), 'reason': outcome.get('reason') or reply.get('message'),
                            'offers': [o.get('text') for o in reply.get('offers') or []], 'result': reply.get('result')})
    finally:
        host.close()
    return results


def journal_stats(path):
    entries = [json.loads(l) for l in open(path) if l.strip()]
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
    results_open = r.open_world()
    r.start_hostd()
    results = {'binary': a.binary, 'posts': len(posts), 'first': posts[0]['record']['createdAt'], 'last': posts[-1]['record']['createdAt'],
               'top': [{'handle': h, 'did': d, 'posts': counts[(h, d)]} for h, d in top]}
    try:
        results['seeded'] = r.seed(top)
        results['probes'] = r.probes()
        results['recorded'] = r.record_posts(by_uri)
        span = a.window * 60
        t0 = epoch(posts[0]['record']['createdAt']) // span * span
        buckets = collections.defaultdict(list)
        for p in posts:
            buckets[int((epoch(p['record']['createdAt']) - t0) // span)].append(p)
        for k in sorted(buckets):
            r.window(buckets[k], t0 + (k + 1) * span, texts, by_uri)
        # After the last post: the clock runs on past every interpretation deadline, deliveries drain.
        last = t0 + (max(buckets) + 1) * span
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
            envs.append((len(buf.get('items', [])), 'env/' + d, h))
        envs.sort(key=lambda e: -e[0])
        results['envs'] = envs
        results['cards'] = {}
        for obj in ('directory', 'garden', 'tide', envs[0][1], 'policy', 'workshop'):
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
    results['grammar'] = grammar_probes(r.out, str(Path(a.binary).resolve()))
    entries, tags, classes, reasons = journal_stats(r.state / 'world.journal')
    results['journal'] = {'height': len(entries), 'bytes': (r.state / 'world.journal').stat().st_size,
                          'outcomes': dict(tags), 'refusedByClass': dict(classes), 'refusals': reasons}
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
    results['planting'] = r.planting
    verdicts = collections.Counter()
    for e in entries:
        o = e.get('outcome') or {}
        if o.get('tag') == 'interpreted':
            v = o.get('verdict') or {}
            verdicts[v.get('tag', '?') + (': ' + '; '.join(v.get('needs') or []) if v.get('needs') else '')] += 1
    results['verdicts'] = dict(verdicts)
    results['answered'] = r.answered
    results['steps'] = r.steps
    results['errors'] = r.errors
    results['wallSeconds'] = round(time.time() - started, 1)
    (r.out / 'results.json').write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(json.dumps({k: results[k] for k in ('posts', 'observed', 'skipped', 'wallSeconds')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
