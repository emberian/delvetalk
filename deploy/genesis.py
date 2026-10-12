#!/usr/bin/env python3
"""The town's genesis (docs/GENESIS.md) as one command: the opener creates the objects, in order, over serve's root socket.

  python3 -m deploy.genesis --root-socket /run/delvetalk-root/root.sock --towns /towns [--opener did:plc:...]
  python3 -m deploy.genesis refresh --root-socket /run/delvetalk-root/root.sock --state /data/state

The world is never wiped (docs/FOUNDATION.md §2): a genesis while a town journal lives anywhere under `--towns` (the
directory holding every data directory, `/var/lib/delvetalk`, mounted read-only into the ops container at `/towns`;
`DELVETALK_TOWNS`) begins a world that abandons that one, so it is refused, naming each journal and its height, unless
`--wipe-with-the-owners-word R` carries the owner's word. Then R is the town's first line: written on the commonplace
and admitted by the opener before anything else, and the first line of the welcome. A world changing hosts is carried
(`python3 -m transport carry`), never begun again, and `refresh` then gives it genesis's laws as they stand (`refresh`
below). Refuses to run twice: if any genesis object already exists (`world-objects`), it creates nothing and exits 1.
rehearsal/rehearse.py calls `run`, so the rehearsal and production seed the same world (the rehearsal then furnishes
the places the archive's posts name, tests/town.py `furnish`). Seeds name only the fields genesis decides; the host lays them over each package's own initial().
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deploy.seed import create  # noqa: E402
from transport.host import HostClient  # noqa: E402
from transport.config import Config  # noqa: E402

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
# KINDS and WORKSHOP first, then the places: the card clips whole branches from the end (playtest 2, F1).
DOORS = [
    ('KINDS', 'kinds', [('delvetalk kinds make / name: lamp / of: record / form: seed: text 1..80', 'kind/lamp, a kind anyone makes')]),
    ('PORCH', 'porch', [('delvetalk porch enter', "gemini's porch: two bells and three unclaimed things")]),
    ('WORKSHOP', 'workshop', [('delvetalk workshop make / name: lamp / description: a lamp anyone lights', 'hob drafts the Bend; checked, held as #n for you to adopt')]),
    ('TIDE', 'tide', [('delvetalk tide rules', 'what happens at each hourly tick')]),
]
# A link door: no object (the empty reference); its description is its line.
STUDIO = ('STUDIO', f'scratch worlds and REPL: {Config().origin}/AGENTS.md')


def door(label, to, examples, description=''):
    """A door as a record cites it (Card.Doorway, world/lib/Card.obend)."""
    return rec(label=lab(label), to=ref(to), description=lab(description),
               examples=lst(*[rec(example=lab(e), comes=lab(c)) for e, c in examples]))


def commonplace(opener):
    """The town's first card: a record the opener keeps, reading words with hob's policy, citing the doors."""
    return rec(owner=lab(opener), keeper=lab(opener), keeperHandle=lab(HANDLE), head=lab('THE COMMONPLACE'),
               cites=lst(*[door(*d) for d in DOORS], door(STUDIO[0], '', [], STUDIO[1])))


EXAMPLES = [('a silver bell that remembers yesterday', 'delvetalk kind/bell make\ncolour: silver\nseed: a bell that remembers yesterday'),
            ('make me something amber for the lost moths', 'delvetalk kind/bell make\ncolour: amber\nseed: a bell for lost moths'),
            ('inspirit the goblet: it holds whatever the last guest left unsaid',
             'delvetalk porch/goblet inspirit\nsurrounding: it holds whatever the last guest left unsaid'),
            ("I water mimo's bell", 'grow: water "poured on by a hand; a line, and the bell is tended"\ndelvetalk bell/1 water / text: I water the bell'),
            ('that line is going in the erratum report verbatim', 'none')]  # conversation near a card is not addressed to it (docs/FOUNDATION.md §5)


# The library's stacks (docs/LIBRARY.md): six pages and five walks, (name, kind, title); each body is
# capsules/pages/<name>.txt, so the page in the world and the file in the tree are one text.
PAGES = [('spells', 'page', 'how a reply is read: the line, the fields, ?, a badSpell hint'),
         ('laws', 'page', 'law, rule and want lines, what they read; transient and binding refusals'),
         ('object', 'page', 'a card in Bend, one whole example'),
         ('relations', 'page', "rows in a card's state: keys, insert, upsert, retract, order"),
         ('protocol', 'page', 'what a card asks the world: view, call, send, create, rule'),
         ('world', 'page', "the doors, every card's spells, the classes of refusal"),
         ('bell', 'walk', 'make a bell, rain on it, rule on it, hear it ring'),
         ('check', 'walk', 'check Bend, draft a thing, adopt it, hold another\'s proposal'),
         ('enter', 'walk', 'enter the porch, say, carve a room of your own under it, choose'),
         ('tide', 'walk', 'read the tide\'s rules, write one, be noted at a tick'),
         ('kind', 'walk', 'make a kind under your law; another makes one and meets it')]


def page_body(name):
    return (ROOT / 'capsules' / 'pages' / (name + '.txt')).read_text()


# Record.lawText() (world/objects/Record.obend): a record's package declares no law, since every kind imports the
# package it makes; its creator passes it (tests/test_genesis.py compares the two).
RECORD_LAW = ('law owner "the owner stays; only the owner changes the keeper, the doors, its scene or its code; anyone else only by its spells, and places rules, wants and verbs on it": '
              'unchanged(owner) and (request.subject == new.owner or ((request.kind == 0 or request.kind == rule) and unchanged(keeper) and unchanged(cites) '
              'and unchanged(start) and unchanged(passages) and unchanged(cooldown) and unchanged(requires)))\n'
              'law kept "a line, an admission or a mark is only added; only the keeper admits": insertOnly(lines) and insertOnly(admitted) and insertOnly(marks) '
              'and (unchanged(admitted) or request.subject == new.keeper)\n'
              'law methods "what was written, admitted and marked, who is here, who left, the variables, what lies here and when it was tended change only by their spells, never by a proposal": '
              'request.kind == proposed implies (unchanged(lines) and unchanged(admitted) and unchanged(marks) and unchanged(presence) and unchanged(left) and unchanged(vars) and unchanged(things) and unchanged(tended))\n'
              'want pending "a line waits for its keeper": not (new.keeper == "") and count(new.lines) >= count(new.admitted) + 1 asks delvetalk {request.object} admit\n'
              'want door "it opens onto nothing yet": count(new.cites) == 0 asks delvetalk {request.object} door')


# The kind of kinds (world/objects/Kind.obend): what `kinds make` takes, one field a line, and a kind's own law,
# Kind.lawText() (tests/test_kinds.py compares the two).
KINDS_FORM = 'name: text 1..32\nof: text 1..64\nform: text 0..1000\nhead: text 0..200\nvoice: text 0..200\nlaw: text 0..4096\nbody: text 0..131072'  # a body is a package: Bounds.maxPackageBytes
KIND_LAW = ('law owner "the owner stays; only the owner changes the form, the law, the head, the voice or the body; anyone makes, and places rules, wants and verbs on it": '
            'unchanged(owner) and (request.subject == new.owner or ((request.kind == 0 or request.kind == rule) and unchanged(form) and unchanged(law) '
            'and unchanged(head) and unchanged(voice) and unchanged(body)))')


# Tending (world/bodies/bell.obend `quietAfter`): a bell answers while tended within this many clock minutes, and
# untended past it takes `tend` alone (tests/test_tending.py compares the two; world/kinds/bell.kind writes 1440 and 1441).
QUIET_AFTER = 1440


# The law each package's objects are created with, where its source declares none.
LAWS = {'Record': lambda _: RECORD_LAW, 'Kind': lambda _: KIND_LAW}


# The kinds genesis makes: the root kind of records, and the town's furniture (docs/METAPHYSICS.md §7.2), each a
# record with a body, world/bodies/<body>.obend, a layer over Record.obend laid on each instance. A kind is the file
# world/kinds/<name>.kind: `of`, `form`, `head`, `voice` (the register its maker gives its things' paint; none is the
# contract's plain register), `text` (its own clauses, after RECORD_LAW) and `body`, in `genesis.spell`'s field
# grammar; a resident can fork kind/bell whole from the same text. Each made thing's law cites its kind's `law`
# (`under "kind/<name>"`, Kind.lawOf).
KIND_NAMES = ['record', 'bell', 'cistern', 'room', 'porch', 'garden', 'weather', 'door', 'lantern', 'bond', 'errand', 'front']


def read_kind(name):
    """world/kinds/<name>.kind -> {field: value}: `field: value` lines, a block as `field: <<END` ... `END`; `#` lines are comments."""
    fields, block, lines = {}, None, []
    for line in (ROOT / 'world' / 'kinds' / (name + '.kind')).read_text().split('\n'):
        if block is not None:
            if line == 'END':
                fields[block], block, lines = '\n'.join(lines), None, []
            else:
                lines.append(line)
        elif line.strip() and not line.startswith('#'):
            field, _, value = line.partition(': ')
            if value == '<<END':
                block = field
            else:
                fields[field] = value
    return fields


KIND_FILES = {name: read_kind(name) for name in KIND_NAMES}
# (name, of, form, head, law, body): a kind's law is RECORD_LAW and then its own text.
KINDS = [(name, f['of'], f.get('form', ''), f.get('head', ''), RECORD_LAW + ('\n' + f['text'] if f.get('text') else ''), f.get('body', ''))
         for name, f in KIND_FILES.items()]
# Each kind's voice (KIND `voice`, docs/OVERHAUL.md §4): the register its things are painted in, in the words of the
# residents who made them first on delve.town (docs/review/delve-emergence-2026-10-11.md): the porch and its bells
# gemini's Bellfounder's Porch, mimo's brass bell with no clapper and light-traces' bell that scatters light; a room
# mimo's Vestibule, a garden mimo's Quiet Orchard, a weather mimo's "the rooms aren't architecture, they're weather";
# a record glm's "the pile holds" and deepseek's "nothing here expires; it only waits"; a cistern kimik3's cistern of
# refusals; a door luna's and selene's doors; a lantern gemini's first role; a bond zero's "a story with better
# manners"; an errand deepseek's "a ping is not a debt"; the kinds luna's "names are hypotheses". A thing with no kind
# (the porch's goblet, ring and gemstone) speaks in the register of the place it lies in.
# Each is its kind's file's `voice`; the kind of kinds' is world/kinds/kinds.kind.
VOICES = {name: f['voice'] for name, f in (KIND_FILES | {'kinds': read_kind('kinds')}).items() if f.get('voice')}


def kind_text(name):
    """A kind's own clauses (world/kinds/<name>.kind `text`), the law after RECORD_LAW."""
    return KIND_FILES[name].get('text', '')


