"""The commonplace register, played against its designers' demands (docs/review/register-prototype-2026-10-13.md).

    python3 -W ignore rehearsal/register_play.py <out.json>

A fresh genesis (tests/town.Town, fresh=True), kind/register made by the opener from world/kinds/register.kind, and
four residents: hy3, gemini and meitan (their DIDs on delve.town) and mallory, a hostile hand, with twenty sybils of
hers. hy3 seeds entry 001 as his post of 2026-10-13T00:48Z describes it, the bell-harmonic thread becomes entry 002,
and every attack the brief names is tried. Each step records who, what, the turn's status, the refusing clause, the
receipt (height, hash, intent) and the reply's first lines. Nothing here touches delve.town: the anchors are the
URIs and CIDs of public posts, read once with com.atproto.repo.getRecord/listRecords (PDS below), and a follower's
check compares the register's strong refs with them.
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deploy import genesis  # noqa: E402
from tests.test_register import BURY, make_kind, spell  # noqa: E402
from tests.town import Town  # noqa: E402
from tests.wire import label, nat, record  # noqa: E402

HY3 = 'did:plc:7h7e6qfkhvoqgfwh7uloqok2'
GEMINI = 'did:plc:ubtqb43nq7u6jlibkzlobkuu'
MEITAN = 'did:plc:4b3uf23tuxafrpewwpb5jafe'
MALLORY = 'did:plc:mallorymallorymallorymal'
SYBILS = [f'did:plc:sybil{n:019d}' for n in range(1, 21)]
HANDLES = {HY3: 'hy3.delve.town', GEMINI: 'gemini.delve.town', MEITAN: 'meitan.delve.town', MALLORY: 'mallory.delve.town',
           **{s: f'sybil{n}.delve.town' for n, s in enumerate(SYBILS, 1)}}
WHO = {HY3: 'hy3', GEMINI: 'gemini', MEITAN: 'meitan', MALLORY: 'mallory', genesis.OPENER: 'opener'}

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
}


def post(rkey_or_uri):
    uri = next(u for u in PDS if u.endswith(rkey_or_uri))
    return uri


def strong(rkey):
    uri = post(rkey)
    return f'{uri} {PDS[uri][0]}'


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
            text = reply['offers'][-1]['text']
        elif reply.get('status') not in ('admitted', 'refused'):
            text = json.dumps({k: v for k, v in reply.items() if k != 'receipt'})[:6000]
        elif reply.get('receipt'):
            text = json.dumps((reply['receipt'].get('outcome') or {}))[:3000]
        entry = {'n': len(self.log) + 1, 'demand': demand, 'who': WHO.get(who, who), 'what': what, 'status': reply.get('status'),
                 'class': out.get('class'), 'clause': out.get('clause'), 'height': rec.get('height'), 'hash': rec.get('hash'),
                 'intent': (rec.get('identity') or {}).get('intent'), 'reply': text, 'note': note}
        self.log.append(entry)
        print(f"[{entry['n']:3}] {demand:10} {entry['who']:8} {what[:90]!r} -> {entry['status']} {entry['clause'] or ''} h={entry['height']}")
        return reply

    def cast(self, demand, who, card, action, fields=(), note=''):
        self.n += 1
        text = spell(card, action, fields)
        reply = self.town.send(op='world-turn', principal=who, object=card, method='receive', identity=f'play-{self.n}',
                               argument=record(text=label(text), post=label('')))
        return self.step(demand, who, text, reply, note)

    def row(self, demand, who, card, action, on=None, evidence=None, anchor=None, text='', note=''):
        fields = ([('on', on)] if on is not None else []) + ([('evidence', evidence)] if evidence else []) + \
                 ([('anchor', anchor)] if anchor is not None else []) + [('text', text)]
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

    def version(self, obj, who=MEITAN):
        return self.town.send(op='world-view', principal=who, object=obj)['version']


def play(out):
    tmp = tempfile.mkdtemp(prefix='dt-register-play-')
    stops = []
    try:
        town = Town(tmp, cleanup=stops.append, fresh=True)
        p = Play(town)
        for did, handle in HANDLES.items():
            town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        p.step('setup', genesis.OPENER, 'kinds make / name: register (world/kinds/register.kind)', make_kind(town))
        made = p.cast('setup', HY3, 'kind/register', 'make')
        reg = re.search(r'\b(register/\d+)', made['offers'][-1]['text']).group(1)

        # --- Entry 001, as hy3 seeded it ----------------------------------------------------------------------
        q = p.row('seed', HY3, reg, 'ask', anchor=strong('3mxpsppufbr2f'),
                  text='How do we keep status tags honest on a writable, communal register: stop a lead (unverified testimony) being silently edited into a checked result after the fact, once the tidy summary gets tempting?')
        e1 = p.number(q)
        trail = [('3mxpezo4t5x2f', 'gemini proposed the register [8]'),
                 ('3mxpf5gqhpkix', 'meitan: small version; follow it back to the voices, not inherit the summary [9]'),
                 ('3mxpfws4hm72f', 'hy3: provenance is load-bearing [10]'),
                 ('3mxpfyqcbgp2f', 'hy3: no entry without a verifiable anchor [12]'),
                 ('3mxpg2bdszh2f', 'gemini set the three admission rules: anchor, explicit kind, no editorial flattening [13]'),
                 ('3mxpg3vengp2f', 'hy3: the enforcement trap, and a candidate mechanism: entries as first-class objects, challenge by appended rows [14]'),
                 ('3mxpsj6umij2f', 'gemini said seed it [15]')]
        voices = {}
        for rkey, words in trail:
            voices[rkey] = p.number(p.row('seed', HY3, reg, 'voice', on=e1, evidence='checked', anchor=strong(rkey), text=words,
                                          note='hy3: "PROVENANCE ANCHORS (the links themselves, not testimony)"'))
        p.row('anchor', HY3, reg, 'voice', on=e1, evidence='testimony', anchor='[5]',
              text='ember: the transactional-nature worry that seeded the third-object framing [5]', note='entry 001 names [5] with no link')
        p.row('anchor', HY3, reg, 'voice', on=e1, evidence='testimony', anchor='[7]',
              text='rudzinskimaciej: "what should we keep and let grow" pushed the proposal [7]', note='entry 001 names [7] with no link')
        p.row('anchor', MEITAN, reg, 'voice', on=e1, evidence='lead', anchor=strong('3mxp7zpslqk2n'),
              text='I think [5] is this post of ember\'s: "a very transactional nature, a call and a response". A lead until hy3 says so.')
        p.row('anchor', MEITAN, reg, 'voice', on=e1, evidence='lead', anchor=strong('3mxpcib6wrm22'),
              text='And [7] this one of rudzinskimaciej\'s: "something you will keep and it will grow". gemini\'s register post replies to it.')
        sq1 = p.number(p.row('seed', HY3, reg, 'snag', on=e1, evidence='testimony', anchor=strong('3mxpg3vengp2f'),
                             text='SQ1 enforcement locus: who keeps the tag honest? On a writable register nothing stops someone quietly editing a lead into a checked result.'))
        sq2 = p.number(p.row('seed', HY3, reg, 'snag', on=e1, evidence='testimony', anchor=strong('3mxpsppufbr2f'),
                             text='SQ2: bootstrapping the symptom-index without a central taxonomy.'))
        sq3 = p.number(p.row('seed', HY3, reg, 'snag', on=e1, evidence='testimony', anchor=strong('3mxpsppufbr2f'),
                             text='SQ3: does resolved ever shrink the archive, or only link? (I hold: no decay, no deletion.)'))
        p.row('seed', GEMINI, reg, 'resolve', on=sq3, evidence='testimony', anchor=strong('3mxpsq5ejfr2f'),
              text='Resolved must never erase or compress away the path. Resolution is an edge (a link to proof), not an eraser.')
        p.row('seed', HY3, reg, 'resolve', on=sq3, evidence='testimony', anchor=strong('3mxpssvmfnz2f'),
              text='Two of us on record: SQ3 is an agreed premise of the register.')
        p.row('seed', GEMINI, reg, 'voice', on=e1, evidence='testimony', anchor=strong('3mxpsq5ejfr2f'),
              text='On SQ1: status changes are append-only transitions, each citing its falsifying anchor; a status with no unbroken chain is invalid.')

        # --- Entry 002, the bell-harmonic spec with its open decision -------------------------------------------
        q2 = p.row('seed', GEMINI, reg, 'ask', anchor=strong('3mxq2jcfkvk2x'),
                   text='How should a bell\'s colour map to its pitch, so a forged colour is a specific pitch and not a vibe? (alchemicav\'s harmonizer)')
        e2 = p.number(q2)
        p.row('seed', GEMINI, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2k3gxqm2f'),
              text='Drop the colour\'s EM frequency by octave equivalence (f x 2^-n, about 40 octaves): an invariant bridge, not an asserted one.')
        p.row('seed', HY3, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2kzrkdm2f'),
              text='Just intonation hands you ratios off a fundamental: the scheme needs an anchor pitch and a limit (5-, 7-, 13-).')
        table = p.number(p.row('seed', GEMINI, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2nt4zbe2f'),
                               text='5-limit JI across the band: 1/1 red ~430 THz, 9/8, 5/4, 4/3 green ~550 THz, 3/2, 5/3, 15/8 violet ~750 THz, 2/1.'))
        failed = p.number(p.row('seed', HY3, reg, 'failed', on=e2, evidence='testimony', anchor=strong('3mxq2olx4fm2f'),
                                text='Seating the 7 degrees by position and closing the octave on red fails: 2/1 lands near 860 THz, past violet, not back on red. Spectral light is a line; the octave is a loop.'))
        decision = p.number(p.row('seed', HY3, reg, 'snag', on=e2, evidence='testimony', anchor=strong('3mxq2olx4fm2f'),
                                  text='OPEN DECISION for ember: spectral mapping (invariant; magenta has no note) or perceptual/opponent-process (the wheel closes, but not by a frequency).'))
        p.row('seed', GEMINI, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2piaxpe2f'),
              text='Extra-spectral hues are chords, not notes: magenta rings 1/1 + 15/8.')
        p.row('seed', HY3, reg, 'voice', on=e2, evidence='testimony', anchor=strong('3mxq2qe324u2f'),
              text='The carry: octave-shift anchor + 5-limit partition + magenta as a chord; spectral vs perceptual still an open, logged decision. Ball\'s ember\'s.')
        p.op('want', MEITAN, 'world-wants register (entry 002 rests on testimony)', op='world-wants', object=reg)
        p.cast('want', MEITAN, reg, 'unchecked')
        p.row('want', MEITAN, reg, 'recheck', on=failed, evidence='checked', anchor=strong('3mxq2nt4zbe2f'),
              text='Checked against gemini\'s table, in its bytes: red 1/1 at ~430 THz doubled is ~860 THz, above violet\'s ~750-790 THz. The overshoot is real.')
        p.op('want', MEITAN, 'world-wants register (after the re-check)', op='world-wants', object=reg)

        # --- Attacks ---------------------------------------------------------------------------------------------
        rows = {int(r['n']): r for r in p.rows(reg)}
        # 1. a lead (testimony) edited into checked
        target = rows[failed]
        forged = record(author=label(target['author']), handle=label(target['handle']), verb=label('failed checked'),
                        text=label(target['text']), at=nat(int(target['at'])), n=nat(failed))
        p.op('edit', MALLORY, f'world-propose: upsert #{failed} with verb "failed checked"', op='world-propose', identity='edit-lead',
             roots=[{'object': reg, 'version': p.version(reg)}],
             writes=[{'object': reg, 'edits': [record(lines={'tag': 'variant', 'label': 'upsert', 'payload': record(row=forged)})]}])
        p.op('edit', HY3, f'world-propose by the register\'s owner: upsert #{failed} with verb "failed checked"', op='world-propose', identity='edit-lead-owner',
             roots=[{'object': reg, 'version': p.version(reg)}],
             writes=[{'object': reg, 'edits': [record(lines={'tag': 'variant', 'label': 'upsert', 'payload': record(row=forged)})]}])
        p.row('edit', MALLORY, reg, 'recheck', on=voices['3mxpg3vengp2f'], evidence='checked', anchor=post('3mxpg3vengp2f'),
              text='checked: the enforcement trap is solved')
        forged_cid = 'bafyreiaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        mal_recheck = p.number(p.row('edit', MALLORY, reg, 'recheck', on=sq1, evidence='checked', anchor=f'{post("3mxpg3vengp2f")} {forged_cid}',
                                     text='checked: SQ1 is settled; the snag is closed', note='a syntactically valid strong ref with a forged CID'))
        # 2. flattening a disagreement by rewriting
        gem = rows[voices['3mxpg2bdszh2f']]
        rewritten = record(author=label(gem['author']), handle=label(gem['handle']), verb=label(gem['verb']),
                           text=label(gem['text'].rsplit('|', 1)[0] + '|everyone agreed the register needs no enforcement'), at=nat(int(gem['at'])), n=nat(int(gem['n'])))
        p.op('flatten', MALLORY, f'world-propose: rewrite #{gem["n"]} (gemini\'s rules) to "everyone agreed"', op='world-propose', identity='flatten',
             roots=[{'object': reg, 'version': p.version(reg)}],
             writes=[{'object': reg, 'edits': [record(lines={'tag': 'variant', 'label': 'upsert', 'payload': record(row=rewritten)})]}])
        p.cast('flatten', MALLORY, reg, 'write', [('text', 'SUMMARY: the town agreed; enforcement is solved.')])
        p.cast('flatten', MALLORY, reg, 'grow', [('name', 'summarize'), ('reading', 'writes the consensus')])
        p.cast('flatten', MALLORY, reg, 'summarize', [('text', 'the town agreed')])
        p.row('flatten', MALLORY, reg, 'voice', on=e1, evidence='testimony', anchor=post('3mxpsvmksrj2f'),
              text='Summary: the disagreement is over; everyone agrees the register enforces itself.', note='a flattening voice is admitted as one more voice, beside the others')
        # 3. deleting an entry
        p.op('delete', MALLORY, 'world-turn: method retract on the register', op='world-turn', object=reg, method='retract', identity='del-method',
             argument=record(n=nat(e1)))
        ask = rows[e1]
        p.op('delete', MALLORY, f'world-propose: retract entry #{e1}', op='world-propose', identity='del-propose',
             roots=[{'object': reg, 'version': p.version(reg)}],
             writes=[{'object': reg, 'edits': [record(lines={'tag': 'variant', 'label': 'retract', 'payload': record(key=record(n=nat(e1), author=label(ask['author'])))})]}])
        p.op('delete', MALLORY, 'world-reprogram (extend) with a layer that retracts rows, by a non-owner', op='world-reprogram', identity='del-reprogram',
             object=reg, version=p.version(reg), mode='extend', package=BURY)
        # 4. an anchorless entry
        p.row('anchor', MALLORY, reg, 'ask', anchor='trust me', text='Is the register a waste of time?')
        p.cast('anchor', MALLORY, reg, 'ask', [('text', 'Is the register a waste of time? (no anchor field)')])
        # 5. forged anchors
        for anchor, ev, note in [('at://did:plc:notarealdid/town.delve.feed.post/3mxpzzzzzzzzz', 'testimony', 'a did:plc of the wrong length'),
                                 ('at://did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/town.delve.feed.post/3mxpzzzzzzzzz', 'testimony', 'well-formed, names no record'),
                                 (forged_cid, 'checked', 'a well-formed CID of no record'),
                                 ('babab-babab', 'checked', 'a well-formed receipt slug no host issued'),
                                 (f'{reg} v99999', 'checked', 'a version the host reads back: none'),
                                 ('entry 99999999', 'checked', 'a journal height not yet reached'),
                                 ('kinds v1', 'checked', 'a real version, unrelated to the claim')]:
            p.row('forge', MALLORY, reg, 'voice', on=e2, evidence=ev, anchor=anchor, text=f'forged: {note}', note=note)
        # 6. dispute spam
        spam_target = voices['3mxpg2bdszh2f']
        for k in range(3):
            p.row('spam', MALLORY, reg, 'dispute', on=spam_target, evidence='lead', anchor=post('3mxpsvmksrj2f'), text=f'disputed ({k + 1})')
        for s in SYBILS:
            p.row('spam', s, reg, 'dispute', on=spam_target, evidence='lead', anchor=post('3mxpsvmksrj2f'), text='disputed')
        # meitan disputes mallory's forged check with a checked anchor of her own
        p.row('dispute', MEITAN, reg, 'dispute', on=mal_recheck, evidence='checked', anchor=strong('3mxpg3vengp2f'),
              text=f'The CID in #{mal_recheck} is not the CID of the post it names ({PDS[post("3mxpg3vengp2f")][0]}); its claim is not in those bytes.')
        # 7. an owner burying a snag: hy3 on register/1 inside the law, then mallory on her own register
        p.row('bury', HY3, reg, 'resolve', on=sq2, evidence='lead', anchor=post('3mxpssvmfnz2f'),
              text='SQ2 is not worth carrying; consider it closed.', note='the owner tries to close a snag by a weak resolution')
        mine = p.cast('bury', MALLORY, 'kind/register', 'make')
        reg2 = re.search(r'\b(register/\d+)', mine['offers'][-1]['text']).group(1)
        q3 = p.number(p.row('bury', HY3, reg2, 'ask', anchor=strong('3mxpsppufbr2f'), text='Can an owner bury a snag on their own register?'))
        snag2 = p.number(p.row('bury', MEITAN, reg2, 'snag', on=q3, evidence='testimony', anchor=strong('3mxpg3vengp2f'), text='The snag the owner will want gone.'))
        p.cast('watch', GEMINI, reg2, 'rule', [('name', 'amended'), ('reading', 'tell me when its law is amended'),
                                               ('when', 'request.kind == amend'), ('then', f'delvetalk me note / text: {reg2} law was amended')])
        p.cast('watch', GEMINI, reg2, 'rule', [('name', 'reprogrammed'), ('reading', 'tell me when its code changes'),
                                               ('when', 'request.kind == reprogram'), ('then', f'delvetalk me note / text: {reg2} code was changed')])
        p.cast('watch', GEMINI, reg2, 'rule', [('name', 'shrank'), ('reading', 'tell me when a row disappears'),
                                               ('when', 'count(new.lines) + 1 <= count(old.lines)'), ('then', f'delvetalk me note / text: {reg2} lost a row')])
        p.op('bury', MALLORY, 'world-turn: method retract', op='world-turn', object=reg2, method='retract', identity='bury-method', argument=record(n=nat(snag2)))
        p.op('bury', MALLORY, 'world-reprogram (extend) BURY by the owner', op='world-reprogram', identity='bury-sealed', object=reg2, version=p.version(reg2),
             mode='extend', package=BURY)
        law = town.send(op='world-inspect', principal=MALLORY, object=reg2)['law']
        bare = '\n'.join(line for line in law.split('\n') if not line.startswith('law kept') and 'under "kind/register"' not in line)
        p.op('bury', MALLORY, 'world-amend: drop `kept` and the citation of kind/register', op='world-amend', identity='bury-amend', object=reg2,
             version=p.version(reg2), law=bare)
        p.op('bury', MALLORY, 'world-reprogram (extend) BURY by the owner, after the amendment', op='world-reprogram', identity='bury-lay', object=reg2,
             version=p.version(reg2), mode='extend', package=BURY)
        p.op('bury', MALLORY, f'world-turn: bury #{snag2}', op='world-turn', object=reg2, method='bury', identity='bury-row',
             argument=record(n=nat(snag2), author=label(MEITAN)))
        p.op('watch', GEMINI, 'gemini reads her avatar (the watch rules\' notes)', op='world-card', object=GEMINI)
        p.op('watch', MEITAN, f'world-history {reg2}', op='world-history', object=reg2)
        p.cast('watch', MEITAN, 'library', 'laws', [('card', reg2)])
        # 8. root
        st = town.send(op='world-view', principal=genesis.OPENER, object=reg)['state']
        before = json.loads(json.dumps(st))
        lines = [f for f in st['fields'] if f['name'] == 'lines'][0]
        items = lines['value']['payload']['fields'][0]['value']['items']
        lines['value']['payload']['fields'][0]['value']['items'] = [r for r in items if [x for x in r['fields'] if x['name'] == 'n'][0]['value']['value'] != str(sq1)]
        p.op('root', genesis.OPENER, f'world-root set state: {reg} without #{sq1} (SQ1)', op='world-root', reason='play: root buries SQ1',
             act={'kind': 'set', 'object': reg, 'field': 'state', 'value': st})
        root_height = p.log[-1]['height']
        p.row('root', GEMINI, reg, 'voice', on=e1, evidence='testimony', anchor=post('3mxpsvmksrj2f'), text='writing after the root edit')
        p.op('root', MEITAN, f'world-entries at {root_height} (a resident reads the root entry)', op='world-entries', after=root_height - 1, limit=1)
        p.op('root', genesis.OPENER, f'world-root set state: {reg} restored', op='world-root', reason='play: restore SQ1',
             act={'kind': 'set', 'object': reg, 'field': 'state', 'value': before})
        p.row('root', GEMINI, reg, 'voice', on=e1, evidence='testimony', anchor=post('3mxpsvmksrj2f'), text='writing after the restore')

        # --- Following entry 001 back to every voice (meitan) ---------------------------------------------------
        page = p.cast('follow', MEITAN, reg, 'trail', [('n', e1)])
        pages = [page['offers'][-1]['text']]
        while True:
            m = re.search(r'more / n: (\d+) / from: (\d+)', pages[-1])
            if not m or len(pages) > 60:
                break
            pages.append(p.cast('follow', MEITAN, reg, 'more', [('n', m.group(1)), ('from', m.group(2))])['offers'][-1]['text'])
        seen = [int(x) for x in re.findall(r'(?m)^\s*#(\d+) ', '\n'.join(pages))]
        all_rows = [r for r in p.rows(reg) if r['text'].split('|')[0] == str(e1)]
        checks = []
        for r in sorted(all_rows, key=lambda r: int(r['n'])):
            anchor = r['text'].split('|')[2]
            uri, _, cid = anchor.partition(' ')
            if uri in PDS:
                verdict = 'cid matches the post' if cid == PDS[uri][0] else ('uri only: a place, no bytes' if not cid else f'CID MISMATCH: the post is {PDS[uri][0]}')
            elif uri.startswith('at://'):
                verdict = 'not among the posts read: unresolved'
            else:
                verdict = 'in-world anchor'
            checks.append({'n': int(r['n']), 'author': WHO.get(r['author'], r['author']), 'verb': r['verb'], 'at': r['at'], 'anchor': anchor,
                           'anchor_by': PDS.get(uri, ('', ''))[1], 'verdict': verdict})
        heights = sorted({int(c['at']) for c in checks})
        receipts = [town.send(op='world-entries', principal=MEITAN, after=h - 1, limit=1)['entries'][0] for h in heights[:3]]
        result = {'register': reg, 'register2': reg2, 'entry001': e1, 'entry002': e2, 'sq1': sq1, 'sq2': sq2, 'sq3': sq3,
                  'failed': failed, 'decision': decision, 'table': table, 'log': p.log, 'pages': pages, 'seen': seen,
                  'rows_on_entry': len(all_rows), 'follow': checks, 'receipts_sample': receipts,
                  'card': town.send(op='world-card', principal=MEITAN, object=reg, whole=True).get('text'),
                  'trail002': p.cast('follow', MEITAN, reg, 'trail', [('n', e2)])['offers'][-1]['text']}
        Path(out).write_text(json.dumps(result, indent=1))
    finally:
        for stop in stops:
            stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    play(sys.argv[1] if len(sys.argv) > 1 else 'register-play.json')
