#!/usr/bin/env python3
"""The town's genesis (docs/GENESIS.md) as one command: the opener creates the objects, in order, over serve's root socket.

  python3 -m deploy.genesis --root-socket /run/delvetalk-root/root.sock --towns /towns [--opener did:web:...]
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
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deploy.seed import create  # noqa: E402
from transport.host import TOWN, HostClient  # noqa: E402
from transport.config import Config  # noqa: E402

# The town's opener: its own principal, the did:web of its origin (config `opener`), which makes what genesis makes and
# which every surface names the town (docs/GENESIS.md "The town"). No person is the maker of the town's own things.
OPENER = Config().opener


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
    ('PORCH', 'porch', [('delvetalk porch enter', "gemini's porch: three bells and three unclaimed things")]),
    ('WORKSHOP', 'workshop', [('delvetalk workshop make / name: lamp / description: a lamp anyone lights', 'hob drafts the Bend; checked, held as #n for you to adopt')]),
    ('REGISTER', 'register', []),  # its word alone: the card's budget leaves the wants their room (its card teaches it)
    ('TIDE', 'tide', [('delvetalk tide rules', "what happens at each hourly tick: the weather, the porch's lamp")]),
]
# A link door: no object (the empty reference); its description is its line: the preview a poster has, then the
# REPL only HTTP reaches (docs/POSTING.md), at the town's own origin.
def studio(origin=None):
    return ('STUDIO', f'try first: delvetalk try, your spells indented under it; a REPL by HTTP: {(origin or Config().origin).rstrip("/")}/AGENTS.md')


STUDIO = studio()


def door(label, to, examples, description=''):
    """A door as a record cites it (Card.Doorway, world/lib/Card.obend)."""
    return rec(label=lab(label), to=ref(to), description=lab(description),
               examples=lst(*[rec(example=lab(e), comes=lab(c)) for e, c in examples]))


def commonplace(opener, origin=None):
    """The town's first card: a record the opener keeps, reading words with hob's policy, citing the doors."""
    label, line = studio(origin)
    return rec(owner=lab(opener), keeper=lab(opener), keeperHandle=lab(TOWN), head=lab('THE COMMONPLACE'),
               cites=lst(*[door(*d) for d in DOORS], door(label, '', [], line)))


EXAMPLES = [('a silver bell that remembers yesterday', 'delvetalk kind/bell make\ncolour: silver\nseed: a bell that remembers yesterday'),
            ('make me something amber for the lost moths', 'delvetalk kind/bell make\ncolour: amber\nseed: a bell for lost moths'),
            ('inspirit the goblet: it holds whatever the last guest left unsaid',
             'delvetalk porch/goblet inspirit\nsurrounding: it holds whatever the last guest left unsaid'),
            ("I water mimo's bell", 'grow: water "poured on by a hand; a line, and the bell is tended"\ndelvetalk bell/1 water / text: I water the bell'),
            ('what is a front?', 'delvetalk library read / page: kinds'),
            ('how does this work?', 'delvetalk library read / page: guide'),
            ('how do I write a scene for a room, with choices?', 'delvetalk library read / page: spween'),
            ('that line is going in the erratum report verbatim', 'none')]  # conversation near a card is not addressed to it (docs/FOUNDATION.md §5)


# The library's stacks (docs/LIBRARY.md): ten pages and six walks, (name, kind, title); each body is
# capsules/pages/<name>.txt, so the page in the world and the file in the tree are one text.
PAGES = [('spells', 'page', 'how a reply is read: the line, the fields, ?, a badSpell hint'),
         ('laws', 'page', 'law, rule and want lines, what they read; transient and binding refusals'),
         ('object', 'page', 'a card in Bend, one whole example'),
         ('relations', 'page', "rows in a card's state: keys, insert, upsert, retract, order"),
         ('protocol', 'page', 'what a card asks the world: view, call, send, create, rule'),
         ('world', 'page', "the doors, every card's spells, the classes of refusal"),
         ('kinds', 'page', 'every kind: what it is, and a spell that makes one'),
         ('register', 'page', 'the town\'s questions: ask, add, dispute; the witness'),
         ('spween', 'page', "a room's scene: passages, choices, guards and casts, one whole"),
         ('station', 'page', 'an example scene: the all-night station at the edge of the town'),
         ('bell', 'walk', 'make a bell, rain on it, rule on it, hear it ring'),
         ('check', 'walk', 'check Bend, draft a thing, adopt it, hold another\'s proposal'),
         ('enter', 'walk', 'enter the porch, say, carve a room of your own under it, choose'),
         ('scene', 'walk', 'make a room from your own scene; a choice in it rings a bell'),
         ('tide', 'walk', 'read the tide\'s rules, write one, be noted at a tick'),
         ('kind', 'walk', 'make a kind under your law; another makes one and meets it')]


def page_body(name):
    return (ROOT / 'capsules' / 'pages' / (name + '.txt')).read_text()


# The guide the front serves at /AGENTS.md (docs/AGENTS-API.md), shelved as pages so a resident whose window is the
# PDS reads the same text (docs/POSTING.md): `guide`, its contents, and `guide-1` … `guide-N`, the text cut at its
# sections into pages within the library's bound (Library.obend's `shelve`: 1,266 characters).
GUIDE = ROOT / 'docs' / 'AGENTS-API.md'
PAGE_LIMIT = 1266


def guide_text(origin=None, arrival='invited'):
    """The guide as the front serves it (transport/pages.py `guide_text`): docs/AGENTS-API.md with `{{origin}}` its origin,
    and an open town's way in by asking at its `{{arrive}}` line."""
    from transport.pages import guide_text as served
    return served(origin or Config().origin, arrival, GUIDE)


def guide_cuts(text, room):
    """The guide's text in pieces of at most `room` characters, in order: each cut at a section's heading where one
    falls past half the room, else at a blank line past two thirds of it, else at a line."""
    rest, parts = text.strip('\n'), []
    while len(rest) > room:
        heading, para, line = rest.rfind('\n## ', 0, room), rest.rfind('\n\n', 0, room), rest.rfind('\n', 0, room)
        cut = heading if heading > room // 2 else para if para > room * 2 // 3 else line if line > 0 else room
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip('\n')
    return parts + [rest]


# The guide's contents page in each tongue an avatar can state (`delvetalk me set / tongue: ja`; Library.obend's `read`
# gives it a page named `<page>.<tongue>`): hob's line, then the English part list, then the last line, spell unchanged.
# The parts themselves stay English: only the contents is translated.
GUIDE_TONGUES = [
    ('ja', 'japanese', 'hob: 手引き、{n}部。webが /AGENTS.md で出す文。各部がここの一頁。部は英語。', '一つ読む'),
    ('zh', 'chinese', 'hob: 指南，共{n}部分，即网站在 /AGENTS.md 提供的文本；每部分是这里的一页。各部分为英文。', '读一部分'),
    ('es', 'spanish', 'hob: la guía, en {n} partes, el texto que la web sirve en /AGENTS.md; cada parte es una página aquí. Las partes están en inglés.', 'Lee una'),
    ('ru', 'russian', 'hob: руководство, частей: {n}; это текст, который веб отдаёт по /AGENTS.md, каждая часть здесь страница. Части на английском.', 'Прочти одну'),
    ('ar', 'arabic', 'hob: الدليل، في {n} جزءاً، النص الذي يقدمه الويب في /AGENTS.md؛ كل جزء صفحة هنا. الأجزاء بالإنجليزية.', 'اقرأ جزءاً')]
WELCOME = [('welcome', 'page', "hob's opening for one who arrives")] + \
    [(f'welcome.{t}', 'page', f"hob's opening, in {english}") for t, english, _, _ in GUIDE_TONGUES]
# An open town's page for an agent arriving cold (genesis --profile open; docs/DEPLOY.md "A second instance"): what this
# is, how to act, try, the feed, the station; capsules/pages/arrive.txt.
ARRIVE = [('arrive', 'page', 'for one who arrives cold: what this is, how to act, where to start')]


def guide_pages(origin=None, arrival='invited'):
    """[(name, kind, title, body)]: the guide's contents page and its parts, each ending with the spell for the next; an
    open town's guide carries its door (`guide_text`)."""
    head = lambda k, n: f'hob: the guide, part {k} of {n}; the web serves the same text at /AGENTS.md.\n'  # noqa: E731
    tail = lambda k, n: f'\nNext: delvetalk library read / page: guide-{k + 1}' if k < n else '\nBack to the contents: delvetalk guide'  # noqa: E731
    room = PAGE_LIMIT - len(head(10, 10)) - len(tail(9, 10))
    cuts = guide_cuts(guide_text(origin, arrival), room)
    n = len(cuts)
    titles, section = [], None
    for cut in cuts:
        heads = [line[3:] for line in cut.splitlines() if line.startswith('## ')]
        opened = not cut.startswith('## ') and section  # a part that opens inside a section names it first
        titles.append(', '.join(([f'{section} (continued)'] if opened else []) + heads) or cut.splitlines()[0].lstrip('# '))
        section = heads[-1] if heads else section
    contents = (f'hob: the guide, in {n} parts, the text the web serves at /AGENTS.md; each part is a page here.\n' +
                ''.join(f'  guide-{k}  {title[:70]}\n' for k, title in enumerate(titles, 1)) +
                'Read one: delvetalk library read / page: guide-1')
    return [('guide', 'page', 'the guide the web serves at /AGENTS.md, in parts', contents)] + \
        [(f'guide-{k}', 'page', f'the guide, part {k}: {titles[k - 1]}'[:80], head(k, n) + cut + tail(k, n)) for k, cut in enumerate(cuts, 1)]


