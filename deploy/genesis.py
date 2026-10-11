#!/usr/bin/env python3
"""The town's genesis (docs/GENESIS.md) as one command: the opener creates the objects, in order, over serve's root socket.

  python3 -m deploy.genesis --root-socket /run/delvetalk-root/root.sock --opener did:plc:...

Refuses to run twice: if any genesis object already exists (`world-objects`), it creates nothing and exits 1.
rehearsal/rehearse.py calls `run`, so the rehearsal and production seed the same world. Seeds name only the
fields genesis decides; the host lays them over each package's own initial().
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deploy.seed import create  # noqa: E402
from transport.host import HostClient  # noqa: E402
from transport.identity import ORIGIN  # noqa: E402

OPENER = 'did:plc:6amo7col5h4ciq2gpm5eur7b'  # ember.delve.town
HANDLE = 'ember.delve.town'


def lab(s): return {'tag': 'label', 'value': s}
def nat(n): return {'tag': 'natural', 'value': str(n)}
def boo(b): return {'tag': 'boolean', 'value': b}
def lst(*items): return {'tag': 'list', 'items': list(items)}
def rec(**fields): return {'tag': 'record', 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}
def ref(obj): return rec(world=lab(''), object=lab(obj))
def relation(*rows): return {'tag': 'variant', 'label': 'rows', 'payload': rec(items=lst(*rows))}  # world/lib/Relation.obend


# The commonplace's doors (label, object, [(spell, what comes back)]): the hand's named things, cited from the town's
# first card (world/bodies/commonplace.obend). The spells and their `»` lines are the menu's (docs/MENU.md §1).
DOORS = [
    ('GARDEN', 'garden', [('delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver', 'a bell, garden/bell/N; you hear when it rings')]),
    ('ROOMS', 'rooms', [('delvetalk rooms enter', ''),
                        ('delvetalk rooms choose / choice: Open', 'the passage moves; a ```spween block here makes your own')]),
    ('WORKSHOP', 'workshop', [('delvetalk workshop make / name: lamp / description: a lamp anyone lights', 'hob drafts the Bend; checked, held as #n for you to adopt')]),
    ('TIDE', 'tide', [('delvetalk tide subscribe / every: 3 / note: first light', ''),
                      ('delvetalk tide tick', 'too soon: refused tooSoon; a due tick notes your avatar')]),
    ('PORCH', 'porch', [('delvetalk porch enter', ''), ('delvetalk porch say / line: the bell kept both of us', 'heard by everyone here')]),
    ('ANTHOLOGY', 'anthology', [('delvetalk anthology write / text: the bell kept both of us', 'numbered, [pending] until the keeper admits')]),
    ('KINDS', 'kinds', [('delvetalk kinds make / name: lamp / of: record / form: seed: text 1..80', 'kind/lamp, a kind anyone makes')]),
]
# A link door: no object (the empty reference); its description is its line.
STUDIO = ('STUDIO', f'heap and REPL: {ORIGIN}/AGENTS.md')


def door(label, to, examples, description=''):
    """A door as a record cites it (Card.Doorway, world/lib/Card.obend)."""
    return rec(label=lab(label), to=ref(to), description=lab(description),
               examples=lst(*[rec(example=lab(e), comes=lab(c)) for e, c in examples]))


def commonplace(opener):
    """The town's first card: a record the opener keeps, reading words with hob's policy, citing the doors."""
    return rec(owner=lab(opener), keeper=lab(opener), keeperHandle=lab(HANDLE), head=lab('THE COMMONPLACE'),
               policy=ref('policy'), cites=lst(*[door(*d) for d in DOORS], door(STUDIO[0], '', [], STUDIO[1])))


# hob's instruction (docs/FLEX.md §2), as Policy.hob() (world/objects/Policy.obend) has it.
POLICY_SYSTEM = ('hob reads for a town of cards. A participant answered the card below in words. Give the spell they meant, so the card can run it; '
                 'the card and its law decide what is admitted, never you.')
LEXICON = [('colour', 'one of amber, violet or silver'), ('seed', 'what might grow, 1 to 80 characters')]
# The Moss Gate's scene, as spween (world/lib/Spween.obend): the hand's room, made by kind/room's make with
# this as its `spween` field, as a block posted to a room carves one under it.
MOSS_GATE = """---
id: gate
title: The Moss Gate
---
=== gate
A moss gate, ajar.
* [Open]
  ~ gate = open
  -> yard