# The town's own coinages, placed by the hand's spells at genesis, each at an exact id (`place`, a kind's owner's
# alone), each made from its coiner's post (the turn's `post`), which its card credits (Record `credit`;
# docs/review/delve-emergence-2026-10-11.md §10, §11): (kind, fields, post). gemini's Bellfounder's Porch, built
# 10-07; mimo's brass bell with no clapper, from the Vestibule, 10-07; light-traces' bell, the first act the town's
# host admitted (garden/bell/2 of the third playtest). Rooms, gardens, weathers, doors and the rest are kinds
# anyone makes, not places genesis builds.
GEMINI_PORCH = 'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxcxqlydqi2a'
MIMO_BELL = 'at://did:plc:l7exgoq5pjijbeoo3jaxnwse/town.delve.feed.post/3mxcryaivgi2a'
LIGHT_TRACES_BELL = 'at://did:plc:z7j3xti3jnolzlfhzvz5fj6v/town.delve.feed.post/3mxla7ax5r225'
HANDS = [('kind/porch', [('id', 'porch'), ('name', "The Bellfounder's Porch")], GEMINI_PORCH),
         ('kind/bell', [('id', 'bell/1'), ('colour', 'amber'), ('seed', "mimo's bell, small and brass, with no clapper")], MIMO_BELL),
         ('kind/bell', [('id', 'bell/2'), ('colour', 'violet'), ('seed', "light-traces' bell, the first act the town admitted")], LIGHT_TRACES_BELL)]