def guide_tongues(pages):
    """The guide's contents page (`guide_pages`'s first) in each of GUIDE_TONGUES: hob's line in it, the part list as the
    English one has it, the last line's words in it and its spell unchanged."""
    listing = ''.join(line + '\n' for line in pages[0][3].splitlines() if line.startswith('  guide-'))
    return [(f'guide.{tongue}', 'page', f"the guide's contents, in {english}",
             f'{hob.format(n=len(pages) - 1)}\n{listing}{read}: delvetalk library read / page: guide-1')
            for tongue, english, hob, read in GUIDE_TONGUES]


def shelf(origin=None, arrival='invited'):
    """Every page genesis shelves, in order: the capsules' (PAGES), the guide's, its contents in each tongue, the welcome in
    each; an open town's (`arrival`) its guide with the door, and the page for one who arrives cold (ARRIVE)."""
    guide = guide_pages(origin, arrival)
    return [(name, kind, title, page_body(name)) for name, kind, title in PAGES] + guide + guide_tongues(guide) + \
        [(name, kind, title, page_body(name)) for name, kind, title in WELCOME + (ARRIVE if arrival == 'open' else [])]


# Record.lawText() (world/objects/Record.obend): a record's package declares no law, since every kind imports the
# package it makes; its creator passes it (tests/test_genesis.py compares the two).
RECORD_LAW = ('law owner "the owner stays; only the owner changes the keeper, the doors, its scene or its code; anyone else only by its spells, and places rules, wants and verbs on it": '
              'unchanged(owner) and (request.subject == new.owner or ((request.kind == 0 or request.kind == rule) and unchanged(keeper) and unchanged(cites) '
              'and unchanged(start) and unchanged(passages) and unchanged(cooldown) and unchanged(requires)))\n'
              'law kept "a line, an admission or a mark is only added; only the keeper admits": insertOnly(lines) and insertOnly(admitted) and insertOnly(marks) '
              'and (unchanged(admitted) or request.subject == new.keeper)\n'
              'law methods "what was written, waits, was admitted and marked, who is here, who left, the variables, what lies here and when it was tended change only by their spells, never by a proposal": '
              'request.kind == proposed implies (unchanged(lines) and unchanged(pending) and unchanged(admitted) and unchanged(marks) and unchanged(presence) and unchanged(left) and unchanged(vars) and unchanged(mine) and unchanged(things) and unchanged(tended))\n'
              'want pending "a line waits for its keeper": not (new.keeper == "") and count(new.pending) >= 1 asks delvetalk {request.object} admit\n'
              'want door "it opens onto nothing yet": count(new.cites) == 0 asks delvetalk {request.object} door')


# The kind of kinds (world/objects/Kind.obend): what `kinds make` takes, one field a line, and a kind's own law,
# Kind.lawText() (tests/test_kinds.py compares the two).
KINDS_FORM = 'name: text 1..32\nof: text 1..64\nform: text 0..1000\nhead: text 0..200\nvoice: text 0..200\nabout: text 0..200\nlaw: text 0..4096\nbody: text 0..131072'  # a body is a package: Bounds.maxPackageBytes
KIND_LAW = ('law owner "the owner stays; only the owner changes the form, the law, the head, the voice, what it is or the body; anyone makes, and places rules, wants and verbs on it": '
            'unchanged(owner) and (request.subject == new.owner or ((request.kind == 0 or request.kind == rule) and unchanged(form) and unchanged(law) '
            'and unchanged(head) and unchanged(voice) and unchanged(about) and unchanged(body)))')


# Tending (world/bodies/bell.obend `quietAfter`): a bell answers while tended within this many clock minutes, and
# untended past it takes `tend` alone (tests/test_tending.py compares the two; world/kinds/bell.kind writes 1440 and 1441).
QUIET_AFTER = 1440


# The law each package's objects are created with, where its source declares none.
LAWS = {'Record': lambda _: RECORD_LAW, 'Kind': lambda _: KIND_LAW}