* [Wait] -> gate
=== yard
A quiet yard.
* [Back] -> gate
* [Knock]
  ~ knock = twice
  -> yard
"""


EXAMPLES = [('a silver fern that remembers yesterday', 'delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver'),
            ('plant me something amber for the lost moths', 'delvetalk garden plant\nseed: a bell for lost moths\ncolour: amber'),
            ('how many have been planted?', 'card')]  # a question the card already answers (docs/FLEX.md §3)


# The library's stacks (docs/LIBRARY.md): (name, kind, title); each body is capsules/pages/<name>.txt, so the page in
# the world and the file in the tree are one text.
PAGES = [('spells', 'page', 'how a reply is read: the line, the fields, ?, a badSpell hint'),
         ('laws', 'page', 'one line a clause, its reading; who may; transient and binding refusals'),
         ('object', 'page', 'a card in Bend, one whole example'),
         ('relations', 'page', "rows in a card's state: keys, insert, upsert, retract, order"),
         ('protocol', 'page', 'what a card asks the world: view, call, send, create, subscribe'),
         ('world', 'page', "the doors, every card's spells, the classes of refusal")]


def page_body(name):
    return (ROOT / 'capsules' / 'pages' / (name + '.txt')).read_text()


# Record.lawText() (world/objects/Record.obend): a record's package declares no law, since every kind imports the
# package it makes; its creator passes it (tests/test_genesis.py compares the two).
RECORD_LAW = ('law owner "the owner stays; only the owner changes the keeper, the policy, the doors, its scene or its code; anyone else only by its spells": '
              'unchanged(owner) and (request.subject == new.owner or (request.kind == 0 and unchanged(keeper) and unchanged(policy) and unchanged(cites) '
              'and unchanged(start) and unchanged(passages) and unchanged(cooldown) and unchanged(requires)))\n'
              'law kept "a line, an admission, a mark or a greeting is only added; only the keeper admits": insertOnly(lines) and insertOnly(admitted) and insertOnly(marks) and insertOnly(greeted) '
              'and (unchanged(admitted) or request.subject == new.keeper)\n'
              'law methods "what was written, admitted and marked, who is here, who left, the variables and what lies here change only by their spells, never by a proposal": '
              'request.kind == proposed implies (unchanged(lines) and unchanged(admitted) and unchanged(marks) and unchanged(presence) and unchanged(left) and unchanged(vars) and unchanged(things))')


# The kind of kinds (world/objects/Kind.obend): what `kinds make` takes, one field a line, and a kind's own law,
# Kind.lawText() (tests/test_kinds.py compares the two).
KINDS_FORM = 'name: text 1..32\nof: text 1..16\nform: text 0..1000\nhead: text 0..200\nlaw: text 0..4096\nbody: text 0..131072'  # a body is a package: Bounds.maxPackageBytes
KIND_LAW = ('law owner "the owner stays; only the owner changes the form, the law, the head or the body; anyone makes": '
            'unchanged(owner) and (request.subject == new.owner or (request.kind == 0 and unchanged(form) and unchanged(law) '
            'and unchanged(head) and unchanged(body)))')


# The law each package's objects are created with, where its source declares none.
LAWS = {'Record': lambda _: RECORD_LAW, 'Kind': lambda _: KIND_LAW}


# The kinds genesis makes (name, of, form, head, law, body): the root kind of records, and the town's furniture
# (docs/METAPHYSICS.md §7.2), each a record with a body, world/bodies/<body>.obend, a layer over Record.obend laid
# on each instance. A bell's colour and seed, a weather's garden and tide, a lantern's door are its fixed `fields`.
NAMED = 'name: text 1..64'
KINDS = [('record', 'record', '', 'A RECORD, begun by {maker}', RECORD_LAW, ''),
         ('bell', 'record', 'colour: amber | violet | silver\nseed: text 1..80', '', RECORD_LAW, 'bell'),
         ('cistern', 'record', '', '', RECORD_LAW + '\nlaw level "the level only rises": monotone(next)', 'cistern'),
         ('room', 'record', NAMED + '\nspween: text 0..16384', '{name}', RECORD_LAW, 'room'),
         ('porch', 'record', NAMED, '{name}', RECORD_LAW, 'room'),
         ('garden', 'record', NAMED, '{name}', RECORD_LAW, 'garden'),
         ('weather', 'record', 'garden: text 1..128\ntide: text 1..128', '', RECORD_LAW, 'weather'),
         ('door', 'record', NAMED, '{name}', RECORD_LAW, 'door'),
         ('lantern', 'record', NAMED + '\ndoor: text 1..128', '{name}', RECORD_LAW, 'lantern')]


# The hand's own things, made by spell on their kinds at genesis, each at an exact id (a kind's owner's alone), so
# each has a maker and the commonplace cites them: (kind, fields). The weather is made after the tide it watches,
# and the garden then cites it, which is what lets it write the garden's weather.
HANDS = [('kind/garden', [('id', 'garden'), ('name', 'THE NIGHT GARDEN')]),
         ('kind/room', [('id', 'rooms'), ('name', 'The Moss Gate'), ('spween', MOSS_GATE)]),
         ('kind/porch', [('id', 'porch'), ('name', "The Bellfounder's Porch")]),
         ('kind/weather', [('id', 'weather'), ('garden', 'garden'), ('tide', 'tide')])]


def spell(card, action, fields):
    """A spell as the hand types it: the delvetalk line, then a `field: value` line each, a multi-line value as a block."""
    lines = [f'delvetalk {card} {action}']
    for name, value in fields:
        lines += [f'{name}: <<END', value.rstrip('\n'), 'END'] if '\n' in value else [f'{name}: {value}']
    return '\n'.join(lines)


def body_of(name):
    return (ROOT / 'world' / 'bodies' / (name + '.obend')).read_text() if name else ''


def seeds(opener):
    """(object, package, partial seed), in the order GENESIS.md creates them."""
    return [('policy', 'Policy', rec(owner=lab(opener), model=lab('claude-haiku-5-5'), system=lab(POLICY_SYSTEM),
                                     lexicon=lst(*[rec(word=lab(w), meaning=lab(m)) for w, m in LEXICON]),
                                     examples=lst(*[rec(utterance=lab(u), spell=lab(s)) for u, s in EXAMPLES]))),
            ('commonplace', 'Record', commonplace(opener)),  # created with RECORD_LAW, then given its body
            ('tide', 'Tide', rec(gap=nat(1))),
            ('workshop', 'Workshop', rec(title=lab('Workshop'), policy=ref('policy'))),
            ('kinds', 'Kind', rec(owner=lab(opener), ownerHandle=lab(HANDLE), name=lab('kinds'), of=lab('kind'), form=lab(KINDS_FORM))),  # shaped, then makes KINDS
            ('anthology', 'Record', rec(owner=lab(opener), keeper=lab(opener), keeperHandle=lab(HANDLE), head=lab('THE ANTHOLOGY'))),  # created with RECORD_LAW
            ('library', 'Library', rec(owner=lab(opener), ownerHandle=lab(HANDLE)))]


def existing(host, opener):
    """Every object id the opener can see (all pages)."""
    ids, after = [], None
    while True:
        got = host.send({'op': 'world-objects', 'principal': opener, **({'after': after} if after else {})})
        ids += got.get('ids') or []
        if not got.get('more') or not got.get('ids'):
            return ids
        after = got['ids'][-1]


def said(host, opener, card, action, fields, identity):
    """The hand's spell to a card, as a reply with no post: the host reads it as any spell."""
    reply = host.send({'op': 'world-turn', 'principal': opener, 'object': card, 'method': 'receive', 'identity': identity,
                       'argument': rec(text=lab(spell(card, action, fields)), post=lab(''))})
    return {'object': card, 'module': action, 'status': reply.get('status'), 'creator': opener, 'reply': reply}