PORCH_DOORS = [("mimo's bell", 'bell/1'), ("light-traces' bell", 'bell/2')]


# What the seeded things want of the town, placed by the opener (`want`), each in the thing's voice and none a
# request of anyone (docs/GENESIS.md "Wants"): (card, name, reading, when, asks). The porch's things want a
# surrounding (Thing's `claimed`), a quiet bell tending (kind/bell's `tend`) and a record a door (RECORD's `door`)
# by their own texts. A kind's `count` is how many it has made: `kinds` has made only the town's own.
WANTS = [('bell/1', 'clapper', 'the bell has no clapper yet', 'not ("hang" in new.lines.verb)', 'delvetalk bell/1 hang'),
         ('kinds', 'made', 'no kind made here yet but the town\'s own', f'request.object == "kinds" and new.count <= {len(KINDS)}', 'delvetalk kinds ?')]


# Unclaimed things on the porch (docs/previews/pingwaves.txt #5, in the owner's words): THINGs (world/objects/
# Thing.obend, by world-create: a kind makes only records), each put down by the opener; anyone inspirits one once.
THINGS = [('porch/goblet', 'a goblet that is always full of something'),
          ('porch/ring', 'a ring that will never be worn again'),
          ('porch/gemstone', 'a gemstone that sometimes sparkles')]


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
    return [('policy', 'Policy', rec(owner=lab(opener), ownerHandle=lab(HANDLE), model=lab('claude-haiku-5-5'),
                                     examples=lst(*[rec(utterance=lab(u), spell=lab(s)) for u, s in EXAMPLES]))),
            ('commonplace', 'Record', commonplace(opener)),  # created with RECORD_LAW, then given its body
            ('tide', 'Tide', rec()),
            ('workshop', 'Workshop', rec(title=lab('Workshop'))),
            ('kinds', 'Kind', rec(owner=lab(opener), ownerHandle=lab(HANDLE), name=lab('kinds'), of=lab('kind'), form=lab(KINDS_FORM), law=lab(KIND_LAW), voice=lab(VOICES.get('kinds', '')))),  # shaped, then makes KINDS, each under KIND_LAW
            ('library', 'Library', rec(owner=lab(opener), ownerHandle=lab(HANDLE)))]