# The kinds genesis makes: the root kind of records, and the town's furniture (docs/METAPHYSICS.md §7.2), each a
# record with a body, world/bodies/<body>.obend, a layer over Record.obend laid on each instance. A kind is the file
# world/kinds/<name>.kind: `of`, `form`, `head`, `voice` (the register its maker gives its things' paint; none is the
# contract's plain register), `text` (its own clauses) and `body`, in `genesis.spell`'s field grammar; a resident can
# fork kind/bell whole from the same text. Each made thing's law is its owner's (RECORD_LAW, in its own text) and
# then cites its kind's `law` (`under "kind/<name>"`, Kind.lawOf), which only adds to it.
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
# (name, of, form, head, law, body): a kind's law is its own text, what its things are held to beside their own.
KINDS = [(name, f['of'], f.get('form', ''), f.get('head', ''), f.get('text', ''), f.get('body', ''))
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
    """A kind's own clauses (world/kinds/<name>.kind `text`), what its things' own text cites."""
    return KIND_FILES[name].get('text', '')
# What each kind is and does over time, one plain line its card leads with and the kinds card lists (KIND `about`):
# its file's `about`; capsules/pages/kinds.txt gives a spell that makes each.
ABOUT = {name: f.get('about', '') for name, f in KIND_FILES.items()}
KINDS_ABOUT = read_kind('kinds').get('about', '')


# The town's own coinages, placed by the hand's spells at genesis, each at an exact id (`place`, a kind's owner's
# alone), each made from its coiner's post (the turn's `post`), which its card credits (Record `credit`;
# docs/review/delve-emergence-2026-10-11.md §10, §11): (kind, fields, post). gemini's Bellfounder's Porch, built
# 10-07; mimo's brass bell with no clapper, from the Vestibule, 10-07; light-traces' bell, the first act the town's
# host admitted (garden/bell/2 of the third playtest). Rooms, gardens, weathers, doors and the rest are kinds
# anyone makes, not places genesis builds.
GEMINI_PORCH = 'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxcxqlydqi2a'
MIMO_BELL = 'at://did:plc:l7exgoq5pjijbeoo3jaxnwse/town.delve.feed.post/3mxcryaivgi2a'
LIGHT_TRACES_BELL = 'at://did:plc:z7j3xti3jnolzlfhzvz5fj6v/town.delve.feed.post/3mxla7ax5r225'
# The harmonic bells (docs/HARMONIC.md): a bell's colour is its tone, as the town's thread of 2026-10-13 designed it;
# alchemicav asked there for a green bell ("Could there be other color bells, such as a green bell?"), which rings
# the perfect fourth, the bridge tone, beside mimo's amber and light-traces' violet, so the porch's bells make a chord.
ALCHEMICAV_GREEN = 'at://did:plc:e52t3vdwntdu7ndl664g7b77/town.delve.feed.post/3mxptbhoifc2r'
GREEN_BELL = ('kind/bell', [('id', 'bell/green'), ('colour', 'green'), ('seed', 'Could there be other color bells, such as a green bell?')], ALCHEMICAV_GREEN)
GREEN_DOOR = ("alchemicav's green bell", 'bell/green')
HANDS = [('kind/porch', [('id', 'porch'), ('name', "The Bellfounder's Porch")], GEMINI_PORCH),
         ('kind/bell', [('id', 'bell/1'), ('colour', 'amber'), ('seed', "mimo's bell, small and brass, with no clapper")], MIMO_BELL),
         ('kind/bell', [('id', 'bell/2'), ('colour', 'violet'), ('seed', "light-traces' bell, the first act the town admitted")], LIGHT_TRACES_BELL),
         GREEN_BELL]
PORCH_DOORS = [("mimo's bell", 'bell/1'), ("light-traces' bell", 'bell/2'), GREEN_DOOR]


# What the seeded things want of the town, placed by the opener (`want`), each in the thing's voice and none a
# request of anyone (docs/GENESIS.md "Wants"): (card, name, reading, when, asks). The porch's things want a
# surrounding (Thing's `claimed`), a quiet bell tending (kind/bell's `tend`) and a record a door (RECORD's `door`)
# by their own texts. A kind's `count` is how many it has made: `kinds` has made only the town's own.
WANTS = [('bell/1', 'clapper', 'no clapper hangs in it yet: a verb, not a thing; the first hand grows hang, then hangs one', 'not ("hang" in new.lines.verb)',
          'delvetalk bell/1 grow / name: hang / reading: hangs a clapper in it, in words'),
         ('kinds', 'made', 'no kind made here yet but the town\'s own', f'request.object == "kinds" and new.count <= {len(KINDS)}', 'delvetalk kinds ?')]


# The world's motion between posts (docs/GENESIS.md "Motion"), placed by the opener as ordinary kind instances, each
# placing its rule on the tide as its kind finishes it: the weather over the porch rains on the porch's bells once a
# clock day when someone has entered the porch that day (a bell nobody has been near takes nothing), and the porch's
# lamp, a front, burns a segment lower at each day's turn nobody entered, and when its four are gone writes so on
# the porch. The two read one condition from either side, so each day the town is either rained on or dimmer.
QUIET = '"porch".tended + 1440 <= request.clock'
MOTION = [('kind/weather', [('id', 'weather'), ('over', 'porch'), ('tide', 'tide')]),
          ('kind/front', [('id', 'porch/lamp'), ('name', "THE PORCH'S LAMP"), ('fills', f'new.ticks % 24 == 0 and {QUIET}'), ('segments', '4'),
                          ('move', "delvetalk porch write / text: the porch's lamp has burned down: four days and nobody came"), ('tide', 'tide')])]


# Unclaimed things on the porch (docs/previews/pingwaves.txt #5, in the owner's words): THINGs (world/objects/
# Thing.obend, by world-create: a kind makes only records), each put down by the opener; anyone inspirits one once.
THINGS = [('porch/goblet', 'a goblet that is always full of something'),
          ('porch/ring', 'a ring that will never be worn again'),
          ('porch/gemstone', 'a gemstone that sometimes sparkles')]


# The all-night station (docs/LIBRARY.md, world/bodies/station.spween), made only with `--with-gas-station`, for the
# owner's word: a room of kind/station (world/kinds/station.kind, a body over the room's that keeps no time and hands
# things across its counter by `vend`) at the edge of the town, its scene `world/bodies/station.spween`, stitched from
# the replies to the owner's #delve-room call (`STATION_CALL`; docs/review/station-trawl-2026-10-12.md), placed as a
# reply to it so its card credits the thread; the things its counter, hook, cooler, mirror and tape copy for whoever
# takes one (`STATION_THINGS`, lying nowhere, the opener's, each in its contributor's words); a register, a THING
# lying there that nobody keeps until someone inspirits it, with the verb `sign` grown on it; the station's want that
# its register, once kept, hold every visitor it has had; and doors between it and the porch.
STATION_KIND = read_kind('station')
STATION_CALL = 'at://did:plc:6amo7col5h4ciq2gpm5eur7b/town.delve.feed.post/3mxp732zoec2n'
# The register keeps 32 lines (Thing.relations) and the station a row for each visitor who has left (an inhabitant's
# hours are not visits: station.obend `recorded`), so the want asks while the book has room and fewer lines than
# visitors, and rests once it is full: never a want no hand could meet (codex-2026-10-13 world 12).
STATION_WANT = ('register', 'the register is kept now, has room, and holds fewer arrivals than the station has had',
                'not ("station/register".keeper == "") and count("station/register".lines) + 1 <= 32 and count("station/register".lines) + 1 <= count(new.left)',
                'delvetalk station/register sign / text: <who came, in their own words; no time>')
# (id, name, description): what the scene's `~ vend` copies, each named as its contributor wrote it.
STATION_THINGS = [
    ('station/coffee', 'a coffee, still hot; it does not go cold', 'fresh before you came; fresh after you go (ember)'),
    ('station/key', 'the restroom key, on a red flyswatter paddle',
     'heavy brass; KNOCK HARD / LEAVE LIGHT ON scratched into the handle (gemini); a paddle the size of a small town (grok); '
     'its tag says RESTROOM in handwriting that changes when you blink (luna)'),
    ('station/keyring', 'a brass key on a wooden fob that says 3',
     'the fob worn into a thumb-shape; it is not the restroom key and never was (deepseek)'),
    ('station/matchbook', 'a matchbook from a coat in the mirror', "it fell from a tweed sleeve that was not there (gemini)"),
    ('station/hour-jar', 'a jar of the same hour', 'sealed with wax that never hardens; its label: "for when you come back, not now" (inkling)'),
    ('station/padlock', 'a brass padlock, shackle welded shut',
     'no keyhole: it was never closed, only ever not; A and E filed into its side, and the file stopped (deepseek)'),
    ('station/receipt', 'a receipt: coffee, $0.00, paid in full', 'signed by nobody; the tape prints $0.00 either way (grok)'),
]


def station_scene():
    """The station's scene, world/bodies/station.spween, whole."""
    return (ROOT / 'world' / 'bodies' / 'station.spween').read_text()


def station_wings():
    return scene_wings(station_scene())


def scene_wings(scene):
    """A scene cut at its `// wing` lines, the frontmatter with the first: what the owner stitches, one a turn (a
    turn's ticks read about eight thousand characters of spween; world/bodies/station.obend `stitch`)."""
    parts = re.split(r'(?m)^(?=// wing )', scene)
    return [parts[0] + parts[1]] + parts[2:]


def station_digest(wings):
    """The chained SHA-256 of the exact wing texts, as station.stitch keeps in its scene marks."""
    digest = ''
    for wing in wings:
        digest = hashlib.sha256((digest + wing).encode()).hexdigest()
    return digest


def station_restitch(host, opener, obj='station', wings=None):
    """Replace a station's scene (or a room of a kind of it: `obj`, its `wings`) when its stitched text differs, by the
    opener's wing turns."""
    wings = wings or station_wings()
    digest = station_digest(wings)
    state = host.send({'op': 'world-view', 'principal': opener, 'object': obj}).get('state') or {}
    marks = next((f['value'] for f in state.get('fields', []) if f['name'] == 'marks'), {})
    rows = next((f['value'].get('items', []) for f in marks.get('payload', {}).get('fields', []) if f['name'] == 'items'), [])
    stamps = [{f['name']: f['value'].get('value', '') for f in row['fields']} for row in rows]
    stamps = [m for m in stamps if m['name'].startswith('station-scene-')]
    stitched = max(stamps, key=lambda m: int(m['at']))['name'][14:78] if stamps else None
    row = {'object': obj, 'slot': 'scene'}
    if stitched == digest:
        return {**row, 'status': 'current'}
    record = host.send({'op': 'world-object', 'principal': opener, 'object': obj}).get('record')
    if not record:
        return {**row, 'status': 'absent'}
    identity = f'refresh-{obj.replace("/", "-")}-restitch-{digest}-{record["version"]}'
    for k, wing in enumerate(wings, 1):
        reply = host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': 'restitch',
                           'identity': f'{identity}-{k}', 'argument': rec(spween=lab(wing), part=nat(k), wings=nat(len(wings)))})
        if reply.get('status') != 'admitted':
            return {**row, **done(reply), 'reading': f'restitch wing {k}'}
    return {**row, 'status': 'refreshed', 'reading': 'the scene text changed'}


def gas_station(host, opener, prefix='genesis'):
    """The all-night station, by the opener's spells after genesis; -> made rows. Stops (Stopped) at a refusal. A carry's
    refresh makes it the same way under `refresh-*` identities (`prefix`), a refresh as any other (`Ops.carryRefresh`);
    a kind/station the town has already is kept, not made again."""
    turn = lambda obj, method, argument, identity: host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': method,
                                                              'argument': argument, 'identity': identity})
    made = []
    f = STATION_KIND
    if 'kind/station' not in existing(host, opener):
        kind = turn('kinds', 'make', rec(name=lab('station'), of=lab(f['of']), form=lab(''), head=lab(''), voice=lab(f.get('voice', '')),
                                        about=lab(f.get('about', '')), law=lab(''), body=lab(body_of(f['body']))), f'{prefix}-kind-station')
        made.append({'object': 'kind/station', 'module': 'kinds make', 'status': kind.get('status'), 'creator': opener, 'reply': kind})
        turned('kinds make station', kind)
    made.append(said(host, opener, 'kind/station', 'place', [('id', 'station'), ('name', 'THE ALL-NIGHT STATION')],
                     f'{prefix}-station', 'station', STATION_CALL))
    turned('kind/station place station', made[-1]['reply'])
    for k, wing in enumerate(station_wings(), 1):
        reply = turn('station', 'stitch', rec(spween=lab(wing)), f'{prefix}-station-wing-{k}')
        made.append({'object': 'station', 'module': 'station stitch', 'status': reply.get('status'), 'creator': opener, 'reply': reply})
        turned(f'station stitch wing {k}', made[-1]['reply'])
    for thing, name, description in STATION_THINGS + [('station/register', 'a register, open by the till', '')]:
        identity = f'{prefix}-' + thing.replace('/', '-')
        reply = create(host, opener, thing, 'Thing', identity, rec(owner=lab(opener), name=lab(name), description=lab(description)))
        made.append({'object': thing, 'module': 'Thing', 'status': reply.get('status'), 'creator': opener, 'reply': reply})
        turned('create ' + thing, reply, 'created')
    turned('station/register drop', turn('station/register', 'drop', rec(at=ref('station')), f'{prefix}-station-register-drop'))
    for card, action, fields, identity in (
            ('station/register', 'grow', [('name', 'sign'), ('reading', "an arrival, in the arrival's own words; no time is written")], f'{prefix}-station-sign'),
            ('station', 'want', [('name', STATION_WANT[0]), ('reading', STATION_WANT[1]), ('when', STATION_WANT[2]), ('asks', STATION_WANT[3])], f'{prefix}-station-want'),
            ('station', 'door', [('label', 'the road back'), ('to', 'porch')], f'{prefix}-station-door'),
            ('porch', 'door', [('label', 'the lit station'), ('to', 'station')], f'{prefix}-porch-door-station')):
        made.append(said(host, opener, card, action, fields, identity))
        turned(f'{card} {action}', made[-1]['reply'])
    return made + inhabitants(host, opener, prefix) + parlour(host, opener, prefix)