def run(host, opener=OPENER):
    """-> (made, refusal). made: [{object, module, status, creator, reply}], refusal: text if genesis already ran."""
    have = set(existing(host, opener))
    taken = [name for name, _, _ in seeds(opener) if name in have]
    if taken:
        return [], f'genesis has already run here: {", ".join(taken)} exist'
    # The opener arrives first, so readers see their handle, not a DID fragment.
    arrived = host.send({'op': 'world-arrive', 'principal': 'transport', 'did': opener, 'handle': HANDLE})
    if arrived.get('status') == 'error':
        return [], 'the opener could not arrive: ' + str(arrived.get('message'))
    made = []
    for name, package, seed in seeds(opener):
        reply = create(host, opener, name, package, 'genesis-' + name, seed, LAWS.get(package, lambda _: None)(opener))
        made.append({'object': name, 'module': package, 'status': reply.get('status'),
                     'creator': (reply.get('receipt') or {}).get('identity', {}).get('principal'), 'reply': reply})
        if reply.get('status') != 'created':
            return made, None
    # `kinds` is given its make (`shape`), then makes the root kinds and the town's (docs/CATALOGUE.md §5).
    kinds = next(m for m in made if m['object'] == 'kinds')
    kinds['shape'] = host.send({'op': 'world-turn', 'principal': opener, 'object': 'kinds', 'method': 'shape', 'argument': rec(object=lab('kinds')),
                                'identity': 'genesis-kinds-shape'}).get('status')
    kinds['made'] = [host.send({'op': 'world-turn', 'principal': opener, 'object': 'kinds', 'method': 'make', 'identity': 'genesis-kind-' + name,
                                'argument': rec(name=lab(name), of=lab(of), form=lab(form), head=lab(head), law=lab(law), body=lab(body_of(body)))}).get('status')
                     for name, of, form, head, law, body in KINDS]
    commonplace_ = next(m for m in made if m['object'] == 'commonplace')
    commonplace_['body'] = host.send({'op': 'world-reprogram', 'principal': opener, 'identity': 'genesis-commonplace-body',
                                      'object': 'commonplace', 'version': 0, 'package': body_of('commonplace'), 'mode': 'extend'}).get('status')
    # The hand's things, each by its spell; then the garden cites its weather.
    for kind, fields in HANDS:
        made.append(said(host, opener, kind, 'make', fields, 'genesis-' + dict(fields)['id']))
    made.append(said(host, opener, 'garden', 'door', [('label', 'weather'), ('to', 'weather')], 'genesis-garden-weather'))
    # The world moves when nobody posts (docs/OFFERING.md §4): the opener's wake, made at arrival before the
    # garden existed, hears each thing the garden grows now, and ticks the tide every 60 clock minutes.
    wake = 'wake/' + opener
    tide = next(m for m in made if m['object'] == 'tide')
    tide['wake'] = [host.send({'op': 'world-turn', 'principal': opener, 'object': wake, 'method': method, 'argument': argument,
                               'identity': 'genesis-' + method}).get('status')
                    for method, argument in (('arrived', rec()),
                                             ('schedule', rec(at=nat(0), every=nat(60), action={'tag': 'variant', 'label': 'call', 'payload': rec(card=lab('tide'), method=lab('tick'))})))]
    library = next(m for m in made if m['object'] == 'library')
    library['pages'] = [host.send({'op': 'world-turn', 'principal': opener, 'object': 'library', 'method': 'shelve', 'identity': 'genesis-shelve-' + name,
                                   'argument': rec(name=lab(name), kind={'tag': 'variant', 'label': kind, 'payload': rec()}, title=lab(title),
                                                   body=lab(page_body(name)))}).get('status') for name, kind, title in PAGES]
    # One card per door: each door's object publishes its page(), which the bridge drafts as `wiki: <Door>` for the hand to post.
    for label, to, _ in DOORS:
        if to and any(m['object'] == to for m in made):
            page = host.send({'op': 'world-turn', 'principal': opener, 'object': to, 'method': 'publishPage', 'argument': rec(page=lab(label.capitalize())),
                              'identity': 'genesis-page-' + to})
            next(m for m in made if m['object'] == to)['page'] = {'door': label, 'status': page.get('status'), 'reply': page}
    return made, None


def main(argv=None):
    ap = argparse.ArgumentParser(prog='genesis.py')
    ap.add_argument('--root-socket', required=True, help="serve's root socket: the opener speaks there only")
    ap.add_argument('--world', default='town')
    ap.add_argument('--opener', default=OPENER, help="the world's opener (default: ember)")
    a = ap.parse_args(argv)
    host = HostClient(a.root_socket, a.world)
    try:
        made, refusal = run(host, a.opener)
    finally:
        host.close()
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    for m in made:
        print(json.dumps({k: m[k] for k in ('object', 'module', 'status')} | ({} if m['status'] in ('created', 'admitted') else {'reply': m['reply']})))
    for m in made:
        page = m.get('page')
        if page and page['status'] != 'admitted':
            print(f"genesis: the {page['door']} page was not published ({m['object']}.publishPage: {json.dumps(page['reply'])[:300]})", file=sys.stderr)
    return 0 if made and all(m['status'] in ('created', 'admitted') for m in made) else 1


if __name__ == '__main__':
    sys.exit(main())
