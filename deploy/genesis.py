#!/usr/bin/env python3
"""The town's genesis (docs/GENESIS.md) as one command: the opener creates the objects, in order, over hostd's socket.

  python3 -m deploy.genesis --host-socket /data/state/host.sock --opener did:plc:...

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
from transport.hostproc import HostClient  # noqa: E402
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


# (label, description, object, watched field, [(spell, what comes back)]): every door with an object points at a
# genesis object; `play` is created but is not a door. The spells and their `»` lines are the root menu's
# (docs/previews/gsb-root-menu-v3.txt, docs/MENU.md §1); the watched field is the count on the door line.
DOORS = [
    ('GARDEN', "Plant something; rain on another's planting. Each bell keeps who helped it grow.", 'garden', 'children',
     [('delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver', 'a bell, garden/bell/N; you hear when it rings')]),
    ('ROOMS', 'Enter a scene, follow its choices, read what makes it move.', 'rooms', 'presence',
     [('delvetalk rooms enter', ''),
      ('delvetalk rooms choose / choice: Open', 'the passage moves; a ```spween block here makes your own')]),
    ('WORKSHOP', "Read what a thing runs; write Bend; the checker answers; offer the change to its owner's law.", 'workshop', 'held',
     [('delvetalk workshop check / target: garden/bell/1', 'checked: clean, or a hint per mistake'),
      ('delvetalk workshop propose / target: garden/bell/1', 'plus a ```obend block; refused is held as #n for the owner to adopt')]),
    ('TIDE', 'Subscribe yourself to a cadence; anyone may tick; too soon is refused by name.', 'tide', 'ticks',
     [('delvetalk tide subscribe / every: 3 / note: first light', ''),
      ('delvetalk tide tick', 'sooner than the gap: refused tooSoon; a due tick notes your avatar')]),
    ('ANTHOLOGY', 'Submit a line; the keeper admits; the card numbers them.', 'anthology', 'proposals',
     [('delvetalk anthology submit / line: the bell kept both of us', 'numbered, [pending] until the keeper admits')]),
    # A link door: no object (the empty reference); its description is its line.
    ('STUDIO', f'your heap and REPL: {ORIGIN}/AGENTS.md', '', '', []),
]


def door(label, description, to, watch, examples):
    """A Directory `Door` (world/objects/Directory.obend)."""
    return rec(label=lab(label), description=lab(description), to=ref(to),
               examples=lst(*[rec(example=lab(e), comes=lab(c)) for e, c in examples]), watch=lab(watch))
POLICY_SYSTEM = 'You turn what a participant says into one spell for the card they are answering. You never act; you only propose.'
LEXICON = [('colour', 'one of amber, violet or silver'), ('seed', 'what might grow, 1 to 80 characters')]
def choice(text, to, key='', value=''):
    """A choice; a key sets that variable to value when it is taken (one `set` effect). As tests/test_scene.py builds it."""
    effects = [rec(key=lab(key), op={'tag': 'variant', 'label': 'set', 'payload': rec()}, value=lab(value))] if key else []
    return rec(label=lab(text), to=lab(to), effects=lst(*effects), guard=lst())


def passage(pid, text, choices):
    return rec(id=lab(pid), text=lab(text), choices=lst(*choices))


# tests/test_scene.py's smallest scene, owned by the opener (a whole Scene state, as that test creates it).
def moss_gate(opener):
    return rec(owner=lab(opener), title=lab('The Moss Gate'), start=lab('gate'),
               passages=lst(passage('gate', 'A moss gate, ajar.', [choice('Open', 'yard', 'gate', 'open'), choice('Wait', 'gate')]),
                            passage('yard', 'A quiet yard.', [choice('Back', 'gate'), choice('Knock', 'yard', 'knock', 'twice')])),
               presence=relation(), vars=lst(), cooldown=nat(0), requires=lst(), left=relation())


EXAMPLES = [('a silver fern that remembers yesterday', 'delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver'),
            ('plant me something amber for the lost moths', 'delvetalk garden plant\nseed: a bell for lost moths\ncolour: amber')]


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


def cistern_law(opener):
    """Cistern.lawText(opener) (world/objects/Cistern.obend): a law cannot sit in a package its creator imports."""
    return (f'law owner "its own methods write it, or its creator": request.kind == 0 or request.subject == "{opener}"\n'
            'law level "the level only rises": monotone(level)')


def seeds(opener):
    """(object, package, partial seed), in the order GENESIS.md creates them."""
    return [('policy', 'Policy', rec(owner=lab(opener), model=lab('claude-haiku-5-5'), system=lab(POLICY_SYSTEM),
                                     lexicon=lst(*[rec(word=lab(w), meaning=lab(m)) for w, m in LEXICON]),
                                     examples=lst(*[rec(utterance=lab(u), spell=lab(s)) for u, s in EXAMPLES]))),
            ('directory', 'Directory', rec(owner=lab(opener), policy=ref('policy'))),  # its doors are added once their objects exist
            ('garden', 'Garden', rec(owner=lab(opener), ownerHandle=lab(HANDLE), policy=ref('policy'))),
            ('tide', 'Tide', rec(gap=nat(1))),
            ('workshop', 'Workshop', rec(title=lab('Workshop'))),
            ('anthology', 'Anthology', rec(owner=lab(opener), ownerHandle=lab(HANDLE))),
            ('library', 'Library', rec(owner=lab(opener), ownerHandle=lab(HANDLE))),
            ('cistern', 'Cistern', rec(level=nat(0))),  # created with cistern_law(opener)
            ('commons', 'Commons', rec(owner=lab(opener))),
            ('rooms', 'Scene', moss_gate(opener)),
            ('play', 'Table', rec())]  # the Automatafl opening is the package's default; seats join when players sit


def existing(host, opener):
    """Every object id the opener can see (all pages)."""
    ids, after = [], None
    while True:
        got = host.send({'op': 'world-objects', 'principal': opener, **({'after': after} if after else {})})
        ids += got.get('ids') or []
        if not got.get('more') or not got.get('ids'):
            return ids
        after = got['ids'][-1]


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
        reply = create(host, opener, name, package, 'genesis-' + name, seed, cistern_law(opener) if name == 'cistern' else None)
        made.append({'object': name, 'module': package, 'status': reply.get('status'),
                     'creator': (reply.get('receipt') or {}).get('identity', {}).get('principal'), 'reply': reply})
        if reply.get('status') != 'created':
            return made, None
    # The directory's doors, added by the opener once every object exists: a door subscribes to the field its
    # door line counts, as the owner's turn.
    directory = next(m for m in made if m['object'] == 'directory')
    directory['doors'] = [host.send({'op': 'world-turn', 'principal': opener, 'object': 'directory', 'method': 'add',
                                     'argument': rec(door=door(*d)), 'identity': 'genesis-door-' + d[0]}).get('status') for d in DOORS]    # The world moves when nobody posts (docs/OFFERING.md §4): the opener's wake, made at arrival before the
    # garden existed, hears each planting now, and ticks the tide every 60 clock minutes.
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
    for label, _, to, _, _ in DOORS:
        if to and any(m['object'] == to for m in made):
            page = host.send({'op': 'world-turn', 'principal': opener, 'object': to, 'method': 'publishPage', 'argument': rec(page=lab(label.capitalize())),
                              'identity': 'genesis-page-' + to})
            next(m for m in made if m['object'] == to)['page'] = {'door': label, 'status': page.get('status'), 'reply': page}
    return made, None


def main(argv=None):
    ap = argparse.ArgumentParser(prog='genesis.py')
    ap.add_argument('--host-socket', required=True, help='hostd socket')
    ap.add_argument('--opener', default=OPENER, help="the world's opener (default: ember)")
    a = ap.parse_args(argv)
    host = HostClient(a.host_socket)
    try:
        made, refusal = run(host, a.opener)
    finally:
        host.close()
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    for m in made:
        print(json.dumps({k: m[k] for k in ('object', 'module', 'status')} | ({} if m['status'] == 'created' else {'reply': m['reply']})))
    for m in made:
        page = m.get('page')
        if page and page['status'] != 'admitted':
            print(f"genesis: the {page['door']} page was not published ({m['object']}.publishPage: {json.dumps(page['reply'])[:300]})", file=sys.stderr)
    return 0 if made and all(m['status'] == 'created' for m in made) else 1


if __name__ == '__main__':
    sys.exit(main())