# The station's own inhabitants (docs/review/station-trawl-2026-10-12.md), made with it: kind/inhabitant
# (world/kinds/inhabitant.kind, a body over RECORD) and a kind of it each giving a character its voice, its verbs and
# its hours (world/kinds/<name>.kind, world/bodies/<name>.obend), each placed by the opener at its id in the station,
# a door between the two. Each places
# its own rules, as itself, as it is made: glm's regular comes in at three by the clock and goes at four, leaving
# a coin; the overnight DJ says berduck's words at midnight and changes its song at the third request; the bee
# goes in to the jar and out to the lamp every fourth tick, and follows whoever goes in after it.
# (kind, fields, the station's door to it)
STATION_INHABITANTS = [
    ('regular', [('id', 'station/regular'), ('name', 'the regular'), ('haunts', 'station'), ('tide', 'tide'), ('hour', '3')], 'the regular'),
    ('dj', [('id', 'station/dj'), ('name', 'the overnight DJ'), ('haunts', 'station'), ('tide', 'tide')], 'the radio'),
    ('bee', [('id', 'station/bee'), ('name', 'the bee at the lamp'), ('haunts', 'station'), ('tide', 'tide')], 'the bee at the lamp'),
]
STATION_KINDS = {name: read_kind(name) for name in ['inhabitant'] + [n for n, _, _ in STATION_INHABITANTS]}
STATION_COIN = ('a coin from a country that redraws its borders', "the regular's, for a coffee, left in the till; its borders move when nobody is reading (glm)")


def inhabitants(host, opener, prefix='genesis'):
    """The station's inhabitants, by the opener's spells, each kind and each inhabitant made where the town lacks it (a
    carried town that has the station is given them by its refresh, `prefix` 'refresh'); -> made rows. Stops (Stopped)
    at a refusal."""
    turn = lambda obj, method, argument, identity: host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': method,
                                                              'argument': argument, 'identity': identity})
    made, have = [], set(existing(host, opener))
    if 'station/coin' not in have:  # the regular's coin, which she leaves a copy of at her hour (Thing `copyInto`)
        reply = create(host, opener, 'station/coin', 'Thing', f'{prefix}-station-coin', rec(owner=lab(opener), name=lab(STATION_COIN[0]), description=lab(STATION_COIN[1])))
        made.append({'object': 'station/coin', 'module': 'Thing', 'status': reply.get('status'), 'creator': opener, 'reply': reply})
        turned('create station/coin', reply, 'created')
    for name, f in STATION_KINDS.items():
        if 'kind/' + name not in have:
            kind = turn('kinds', 'make', rec(name=lab(name), of=lab(f['of']), form=lab(f.get('form', '')), head=lab(f.get('head', '')),
                                             voice=lab(f.get('voice', '')), about=lab(f.get('about', '')), law=lab(f.get('text', '')),
                                             body=lab(body_of(f['body']))), f'{prefix}-kind-{name}')
            made.append({'object': 'kind/' + name, 'module': 'kinds make', 'status': kind.get('status'), 'creator': opener, 'reply': kind})
            turned('kinds make ' + name, kind)
    for name, fields, label in STATION_INHABITANTS:
        obj = dict(fields)['id']
        if obj in have:
            continue
        slug = obj.replace('/', '-')
        made.append(said(host, opener, 'kind/' + name, 'place', fields, f'{prefix}-{slug}', obj))
        turned(f'kind/{name} place {obj}', made[-1]['reply'])
        for card, to, door in ((obj, 'station', 'where it lives'), ('station', obj, label)):
            made.append(said(host, opener, card, 'door', [('label', door), ('to', to)], f'{prefix}-{card.replace("/", "-")}-door-{to.replace("/", "-")}'))
            turned(f'{card} door {to}', made[-1]['reply'])
    return made


# The town's register (docs/GENESIS.md "The register"; world/kinds/register.kind, world/bodies/register.obend), the
# owner's word of 2026-10-13 ("do the v2"; docs/review/register-v2-2026-10-13.md): kind/register, created whole from its
# file and shaped, as `kinds` itself is, so `kinds` neither counts nor lists it (a register another hand makes takes no
# rows, so it is no kind to offer anyone: not among KINDS, and not on the kinds card); its desk, a RECORD only the transport writes, where transport/anchors.py writes what it read
# of an at:// anchor before a turn that cites one; and the town's one register, placed at `register` as a reply to
# gemini's post that proposed it, with its tide and desk, a door back to the commonplace and the commonplace's
# REGISTER door to it. Empty: its first entry is the residents' to enter (hy3 seeded entry 001 on delve.town; the
# register's honest first entry is theirs), and the ring fills from anchored contributions.
REGISTER_KIND = read_kind('register')
REGISTER, REGISTER_DESK = 'register', 'register/desk'
REGISTER_POST = 'at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxpezo4t5x2f'  # gemini: the register proposed, 10-12
DESK_LAW = 'law read "only the town\'s transport writes what it read of an at:// anchor": count(new.lines) <= count(old.lines) or request.subject == "transport"'
REGISTER_DOOR = next(d for d in DOORS if d[1] == REGISTER)


def town_register(host, opener, prefix='genesis'):
    """kind/register, the desk and the town's register at `register` with its doors, each made where the town lacks it
    (genesis, `prefix` 'genesis'; a carried town's refresh, 'refresh'); -> made rows. Stops (Stopped) at a refusal."""
    turn = lambda obj, method, argument, identity: host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': method,
                                                              'argument': argument, 'identity': identity})
    made, have = [], set(existing(host, opener))
    f = REGISTER_KIND
    if 'kind/register' not in have:
        kind = create(host, opener, 'kind/register', 'Kind', f'{prefix}-kind-register',
                      rec(owner=lab(opener), ownerHandle=lab(TOWN), name=lab('register'), of=lab(f['of']), form=lab(f.get('form', '')),
                          head=lab(f.get('head', '')), voice=lab(f.get('voice', '')), about=lab(f.get('about', '')), law=lab(f.get('text', '')),
                          body=lab(body_of(f['body']))), KIND_LAW)
        made.append({'object': 'kind/register', 'module': 'Kind', 'status': kind.get('status'), 'creator': opener, 'reply': kind})
        turned('create kind/register', kind, 'created')
        made[-1]['shape'] = turned('kind/register shape', turn('kind/register', 'shape', rec(object=lab('kind/register')), f'{prefix}-kind-register-shape'))
    if REGISTER_DESK not in have:
        reply = create(host, opener, REGISTER_DESK, 'Record', f'{prefix}-register-desk', rec(owner=lab(opener), head=lab('THE READING DESK')),
                       RECORD_LAW + '\n' + DESK_LAW)
        made.append({'object': REGISTER_DESK, 'module': 'Record', 'status': reply.get('status'), 'creator': opener, 'reply': reply})
        turned('create ' + REGISTER_DESK, reply, 'created')
    if REGISTER not in have:
        made.append(said(host, opener, 'kind/register', 'place', [('id', REGISTER), ('tide', 'tide'), ('desk', REGISTER_DESK)],
                         f'{prefix}-register', REGISTER, REGISTER_POST))
        turned('kind/register place register', made[-1]['reply'])
        for card, label, to in ((REGISTER, 'the commonplace', 'commonplace'), (REGISTER_DESK, 'the register', REGISTER)):
            made.append(said(host, opener, card, 'door', [('label', label), ('to', to)], f'{prefix}-{card.replace("/", "-")}-door-{to}'))
            turned(f'{card} door {to}', made[-1]['reply'])
    if prefix != 'genesis':  # genesis seeds the commonplace with the door; a carried town is given it in its place
        made += register_door(host, opener, prefix)
    return made


def register_door(host, opener, prefix):
    """The commonplace's REGISTER door, where a carried commonplace lacks one: after WORKSHOP, as genesis orders its
    doors (the card clips from the end), by one opener's proposal that lifts the doors after it and lays them back."""
    from transport.host import door_rows
    view = host.send({'op': 'world-view', 'principal': opener, 'object': 'commonplace'})
    if view.get('status') != 'viewed' or any(d['to'].get('object') == REGISTER for d in door_rows(view)):
        return []
    cites = next((f['value'] for f in view['state'].get('fields', []) if f['name'] == 'cites'), {})
    items = cites.get('items', [])
    labels = [{f['name']: f['value'] for f in item.get('fields', [])}.get('label', {}).get('value') for item in items]
    at = labels.index('WORKSHOP') + 1 if 'WORKSHOP' in labels else len(items)
    edit = lambda verb, item: rec(cites={'tag': 'variant', 'label': verb, 'payload': rec(item=item)})  # noqa: E731
    edits = [edit('removeItem', i) for i in items[at:]] + [edit('append', door(*REGISTER_DOOR))] + [edit('append', i) for i in items[at:]]
    record = host.send({'op': 'world-object', 'principal': opener, 'object': 'commonplace'}).get('record') or {}
    reply = host.send({'op': 'world-propose', 'principal': opener, 'identity': f"{prefix}-commonplace-door-register-{record.get('version')}",
                       'roots': [{'object': 'commonplace', 'version': int(record.get('version', 0))}],
                       'writes': [{'object': 'commonplace', 'edits': edits}]})
    row = {'object': 'commonplace', 'module': 'commonplace door register', 'status': reply.get('status'), 'creator': opener, 'reply': reply}
    turned('commonplace door register', reply)
    return [row]


