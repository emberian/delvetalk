"""The hand's root console and its moderation verbs (docs/ROOT.md 1.6 and 2.3; HOST-HANDOFF 5.126): one table, read by
the CLI (`hand root <verb>`, `hand <power>`) and the web face (`/hand/<world>/root/`), each write one request on the root
socket under the opener, each carrying a reason (root) or a reading (moderation); the journal is the record, and root's
journal browser reads it whole.
"""
import json
import time
from pathlib import Path

from transport import journal
from transport.host import HISTORY_LIMIT, typed
from transport.identity import SLUG, slug

# verb -> (fields, the request it sends). A field is (name, kind): text, int, json (a value), or ? after it when optional.
ROOT = {
    'set': (('object', 'text'), ('field', 'text'), ('value', 'json')),
    'delete': (('object', 'text'),),
    'as': (('principal', 'text'), ('object', 'text'), ('method', 'text'), ('argument', 'json'), ('intent', 'text')),
    'settings': (('clock', 'int?'), ('postQuota', 'int?'), ('interpretQuota', 'int?'), ('modelQuota', 'int?')),
    'library': (('dir', 'text'),),
    'ignore': (('height', 'int'),), 'unignore': (('height', 'int'),),
    'card': (('object', 'text'), ('text', 'text?')),
    'quiet': (('principal', 'text'), ('hours', 'int')),  # the powers without the law (ROOT 1.1); hours 0 clears a quiet
    'hide': (('object', 'text'),), 'show': (('object', 'text'),), 'retire': (('object', 'text'),), 'unretire': (('object', 'text'),),
    'revoke': (('grant', 'text'),),
    'expire': (('principal', 'text'), ('scratch', 'text')),  # a scratch world is serve's: discarded now, in the hand's log only
}
MOD_SETTINGS = (('postQuota', 'int?'), ('interpretQuota', 'int?'), ('modelQuota', 'int?'))
POWERS = {  # (the object the power is cast on: a field's value, or `world`), its fields
    'quiet': ('world', (('who', 'text'), ('hours', 'int'))), 'unquiet': ('world', (('who', 'text'),)),
    'retire': ('object', (('object', 'text'),)), 'unretire': ('object', (('object', 'text'),)),
    'hide': ('object', (('object', 'text'),)), 'show': ('object', (('object', 'text'),)),
    'revoke': ('world', (('grant', 'text'),)),
}


def value(kind, raw):
    """A form's or a flag's text as the field's value; None for an optional field left empty."""
    if raw is None or (raw == '' and kind.endswith('?')):
        return None
    kind = kind.rstrip('?')
    return int(raw) if kind == 'int' else json.loads(raw) if kind == 'json' else raw


def fields(spec, given):
    return {name: v for name, kind in spec if (v := value(kind, given.get(name))) is not None}


def act(verb, given):
    """`world-root`'s act for a root verb (ROOT 1.1)."""
    got = fields(ROOT[verb], given)
    if verb == 'as':
        return {'kind': 'as', 'principal': got['principal'], 'turn': {k: got[k] for k in ('object', 'method', 'argument')} | {'identity': got['intent']}}
    if verb == 'library':
        return {'kind': 'library', 'modules': [{'name': p.stem, 'source': p.read_text()} for p in sorted(Path(got['dir']).glob('*.obend'))]}
    if verb == 'card':
        return {'kind': 'card', 'object': got['object'], 'text': got.get('text')}  # no text clears the override
    return {'kind': verb, **got}


def request(face, verb, given, opener, clock=time.time):
    """The one request a write verb sends: for face `root` a root act with its reason; for `mod` a moderation power (or
    the receipted `settings`) with its reading."""
    if face == 'root':
        if not (given.get('reason') or '').strip():
            raise ValueError('a root act needs a reason')
        return {'op': 'world-root', 'principal': opener, 'reason': given['reason'].strip(), 'act': act(verb, given)}
    if not (given.get('reading') or '').strip():
        raise ValueError(f'{verb} needs a reading')
    if verb == 'settings':  # the receipted quotas (world-settings), not root's
        return {'op': 'world-settings', 'principal': opener, 'reading': given['reading'].strip(), **fields(MOD_SETTINGS, given)}
    on, spec = POWERS[verb]
    got = fields(spec, given)
    target = got.pop('object') if on == 'object' else 'world'
    return {'op': 'world-turn', 'principal': opener, 'object': target, 'method': verb, 'identity': f'hand:{verb}:{int(clock() * 1000)}',
            'argument': typed({**got, 'reading': given['reading'].strip()})}


def dump(host, opener, obj):
    """An object as the opener reads it: its view (state, version), its record (pin, law, readings, state CID, library),
    its sources, and its dump (owner, read policy, fixed fields, supervisor, causal ledger, the activities waiting)."""
    return {k: host.send({'op': op, 'principal': opener, 'object': obj, **more})
            for k, op, more in (('view', 'world-view', {}), ('record', 'world-object', {}), ('source', 'world-inspect', {'source': True}),
                                ('dump', 'world-dump', {}))}


def entries(st, after=None, limit=20, object=None, principal=None, before=None):
    """A page of the world's journal, whole, each with its slug: read from the journal itself, since the host projects
    another's refusal even to the opener and root reads the record. Newest first (below `before`), or oldest first after
    `after`; `object` and `principal` narrow the page."""
    if after is not None:
        got = journal.read(st.journal, [l for l in journal.links(st.journal) if l['height'] > after][:limit]) if st.journal.exists() else []
    else:
        got = journal.tail(st.journal, limit, before)[::-1]
    keep = lambda e: (not object or object in json.dumps(e.get('roots') or []) + json.dumps((e.get('outcome') or {}).get('object'))) and \
        (not principal or (e.get('identity') or {}).get('principal') == principal)
    return [dict(e, slug=slug(e.get('hash'))) for e in got if keep(e)]


def modlog(host, opener, object=None, tail=20):
    """The moderation log: an object's `world-history`, or the newest root, moderated and opener entries of the journal."""
    if object:
        return host.send({'op': 'world-history', 'principal': opener, 'object': object, 'reverse': True, 'limit': min(tail, HISTORY_LIMIT)}).get('entries') or []
    page = host.send({'op': 'world-entries', 'principal': opener, 'reverse': True, 'limit': 100}).get('entries') or []
    return [e for e in page if e.get('root') or (e.get('outcome') or {}).get('tag') == 'moderated'
            or (e.get('identity') or {}).get('principal') == opener][:tail]


def find(host, opener, text, observed=()):
    """One box (ROOT 2.3): handles the bridge has observed, objects whose id starts with the text, a receipt by slug."""
    t = text.strip()
    return {'handles': sorted({(o['author']['handle'], o['author']['did']) for o in observed if t.lower() in o['author']['handle'].lower()}),
            'objects': host.send({'op': 'world-objects', 'principal': opener, 'prefix': t}).get('ids') or [],
            **({'receipt': host.send({'op': 'world-resolve', 'principal': opener, 'slug': t})} if SLUG.fullmatch(t) else {})}


def edit_command(entry, height, journal_path, path):
    """An entry cannot be edited in place: save its record (without the slug and size the reader derived) and print the
    offline `root-edit rewrite` (ROOT 1.5)."""
    Path(path).write_text(json.dumps({k: v for k, v in entry.items() if k not in ('slug', 'bytes')}, indent=1, sort_keys=True) + '\n')
    return (f'docker compose down && deploy/backup.sh ... && delvetalk-obend root-edit --journal {journal_path} --out {journal_path}.edited '
            f'--reason REASON rewrite --height {height} --entry {path}')