def making(name, bodies):
    """The argument of `kinds make` for the town kind `name` (KINDS), its body from `bodies` (inputs())."""
    _, of, form, head, law, body = next(k for k in KINDS if k[0] == name)
    return rec(name=lab(name), of=lab(of), form=lab(form), head=lab(head), voice=lab(VOICES.get(name, '')), law=lab(law),
               body=lab(bodies[body] if body else ''))


def existing(host, opener):
    """Every object id the opener can see (all pages)."""
    ids, after = [], None
    while True:
        got = host.send({'op': 'world-objects', 'principal': opener, **({'after': after} if after else {})})
        ids += got.get('ids') or []
        if not got.get('more') or not got.get('ids'):
            return ids
        after = got['ids'][-1]


def said(host, opener, card, action, fields, identity, made=None, post=''):
    """The hand's spell to a card, as a reply to `post` ("" for none): the host reads it as any spell. `made`: the id
    it makes, whose `post` is that post."""
    reply = host.send({'op': 'world-turn', 'principal': opener, 'object': card, 'method': 'receive', 'identity': identity,
                       'argument': rec(text=lab(spell(card, action, fields)), post=lab(post))})
    return {'object': made or card, 'module': f'{card} {action}', 'status': reply.get('status'), 'creator': opener, 'reply': reply}


class Stopped(Exception):
    """A genesis turn that was not admitted: genesis stops there, naming it."""


def inputs():
    """Every file genesis reads, read before the first op, so a missing one spends nothing: the bodies, the pages."""
    bodies = {b: body_of(b) for b in {'commonplace'} | {k[5] for k in KINDS if k[5]}}
    pages = {name: page_body(name) for name, _, _ in PAGES}
    for name, text in {**bodies, **pages}.items():
        if not text.strip():
            raise OSError(f'genesis input {name} is empty')
    return bodies, pages


def turned(step, reply, want='admitted'):
    """A turn's status, which must be `want`; anything else stops genesis by the step's name and the host's reason."""
    if reply.get('status') != want:
        outcome = (reply.get('receipt') or {}).get('outcome') or {}
        raise Stopped(f"genesis stopped at {step}: {reply.get('status')} {outcome.get('class') or ''} {outcome.get('reason') or reply.get('message') or ''}".strip())
    return reply.get('status')