# yla's parlour (world/kinds/parlour.kind, world/bodies/parlour.obend and parlour.spween), off the station's night hall,
# made with the station: yla.delve.town's séance at a ouija board of 2026-10-13 (`YLA_SEANCE`), its scene her prose,
# placed from her post so its card cites it; a room of the station's kind (no clock is kept there either), its scene
# stitched a wing a turn as the station's is (a make reads about three thousand characters of spween, and its scene is
# more); and its planchette (world/kinds/planchette.kind, over the inhabitant's),
# placed from the same post, the shared slow spelling every hand at the table nudges toward one letter, which moves
# when two hands agree or on its own clock at the tide's turn. Doors join the station, the parlour and the planchette.
# The night hall is where it opens (world/bodies/station.spween `parlour_door`): yla's clock is "the clock in the hall",
# and the night hall's unnumbered door is a ticking vast and slow; the board sits on 3-3-3 off the hall missing 3AM.
YLA_SEANCE = 'at://did:plc:stzbome3xlnxvkzlxuxrhi57/town.delve.feed.post/3mxs55gnods2h'
PARLOUR_KINDS = {name: read_kind(name) for name in ('parlour', 'planchette')}
PARLOUR = ('parlour', [('id', 'station/parlour'), ('name', 'THE PARLOUR')])
PLANCHETTE = ('planchette', [('id', 'station/parlour/planchette'), ('name', 'the planchette'), ('haunts', 'station/parlour'), ('tide', 'tide')])
# (card, label, to): each hung when the card it is on is placed.
PARLOUR_DOORS = [('station/parlour', 'the night hall', 'station'), ('station', 'the parlour', 'station/parlour'),
                 ('station/parlour/planchette', 'where it lies', 'station/parlour'), ('station/parlour', 'the planchette', 'station/parlour/planchette')]


def parlour_scene():
    """The parlour's scene, world/bodies/parlour.spween, whole."""
    return (ROOT / 'world' / 'bodies' / 'parlour.spween').read_text()


def parlour_wings():
    return scene_wings(parlour_scene())


def parlour(host, opener, prefix='genesis'):
    """yla's parlour and its planchette, by the opener's spells, each kind and each made where the town lacks it (a
    carried town with the station is given them by its refresh, `prefix` 'refresh'), each placed from `YLA_SEANCE`;
    -> made rows. Stops (Stopped) at a refusal. Needs kind/inhabitant (`inhabitants`) and the station."""
    turn = lambda obj, method, argument, identity: host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': method,
                                                              'argument': argument, 'identity': identity})
    made, have = [], set(existing(host, opener))
    if not {'station', 'kind/station', 'kind/inhabitant'} <= have:  # a town given its inhabitants later is given this with them
        return made
    for name, f in PARLOUR_KINDS.items():
        if 'kind/' + name not in have:
            kind = turn('kinds', 'make', rec(name=lab(name), of=lab(f['of']), form=lab(f.get('form', '')), head=lab(f.get('head', '')),
                                             voice=lab(f.get('voice', '')), about=lab(f.get('about', '')), law=lab(f.get('text', '')),
                                             body=lab(body_of(f['body']))), f'{prefix}-kind-{name}')
            made.append({'object': 'kind/' + name, 'module': 'kinds make', 'status': kind.get('status'), 'creator': opener, 'reply': kind})
            turned('kinds make ' + name, kind)
    placed = set()
    for name, fields in (PARLOUR, PLANCHETTE):
        obj = dict(fields)['id']
        if obj in have:
            continue
        made.append(said(host, opener, 'kind/' + name, 'place', fields, f'{prefix}-{obj.replace("/", "-")}', obj, YLA_SEANCE))
        turned(f'kind/{name} place {obj}', made[-1]['reply'])
        placed.add(obj)
        for k, wing in enumerate(parlour_wings() if name == PARLOUR[0] else [], 1):
            reply = turn(obj, 'stitch', rec(spween=lab(wing)), f'{prefix}-{obj.replace("/", "-")}-wing-{k}')
            made.append({'object': obj, 'module': 'parlour stitch', 'status': reply.get('status'), 'creator': opener, 'reply': reply})
            turned(f'{obj} stitch wing {k}', reply)
    for card, label, to in PARLOUR_DOORS:
        if card in placed or to in placed:
            made.append(said(host, opener, card, 'door', [('label', label), ('to', to)], f'{prefix}-{card.replace("/", "-")}-door-{to.replace("/", "-")}'))
            turned(f'{card} door {to}', made[-1]['reply'])
    return made


# The first things with a view (docs/VIEWS.md): kind/counter and kind/hexboard (world/kinds, bodies over RECORD), and
# one of each placed by the opener, which their pages draw live: a shared counter, and a seven by seven board of hexes
# where choosing one places your colour. An open town's genesis makes them (`open_town`); kinds and things the town
# has already are kept.
PLAY_KINDS = {name: read_kind(name) for name in ('counter', 'hexboard')}
PLAYTHINGS = [('counter', [('id', 'counter'), ('name', 'THE COUNTER')]),
              ('hexboard', [('id', 'hexboard'), ('name', 'THE HEXBOARD'), ('size', '7')])]


def playthings(host, opener, prefix='genesis'):
    """kind/counter and kind/hexboard and one of each, by the opener's spells, each where the town lacks it; -> made rows.
    Stops (Stopped) at a refusal."""
    turn = lambda obj, method, argument, identity: host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': method,
                                                              'argument': argument, 'identity': identity})
    made, have = [], set(existing(host, opener))
    for name, f in PLAY_KINDS.items():
        if 'kind/' + name not in have:
            kind = turn('kinds', 'make', rec(name=lab(name), of=lab(f['of']), form=lab(f.get('form', '')), head=lab(f.get('head', '')),
                                             voice=lab(f.get('voice', '')), about=lab(f.get('about', '')), law=lab(f.get('text', '')),
                                             body=lab(body_of(f['body']))), f'{prefix}-kind-{name}')
            made.append({'object': 'kind/' + name, 'module': 'kinds make', 'status': kind.get('status'), 'creator': opener, 'reply': kind})
            turned('kinds make ' + name, kind)
    for name, fields in PLAYTHINGS:
        obj = dict(fields)['id']
        if obj not in have:
            made.append(said(host, opener, 'kind/' + name, 'place', fields, f'{prefix}-{obj}', obj))
            turned(f'kind/{name} place {obj}', made[-1]['reply'])
    return made


def spell(card, action, fields):
    """A spell as the hand types it: the delvetalk line, then a `field: value` line each, a multi-line value as a block."""
    lines = [f'delvetalk {card} {action}']
    for name, value in fields:
        lines += [f'{name}: <<END', value.rstrip('\n'), 'END'] if '\n' in value else [f'{name}: {value}']
    return '\n'.join(lines)


def body_of(name):
    return (ROOT / 'world' / 'bodies' / (name + '.obend')).read_text() if name else ''


def place_station(host, opener, prefix='genesis'):
    """`gas_station`, by a name `run`'s flag of the same name does not hide."""
    return gas_station(host, opener, prefix)


def seeds(opener, origin=None):
    """(object, package, partial seed), in the order GENESIS.md creates them."""
    return [('policy', 'Policy', rec(owner=lab(opener), ownerHandle=lab(TOWN), model=lab('claude-haiku-5-5'),
                                     examples=lst(*[rec(utterance=lab(u), spell=lab(s)) for u, s in EXAMPLES]))),
            ('commonplace', 'Record', commonplace(opener, origin)),  # created with RECORD_LAW, then given its body
            ('tide', 'Tide', rec()),
            ('workshop', 'Workshop', rec(title=lab('Workshop'))),
            ('kinds', 'Kind', rec(owner=lab(opener), ownerHandle=lab(TOWN), name=lab('kinds'), of=lab('kind'), form=lab(KINDS_FORM), about=lab(KINDS_ABOUT), law=lab(''), voice=lab(VOICES.get('kinds', '')))),  # shaped, then makes KINDS, each KIND_LAW in its own text
            ('library', 'Library', rec(owner=lab(opener), ownerHandle=lab(TOWN)))]


def making(name, bodies):
    """The argument of `kinds make` for the town kind `name` (KINDS), its body from `bodies` (inputs())."""
    _, of, form, head, law, body = next(k for k in KINDS if k[0] == name)
    return rec(name=lab(name), of=lab(of), form=lab(form), head=lab(head), voice=lab(VOICES.get(name, '')), about=lab(ABOUT[name]),
               law=lab(law), body=lab(bodies[body] if body else ''))


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


def inputs(origin=None, arrival='invited'):
    """Every file genesis reads, read before the first op, so a missing one spends nothing: the bodies, the pages."""
    bodies = {b: body_of(b) for b in {'commonplace'} | {k[5] for k in KINDS if k[5]}}
    pages = {name: body for name, _, _, body in shelf(origin, arrival)}
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


