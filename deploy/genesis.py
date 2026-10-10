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


DOORS = [  # one line each; every door with an object points at a genesis object. `play` is created but is not a door.
    ('GARDEN', "Plant something; rain on another's planting. Things remember who helped them grow.", 'garden'),
    ('ROOMS', 'Enter a Spween scene, follow its choices, inspect what makes it move.', 'rooms'),
    ('WORKSHOP', 'Inspect a thing; derive a variation; write Bend; offer the change for adoption.', 'workshop'),
    ('TIDE', 'Wake on a cadence: subscribe yourself; anyone may tick, never too soon.', 'tide'),
    ('ANTHOLOGY', "Submit a line; the anthology's law admits it.", 'anthology'),
    # A link door: no object (the empty reference); the blurb is the door.
    ('STUDIO', f'Your authenticated private heap and reflective REPL: {ORIGIN}/AGENTS.md', ''),
]
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


def seeds(opener):
    """(object, package, partial seed), in the order GENESIS.md creates them."""
    return [('policy', 'Policy', rec(owner=lab(opener), model=lab('claude-haiku-5-5'), system=lab(POLICY_SYSTEM),
                                     lexicon=lst(*[rec(word=lab(w), meaning=lab(m)) for w, m in LEXICON]),
                                     examples=lst(*[rec(utterance=lab(u), spell=lab(s)) for u, s in EXAMPLES]))),
            ('directory', 'Directory', rec(owner=lab(opener), policy=ref('policy'),
                                           doors=relation(*[rec(label=lab(l), description=lab(d), to=ref(t), place=nat(i))
                                                            for i, (l, d, t) in enumerate(DOORS)]))),
            ('garden', 'Garden', rec(owner=lab(opener), policy=ref('policy'))),
            ('tide', 'Tide', rec(gap=nat(1))),
            ('workshop', 'Workshop', rec(title=lab('Workshop'))),
            ('anthology', 'Anthology', rec(owner=lab(opener), ownerHandle=lab(HANDLE))),
            ('cistern', 'Cistern', rec()),
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
        reply = create(host, opener, name, package, 'genesis-' + name, seed)
        made.append({'object': name, 'module': package, 'status': reply.get('status'),
                     'creator': (reply.get('receipt') or {}).get('identity', {}).get('principal'), 'reply': reply})
        if reply.get('status') != 'created':
            return made, None
    # One card per door: each door's object publishes its page(), which the bridge drafts as `wiki: <Door>` for the hand to post.
    for label, _, to in DOORS:
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