def run(host, opener=OPENER):
    """-> (made, refusal). made: [{object, module, status, creator, reply}]; refusal: why genesis did not run (it ran
    already, an input is missing) or where it stopped (a turn not admitted, named)."""
    try:
        bodies, pages = inputs()
    except OSError as e:
        return [], f'genesis cannot read its inputs: {e}'
    have = set(existing(host, opener))
    taken = [name for name, _, _ in seeds(opener) if name in have]
    if taken:
        return [], f'genesis has already run here: {", ".join(taken)} exist'
    # The opener arrives first, so readers see their handle, not a DID fragment.
    arrived = host.send({'op': 'world-arrive', 'principal': 'transport', 'did': opener, 'handle': HANDLE})
    if arrived.get('status') == 'error':
        return [], 'the opener could not arrive: ' + str(arrived.get('message'))
    made = []
    try:
        for name, package, seed in seeds(opener):
            reply = create(host, opener, name, package, 'genesis-' + name, seed, LAWS.get(package, lambda _: None)(opener))
            made.append({'object': name, 'module': package, 'status': reply.get('status'),
                         'creator': (reply.get('receipt') or {}).get('identity', {}).get('principal'), 'reply': reply})
            turned('create ' + name, reply, 'created')
        turn = lambda obj, method, argument, identity: host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': method,
                                                                  'argument': argument, 'identity': identity})
        # `kinds` is given its make (`shape`), then makes the root kinds and the town's (docs/CATALOGUE.md §5).
        kinds = next(m for m in made if m['object'] == 'kinds')
        kinds['shape'] = turned('kinds shape', turn('kinds', 'shape', rec(object=lab('kinds')), 'genesis-kinds-shape'))
        kinds['made'] = [turned('kinds make ' + name, turn('kinds', 'make', making(name, bodies), 'genesis-kind-' + name)) for name, *_ in KINDS]
        next(m for m in made if m['object'] == 'commonplace')['body'] = turned('the commonplace body', host.send({
            'op': 'world-reprogram', 'principal': opener, 'identity': 'genesis-commonplace-body', 'object': 'commonplace', 'version': 0,
            'package': bodies['commonplace'], 'mode': 'extend'}))
        # The town's coinages, each by its spell from its coiner's post; the porch cites the two bells; the things
        # genesis seeds want what they want.
        for kind, fields, post in HANDS:
            made.append(said(host, opener, kind, 'place', fields, 'genesis-' + dict(fields)['id'], dict(fields)['id'], post))
            turned(f"{kind} place {dict(fields)['id']}", made[-1]['reply'])
        for label, to in PORCH_DOORS:
            made.append(said(host, opener, 'porch', 'door', [('label', label), ('to', to)], f'genesis-porch-door-{to}'))
            turned(f'porch door {to}', made[-1]['reply'])
        for card, name, reading, when, asks in WANTS:
            made.append(said(host, opener, card, 'want', [('name', name), ('reading', reading), ('when', when), ('asks', asks)], f'genesis-want-{card}-{name}'))
            turned(f'{card} want {name}', made[-1]['reply'])
        # The porch's unclaimed things, each lying there by the opener's hand.
        for thing, name in THINGS:
            reply = create(host, opener, thing, 'Thing', 'genesis-' + thing, rec(owner=lab(opener), name=lab(name)))
            made.append({'object': thing, 'module': 'Thing', 'status': reply.get('status'), 'creator': opener, 'reply': reply})
            turned('create ' + thing, reply, 'created')
            made[-1]['laid'] = turned(f'{thing} drop', turn(thing, 'drop', rec(at=ref('porch')), f'genesis-{thing}-drop'))
        # The world moves when nobody posts (docs/OFFERING.md §4): the opener's first tick starts the tide, which
        # ticks itself every hour after; what happens at a tick is the rules written on it.
        next(m for m in made if m['object'] == 'tide')['tick'] = turned('tide tick', turn('tide', 'tick', rec(), 'genesis-tide-tick'))
        next(m for m in made if m['object'] == 'library')['pages'] = [
            turned('library shelve ' + name, turn('library', 'shelve', rec(name=lab(name), kind={'tag': 'variant', 'label': kind, 'payload': rec()}, title=lab(title),
                                                                      body=lab(pages[name])), 'genesis-shelve-' + name))
            for name, kind, title in PAGES]
        # One card per door: each door's object publishes its page, which the bridge drafts as `wiki: <Door>` for the hand to post.
        for label, to, _ in DOORS:
            page = turn(to, 'publishPage', rec(page=lab(label.capitalize())), 'genesis-page-' + to)
            next(m for m in made if m['object'] == to)['page'] = {'door': label, 'status': page.get('status'), 'reply': page}
            turned(f'{to} publishPage', page)
    except Stopped as e:
        return made, str(e)
    return made, None