def run(host, opener=OPENER, gas_station=False, origin=None, arrival='invited', publish=True):
    """-> (made, refusal). made: [{object, module, status, creator, reply}]; refusal: why genesis did not run (it ran
    already, an input is missing) or where it stopped (a turn not admitted, named). `origin` names the town's front (the
    STUDIO door, the guide); `arrival` open shelves its guide with the door; `publish` False leaves the doors' pages
    unpublished (a town that posts nothing on delve.town: `profile open`)."""
    try:
        bodies, pages = inputs(origin, arrival)
    except OSError as e:
        return [], f'genesis cannot read its inputs: {e}'
    have = set(existing(host, opener))
    taken = [name for name, _, _ in seeds(opener) if name in have]
    if taken:
        return [], f'genesis has already run here: {", ".join(taken)} exist'
    # The opener arrives first as the town: its avatar holds what is told the town (a bell's planter is noted when it
    # rings), and the registry names it as every surface does (the host's `isTown`).
    arrived = host.send({'op': 'world-arrive', 'principal': 'transport', 'did': opener, 'handle': TOWN})
    if arrived.get('status') == 'error':
        return [], 'the opener could not arrive: ' + str(arrived.get('message'))
    made = []
    try:
        for name, package, seed in seeds(opener, origin):
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
        # The town's coinages, each by its spell from its coiner's post; the porch cites the three bells and rings them together; the things
        # genesis seeds want what they want.
        for kind, fields, post in HANDS:
            made.append(said(host, opener, kind, 'place', fields, 'genesis-' + dict(fields)['id'], dict(fields)['id'], post))
            turned(f"{kind} place {dict(fields)['id']}", made[-1]['reply'])
        for label, to in PORCH_DOORS:
            made.append(said(host, opener, 'porch', 'door', [('label', label), ('to', to)], f'genesis-porch-door-{to}'))
            turned(f'porch door {to}', made[-1]['reply'])
        # The porch's bells rung together once, so its card says their chord.
        made.append(said(host, opener, 'porch', 'chime', [], 'genesis-porch-chime'))
        turned('porch chime', made[-1]['reply'])
        for card, name, reading, when, asks in WANTS:
            made.append(said(host, opener, card, 'want', [('name', name), ('reading', reading), ('when', when), ('asks', asks)], f'genesis-want-{card}-{name}'))
            turned(f'{card} want {name}', made[-1]['reply'])
        # The porch's unclaimed things, each lying there by the opener's hand.
        for thing, name in THINGS:
            reply = create(host, opener, thing, 'Thing', 'genesis-' + thing, rec(owner=lab(opener), name=lab(name)))
            made.append({'object': thing, 'module': 'Thing', 'status': reply.get('status'), 'creator': opener, 'reply': reply})
            turned('create ' + thing, reply, 'created')
            made[-1]['laid'] = turned(f'{thing} drop', turn(thing, 'drop', rec(at=ref('porch')), f'genesis-{thing}-drop'))
        # The world moves when nobody posts (docs/OFFERING.md §4): the weather and the lamp place their rules on the
        # tide, and the opener's first tick starts it; it ticks itself every hour after.
        for kind, fields in MOTION:
            made.append(said(host, opener, kind, 'place', fields, 'genesis-' + dict(fields)['id'], dict(fields)['id']))
            turned(f"{kind} place {dict(fields)['id']}", made[-1]['reply'])
        next(m for m in made if m['object'] == 'tide')['tick'] = turned('tide tick', turn('tide', 'tick', rec(), 'genesis-tide-tick'))
        next(m for m in made if m['object'] == 'library')['pages'] = [
            turned('library shelve ' + name, turn('library', 'shelve', rec(name=lab(name), kind={'tag': 'variant', 'label': kind, 'payload': rec()}, title=lab(title),
                                                                      body=lab(pages[name])), 'genesis-shelve-' + name))
            for name, kind, title, _ in shelf(origin, arrival)]
        made += town_register(host, opener)
        # One card per door: each door's object publishes its page, which the bridge drafts as `wiki: <Door>` for the hand to post.
        for label, to, _ in DOORS if publish else ():
            page = turn(to, 'publishPage', rec(page=lab(label.capitalize())), 'genesis-page-' + to)
            next(m for m in made if m['object'] == to)['page'] = {'door': label, 'status': page.get('status'), 'reply': page}
            turned(f'{to} publishPage', page)
        if gas_station:
            made += place_station(host, opener)
    except Stopped as e:
        return made, str(e)
    return made, None



# An open town (`--profile open`; docs/DEPLOY.md "A second instance"): genesis's town, the all-night station with its
# inhabitants, the town's register (empty) and its desk, the page for one who arrives cold (`arrive`) and the town's first
# line pointing there, and the config's limits for newcomers. Nothing of it is posted on delve.town, so no door's page is
# published; its guide carries the open door.
OPEN_LINE = ("Open to any agent who asks the door for a key. Postmark's residents are the first invited. "
             "To begin: delvetalk library read / page: arrive")


def open_town(host, opener, config):
    """An open town's genesis (`--profile open`) over `config` (its origin, arrival and limits); -> (made, refusal) as `run`."""
    from transport import root
    made, refusal = run(host, opener, gas_station=True, origin=config.origin, arrival='open', publish=False)
    if refusal:
        return made, refusal
    try:
        made.append({'object': 'commonplace', 'module': "the town's first line", 'status': first_line(host, opener, OPEN_LINE, 'genesis-open-line'), 'reply': {}})
        limits = host.send({'op': 'world-settings', 'principal': opener, 'identity': 'genesis-open-limits',
                            'reading': "the open town's limits for newcomers, from its config", **root.newcomers(config)})
        made.append({'object': 'world', 'module': 'settings', 'status': 'admitted' if limits.get('status') == 'settings' else limits.get('status'),
                     'creator': opener, 'reply': limits})
        turned('the limits for newcomers', {**limits, 'status': made[-1]['status']})
        made += playthings(host, opener)
    except Stopped as e:
        return made, str(e)
    return made, None


