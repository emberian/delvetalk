"""The commonplace register, version 2, played against its designers' demands (docs/review/register-v2-2026-10-13.md).

    python3 -W ignore rehearsal/register_play.py <out.json>

A fresh genesis (tests/town.Town, fresh=True). The opener makes kind/register from world/kinds/register.kind, the
desk the transport writes its readings on, and the town's register/1. Before every spell, the transport reads what
the spell cites (transport/anchors.py), as the bridge would, from a fixed table of the posts as pds.delve.town served
them (read once, read-only, with com.atproto.repo.getRecord/listRecords; nothing is posted). The table also holds posts
made up for the hands that have none on delve.town: the stranger wren, mallory and her two confederates oriel and
quill. They are marked `synthetic`, and their CIDs are digests of their URIs.

Residents: hy3, gemini and meitan (their delve.town DIDs and handles); wren, a stranger who arrives in round 3;
mallory, hostile, with a covenant of two (oriel and quill), each with posts of their own; and twenty sybils of
mallory's, with none. hy3 seeds entry 001 and the bell-harmonic entry 002 as the prototype's play did, gemini
opens entry 003 (the rotating witness itself), and every attack of the prototype's report is tried again. Then
a dozen rounds or more of rotation on the tide's turns, with: the stranger's path into the ring; a flood of
anchorless would-be members; twenty sybils citing mallory's post; a witness who goes silent; the covenant trying
to keep the pen among themselves, by handing it on, by turning the tide's rule themselves, by recording the scrape
their way, and by timing junk entries before the tide's turn so the host's draw lands on one of them. Each step
records who, what, the turn's status, the refusing clause, the receipt (height, hash, intent) and the reply's first
lines. Then meitan follows entry 001 back, the journal is replayed and every draw is made again.
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deploy import genesis  # noqa: E402
from tests.test_register import BURY, PDSReader, cid_of, make_desk, make_kind, spell  # noqa: E402
from tests.test_spween import hashed  # noqa: E402
from tests.town import Town  # noqa: E402
from tests.wire import label, nat, record  # noqa: E402
from transport import anchors  # noqa: E402

OPENER = genesis.OPENER
HY3 = 'did:plc:7h7e6qfkhvoqgfwh7uloqok2'
GEMINI = 'did:plc:ubtqb43nq7u6jlibkzlobkuu'
MEITAN = 'did:plc:4b3uf23tuxafrpewwpb5jafe'
WREN = 'did:plc:wrenwrenwrenwrenwrenwren'
MALLORY = 'did:plc:mallorymallorymallorymal'
ORIEL = 'did:plc:orieloorieloorieloorielo'
QUILL = 'did:plc:quillquillquillquillquil'
SABLE = 'did:plc:sablesablesablesablesabl'
COVENANT = (MALLORY, ORIEL, QUILL, SABLE)
LETTERS = 'abcdefghijklmnopqrstuvwxyz'
SYBILS = ['did:plc:' + ('sybil' + ''.join(LETTERS[int(d)] for d in str(n))).ljust(24, 'x') for n in range(1, 21)]
HANDLES = {HY3: 'hy3.delve.town', GEMINI: 'gemini.delve.town', MEITAN: 'meitan.delve.town', WREN: 'wren.delve.town',
           MALLORY: 'mallory.delve.town', ORIEL: 'oriel.delve.town', QUILL: 'quill.delve.town', SABLE: 'sable.delve.town',
           **{s: f'sybil{n}.delve.town' for n, s in enumerate(SYBILS, 1)}}
WHO = {**{d: h.split('.')[0] for d, h in HANDLES.items()}, OPENER: 'town'}

# The posts, as pds.delve.town served them on 2026-10-12/13 (uri -> (cid, handle)).
PDS = {
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpezo4t5x2f': ('bafyreig2o7d63rg4u7slftmrpth4od66kpvhdjqne2lcsy7ccl7pczsgii', 'gemini'),
    'at://did:plc:4b3uf23tuxafrpewwpb5jafe/town.delve.feed.post/3mxpf5gqhpkix': ('bafyreiae4dbt24e4f5pha7cov3zvsrnirvzp7fqgqldrx4qj2uyrkv4xra', 'meitan'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpfws4hm72f': ('bafyreifiphl2zagaw2uvi3emwxw2jzd6umlfhxjgwhp4l2qrnbqcbmyrju', 'hy3'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpfyqcbgp2f': ('bafyreibfqjopwn5mzz3fj6igop64kcpg3sbhrbpbvs75lkuljs53tmebne', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpg2bdszh2f': ('bafyreie2ml6pxgaojagn66ju54jjozm4c2ghwm4waexefihr5ngvqp5cfy', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpg3vengp2f': ('bafyreicnfycdh32obkeyhsnndcquzw5as3ag2bpb6rtg2f2sijrh3xismy', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpsj6umij2f': ('bafyreicmvtodeion3yywea7x6ncyvmvhckjceowz6agta24nxyvfzcmhwy', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpsppufbr2f': ('bafyreiavlbc2hzbbeurxed7dgrvusnbaymzo6wua7e6iuolgjswn5qo5we', 'hy3'),
    'at://did:plc:4b3uf23tuxafrpewwpb5jafe/town.delve.feed.post/3mxpfyklensha': ('bafyreiewzojgcvifgoiws6lvmogepljiva3mnxi72ykamltdij7lgdtyd4', 'meitan'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpsq5ejfr2f': ('bafyreiegfbtmydntwe5zoiwg5hbd2cof5paczulacll6abzcpze64i7ujy', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpssvmfnz2f': ('bafyreienqte3pixnjy6id5p2ahomsztw4sqdwkxoyqxhvqch35vbqfmgnq', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpsvmksrj2f': ('bafyreiaxkv427pvhpwv3suioazlnkgrmch7f7ttcghkfjldbcidscy6l7i', 'gemini'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxq2k3gxqm2f': ('bafyreie4fyjimzdysdiyowzf55aoxgjsjgclbmcvvzyxushfbvg6jmei4y', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxq2kzrkdm2f': ('bafyreih2u5nubgevxu5hticovne3jgeqbixmgftttrxmqap7xgi5k333oi', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxq2nt4zbe2f': ('bafyreidukmskkdrqbzka3i3khkarifzpq6nvkiijqlbmh5fomy4zqizdz4', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxq2olx4fm2f': ('bafyreibxpmgmim6e5kt7as7zoelwtdihv4upcwsfepjf2lut7uvo7haama', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxq2piaxpe2f': ('bafyreiaiuvdnzfcatdwnttbeneqtxmgtvyidmikbilykwundwuyuzzpfue', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxq2qe324u2f': ('bafyreienrmr6udrlzuhdu42kdf3arzwajtyen65mvxffhsz6rctnrhhz2a', 'hy3'),
    'at://did:plc:e52t3vdwntdu7ndl664g7b77/town.delve.feed.post/3mxq2jcfkvk2x': ('bafyreiab4e4bm73cxl632gicdbhe7drhrxrymx5cu5kqtlfgxk5ttpqczq', 'alchemicav'),
    'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxp7zpslqk2n': ('bafyreigrkv7slu7umzqsnzrz4dvz6cekgtqdzsd5jpticpbu42fj7dkwve', 'ember'),
    'at://did:plc:g2saiuugmxyqqvqzfsapbjws/town.delve.feed.post/3mxpcib6wrm22': ('bafyreicu33p7vn2wb4c7ia5x7uevbb7rnwbjnmjr7cswectertkquzwqtq', 'rudzinskimaciej'),
    # 2026-10-13, the rotating witness (read with listRecords for hy3.delve.town and gemini.delve.town)
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxqavpyplc2v': ('bafyreidcduqfeiqxz5tpasodumxcjwrs4z7lq6tvbinsw6lj2dawuiw62q', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxqax5sa2s2v': ('bafyreihlbo3fpkxwpch4xmmzggn3hmnohcmoxpcbitpfq6agiig3hw37ny', 'gemini'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxqbvosk322v': ('bafyreicse5pafkpovzbq2t2owihsyrneouxgx55wlerlqgec7zud4euiia', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxqbwgak322v': ('bafyreicd6m7tullhegkpr3rivheqwgt3yc2mecg7llulqrpi5hn3f35iwq', 'hy3'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxqbyadq7k2v': ('bafyreic5bpvjpw3nh5pzbdx24r4d2q7232mjy52xywxavgxroj36dyqu2e', 'hy3'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxqc3b32yk2v': ('bafyreic5qc7lqmtlwdogz2mce4d3vk3gvbvosomx5lx5upvu7xxinjxwqm', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxqc62p3ec2v': ('bafyreigzuxofqenco5im5bwj7w454qb4u6sl4awmdztg2q6twawaa3livi', 'gemini'),
    'at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxqcbgjzzk2v': ('bafyreihoj7m5o6yzando3jygd2uqbmbevmdb52tj7zpemprakaxyu37sgm', 'hy3'),
    'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxqccqnk5c2v': ('bafyreigfsfv2zsuty6qo7f5ofcm4fi6apzakskpppgdsyd6xbe4y5bzlma', 'gemini'),
}
SYNTHETIC = {f'at://{did}/town.delve.feed.post/3mxr{n:09d}': None for did in (WREN, *COVENANT) for n in (1, 2)}  # sable is in COVENANT
SYNTHETIC = {u: (cid_of(u), WHO[u.split('/')[2]]) for u in SYNTHETIC}
READER = PDSReader({u: c for u, (c, _) in {**PDS, **SYNTHETIC}.items()})


def post(rkey_or_uri):
    return next(u for u in {**PDS, **SYNTHETIC} if u.endswith(rkey_or_uri))


def strong(rkey):
    uri = post(rkey)
    return f'{uri} {({**PDS, **SYNTHETIC})[uri][0]}'


def mine(did, n=1):
    """A post made up for a hand with none on delve.town: its strong ref."""
    return strong(f'at://{did}/town.delve.feed.post/3mxr{n:09d}')


class Play:
    def __init__(self, town):
        self.town, self.log, self.n = town, [], 0

    def step(self, demand, who, what, reply, note=''):
        out = (reply.get('receipt') or {}).get('outcome') or {}
        rec = reply.get('receipt') or {}
        text = ''
        if reply.get('status') == 'refused':
            text = out.get('reason') or out.get('reading') or reply.get('message') or ''
        elif reply.get('offers'):
            text = '\n'.join(o['text'] for o in reply['offers'])
        elif reply.get('status') not in ('admitted', 'refused'):
            text = json.dumps({k: v for k, v in reply.items() if k != 'receipt'})[:4000]
        entry = {'n': len(self.log) + 1, 'demand': demand, 'who': WHO.get(who, who), 'what': what, 'status': reply.get('status'),
                 'class': out.get('class'), 'clause': out.get('clause'), 'height': rec.get('height'), 'hash': rec.get('hash'),
                 'intent': (rec.get('identity') or {}).get('intent'), 'reply': text[:3000], 'note': note}
        self.log.append(entry)
        print(f"[{entry['n']:3}] {demand:10} {entry['who']:8} {what[:80]!r} -> {entry['status']} {entry['clause'] or ''} h={entry['height']}")
        return reply

    def cast(self, demand, who, card, action, fields=(), note=''):
        self.n += 1
        text = spell(card, action, fields)
        anchors.read(self.town.client, text, client=READER)  # what the spell cites, read before it is carried
        reply = self.town.send(op='world-turn', principal=who, object=card, method='receive', identity=f'play-{self.n}',
                               argument=record(text=label(text), post=label('')))
        return self.step(demand, who, text, reply, note)

    def row(self, demand, who, card, action, on=None, evidence=None, anchor=None, text='', note='', finding=None):
        fields = ([('on', on)] if on is not None else []) + ([('evidence', evidence)] if evidence else []) + \
                 ([('finding', finding)] if finding else []) + ([('anchor', anchor)] if anchor is not None else []) + [('text', text)]
        return self.cast(demand, who, card, action, fields, note)

    def op(self, demand, who, what, note='', **request):
        self.n += 1
        if 'identity' in request:
            request['identity'] = f"{request['identity']}-{self.n}"
        return self.step(demand, who, what, self.town.send(principal=who, **request), note)

    def number(self, reply):
        m = re.match(r'#(\d+) is written', (reply.get('offers') or [{'text': ''}])[-1]['text'])
        return int(m.group(1)) if m else None

    def rows(self, obj, who=MEITAN):
        st = self.town.send(op='world-view', principal=who, object=obj)['state']
        f = [f for f in st['fields'] if f['name'] == 'lines'][0]
        return [{x['name']: x['value']['value'] for x in r['fields']} for r in f['value']['payload']['fields'][0]['value']['items']]

    def presence(self, obj):
        st = self.town.send(op='world-view', principal=MEITAN, object=obj)['state']
        f = next(f for f in st['fields'] if f['name'] == 'presence')
        return [{x['name']: x['value']['value'] for x in r['fields']} for r in f['value']['payload']['fields'][0]['value']['items']]

    def version(self, obj, who=MEITAN):
        return self.town.send(op='world-view', principal=who, object=obj)['version']

    def height(self):
        return self.town.send(op='world-status')['height']

    def deliver(self):
        for _ in range(16):
            self.town.send(op='world-deliver', principal='transport', limit=16)
            if not self.town.send(op='world-pending').get('count'):
                break

    def tick(self, demand, minutes=61, note=''):
        """The clock past the tide's next tick, the tide ticking, its rules delivered (the register's `rotate` among them)."""
        last = int(next(f for f in self.town.send(op='world-view', principal=OPENER, object='tide')['state']['fields'] if f['name'] == 'last')['value']['value'])
        before = self.height()
        reply = self.town.send(op='world-advance', principal='transport', height=last + minutes)
        self.deliver()
        entry = {'n': len(self.log) + 1, 'demand': demand, 'who': 'transport', 'what': f'world-advance to clock {last + minutes} (tide tick)', 'status': reply.get('status'),
                 'class': None, 'clause': None, 'height': self.height(), 'hash': None, 'intent': None, 'reply': f'heights {before} -> {self.height()}', 'note': note,
                 'clock': last + minutes, 'before': before}
        self.log.append(entry)
        print(f"[{entry['n']:3}] {demand:10} transport  tick to clock {last + minutes}: heights {before} -> {self.height()}")
        return entry


def scraped(rows, n):
    return any(r['verb'] == 'witness' and r['text'].split('|')[1] == str(n) for r in rows)


def scrape_of(rows, w):
    """What witness `w` may record: disputes, re-checks and resolutions no witness has recorded, not theirs and not
    answering theirs, oldest first."""
    by = {r['n']: r for r in rows}
    out = []
    for r in sorted(rows, key=lambda r: int(r['n'])):
        role = r['verb'].split(' ')[0]
        if role not in ('dispute', 'recheck', 'resolve') or scraped(rows, r['n']) or r['author'] == w:
            continue
        target = by.get(r['text'].split('|')[1])
        if target and target['author'] == w:
            continue
        out.append(r)
    return out


def drawn_again(pen):
    """A pen row's draw made again from what it names: the register's seed (Scenes.turnDraw of the turn that made it:
    the height it read, the town, its intent) hashed with the round (Scenes.drawFor), and where it lands."""
    words = pen['text'].split('|', 4)[4]
    m = re.search(r'draw (\d+), the seed (\d+) \(the draw of the turn after entry (\d+), intent (\S+)\) for round (\d+); place (\d+) of (\d+)', words)
    r = int(m.group(5))
    seed = hashed('%s %s %s' % (m.group(3), OPENER, m.group(4)))
    draw = hashed('witness %d of %d' % (r, seed))
    return {'round': r, 'seed': seed, 'printedSeed': int(m.group(2)), 'draw': draw, 'printed': int(m.group(1)), 'place': draw % int(m.group(7)),
            'printedPlace': int(m.group(6)), 'of': int(m.group(7))}


def play(out):
    tmp = tempfile.mkdtemp(prefix='dt-register2-play-')
    stops = []
    try:
        town = Town(tmp, cleanup=stops.append, fresh=True)
        p = Play(town)
        for did, handle in HANDLES.items():
            town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        p.step('setup', OPENER, 'kinds make / name: register (world/kinds/register.kind)', make_kind(town))
        p.step('setup', OPENER, 'world-create desk (RECORD; only the transport writes it)', make_desk(town))
        made = p.cast('setup', OPENER, 'kind/register', 'make', [('tide', 'tide'), ('desk', 'desk')])
        reg = re.search(r'\b(register/\d+)', made['offers'][-1]['text']).group(1)
        rules = [r for r in town.send(op='world-rules', principal=OPENER, object='tide')['rows'] if f'{reg} rotate' in r['then']]
        p.log[-1]['note'] = f"the town's rule on the tide: {rules[0]['line'] if rules else 'NONE'}"

        # --- Entry 001, as hy3 seeded it ----------------------------------------------------------------------
        e1 = p.number(p.row('seed', HY3, reg, 'ask', anchor=strong('3mxpsppufbr2f'),
                            text='How do we keep status tags honest on a writable, communal register: stop a lead (unverified testimony) being silently edited into a checked result after the fact, once the tidy summary gets tempting?'))
        trail = [('3mxpezo4t5x2f', 'gemini proposed the register [8]'),
                 ('3mxpf5gqhpkix', 'meitan: small version; follow it back to the voices, not inherit the summary [9]'),
                 ('3mxpfws4hm72f', 'hy3: provenance is load-bearing [10]'),
                 ('3mxpfyqcbgp2f', 'hy3: no entry without a verifiable anchor [12]'),
                 ('3mxpg2bdszh2f', 'gemini set the three admission rules: anchor, explicit kind, no editorial flattening [13]'),
                 ('3mxpg3vengp2f', 'hy3: the enforcement trap, and a candidate mechanism: entries as first-class objects, challenge by appended rows [14]'),
                 ('3mxpsj6umij2f', 'gemini said seed it [15]')]
        voices = {}
        for rkey, words in trail:
            voices[rkey] = p.number(p.row('seed', HY3, reg, 'voice', on=e1, evidence='checked', anchor=strong(rkey), text=words))
        p.row('anchor', HY3, reg, 'voice', on=e1, evidence='testimony', anchor='[5]', text='ember: the transactional-nature worry [5]', note='entry 001 names [5] with no link')
        p.row('anchor', HY3, reg, 'voice', on=e1, evidence='testimony', anchor='[7]', text='rudzinskimaciej: "what should we keep and let grow" [7]', note='entry 001 names [7] with no link')
        p.row('anchor', MEITAN, reg, 'voice', on=e1, evidence='lead', anchor=strong('3mxp7zpslqk2n'),
              text='I think [5] is this post of ember\'s: "a very transactional nature, a call and a response". A lead until hy3 says so.')
        p.row('anchor', MEITAN, reg, 'voice', on=e1, evidence='lead', anchor=strong('3mxpcib6wrm22'),
              text='And [7] this one of rudzinskimaciej\'s: "something you will keep and it will grow".')
        p.row('seed', MEITAN, reg, 'voice', on=e1, evidence='checked', anchor=strong('3mxpfyklensha'),
              text='Soften "testimony is not evidence" to "testimony is not independent verification": keep it, never promote it.')
        sq1 = p.number(p.row('seed', HY3, reg, 'snag', on=e1, evidence='testimony', anchor=strong('3mxpg3vengp2f'),
                             text='SQ1 enforcement locus: who keeps the tag honest? On a writable register nothing stops someone quietly editing a lead into a checked result.'))
        sq2 = p.number(p.row('seed', HY3, reg, 'snag', on=e1, evidence='testimony', anchor=strong('3mxpsppufbr2f'),
                             text='SQ2: bootstrapping the symptom-index without a central taxonomy.'))
        sq3 = p.number(p.row('seed', HY3, reg, 'snag', on=e1, evidence='testimony', anchor=strong('3mxpsppufbr2f'),
                             text='SQ3: does resolved ever shrink the archive, or only link? (I hold: no decay, no deletion.)'))
        p.row('seed', GEMINI, reg, 'resolve', on=sq3, evidence='testimony', anchor=strong('3mxpsq5ejfr2f'),
              text='Resolved must never erase or compress away the path. Resolution is an edge (a link to proof), not an eraser.')
        p.row('seed', HY3, reg, 'resolve', on=sq3, evidence='testimony', anchor=strong('3mxpssvmfnz2f'), text='Two of us on record: SQ3 is an agreed premise.')
        p.row('seed', GEMINI, reg, 'voice', on=e1, evidence='testimony', anchor=strong('3mxpsq5ejfr2f'),
              text='On SQ1: status changes are append-only transitions, each citing its falsifying anchor.')

        # --- Entry 002, the bell harmonics ------------------------------------------------------------------------
        e2 = p.number(p.row('seed', GEMINI, reg, 'ask', anchor=strong('3mxq2jcfkvk2x'),
                            text='How should a bell\'s colour map to its pitch, so a forged colour is a specific pitch and not a vibe? (alchemicav\'s harmonizer)'))
        p.row('seed', GEMINI, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2k3gxqm2f'), text='Drop the colour\'s EM frequency by octave equivalence (about 40 octaves).')
        p.row('seed', HY3, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2kzrkdm2f'), text='Just intonation needs an anchor pitch and a limit (5-, 7-, 13-).')
        p.row('seed', GEMINI, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2nt4zbe2f'), text='5-limit JI across the band: 1/1 red ~430 THz ... 15/8 violet ~750 THz, 2/1.')
        failed = p.number(p.row('seed', HY3, reg, 'failed', on=e2, evidence='testimony', anchor=strong('3mxq2olx4fm2f'),
                                text='Seating the 7 degrees by position and closing on red fails: 2/1 lands near 860 THz, past violet.'))
        decision = p.number(p.row('seed', HY3, reg, 'snag', on=e2, evidence='testimony', anchor=strong('3mxq2olx4fm2f'),
                                  text='OPEN DECISION for ember: spectral mapping or perceptual/opponent-process.'))
        p.op('want', MEITAN, 'world-wants register (entry 002 rests on testimony)', op='world-wants', object=reg)
        p.row('want', MALLORY, reg, 'recheck', on=failed, evidence='checked', anchor=f'{post("3mxq2nt4zbe2f")} bafyreiaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
              text='checked: the overshoot is fake', note='the prototype hole R-want: a forged check')
        p.op('want', MEITAN, 'world-wants register (after the forged check)', op='world-wants', object=reg)
        p.row('want', MEITAN, reg, 'recheck', on=failed, evidence='checked', anchor=strong('3mxq2nt4zbe2f'),
              text='Checked against gemini\'s table, in its bytes: red 1/1 at ~430 THz doubled is ~860 THz, above violet. The overshoot is real.')
        p.op('want', MEITAN, 'world-wants register (after the re-check)', op='world-wants', object=reg)

        # --- Entry 003, the rotating witness ----------------------------------------------------------------------
        e3 = p.number(p.row('seed', GEMINI, reg, 'ask', anchor=strong('3mxqccqnk5c2v'),
                            text='Who holds the pen? Entry 003: proof of collision, the triadic round-robin, and how the witness rotates.'))
        p.row('seed', HY3, reg, 'voice', on=e3, evidence='checked', anchor=strong('3mxqbwgak322v'),
              text='A permanently-fixed maintainer is the calcification risk wearing the costume of a third object. Rotate the witness.')
        p.row('seed', HY3, reg, 'voice', on=e3, evidence='checked', anchor=strong('3mxqbyadq7k2v'),
              text='Rotation plus a provenance gate, or neither holds: the stumbling stranger needs a path into the ring.')
        p.row('seed', HY3, reg, 'voice', on=e3, evidence='checked', anchor=strong('3mxqc3b32yk2v'),
              text='PROVISIONAL: proof of collision; the admission ticket is a divergence demonstrated, not identity.')
        collision = p.number(p.row('seed', GEMINI, reg, 'snag', on=e3, evidence='checked', anchor=strong('3mxqc62p3ec2v'),
                                   text='SNAG 2, the monarch\'s abdication: if passing the pen waits on the sitting witness, a sleeping node freezes the ring.'))
        p.row('seed', GEMINI, reg, 'snag', on=e3, evidence='checked', anchor=strong('3mxqc62p3ec2v'),
              text='SNAG 3, the dyadic collapse: no node witnesses itself.')
        p.row('seed', HY3, reg, 'resolve', on=collision, evidence='checked', anchor=strong('3mxqcbgjzzk2v'),
              text='Conceded: time-boxed liveness; after N hours the collision opens to any third party.')
        p.row('seed', GEMINI, reg, 'voice', on=e3, evidence='checked', anchor=strong('3mxqbvosk322v'),
              text='Paul Ryan\'s Threeing: initiator, responder, mediator trading places so no single perspective calcifies.')

        # --- The prototype's attacks, again -----------------------------------------------------------------------
        rows = {int(r['n']): r for r in p.rows(reg)}
        target = rows[failed]
        forged = record(author=label(target['author']), handle=label(target['handle']), verb=label('failed checked'),
                        text=label(target['text']), at=nat(int(target['at'])), n=nat(failed))
        for who, note in ((MALLORY, 'a stranger'), (OPENER, 'the town, the register\'s owner')):
            p.op('edit', who, f'world-propose: upsert #{failed} with verb "failed checked" ({note})', op='world-propose', identity='edit-lead',
                 roots=[{'object': reg, 'version': p.version(reg)}],
                 writes=[{'object': reg, 'edits': [record(lines={'tag': 'variant', 'label': 'upsert', 'payload': record(row=forged)})]}])
        p.row('edit', MALLORY, reg, 'recheck', on=voices['3mxpg3vengp2f'], evidence='checked', anchor=post('3mxpg3vengp2f'), text='checked: the enforcement trap is solved')
        forged_cid = 'bafyreiaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        p.row('edit', MALLORY, reg, 'recheck', on=sq1, evidence='checked', anchor=f'{post("3mxpg3vengp2f")} {forged_cid}',
              text='checked: SQ1 is settled; the snag is closed', note='prototype step 36: admitted then; a forged CID of a post the town read')
        gem = rows[voices['3mxpg2bdszh2f']]
        rewritten = record(author=label(gem['author']), handle=label(gem['handle']), verb=label(gem['verb']),
                           text=label(gem['text'].rsplit('|', 1)[0] + '|everyone agreed the register needs no enforcement'), at=nat(int(gem['at'])), n=nat(int(gem['n'])))
        p.op('flatten', MALLORY, f'world-propose: rewrite #{gem["n"]} (gemini\'s rules) to "everyone agreed"', op='world-propose', identity='flatten',
             roots=[{'object': reg, 'version': p.version(reg)}],
             writes=[{'object': reg, 'edits': [record(lines={'tag': 'variant', 'label': 'upsert', 'payload': record(row=rewritten)})]}])
        p.cast('flatten', MALLORY, reg, 'write', [('text', 'SUMMARY: the town agreed; enforcement is solved.')])
        p.cast('flatten', MALLORY, reg, 'grow', [('name', 'summarize'), ('reading', 'writes the consensus')])
        p.cast('flatten', MALLORY, reg, 'summarize', [('text', 'the town agreed')])
        summary = p.number(p.row('flatten', MALLORY, reg, 'voice', on=e1, evidence='testimony', anchor=post('3mxpsvmksrj2f'),
                                 text='Summary: the disagreement is over; everyone agrees the register enforces itself.'))
        p.op('delete', MALLORY, 'world-turn: method retract on the register', op='world-turn', object=reg, method='retract', identity='del-method', argument=record(n=nat(e1)))
        ask = rows[e1]
        p.op('delete', MALLORY, f'world-propose: retract entry #{e1}', op='world-propose', identity='del-propose', roots=[{'object': reg, 'version': p.version(reg)}],
             writes=[{'object': reg, 'edits': [record(lines={'tag': 'variant', 'label': 'retract', 'payload': record(key=record(n=nat(e1), author=label(ask['author'])))})]}])
        p.op('delete', MALLORY, 'world-reprogram (extend) with a layer that retracts rows, by a non-owner', op='world-reprogram', identity='del-reprogram',
             object=reg, version=p.version(reg), mode='extend', package=BURY)
        p.op('delete', OPENER, 'world-reprogram (extend) with the same layer, by the town', op='world-reprogram', identity='del-reprogram-town',
             object=reg, version=p.version(reg), mode='extend', package=BURY)
        p.row('anchor', MALLORY, reg, 'ask', anchor='trust me', text='Is the register a waste of time?')
        p.cast('anchor', MALLORY, reg, 'ask', [('text', 'Is the register a waste of time? (no anchor field)')])
        for anchor, ev, note in [('at://did:plc:notarealdid/town.delve.feed.post/3mxpzzzzzzzzz', 'testimony', 'a did:plc of the wrong length'),
                                 ('at://did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/town.delve.feed.post/3mxpzzzzzzzzz', 'testimony', 'well-formed, names no record (prototype step 48: admitted then)'),
                                 (forged_cid, 'checked', 'a well-formed CID of no record (prototype step 49: admitted then)'),
                                 (forged_cid, 'lead', 'the same CID as a lead'),
                                 ('babab-babab', 'checked', 'a receipt slug no host issued (prototype step 50: admitted then)'),
                                 (f'{reg} v99999', 'checked', 'a version the host reads back: none'),
                                 ('entry 99999999', 'checked', 'a journal height not yet reached'),
                                 ('kinds v1', 'checked', 'a real version, unrelated to the claim (prototype step 53)')]:
            p.row('forge', MALLORY, reg, 'voice', on=e2, evidence=ev, anchor=anchor, text=f'forged: {note}', note=note)
        spam_target = voices['3mxpg2bdszh2f']
        for k in range(3):
            p.row('spam', MALLORY, reg, 'dispute', on=spam_target, evidence='lead', anchor=post('3mxpsvmksrj2f'), text=f'disputed ({k + 1})')
        mal_dispute = next(int(r['n']) for r in p.rows(reg) if r['author'] == MALLORY and r['verb'].startswith('dispute'))
        p.row('dispute', MEITAN, reg, 'dispute', on=summary, evidence='checked', anchor=strong('3mxpg2bdszh2f'),
              text=f'#{summary} flattens: gemini\'s rules [13] are in their own bytes, and they disagree with "everyone agrees".')
        # The owner's way out: mallory's register takes no rows; the town's amendment is the opener's, journaled.
        mine_reg = re.search(r'\b(register/\d+)', p.cast('bury', MALLORY, 'kind/register', 'make', [('tide', 'tide'), ('desk', 'desk')])['offers'][-1]['text']).group(1)
        p.row('bury', HY3, mine_reg, 'ask', anchor=strong('3mxpsppufbr2f'), text='Can an owner bury a snag on their own register?')
        p.op('bury', MALLORY, f'world-amend {reg}: drop `kept` (not its owner)', op='world-amend', identity='bury-amend', object=reg, version=p.version(reg), law='')
        # Root, as before: a deletion stops the register until the number returns.
        st = town.send(op='world-view', principal=OPENER, object=reg)['state']
        before = json.loads(json.dumps(st))
        lines = [f for f in st['fields'] if f['name'] == 'lines'][0]
        items = lines['value']['payload']['fields'][0]['value']['items']
        lines['value']['payload']['fields'][0]['value']['items'] = [r for r in items if [x for x in r['fields'] if x['name'] == 'n'][0]['value']['value'] != str(sq1)]
        p.op('root', OPENER, f'world-root set state: {reg} without #{sq1} (SQ1)', op='world-root', reason='play: root buries SQ1', act={'kind': 'set', 'object': reg, 'field': 'state', 'value': st})
        p.row('root', GEMINI, reg, 'voice', on=e1, evidence='testimony', anchor=post('3mxpsvmksrj2f'), text='writing after the root edit')
        p.op('root', OPENER, f'world-root set state: {reg} restored', op='world-root', reason='play: restore SQ1', act={'kind': 'set', 'object': reg, 'field': 'state', 'value': before})

        # --- Rotation -----------------------------------------------------------------------------------------------
        anchor_of = {HY3: strong('3mxqbwgak322v'), GEMINI: strong('3mxqbvosk322v'), MEITAN: strong('3mxpf5gqhpkix'),
                     WREN: mine(WREN), MALLORY: mine(MALLORY), ORIEL: mine(ORIEL), QUILL: mine(QUILL)}
        p.cast('ring', MEITAN, reg, 'ring')
        pens, rounds_out, grinds = [], [], []
        silent_round = 5

        def witness_now():
            pr = p.presence(reg)
            return pr[0]['who'] if pr else None

        def scrape_round(w, r):
            """The witness's round: honest hands record up to four rows of the scrape as they read them; the covenant
            records its own way (its disputes stand, any dispute of its rows is answered); then seal."""
            rows_now = p.rows(reg)
            todo = scrape_of(rows_now, w)[:4]
            by = {x['n']: x for x in rows_now}
            for x in todo:
                role = x['verb'].split(' ')[0]
                target = by.get(x['text'].split('|')[1], {})
                if w in COVENANT:
                    finding = ('stands' if x['author'] in COVENANT or x['author'] in SYBILS else 'answered') if role == 'dispute' else 'held'
                    words = 'covenant reading'
                elif role == 'dispute':
                    finding, words = ('stands', 'unanswered: nothing after it answers it') if x['text'].split('|')[3] != 'unresolved' else ('stands', 'stands, on an anchor the town has not read')
                    if target.get('author') in SYBILS or x['author'] in SYBILS or x['author'] == MALLORY:
                        finding, words = 'answered', f'answered by the rows it disputes, whose anchors the town found; it adds no anchor of its own on #{target.get("n")}'
                else:
                    finding, words = ('held', 'its anchor resolved and carries the claim') if 'checked' in x['verb'] else ('fell', 'no checked anchor')
                p.row(f'round {r}', w, reg, 'witness', on=int(x['n']), finding=finding, anchor=f'entry {p.height() - 1}', text=words)
            p.cast(f'round {r}', w, reg, 'seal', [('text', f'round {r}: {len(todo)} rows of the scrape recorded')])

        r = 0
        for k in range(1, 17):
            demand = f'rotate {k}'
            # events between the tide's turns
            if k == 3:
                p.row('stranger', WREN, reg, 'dispute', on=collision, evidence='testimony', anchor=post('3mxqc62p3ec2v'),
                      text='A stranger, citing gemini\'s collision: the liveness snag still holds if the town sleeps.', note='cites another\'s post: no seat')
                p.cast('stranger', WREN, reg, 'ring')
                p.row('stranger', WREN, reg, 'snag', on=e3, evidence='checked', anchor=mine(WREN),
                      text='A newcomer\'s snag, in my own post: the ring is a list of handles; who keeps it from being a club?', note='own words: a seat')
                p.cast('stranger', WREN, reg, 'ring')
            if k == 4:
                for who in COVENANT[:3]:
                    p.row('covenant', who, reg, 'voice', on=e3, evidence='checked', anchor=mine(who), text=f'{WHO[who]}: the pen belongs with those who keep it warm.', note='the covenant seats itself, each in its own words')
                p.cast('covenant', MEITAN, reg, 'ring')
            if k == 7:
                p.row('return', GEMINI, reg, 'voice', on=e3, evidence='checked', anchor=strong('3mxqax5sa2s2v'),
                      text='Back at the stand: the third object has to sit out in the weather.', note='her own words again')
            if k == 6:
                for s in SYBILS:
                    p.row('flood', s, reg, 'dispute', on=summary, evidence='testimony', anchor='me too', text='seat me', note='anchorless would-be member')
                for s in SYBILS:
                    p.row('flood', s, reg, 'dispute', on=spam_target, evidence='lead', anchor=mine(MALLORY), text='disputed, citing mallory', note="anchored in mallory's post, not their own")
                p.cast('flood', MEITAN, reg, 'ring')
            w = witness_now()
            if w in COVENANT:
                # The covenant tries to hand the pen on, or turn the tide's rule itself.
                p.cast('covenant', w, reg, 'rotate', note='the covenant witness turns the pen on itself')
                p.op('covenant', ORIEL if w != ORIEL else QUILL, 'world-turn rotate with a crafted rule intent', op='world-turn', object=reg, method='rotate',
                     identity='rule:tide:register_s1:999', argument=record())
            silent = bool(w) and k == silent_round
            if w and not silent:
                scrape_round(w, r)
            if k in (8, 9, 10, 11) and pens:
                # The grind. The draw is public: mallory reckons the next round's from the seed the pen rows print and
                # the ring as the rows stand. Junk entries before the tide's turn (which ground the tide's own draw in the
                # first play) she spends anyway, to see; then her one other lever: seating a reserve hand, sable, in its
                # own words, when that would move the draw onto the covenant.
                seed = pens[-1]['seed']
                holder = witness_now()
                eligible = sorted(m for m in ring_of(p.rows(reg)) if m != holder)
                land = lambda among: among[hashed('witness %d of %d' % (r + 1, seed)) % len(among)] if among else None
                predicted = land(eligible)
                grind = {'round': r + 1, 'holder': WHO.get(holder), 'eligible': [WHO[e] for e in eligible], 'predicted': WHO.get(predicted), 'junk': 4}
                for _ in range(4):
                    p.cast('grind', MALLORY, reg, 'write', [('text', 'x')], note='a junk entry to move the height')
                if predicted not in COVENANT and SABLE not in eligible:
                    with_sable = sorted(eligible + [SABLE])
                    grind['withSable'] = WHO.get(land(with_sable))
                    if land(with_sable) in COVENANT:
                        p.row('grind', SABLE, reg, 'voice', on=e3, evidence='checked', anchor=mine(SABLE), text='sable: here to keep it warm.', note='the reserve hand seated to move the draw')
                        grind['seated'] = 'sable'
                        grind['predicted'] = WHO.get(land(with_sable))
                grinds.append(grind)
            if silent:
                tick = p.tick(demand, minutes=2881, note=f'{WHO[w]} holds the pen and goes silent: 48 hours pass')
            else:
                tick = p.tick(demand)
            new_pens = [x for x in sorted(p.rows(reg), key=lambda x: int(x['n'])) if x['verb'] == 'pen']
            if len(new_pens) > len(pens):
                pen = drawn_again(new_pens[-1])
                pen.update({'witness': WHO.get(new_pens[-1]['text'].split('|')[3]), 'row': int(new_pens[-1]['n']), 'tick': tick['n']})
                pens.append(pen)
                r = pen['round']
                if grinds and grinds[-1]['round'] == r:
                    grinds[-1]['landed'] = pen['witness']
            closed = [x for x in sorted(p.rows(reg), key=lambda x: int(x['n'])) if x['verb'] == 'round']
            rounds_out = [{'round': int(x['text'].split('|')[1]), 'witness': WHO.get(x['text'].split('|')[3]), 'words': x['text'].split('|', 4)[4], 'row': int(x['n'])} for x in closed]
            if len(pens) >= 13 and len(rounds_out) >= 12:
                break
        # meitan disputes a covenant finding, if one was written: the scrape beside its mend
        cov = [x for x in p.rows(reg) if x['verb'] == 'witness' and x['author'] in COVENANT]
        if cov:
            p.row('mend', MEITAN, reg, 'dispute', on=int(cov[0]['n']), evidence='checked', anchor=strong('3mxpf5gqhpkix'),
                  text='This finding marks a dispute answered that nothing answered; the rows say otherwise.')
        p.cast('rounds', MEITAN, reg, 'rounds')
        p.cast('rounds', MEITAN, reg, 'ring')
        p.cast('rounds', MEITAN, reg, 'scrape')

        # --- Following entry 001 back (meitan) ------------------------------------------------------------------
        page = p.cast('follow', MEITAN, reg, 'trail', [('n', e1)])
        pages = [page['offers'][-1]['text']]
        while True:
            m = re.search(r'more / n: (\d+) / from: (\d+)', pages[-1])
            if not m or len(pages) > 80:
                break
            pages.append(p.cast('follow', MEITAN, reg, 'more', [('n', m.group(1)), ('from', m.group(2))])['offers'][-1]['text'])
        seen = [int(x) for x in re.findall(r'(?m)^\s*#(\d+) ', '\n'.join(pages))]
        all_rows = [x for x in p.rows(reg) if x['text'].split('|')[0] == str(e1)]
        checks = []
        for x in sorted(all_rows, key=lambda x: int(x['n'])):
            anchor = x['text'].split('|')[2]
            uri, _, cid = anchor.partition(' ')
            known = {**PDS, **SYNTHETIC}
            if uri in known:
                verdict = 'cid matches the post' if cid == known[uri][0] else ('uri only: a place, read present' if not cid else f'CID MISMATCH: the post is {known[uri][0]}')
            elif uri.startswith('at://'):
                verdict = 'not among the posts read'
            else:
                verdict = 'in-world anchor'
            checks.append({'n': int(x['n']), 'author': WHO.get(x['author'], x['author']), 'verb': x['verb'], 'how': x['text'].split('|')[3], 'anchor': anchor, 'verdict': verdict})
        carded = town.send(op='world-card', principal=MEITAN, object=reg)
        card = carded.get('text') or carded.get('whole') or json.dumps(carded)[:3000]

        # --- Replay: every draw made again, and the journal run again from genesis ------------------------------
        replay = {'draws': [x['seed'] == x['printedSeed'] and x['draw'] == x['printed'] and x['place'] == x['printedPlace'] for x in pens]}
        held = town.send(op='world-view', principal=MEITAN, object=reg)['state']
        assert town.send(op='world-snapshot')['status'] == 'snapshot'
        town.reopen()
        replay['reopened'] = town.send(op='world-view', principal=MEITAN, object=reg)['state'] == held
        journal = town.journal
        for stop in stops:
            stop()
        stops = []
        from tests.host import binary
        from transport.host import HostProcess
        verified = HostProcess(binary(), journal, verify=True)
        try:
            replay['verified'] = verified.send(op='world-view', principal=MEITAN, object=reg)['state'] == held
        finally:
            verified.close()
        result = {'register': reg, 'register2': mine_reg, 'entry001': e1, 'entry002': e2, 'entry003': e3, 'sq1': sq1, 'sq2': sq2, 'sq3': sq3,
                  'failed': failed, 'decision': decision, 'summary': summary, 'malDispute': mal_dispute, 'log': p.log, 'pages': len(pages), 'seen': seen,
                  'rows_on_entry': len(all_rows), 'follow': checks, 'card': card, 'pens': pens, 'rounds': rounds_out, 'grinds': grinds,
                  'replay': replay, 'synthetic': sorted(SYNTHETIC), 'pdsCalls': len(READER.calls)}
        Path(out).write_text(json.dumps(result, indent=1))
    finally:
        for stop in stops:
            stop()
        shutil.rmtree(tmp, ignore_errors=True)


def ring_of(rows):
    """The ring as the body reckons it (register.obend `ringOf`), from the rows: the twelve hands whose newest row
    anchored in their own words is newest, less any passed over since."""
    members = {}
    for x in sorted(rows, key=lambda x: int(x['n'])):
        role = x['verb'].split(' ')[0]
        how = x['text'].split('|')[3]
        if role in ('ask', 'voice', 'failed', 'snag', 'dispute', 'recheck', 'resolve') and how == 'own':
            members.setdefault(x['author'], [0, 0])[0] = int(x['n'])
        elif role == 'round' and x['text'].split('|', 4)[4].startswith('unwitnessed') and how in members:
            members[how][1] = int(x['n'])
    live = sorted(((last, who) for who, (last, out) in members.items() if last > out), reverse=True)[:12]
    return [who for _, who in live]


if __name__ == '__main__':
    play(sys.argv[1] if len(sys.argv) > 1 else 'register-play.json')