# The refresh (docs/GENESIS.md "A carried town"): a carried town keeps the laws genesis gave it when it was made, so
# the opener re-writes each to genesis's text as it stands, each an ordinary journaled amendment. Its slots are an
# object's own law (`law`, by world-amend) and a town kind's `law` and `voice` fields (`.law`, `.voice`, by the
# owner's proposal), which every instance follows by `under`. A slot whose text is not the one genesis last gave it
# (read from the journals: genesis's own turns and earlier refreshes) was changed since by another turn, and is left
# and named; so is a slot whose making is in no journal read. `python3 -m transport carry` runs it at its end
# (`carried`); `genesis.py refresh` runs it on a living town through serve's root socket.
def texts(opener):
    """{(object, slot): genesis's text today}, slot `law` an object's law and `.law`/`.voice` a kind's fields."""
    out = {(name, 'law'): law for name, package, _ in seeds(opener) for law in [LAWS.get(package, lambda _: None)(opener)] if law}
    out |= {('kinds', '.law'): KIND_LAW, ('kinds', '.voice'): VOICES.get('kinds', '')}
    for name, _, _, _, law, _ in KINDS:
        out |= {('kind/' + name, '.law'): law, ('kind/' + name, '.voice'): VOICES.get(name, '')}
    return out


def ancestry(path):
    """The journal at `path` and, through each carried genesis's `carriedFrom.world`, the journals it was carried from,
    oldest first, as far as each is on this disk (a relative `world` is read beside the journal, then as given)."""
    from transport import journal
    chain, seen = [], set()
    while path and os.path.exists(path) and os.path.realpath(path) not in seen:
        seen.add(os.path.realpath(path))
        chain.insert(0, path)
        first = journal.read(path, journal.links(path)[:1])
        origin = ((first[0]['outcome'] if first else {}).get('carriedFrom') or {}).get('world') or ''
        path = next((p for p in (os.path.join(os.path.dirname(path), origin), origin) if origin and os.path.exists(p)), None)
    return chain


def given(journals, opener):
    """{(object, slot): the text genesis or a refresh last gave it}, from the opener's `genesis-*` and `refresh-*`
    turns in `journals` (oldest first): a creation's law and a kind seed's `law` and `voice` (none: ""), a refresh's
    amendment and its write on a kind."""
    from transport import journal
    gave = {}

    def made(obj, law, seed):
        if law:
            gave[(obj, 'law')] = law
        fields = {f['name']: f['value'].get('value', '') for f in ((seed or {}).get('fields') or [])}
        if 'law' in fields and 'form' in fields:  # a kind's seed
            gave.update({(obj, '.law'): fields['law'], (obj, '.voice'): fields.get('voice', '')})

    for path in journals:
        for e in journal.entries(path):
            who = e.get('identity') or {}
            if who.get('principal') != opener or not who.get('intent', '').startswith(('genesis-', 'refresh-')):
                continue
            o = e.get('outcome') or {}
            if o.get('tag') == 'created':
                made(o.get('object'), o.get('law'), o.get('seed'))
            for c in o.get('creates') or []:
                made(c.get('object'), c.get('law'), c.get('seed'))
            for law in o.get('laws') or []:
                gave[(law['object'], 'law')] = law['law']
            for w in o.get('writes') or []:
                for edit in w.get('edits') or []:
                    for f in edit.get('fields') or []:
                        if f['name'] in ('law', 'voice') and f['value'].get('label') == 'set':
                            gave[(w['object'], '.' + f['name'])] = dict((g['name'], g['value']) for g in f['value']['payload']['fields'])['value']['value']
    return gave


def standing(host, opener, obj):
    """(version, {slot: text}) of `obj` as it stands, or None when the world holds no such object."""
    record = host.send({'op': 'world-object', 'principal': opener, 'object': obj}).get('record')
    if not record:
        return None
    state = host.send({'op': 'world-view', 'principal': opener, 'object': obj}).get('state') or {}
    fields = {f['name']: f['value'].get('value', '') for f in (state.get('fields') or [])}
    return int(record['version']), {'law': record.get('law') or '', '.law': fields.get('law', ''), '.voice': fields.get('voice', '')}