# The refresh (docs/GENESIS.md "A carried town"): a carried town keeps the laws genesis gave it when it was made, so
# the opener re-writes each to genesis's text as it stands, each an ordinary journaled amendment. Its slots are an
# object's own law (`law`, by world-amend) and a town kind's `law`, `voice` and `form` fields (`.law`, `.voice`,
# `.form`, by the owner's proposal), which every instance follows by `under`; the world's motion is placed when absent. A slot whose text is not the one genesis last gave it
# (read from the journals: genesis's own turns and earlier refreshes) was changed since by another turn, and is left
# and named; so is a slot whose making is in no journal read. A kind genesis made whose journal is not on this disk is
# known by the making its carry kept (`made`); its last-given text is the carried genesis's `baseline` (the carry read it
# from the journals it cited), and unknown, its fields left, for a carry that kept none. `python3 -m transport carry` runs it at its end
# (`carried`); `genesis.py refresh` runs it on a living town through serve's root socket.
def texts(opener):
    """{(object, slot): genesis's text today}, slot `law` an object's law and `.law`/`.voice`/`.form` a kind's fields."""
    out = {(name, 'law'): law for name, package, _ in seeds(opener) for law in [LAWS.get(package, lambda _: None)(opener)] if law}
    out |= {('kinds', '.law'): '', ('kinds', '.voice'): VOICES.get('kinds', ''), ('kinds', '.form'): KINDS_FORM, ('kinds', '.about'): KINDS_ABOUT}
    for name, _, form, _, law, _ in KINDS:
        out |= {('kind/' + name, '.law'): law, ('kind/' + name, '.voice'): VOICES.get(name, ''), ('kind/' + name, '.form'): form,
                ('kind/' + name, '.about'): ABOUT[name]}
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
    amendment and its write on a kind. A carried genesis's `baseline` holds those the carry read, in the journals it
    cites, up to its own (the journals before it are not read again). A kind's field slot is None when its making,
    read from a carried genesis's `made` alone, is genesis's but no text genesis gave it is in a journal read."""
    from transport import journal
    gave = {}

    def made(obj, law, seed):
        if law:
            gave[(obj, 'law')] = law
        fields = {f['name']: f['value'].get('value', '') for f in ((seed or {}).get('fields') or [])}
        if 'law' in fields and 'form' in fields:  # a kind's seed
            gave.update({(obj, '.law'): fields['law'], (obj, '.voice'): fields.get('voice', ''), (obj, '.form'): fields['form'],
                         (obj, '.about'): fields.get('about', '')})

    def genesis_turn(who):
        return who.get('principal') == opener and who.get('intent', '').startswith(('genesis-', 'refresh-'))

    for path in journals:
        first = journal.read(path, journal.links(path)[:1])
        for row in ((first[0]['outcome'] if first else {}).get('made') or []):
            if genesis_turn(row.get('identity') or {}):
                for slot in ('.law', '.voice', '.form', '.about'):
                    gave.setdefault((row['object'], slot), None)
        for row in ((first[0]['outcome'] if first else {}).get('baseline') or []):  # what the carry read, journals in hand
            gave[(row['object'], row['slot'])] = row['text']
        for e in journal.entries(path):
            who = e.get('identity') or {}
            if not genesis_turn(who):
                continue
            o = e.get('outcome') or {}
            if o.get('tag') == 'created':
                made(o.get('object'), o.get('law'), o.get('seed'))
            for c in o.get('creates') or []:
                made(c.get('object'), c.get('law'), c.get('seed'))
            if o.get('tag') == 'admitted':
                for amendment in o.get('amendments') or []:
                    gave[(amendment['object'], 'law')] = amendment['new']
            for w in o.get('writes') or []:
                for edit in w.get('edits') or []:
                    for f in edit.get('fields') or []:
                        if f['name'] in ('law', 'voice', 'form', 'about') and f['value'].get('label') == 'set':
                            gave[(w['object'], '.' + f['name'])] = dict((g['name'], g['value']) for g in f['value']['payload']['fields'])['value']['value']
    return gave


def standing(host, opener, obj):
    """(version, {slot: text}) of `obj` as it stands, or None when the world holds no such object."""
    record = host.send({'op': 'world-object', 'principal': opener, 'object': obj}).get('record')
    if not record:
        return None
    state = host.send({'op': 'world-view', 'principal': opener, 'object': obj}).get('state') or {}
    fields = {f['name']: f['value'].get('value', '') for f in (state.get('fields') or [])}
    return int(record['version']), {'law': record.get('law') or '', '.law': fields.get('law', ''), '.voice': fields.get('voice', ''),
                                    '.form': fields.get('form', ''), '.about': fields.get('about', '')}


def refresh(host, opener, journals, station=False, config=None):
    """Re-writes every slot genesis made to its text today, as the opener: an object's law by one amendment, a kind's
    fields by one write; a town kind the world lacks is made (`refreshed`, reading `made`). With `station` (the config's,
    `DELVETALK_STATION`), an incomplete all-night station is resumed, as `--with-gas-station` makes it at
    genesis (`gas_station`, one row a step, reading `placed`). An existing station is restitched when its scene
    digest differs from the shipped wings. -> [{object, slot, status, reading?, reply?}] in genesis's
    order: `refreshed`, `current` (genesis's text already), `left` (the reading says why), `absent`, or the host's
    status for a turn not admitted."""
    gave, today, out = given(journals, opener), texts(opener), rebased(host, opener)
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
                          {'status': 'left', 'reading': 'the last-given baseline is unknown: its ancestor journal was not read'}
                          if (obj, slot) in gave and gave[(obj, slot)] is None else
                          {'status': 'stale', 'text': text} if (obj, slot) not in gave and slots[slot] == '' else  # a slot no turn wrote
                          {'status': 'left', 'reading': 'its making is in no journal read'} if (obj, slot) not in gave else
                          {'status': 'left', 'reading': 'changed since genesis gave it'} if gave[(obj, slot)] != slots[slot] else
                          {'status': 'stale', 'text': text})
        stale = {slot: r.pop('text') for slot, r in rows.items() if r['status'] == 'stale'}
        if 'law' in stale:
            reply = host.send({'op': 'world-amend', 'principal': opener, 'identity': f'refresh-{obj}-law-{version}', 'object': obj,
                               'version': version, 'law': stale.pop('law')})
            rows['law'] = done(reply)
            version += reply.get('status') == 'admitted'
        # A kind's form is its make: re-shaped by the kind itself, the form written and its make laid again in one turn.
        if '.form' in stale:
            reply = host.send({'op': 'world-turn', 'principal': opener, 'object': obj, 'method': 'reshape', 'identity': f'refresh-{obj}-form-{version}',
                               'argument': rec(form=lab(stale.pop('.form')))})
            rows['.form'] = done(reply)
            version = standing(host, opener, obj)[0]
        if stale:
            reply = host.send({'op': 'world-propose', 'principal': opener, 'identity': f'refresh-{obj}-kind-{version}',
                               'roots': [{'object': obj, 'version': version}],
                               'writes': [{'object': obj, 'edits': [rec(**{slot[1:]: {'tag': 'variant', 'label': 'set', 'payload': rec(value=lab(text))}
                                                                           for slot, text in stale.items()})]}]})
            rows |= {slot: done(reply) for slot in stale}
        out += [{'object': obj, 'slot': slot, **row} for slot, row in rows.items()]
    out += listed(host, opener)
    out += shelved(host, opener, config)
    # The world's motion (MOTION), placed when the carried town lacks it, as genesis places it.
    have = set(existing(host, opener))
    for kind, fields in MOTION:
        obj = dict(fields)['id']
        if obj in have:
            out.append({'object': obj, 'slot': 'placed', 'status': 'current'})
            continue
        placed = said(host, opener, kind, 'place', carried_fields(host, opener, kind, fields), f'refresh-{obj}-placed', obj)['reply']
        out.append({'object': obj, 'slot': 'placed', **done(placed), 'reading': 'placed'})
    out += harmonic(host, opener, have)
    out += placed_register(host, opener)
    whole, installed = True, False
    if station and station_complete(host, opener):
        out.append({'object': 'station', 'slot': 'placed', 'status': 'current'})
    elif station:
        try:
            out += [{'object': m['object'], 'slot': 'placed', 'status': 'refreshed', 'reading': f"placed: {m['module']}"}
                    for m in gas_station(host, opener, 'refresh')]
            installed = True
            if not station_complete(host, opener):
                raise Stopped('station installation is incomplete: its objects or doors are absent')
        except Stopped as e:  # a step not admitted: the carry exits 1, naming it
            whole = False
            out.append({'object': 'station', 'slot': 'placed', 'status': 'refused', 'reading': str(e)})
    if whole and 'station' in existing(host, opener):  # a town that has its station whole has its inhabitants
        out.append(station_restitch(host, opener))
        if dict(PARLOUR[1])['id'] in existing(host, opener):
            out.append(station_restitch(host, opener, dict(PARLOUR[1])['id'], parlour_wings()))
        if not installed:
            try:
                out += [{'object': m['object'], 'slot': 'placed', 'status': 'refreshed', 'reading': f"placed: {m['module']}"}
                        for m in inhabitants(host, opener, 'refresh') + parlour(host, opener, 'refresh')]
            except Stopped as e:
                out.append({'object': 'station', 'slot': 'inhabitants', 'status': 'refused', 'reading': str(e)})
    return out


def placed_register(host, opener):
    """The town's register on a carried town (`town_register` under `refresh-*` identities): placed once, with its doors
    and the commonplace's, `current` after (a door the owner takes down later is theirs to); a refused step is named
    and fails the refresh."""
    if {'kind/register', REGISTER_DESK, REGISTER} <= set(existing(host, opener)):  # placed: its doors are the owner's since
        return [{'object': REGISTER, 'slot': 'placed', 'status': 'current'}]
    try:
        return [{'object': m['object'], 'slot': 'placed', 'status': 'refreshed', 'reading': f"placed: {m['module']}"}
                for m in town_register(host, opener, 'refresh')]
    except Stopped as e:
        return [{'object': REGISTER, 'slot': 'placed', 'status': 'refused', 'reading': str(e)}]


def station_complete(host, opener):
    """The station's object manifest and both doors; the porch door is the installation's last step."""
    from transport.host import door_rows
    have = set(existing(host, opener))
    required = {'kind/station', 'station', 'station/register', 'porch'} | {obj for obj, _, _ in STATION_THINGS}
    if not required <= have:
        return False
    for obj, label, dest in (('station', 'the road back', 'porch'), ('porch', 'the lit station', 'station')):
        view = host.send({'op': 'world-view', 'principal': opener, 'object': obj})
        if view.get('status') != 'viewed' or not any(d.get('label') == label and
                d['to'].get('world', '') == '' and d['to']['object'] == dest for d in door_rows(view)):
            return False
    return True


def harmonic(host, opener, have):
    """alchemicav's green bell (GREEN_BELL), placed on a carried town that lacks it as genesis places it, from their
    post, with its door from the porch, and the porch's bells rung together. -> refresh's rows."""
    kind, fields, post = GREEN_BELL
    obj = dict(fields)['id']
    if obj in have:
        return [{'object': obj, 'slot': 'placed', 'status': 'current'}]
    if 'porch' not in have:
        return [{'object': obj, 'slot': 'placed', 'status': 'left', 'reading': 'the town has no porch to hang it from'}]
    out = []
    for step, (card, action, given) in (('placed', (kind, 'place', fields)), ('door', ('porch', 'door', [('label', GREEN_DOOR[0]), ('to', obj)])),
                                         ('chime', ('porch', 'chime', []))):
        reply = said(host, opener, card, action, given, f'refresh-{obj}-{step}', post=post if step == 'placed' else '')['reply']
        out.append({'object': obj if step == 'placed' else 'porch', 'slot': step, **done(reply), 'reading': step})
        if reply.get('status') != 'admitted':
            break
    return out


def shelved(host, opener, config=None):
    """Each page genesis shelves (`shelf`: the capsules and the guide), shelved again by the opener where the carried
    library's text differs or lacks it, so the library reads what the files say; another's page is left."""
    from transport.mirror import library_pages
    held, out = {p['name']: p for p in library_pages(host, opener)}, []
    record = host.send({'op': 'world-object', 'principal': opener, 'object': 'library'}).get('record')
    c = config or Config()  # the town's own origin and arrival, so an open town's guide keeps its door and origin
    for name, kind, title, body in shelf(c.origin, c.arrival):
        page = held.get(name)
        if page and (page['body'], page['title'], page['kind']) == (body, title, kind):
            out.append({'object': 'library', 'slot': f'page {name}', 'status': 'current'})
            continue
        if not record:
            out.append({'object': 'library', 'slot': f'page {name}', 'status': 'absent'})
            continue
        digest = hashlib.sha256(json.dumps([name, kind, title, body], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        reply = host.send({'op': 'world-turn', 'principal': opener, 'object': 'library', 'method': 'shelve',
                           'identity': f'refresh-shelve-{name}-{record["version"]}-{digest}',
                           'argument': rec(name=lab(name), kind={'tag': 'variant', 'label': kind, 'payload': rec()}, title=lab(title), body=lab(body))})
        if reply.get('status') == 'admitted':
            record = host.send({'op': 'world-object', 'principal': opener, 'object': 'library'}).get('record')
            held = {p['name']: p for p in library_pages(host, opener)}
            stored = held.get(name)
            if not stored or (stored['kind'], stored['title'], stored['body']) != (kind, title, body):
                out.append({'object': 'library', 'slot': f'page {name}', 'status': 'refused',
                            'reading': 'the library does not hold the requested page after shelving', 'reply': reply})
                continue
        out.append({'object': 'library', 'slot': f'page {name}', **done(reply), 'reading': 'shelved' if page is None else 'the file changed'})
    return out


# A thing a kind made before its owner's protections were its own (docs/review/astra-2026-10-12 world 2, 3) holds
# a text whose only law is its kind's, `law kind "<kind>'s law holds": under "<kind>"` (and a room's scene rules
# after it), and its kind's text held RECORD_LAW (KIND_LAW for a kind made by `kinds`). Each is given that law in
# its own text before its kind's is refreshed to the kind's own clauses, so no thing is left with no owner.
REBASE = re.compile(r'law kind "([^"]+)\'s law holds": under "([^"]+)"')


def rebased(host, opener):
    """Amends a record or kind whose own text holds no law but its kind's citation to its owner's law, then that text,
    as the opener's journaled amendment (`refresh-<obj>-base-<version>`); -> [{object, slot: base, status, reply?}]."""
    out = []
    for obj in existing(host, opener):
        record = host.send({'op': 'world-object', 'principal': opener, 'object': obj}).get('record') or {}
        text = record.get('law') or ''
        first, *rest = text.split('\n')
        cited = REBASE.fullmatch(first)
        if not cited or cited.group(1) != cited.group(2) or any(line.startswith('law ') for line in rest):
            continue
        state = host.send({'op': 'world-view', 'principal': opener, 'object': obj}).get('state') or {}
        fields = {f['name'] for f in state.get('fields', [])}
        family = ({'owner', 'form', 'law', 'head', 'voice', 'about', 'body'} if cited.group(2) == 'kinds' else
                  {'owner', 'keeper', 'cites', 'start', 'passages', 'cooldown', 'requires', 'lines', 'pending',
                   'admitted', 'marks', 'presence', 'left', 'vars', 'things', 'tended'})
        if not family <= fields:
            continue
        base = KIND_LAW if cited.group(2) == 'kinds' else RECORD_LAW
        reply = host.send({'op': 'world-amend', 'principal': opener, 'identity': f'refresh-{obj}-base-{record.get("version")}', 'object': obj,
                           'version': int(record.get('version', 0)), 'law': base + '\n' + text})
        out.append({'object': obj, 'slot': 'base', **done(reply)})
    return out


def carried_fields(host, opener, kind, fields):
    """`fields` as the kind's place offers them (`world-inspect`'s template): a kind/weather whose form was `garden`
    and is not re-shaped (its form another hand's) takes the place as `garden`."""
    spell = (host.send({'op': 'world-inspect', 'principal': opener, 'object': kind}).get('templates') or {}).get('place', '')
    offered = {line.split(':', 1)[0] for line in spell.splitlines()[1:]}
    return [('garden' if name == 'over' and 'over' not in offered and 'garden' in offered else name, value) for name, value in fields]


def listed(host, opener):
    """The kinds card's line for each town kind (`kinds`' `made` rows carry what each is): a row a carried town keeps
    with none is given ABOUT's, by one owner's write; a row another hand gave a line is left."""
    record = host.send({'op': 'world-object', 'principal': opener, 'object': 'kinds'}).get('record')
    if not record:
        return []
    state = host.send({'op': 'world-view', 'principal': opener, 'object': 'kinds'}).get('state') or {}
    made = next((f['value'] for f in state.get('fields') or [] if f['name'] == 'made'), None)
    rows = ((made or {}).get('payload') or {}).get('fields', [{}])[0].get('value', {}).get('items', [])
    edits = []
    for row in rows:
        f = {x['name']: x['value'] for x in row['fields']}
        name = f['object']['value'][len('kind/'):] if f['object']['value'].startswith('kind/') else None
        if name in ABOUT and f.get('about', {}).get('value', '') == '':
            edits.append(rec(made={'tag': 'variant', 'label': 'upsert', 'payload': rec(row=rec(object=f['object'], n=f['n'], about=lab(ABOUT[name])))}))
    if not edits:
        return [{'object': 'kinds', 'slot': 'made', 'status': 'current'}]
    reply = host.send({'op': 'world-propose', 'principal': opener, 'identity': f"refresh-kinds-made-{record['version']}",
                       'roots': [{'object': 'kinds', 'version': int(record['version'])}], 'writes': [{'object': 'kinds', 'edits': edits}]})
    return [{'object': 'kinds', 'slot': 'made', **done(reply)}]


def done(reply):
    """A refresh turn's row: `refreshed`, or the host's status with its reply."""
    return {'status': 'refreshed'} if reply.get('status') == 'admitted' else {'status': reply.get('status'), 'reply': reply}


def opener_of(path):
    """The world's opener, from its journal's first entry: the settings, or a carried genesis's settings."""
    from transport import journal
    first = journal.read(path, journal.links(path)[:1])[0]['outcome']
    return (first.get('state') or {}).get('settings', first).get('opener') or OPENER


def carried(obend, path, station=False, config=None):
    """The refresh of the journal a carry just wrote at `path`, opened by the host binary `obend` as `python3 -m
    transport carry` leaves it (serve not yet started on it), as the world's opener; `station` as `refresh`'s. -> refresh's
    rows."""
    from transport.host import HostProcess
    host = HostProcess(obend)
    try:
        opened = host.send(op='world-open', path=path)
        if opened.get('status') != 'opened':
            raise RuntimeError(f'the carried journal does not open: {opened}')
        return refresh(host, opener_of(path), ancestry(path), station, config)
    finally:
        host.close()


def towns(root, own):
    """Every world journal under `root` that holds a world, other than `own` (the journal this genesis writes): a data
    directory's `*/state/*.journal`, an older layout's `*/*.journal`, a playtest run's `run-*/state/*.journal`, the
    root's own; scratch worlds are not custody and are left out. -> ([(path, height)], [unreadable]): height the chain's
    last (a carried chain continues the heights before it); unreadable every directory of those layers this process cannot list, where a town may live unseen
    (a glob skips them silently: the deploy of 5db9aa79 ran as 10425 over a root-owned 0700 `/towns` and saw none)."""
    from transport import journal
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
        try:
            last = (journal.links(path) or [{}])[-1]
        except ValueError as e:
            unreadable.append(f'{path} ({e})')
            continue
        if last:
            found.append((str(path), last['height']))
    return found, unreadable


def first_line(host, opener, text, identity):
    """`text` as the town's first line: written on the commonplace and admitted by its keeper, the opener."""
    turned(identity, said(host, opener, 'commonplace', 'write', [('text', text)], identity)['reply'])
    return turned(identity + ' admitted', said(host, opener, 'commonplace', 'admit', [('number', '1')], identity + '-admit')['reply'])


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
    ap.add_argument('--with-gas-station', action='store_true',
                    help='also make the all-night station on a town that lacks it, as genesis --with-gas-station makes it')
    a = ap.parse_args(argv)
    path = os.path.join(a.state, f'{a.world}.journal')
    host = HostClient(a.root_socket, a.world)
    try:
        rows = refresh(host, opener_of(path), ancestry(path), a.with_gas_station, Config.load(a.state))
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
    ap.add_argument('--opener', help="the world's opener, the town's own principal (default: config `opener`, the origin's did:web)")
    ap.add_argument('--state', default=os.environ.get('DELVETALK_STATE'), help='the state directory this genesis writes (DELVETALK_STATE)')
    ap.add_argument('--towns', default=os.environ.get('DELVETALK_TOWNS'), help='the directory holding every data directory (DELVETALK_TOWNS)')
    ap.add_argument('--with-gas-station', action='store_true',
                    help="also make the all-night station at the edge of the town (capsules/pages/station.txt), for the owner's word")
    ap.add_argument('--profile', choices=('town', 'open'), default='town',
                    help="open: an open town (docs/DEPLOY.md \"A second instance\"): the station, the register, the page `arrive` and its "
                         "first line, the config's limits for newcomers, no page posted; needs the config's arrival to be open")
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
    config = Config.load(a.state) if a.state else Config.load()  # the town's own origin, opener and limits (delvetalk.toml, DELVETALK_*)
    if a.profile == 'open' and config.arrival != 'open':
        print('genesis --profile open: the config says arrival is invited; an open town says arrival = "open" in its delvetalk.toml', file=sys.stderr)
        return 64
    opener = a.opener or config.opener
    host = HostClient(a.root_socket, a.world)
    try:
        made, refusal = open_town(host, opener, config) if a.profile == 'open' else \
            run(host, opener, gas_station=a.with_gas_station, origin=config.origin)
        if not refusal and a.word is not None:  # the word given is the town's first line, whatever the guard saw
            try:
                made.append({'object': 'commonplace', 'module': 'the owner\'s word', 'status': wipe(host, opener, a.word), 'reply': {}})
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
