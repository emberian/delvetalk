#!/usr/bin/env python3
"""Retained typed cards for posts-only worlds. No publishing or admission."""
import copy
from contextlib import contextmanager, closing
import importlib.util
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affordances
import world
import references

FORMAT = 'delvetalk-town-cardbook-v1'
FEED = 'town.delve.feed.post'
ALIAS = re.compile(r'[a-z][a-z0-9-]{0,47}\Z')
ACTION = re.compile(r'a[1-9][0-9]{0,5}\Z')
DID = re.compile(r'did:plc:[a-z2-7]{24}\Z')
MAX_CARD_BYTES = 12000
MAX_CARDS = 10000
MAX_REPLY_BYTES = 65536
MARKER = re.compile(r'^\[\[(/?)delvetalk-card ([a-z][a-z0-9-]{0,47})\]\]$', re.M)


def loads(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate JSON field: ' + key)
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('non-JSON number: ' + value)
    return json.loads(raw, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=pairs)


def canonical(value):
    def ordered(item):
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError('JSON keys must be strings')
            return {k: ordered(item[k]) for k in sorted(item)}
        if isinstance(item, list):
            return [ordered(x) for x in item]
        return item
    return world.wire_dumps(ordered(value))


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def alias_name(value):
    if not isinstance(value, str) or not ALIAS.fullmatch(value):
        raise ValueError('card name must be 1..48 lowercase ASCII letters/digits/hyphens, starting with a letter')
    return value


def publication_source(source, issuer=None):
    if not isinstance(source, dict) or not {'uri', 'cid'} <= set(source):
        raise ValueError('publication requires exact URI and CID')
    uri, cid = source['uri'], source['cid']
    parts = uri.split('/') if isinstance(uri, str) else []
    if (len(parts) != 5 or parts[:2] != ['at:', ''] or not DID.fullmatch(parts[2])
            or parts[3] != FEED or not re.fullmatch(r'[A-Za-z0-9._~:-]{1,512}', parts[4])
            or parts[4] in ('.', '..') or not isinstance(cid, str) or not 1 <= len(cid) <= 200):
        raise ValueError('expected a feed-post URI and nonempty CID')
    if issuer is not None and parts[2] != issuer:
        raise ValueError('publication issuer differs from configured DID')
    return {'uri': uri, 'cid': cid}


def parse_reply(text):
    """Shape/typed-JSON syntax only; never look up a card or infer an action."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_REPLY_BYTES:
        raise ValueError('town reply text exceeds 64 KiB')
    match = re.fullmatch(r'delvetalk ([a-z][a-z0-9-]{0,47}) (a[1-9][0-9]{0,5}) (\{.*\})', text.strip(), re.S)
    if not match:
        raise ValueError('reply must be exactly: delvetalk CARD ACTION {JSON fields}')
    fields = loads(match[3])
    if not isinstance(fields, dict):
        raise ValueError('town reply fields must be a JSON object')
    return {'card': match[1], 'action': match[2], 'fields': fields}


def _field(field):
    kind = field['type']
    if kind == 'string':
        bounds = str(field['minLength']) + '..' + str(field['maxLength']) + ' chars'
    elif kind == 'nat':
        bounds = str(field['minimum']) + '..' + str(field['maximum'])
    elif kind == 'enum':
        bounds = canonical(field['options'])
    else:
        bounds = 'true|false'
    return canonical(field['name']) + ': ' + kind + ' ' + bounds


def _example(action):
    values = {}
    for field in action['fields']:
        if field['type'] == 'string':
            values[field['name']] = 'x' * max(field['minLength'], min(field['maxLength'], 4))
        elif field['type'] == 'nat':
            values[field['name']] = field['minimum']
        elif field['type'] == 'enum':
            values[field['name']] = field['options'][0]
        else:
            values[field['name']] = False
    # Child names have a stricter alphabet than ordinary bounded strings.
    for child in action.get('children', []):
        if 'value' not in child:
            field = next(f for f in action['fields'] if f['name'] == child['field'])
            values[child['field']] = 'x' * max(1, field['minLength'])
    return values


def _panels(view):
    declared = view['root']['protocol'].get('viewPanels', [])
    if not isinstance(declared, list) or len(declared) > 8:
        raise ValueError('viewPanels must be an array of at most eight panels')
    seen, panels = set(), []
    for entry in declared:
        if (not isinstance(entry, dict) or set(entry) != {'id', 'label'}
                or any(not isinstance(entry[k], str) or not entry[k] or len(entry[k].encode('utf-8')) > 128 for k in entry)
                or entry['id'] in seen):
            raise ValueError('invalid or duplicate declared view panel')
        seen.add(entry['id'])
        if view['mode'] != 'projection':
            raise ValueError('declared panels require an installed pure view program')
        spec = importlib.util.spec_from_file_location('town_room', Path(__file__).resolve().parents[1] / 'scene/room.py')
        room = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(room)
        panel = room.inspect_object(view['root'], view['object'], panel=entry['id'])
        if (panel.get('mode') != 'projection' or panel.get('object') != view['object']
                or canonical(panel.get('root')) != canonical(view['root'])):
            raise ValueError('declared panel did not produce a pure view of the captured root')
        panels.append({**entry, 'view': panel})
    return panels


def render_card(alias, card, view, panels=(), display_names=None):
    lines = ['[[delvetalk-card ' + alias + ']]', canonical(card['title']),
             'Object ' + canonical(card['object']) + ' · captured version ' + str(card['version'])]
    def prose(text):
        def display(match):
            return (display_names or {}).get(match[0], match[0])
        shown = re.sub(r'did:plc:[a-z2-7]{24}(?![a-z2-7])', display, text)
        return '\n'.join('| ' + line for line in shown.split('\n'))
    if card['prose']:
        lines.append(prose(card['prose']))
    for panel in panels:
        data = panel['view']['data']
        lines.append(canonical(panel['label']) + ':')
        lines.append(prose(data['prose']))
    if view['mode'] == 'raw':
        lines.append('State: ' + canonical(view['root']['state']))
    lines.append('Reply to THIS post with one complete command. Edit example values to your choice.')
    for action in card['actions']:
        lines.append(action['id'] + ': ' + canonical(action['label']))
        if not action.get('available') or action.get('inspectOnly'):
            lines.append('Inspection only; no executable reply form.')
            continue
        lines.extend('  ' + _field(f) for f in action['fields'])
        if action.get('children'):
            lines.append('Requires absent children: ' + ', '.join(
                canonical(child.get('value', '<' + child['field'] + '>')) for child in action['children']))
        if action.get('observedAvailable') is False:
            lines.append('The captured view reports this guard unavailable; admission may refuse.')
        lines.append('delvetalk ' + alias + ' ' + action['id'] + ' ' + canonical(_example(action)))
    if not card['actions']:
        lines.append('No typed actions are available on this card.')
    lines.extend(['Someone may act first; an old card can be refused. Use the next card after a refusal.',
                  'If no result appears, ask us to check your original reply. Do not repost the command.',
                  '[[/delvetalk-card ' + alias + ']]'])
    body = '\n'.join(lines)
    if len(body.encode('utf-8')) > MAX_CARD_BYTES:
        raise ValueError('town card exceeds 12000 bytes; choose a smaller explicit view/projection')
    _block(body, alias)  # Reject application prose that tries to forge delimiters.
    return body


def _block(text, alias):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 1024 * 1024:
        raise ValueError('publication text missing or exceeds 1 MiB')
    active = None
    blocks = {}
    for marker in MARKER.finditer(text):
        closing, name = marker[1], marker[2]
        if not closing:
            if active is not None or name in blocks:
                raise ValueError('nested or duplicate card block')
            active = (name, marker.start())
        else:
            if active is None or active[0] != name:
                raise ValueError('unbalanced card block')
            blocks[name] = text[active[1]:marker.end()]
            active = None
    if active is not None or alias not in blocks:
        raise ValueError('missing or incomplete bound card block')
    return blocks[alias]


class CardBook:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_dir() or not (self.path / 'cards.sqlite3').is_file():
            raise ValueError('cardbook does not exist; create it explicitly')
        self.metadata()  # Validate opened custody before any action.

    @classmethod
    def create(cls, path, *, issuer_did, world_id, runtime, display_names=None):
        if not isinstance(issuer_did, str) or not DID.fullmatch(issuer_did):
            raise ValueError('card issuer must be an explicitly configured PLC DID')
        references.component(world_id)
        display_names = {} if display_names is None else display_names
        if (not isinstance(display_names, dict) or len(display_names) > 256
                or any(not isinstance(did, str) or not DID.fullmatch(did) or not isinstance(label, str)
                       or not 1 <= len(label.encode('utf-8')) <= 128 or '\n' in label
                       for did, label in display_names.items())):
            raise ValueError('invalid explicit DID display-name mapping')
        if not isinstance(runtime, dict) or not runtime:
            raise ValueError('explicit pinned runtime required')
        path = Path(path).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        metadata = {'format': FORMAT, 'issuerDid': issuer_did, 'worldId': world_id, 'runtime': runtime, 'displayNames': display_names}
        with closing(sqlite3.connect(path / 'cards.sqlite3', timeout=10)) as db, db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS cards (alias TEXT PRIMARY KEY, value TEXT NOT NULL, digest TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS bindings (alias TEXT PRIMARY KEY REFERENCES cards(alias), value TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO metadata VALUES(1, ?)', (canonical(metadata),))
            if db.execute('SELECT value FROM metadata WHERE id=1').fetchone()[0] != canonical(metadata):
                raise ValueError('cardbook already bound to another issuer, world or runtime')
        (path / 'cards.sqlite3').chmod(0o600)
        return cls(path)

    open = classmethod(lambda cls, path: cls(path))

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path / 'cards.sqlite3', timeout=10)) as db, db:
            db.execute('PRAGMA synchronous=FULL')
            yield db

    def metadata(self):
        with self._db() as db:
            row = db.execute('SELECT value FROM metadata WHERE id=1').fetchone()
        value = loads(row[0]) if row else None
        if (not isinstance(value, dict) or set(value) != {'format', 'issuerDid', 'worldId', 'runtime', 'displayNames'}
                or value['format'] != FORMAT or not DID.fullmatch(value['issuerDid'])):
            raise ValueError('invalid cardbook metadata')
        return value

    def aliases(self):
        with self._db() as db:
            return [row[0] for row in db.execute('SELECT alias FROM cards ORDER BY rowid')]

    def capture(self, view, alias=None):
        """Retain a captured view; never read a world or publish a post."""
        if alias is not None:
            alias_name(alias)
        metadata = self.metadata()
        view = copy.deepcopy(view)
        card = affordances.card(view)
        panels = _panels(view)
        object_ref = references.object_reference(metadata['worldId'], view['object'])
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if alias is None:
                # Never reuse an alias, including after an explicit card-N name.
                serial = db.execute('SELECT COALESCE(MAX(rowid),0)+1 FROM cards').fetchone()[0]
                while db.execute('SELECT 1 FROM cards WHERE alias=?', ('card-' + str(serial),)).fetchone():
                    serial += 1
                alias = 'card-' + str(serial)
            body = render_card(alias, card, view, panels, metadata['displayNames'])
            value = {'format': 'delvetalk-town-card-v1', 'alias': alias, 'view': view,
                     'card': card, 'runtime': metadata['runtime'],
                     'objectRef': object_ref, 'panels': panels,
                     'body': body, 'textSha256': sha(body)}
            encoded = canonical(value)
            existing = db.execute('SELECT value FROM cards WHERE alias=?', (alias,)).fetchone()
            if existing:
                if existing[0] != encoded:
                    raise ValueError('card alias is already bound to another captured view')
            else:
                if db.execute('SELECT COUNT(*) FROM cards').fetchone()[0] >= MAX_CARDS:
                    raise ValueError('cardbook retention bound reached')
                db.execute('INSERT INTO cards VALUES(?,?,?)', (alias, encoded, sha(encoded)))
        return value

    def card(self, alias):
        with self._db() as db:
            row = db.execute('SELECT value,digest FROM cards WHERE alias=?', (alias_name(alias),)).fetchone()
        if not row or sha(row[0]) != row[1]:
            raise ValueError('unknown or damaged captured card')
        value = loads(row[0])
        if value['alias'] != alias or sha(value['body']) != value['textSha256']:
            raise ValueError('captured card content mismatch')
        return value

    def publication(self, alias):
        self.card(alias)
        with self._db() as db:
            row = db.execute('SELECT value FROM bindings WHERE alias=?', (alias,)).fetchone()
        if not row:
            raise ValueError('card has no verified publication binding')
        return loads(row[0])

    def _verified(self, alias, source, fetch_record):
        source = publication_source(source, self.metadata()['issuerDid'])
        record = fetch_record(source['uri'], source['cid'])
        if not isinstance(record, dict) or record.get('$type') != FEED:
            raise ValueError('publication is not a feed post')
        card = self.card(alias)
        if _block(record.get('text'), alias) != card['body']:
            raise ValueError('published card block differs from immutable captured text')
        return {'source': source, 'record': record, 'textSha256': sha(record['text'])}

    def bind(self, alias, source, fetch_record):
        """Caller supplies authenticated GET-only URI/CID verification; no posting."""
        verified = self._verified(alias, source, fetch_record)
        encoded = canonical(verified)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT value FROM bindings WHERE alias=?', (alias,)).fetchone()
            if old and old[0] != encoded:
                raise ValueError('card already bound to another immutable publication')
            db.execute('INSERT OR IGNORE INTO bindings VALUES(?,?)', (alias, encoded))
        return verified

    def resolve(self, record, author, source, fetch_record, issuers):
        metadata = self.metadata()
        if metadata['issuerDid'] not in issuers:
            raise ValueError('card issuer is not configured for this receiver')
        publication_source(source, author)
        if source.get('author', author) != author:
            raise ValueError('verified reply author mismatch')
        if not isinstance(record, dict) or record.get('$type') != FEED:
            raise ValueError('literal reply requires a feed post')
        parsed = parse_reply(record.get('text'))
        alias = parsed['card']
        captured, bound = self.card(alias), self.publication(alias)
        reply = record.get('reply')
        if not isinstance(reply, dict):
            raise ValueError('reply parent must name the bound card publication')
        parent = reply.get('parent')
        if not isinstance(parent, dict) or set(parent) != {'uri', 'cid'} or parent != bound['source']:
            raise ValueError('reply parent does not match the bound card publication')
        verified = self._verified(alias, bound['source'], fetch_record)
        if canonical(verified) != canonical(bound):
            raise ValueError('bound publication changed since capture')
        request = affordances.request(captured['view'], parsed['action'], author,
                                      'delve:' + source['uri'], parsed['fields'])
        if len(canonical(request).encode('utf-8')) > MAX_REPLY_BYTES:
            raise ValueError('derived card request exceeds 64 KiB')
        wire = {key: value for key, value in request.items() if key not in ('principal', 'intent')}
        evidence = {'format': 'delvetalk-town-resolution-v1', 'metadata': metadata,
                    'card': captured, 'publication': bound, 'replySource': copy.deepcopy(source),
                    'parsed': parsed, 'wireSha256': sha(canonical(wire))}
        return wire, evidence

    def prepare_outcome(self, receipt, current_views=(), *, label='Turn'):
        """Render confirmed/refused/uncertain outcomes plus explicitly supplied current views.

        The caller authenticates the receipt and supplies current snapshots; this
        helper neither refreshes them nor treats a missing reply as failure.
        """
        if not isinstance(receipt, dict) or receipt.get('kind') not in ('committed', 'refused', 'uncertain'):
            raise ValueError('explicit committed, refused or uncertain receipt required')
        if receipt['kind'] == 'uncertain':
            body = label + ': outcome unknown. Ask us to check your original reply. Do not repost the command.'
        elif receipt['kind'] == 'refused':
            body = label + ': refused. ' + canonical(receipt.get('data')) + '\nNo application changes committed.'
        else:
            body = label + ': committed.'
            children = affordances.allocated_refs(receipt)
            if children:
                body += '\nCreated: ' + ', '.join(canonical(child['object']) for child in children)
        cards = [self.capture(view) for view in current_views]
        if cards:
            body += '\n\nCurrent captured views and next actions:\n' + '\n\n'.join(card['body'] for card in cards)
        return {'body': body, 'textSha256': sha(body), 'cards': cards, 'receipt': copy.deepcopy(receipt),
                'scope': 'Prepared locally; publication and subsequent binding are separate.'}


def resolver(book, record, author, source, fetch_record, issuers):
    return book.resolve(record, author, source, fetch_record, issuers)