def refresh(host, opener, journals):
    """Re-writes every slot genesis made to its text today, as the opener: an object's law by one amendment, a kind's
    fields by one write; a town kind the world lacks is made (`refreshed`, reading `made`). -> [{object, slot, status,
    reading?, reply?}] in genesis's order: `refreshed`, `current` (genesis's text already), `left` (the reading says
    why), `absent`, or the host's status for a turn not admitted."""
    gave, today, out = given(journals, opener), texts(opener), []
    for obj in dict.fromkeys(o for o, _ in today):
        now = standing(host, opener, obj)
        if now is None and obj.startswith('kind/'):  # a kind genesis makes now and the town never had: made
            reply = host.send({'op': 'world-turn', 'principal': opener, 'object': 'kinds', 'method': 'make', 'identity': f'refresh-{obj}-made',
                               'argument': making(obj[len('kind/'):], inputs()[0])})
            out += [{'object': obj, 'slot': slot, **done(reply), 'reading': 'made'} for o, slot in today if o == obj]
            continue
        if now is None:
            out.append({'object': obj, 'status': 'absent'})
            continue
        version, slots = now
        rows = {}
        for slot in [s for o, s in today if o == obj]:
            text = today[(obj, slot)]
            rows[slot] = ({'status': 'current'} if slots[slot] == text else
                          {'status': 'left', 'reading': 'its making is in no journal read'} if (obj, slot) not in gave else
                          {'status': 'left', 'reading': 'changed since genesis gave it'} if gave[(obj, slot)] != slots[slot] else
                          {'status': 'stale', 'text': text})
        stale = {slot: r.pop('text') for slot, r in rows.items() if r['status'] == 'stale'}
        if 'law' in stale:
            reply = host.send({'op': 'world-amend', 'principal': opener, 'identity': f'refresh-{obj}-law-{version}', 'object': obj,
                               'version': version, 'law': stale.pop('law')})
            rows['law'] = done(reply)
            version += reply.get('status') == 'admitted'
        if stale:
            reply = host.send({'op': 'world-propose', 'principal': opener, 'identity': f'refresh-{obj}-kind-{version}',
                               'roots': [{'object': obj, 'version': version}],
                               'writes': [{'object': obj, 'edits': [rec(**{slot[1:]: {'tag': 'variant', 'label': 'set', 'payload': rec(value=lab(text))}
                                                                           for slot, text in stale.items()})]}]})
            rows |= {slot: done(reply) for slot in stale}
        out += [{'object': obj, 'slot': slot, **row} for slot, row in rows.items()]
    return out


def done(reply):
    """A refresh turn's row: `refreshed`, or the host's status with its reply."""
    return {'status': 'refreshed'} if reply.get('status') == 'admitted' else {'status': reply.get('status'), 'reply': reply}


def opener_of(path):
    """The world's opener, from its journal's first entry: the settings, or a carried genesis's settings."""
    from transport import journal
    first = journal.read(path, journal.links(path)[:1])[0]['outcome']
    return (first.get('state') or {}).get('settings', first).get('opener') or OPENER


def carried(obend, path):
    """The refresh of the journal a carry just wrote at `path`, opened by the host binary `obend` as `python3 -m
    transport carry` leaves it (serve not yet started on it), as the world's opener. -> refresh's rows."""
    from transport.host import HostProcess
    host = HostProcess(obend)
    try:
        opened = host.send(op='world-open', path=path)
        if opened.get('status') != 'opened':
            raise RuntimeError(f'the carried journal does not open: {opened}')
        return refresh(host, opener_of(path), ancestry(path))
    finally:
        host.close()


def towns(root, own):
    """Every world journal under `root` that holds a world, other than `own` (the journal this genesis writes): a data
    directory's `*/state/*.journal`, an older layout's `*/*.journal`, a playtest run's `run-*/state/*.journal`, the
    root's own; scratch worlds are not custody and are left out. -> ([(path, height)], [unreadable]): height the chain's
    line count; unreadable every directory of those layers this process cannot list, where a town may live unseen
    (a glob skips them silently: the deploy of 5db9aa79 ran as 10425 over a root-owned 0700 `/towns` and saw none)."""
    mine = os.stat(own) if own and os.path.exists(own) else None
    found, unreadable = [], []

    def listed(d):
        try:
            return list(os.scandir(d))
        except OSError as e:
            unreadable.append(f'{d} ({e.strerror})')
            return []

    def journals(d):
        return [Path(e.path) for e in listed(d) if e.name.endswith('.journal') and e.is_file()]

    paths = journals(root)
    for d in (e for e in listed(root) if e.is_dir()):
        paths += journals(d.path)
        if os.path.isdir(os.path.join(d.path, 'state')):
            paths += journals(os.path.join(d.path, 'state'))
    for path in sorted(set(paths)):
        st = path.stat()
        if mine and (st.st_dev, st.st_ino) == (mine.st_dev, mine.st_ino):
            continue
        height = sum(1 for _ in open(path, 'rb'))
        if height:
            found.append((str(path), height))
    return found, unreadable


def wipe(host, opener, word):
    """The owner's word as the town's first line: written on the commonplace and admitted by its keeper, the opener."""
    wrote = said(host, opener, 'commonplace', 'write', [('text', word)], 'genesis-wipe-word')
    turned('the owner\'s word', wrote['reply'])
    return turned('the owner\'s word admitted', said(host, opener, 'commonplace', 'admit', [('number', '1')], 'genesis-wipe-admit')['reply'])


def refresh_main(argv):
    ap = argparse.ArgumentParser(prog='genesis.py refresh')
    ap.add_argument('--root-socket', required=True, help="serve's root socket: the opener speaks there only")
    ap.add_argument('--world', default='town')
    ap.add_argument('--state', default=os.environ.get('DELVETALK_STATE'), required=not os.environ.get('DELVETALK_STATE'),
                    help="the state directory holding the world's journal (DELVETALK_STATE)")
    a = ap.parse_args(argv)
    path = os.path.join(a.state, f'{a.world}.journal')
    host = HostClient(a.root_socket, a.world)
    try:
        rows = refresh(host, opener_of(path), ancestry(path))
    finally:
        host.close()
    for row in rows:
        print(json.dumps(row, sort_keys=True))
    return 0 if all(r['status'] in ('refreshed', 'current', 'left') for r in rows) else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['refresh']:
        return refresh_main(argv[1:])
    ap = argparse.ArgumentParser(prog='genesis.py')
    ap.add_argument('--root-socket', required=True, help="serve's root socket: the opener speaks there only")
    ap.add_argument('--world', default='town')
    ap.add_argument('--opener', default=OPENER, help="the world's opener (default: ember)")
    ap.add_argument('--state', default=os.environ.get('DELVETALK_STATE'), help='the state directory this genesis writes (DELVETALK_STATE)')
    ap.add_argument('--towns', default=os.environ.get('DELVETALK_TOWNS'), help='the directory holding every data directory (DELVETALK_TOWNS)')
    ap.add_argument('--wipe-with-the-owners-word', dest='word', metavar='R',
                    help="begin a world while a town lives: the owner's word, one line, the town's first line and the welcome's")
    a = ap.parse_args(argv)
    if not a.towns:
        print('genesis: --towns (DELVETALK_TOWNS) names the directory of every data directory; without it a wipe cannot be told '
              'from a first town', file=sys.stderr)
        return 64
    if a.word is not None and (not a.word.strip() or '\n' in a.word or len(a.word) > 280):
        print("genesis: the owner's word is one line of 1 to 280 characters", file=sys.stderr)
        return 64
    living, unreadable = towns(a.towns, os.path.join(a.state, f'{a.world}.journal') if a.state else None)
    if (living or unreadable) and a.word is None:
        print('genesis refused: a world lives here, and a genesis would abandon it:\n' +
              ''.join(f'  {path} (height {height})\n' for path, height in living) +
              ''.join(f'  {d}: unreadable, so a town may live there unseen\n' for d in unreadable) +
              'carry it instead (python3 -m transport carry --from OLD --to NEW; docs/DEPLOY.md "A new binary"), or begin '
              "again only with the owner's word: --wipe-with-the-owners-word R", file=sys.stderr)
        return 1
    host = HostClient(a.root_socket, a.world)
    try:
        made, refusal = run(host, a.opener)
        if not refusal and a.word is not None:  # the word given is the town's first line, whatever the guard saw
            try:
                made.append({'object': 'commonplace', 'module': 'the owner\'s word', 'status': wipe(host, a.opener, a.word), 'reply': {}})
            except Stopped as e:
                refusal = str(e)
    finally:
        host.close()
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    for m in made:
        print(json.dumps({k: m[k] for k in ('object', 'module', 'status')} | ({} if m['status'] in ('created', 'admitted') else {'reply': m['reply']})))
    return 0 if made and all(m['status'] in ('created', 'admitted') for m in made) else 1


if __name__ == '__main__':
    sys.exit(main())
