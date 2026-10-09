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
import adoption
import composite_offers

_projection_spec = importlib.util.spec_from_file_location('town_projection',
    Path(__file__).resolve().parents[1] / 'scene/projection.py')
projection = importlib.util.module_from_spec(_projection_spec)
_projection_spec.loader.exec_module(projection)

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


WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_-]{0,127}\Z')
DELIMITER = re.compile(r'<<([A-Za-z][A-Za-z0-9_-]{0,31})\Z')


def parse_reply(text):
    """Parse literal syntax; action and field meanings require a captured card."""
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_REPLY_BYTES:
        raise ValueError('town reply text exceeds 64 KiB')
    legacy = re.fullmatch(r'delvetalk ([a-z][a-z0-9-]{0,47}) (a[1-9][0-9]{0,5}) (\{.*\})', text.strip(), re.S)
    if legacy:
        return {'card': legacy[1], 'action': legacy[2], 'fields': loads(legacy[3])}
    # Strip only blank framing lines. Never strip a field value or normalize Unicode.
    lines = text.split('\n')
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while start < end and not lines[end - 1].strip():
        end -= 1
    lines = lines[start:end]
    header = re.fullmatch(r'delvetalk ([a-z][a-z0-9-]{0,47}) ([A-Za-z_][A-Za-z0-9_-]{0,127})',
                          lines[0].strip() if lines else '')
    if not header:
        raise ValueError('reply must start with exactly: delvetalk CARD OFFERED-WORD')
    fields, index = {}, 1
    while index < len(lines):
        field = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_-]{0,127}):(?: (.*))?', lines[index])
        if not field or field[1] in fields:
            raise ValueError('expected unique offered field: literal value lines')
        key, value = field[1], field[2] or ''
        index += 1
        if value.startswith('<<'):
            marker = DELIMITER.fullmatch(value)
            if not marker:
                raise ValueError('literal block requires <<DELIMITER and an exact closing line')
            start = index
            while index < len(lines) and lines[index] != marker[1]:
                index += 1
            if index == len(lines):
                raise ValueError('literal block has no exact closing delimiter')
            value = '\n'.join(lines[start:index])
            index += 1
        fields[key] = value
    return {'card': header[1], 'action': header[2], 'fields': fields, 'syntax': 'delvetalk-town-spell-v1'}


def action_word(action, actions):
    """Only a unique actual method, never a label, gets a readable selector."""
    command = action.get('command', '')
    if (WORD.fullmatch(command) and not ACTION.fullmatch(command)
            and sum(item.get('command') == command for item in actions) == 1):
        return command
    return action['id']


def field_words(action):
    fields = action['fields']
    # Alias the entire schema if necessary: actual 'f1' cannot collide with alias f1.
    if all(WORD.fullmatch(field['name']) for field in fields):
        return {field['name']: field['name'] for field in fields}
    return {'f' + str(i + 1): field['name'] for i, field in enumerate(fields)}


def spell(alias, action, fields, *, selector=None):
    """Render a complete literal reply; its caller supplies the captured action."""
    alias_name(alias)
    values = affordances.validate_fields(action, fields)
    selector = action['id'] if selector is None else selector
    if not WORD.fullmatch(selector):
        raise ValueError('invalid offered word')
    lines = ['delvetalk ' + alias + ' ' + selector]
    for token, name in field_words(action).items():
        value = values[name]
        value = ('true' if value else 'false') if type(value) is bool else str(value)
        if '\n' in value or value.startswith('<<'):
            delimiter, serial = 'END', 0
            while delimiter in value.split('\n'):
                serial += 1
                delimiter = 'END' + str(serial)
            lines.extend([token + ': <<' + delimiter, value, delimiter])
        else:
            lines.append(token + ': ' + value)
    return '\n'.join(lines)


def _spell_fields(action, supplied):
    names = field_words(action)
    if set(supplied) != set(names):
        raise ValueError('supply exactly the offered field words')
    schema = {field['name']: field for field in action['fields']}
    values = {}
    for token, name in names.items():
        value, kind = supplied[token], schema[name]['type']
        if kind == 'nat':
            if not re.fullmatch(r'0|[1-9][0-9]*', value):
                raise ValueError('natural number requires ASCII decimal digits')
            # Schema naturals are bounded; avoid unbounded integer parsing.
            if len(value) > len(str(affordances.MAX_SAFE_NAT)):
                raise ValueError('natural number exceeds supported bounds')
            value = int(value)
        elif kind == 'bool':
            if value not in ('true', 'false'):
                raise ValueError('Boolean requires true or false')
            value = value == 'true'
        values[name] = value
    return affordances.validate_fields(action, values)


def _field(field, token=None):
    kind = field['type']
    if kind == 'string':
        bounds = str(field['minLength']) + '..' + str(field['maxLength']) + ' chars'
    elif kind == 'nat':
        bounds = str(field['minimum']) + '..' + str(field['maximum'])
    elif kind == 'enum':
        bounds = ' | '.join(canonical(option) for option in field['options'])
    else:
        bounds = 'true|false'
    return (token or field['name']) + (' (' + canonical(field['name']) + ')' if token and token != field['name'] else '') + ': ' + kind + ' ' + bounds


def _example(action):
    values = {}
    for field in action['fields']:
        if 'example' in field:
            values[field['name']] = copy.deepcopy(field['example'])
        elif field['type'] == 'string':
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
            if 'example' not in field:
                values[child['field']] = 'x' * max(1, field['minLength'])
    return values


def _panels(view, expected_runtime):
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
        panel = room.inspect_object(view['root'], view['object'], panel=entry['id'],
                                    expected_runtime=expected_runtime)
        if (panel.get('mode') != 'projection' or panel.get('object') != view['object']
                or canonical(panel.get('root')) != canonical(view['root'])):
            raise ValueError('declared panel did not produce a pure view of the captured root')
        panels.append({**entry, 'view': panel})
    return panels


def render_card(alias, card, view, panels=(), display_names=None):
    lines = ['[[delvetalk-card ' + alias + ']]', canonical(card['title'])]
    def prose(text):
        def display(match):
            return (display_names or {}).get(match[0], match[0])
        shown = re.sub(r'did:plc:[a-z2-7]{24}(?![a-z2-7])', display, text)
        return '\n'.join('| ' + line for line in shown.split('\n'))
    if card['prose']:
        lines.append(prose(card['prose']))
    for panel in panels:
        data = panel['view']['data']
        if not data['prose'].strip():
            continue
        lines.append(canonical(panel['label']) + ':')
        lines.append(prose(data['prose']))
    if view['mode'] == 'raw':
        lines.append('Object ' + canonical(card['object']) + ' · version ' + str(card['version']))
        lines.append('State: ' + canonical(view['root']['state']))
    executable = any(action.get('available') and not action.get('inspectOnly') for action in card['actions'])
    if executable:
        lines.append('Reply here: copy a spell and change its values, or describe your intention for us to interpret.')
    for action in card['actions']:
        word = action_word(action, card['actions'])
        lines.append(word + ': ' + canonical(action['label']))
        if not action.get('available') or action.get('inspectOnly'):
            lines.append('Look only; no spell offered.')
            continue
        tokens = {name: token for token, name in field_words(action).items()}
        lines.extend('  ' + _field(f, tokens[f['name']]) for f in action['fields'])
        if action.get('children'):
            chosen = [tokens[child['field']] for child in action['children'] if 'value' not in child]
            fixed = [canonical(child['value']) for child in action['children'] if 'value' in child]
            if chosen:
                lines.append('Choose an unused name.' if chosen == ['name'] else
                             'Choose unused names for ' + ', '.join(chosen) + '.')
            if fixed:
                lines.append('This action requires unused names: ' + ', '.join(fixed) + '.')
        if action.get('observedAvailable') is False:
            lines.append('Unavailable in this view.')
        lines.append(spell(alias, action, _example(action), selector=word))
    if not card['actions']:
        lines.append('Look only; no spell offered.')
    if executable:
        lines.append('If refused because the world changed, ask for a fresh card. No result? Ask us to check your original reply; do not repeat it.')
    lines.append('[[/delvetalk-card ' + alias + ']]')
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
        metadata = self.metadata()
        view = copy.deepcopy(view)
        projection.assert_runtime(view, metadata['runtime'])
        card = affordances.card(view)
        panels = _panels(view, metadata['runtime'])
        object_ref = references.object_reference(metadata['worldId'], view['object'])
        def build(name):
            body = render_card(name, card, view, panels, metadata['displayNames'])
            return {'format': 'delvetalk-town-card-v1', 'alias': name, 'view': view,
                    'card': card, 'runtime': metadata['runtime'],
                    'objectRef': object_ref, 'panels': panels,
                    'body': body, 'textSha256': sha(body)}
        return self._capture(alias, build)

    def capture_composite(self, offer, *, alias=None):
        """Retain a fixed transaction offer, including every exact known read."""
        metadata = self.metadata()
        offer = composite_offers.validate(offer)
        action = composite_offers.action(offer)
        def build(name):
            lines = ['[[delvetalk-card ' + name + ']]', offer['title'], offer['label'],
                     'All steps commit together or none do. Each checks your current permissions.',
                     'Reply here, or describe your intention for us to interpret:',
                     spell(name, action, _example(action), selector=offer['command'])]
            lines.extend(_field(field, token) for token, field_name in field_words(action).items()
                         for field in action['fields'] if field['name'] == field_name)
            lines.extend(['If refused because the world changed, ask for a fresh card. No result? Ask us to check your original reply; do not repeat it.',
                          '[[/delvetalk-card ' + name + ']]'])
            body = '\n'.join(lines)
            if len(body.encode('utf-8')) > MAX_CARD_BYTES:
                raise ValueError('town composite card exceeds 12000 bytes')
            _block(body, name)
            return {'format': 'delvetalk-town-composite-card-v1', 'alias': name,
                    'offer': offer, 'runtime': metadata['runtime'],
                    'body': body, 'textSha256': sha(body)}
        return self._capture(alias, build)

    def capture_adoption(self, candidate_id, expected_candidate, target_id, expected_target, *, alias=None):
        """Capture one fixed adoption, not authority to supply arbitrary transactions."""
        metadata = self.metadata()
        candidate, target = copy.deepcopy(expected_candidate), copy.deepcopy(expected_target)
        if (not isinstance(candidate, dict) or not isinstance(target, dict)
                or set(candidate) != {'law', 'protocol', 'state', 'version'}
                or set(target) != {'law', 'protocol', 'state', 'version'}):
            raise ValueError('adoption requires exact candidate and target roots')
        state = candidate.get('state')
        if (not isinstance(state, dict) or state.get('status') != 'ready'
                or state.get('target') != target_id or not isinstance(state.get('migration'), dict)
                or not isinstance(state.get('protocol'), dict)):
            raise ValueError('adoption requires a ready candidate with its explicit target and migration')
        # Reuse the constructor for its same-object exact-root check as well.
        adoption.request(candidate_id, target_id, '', '', candidate, target)
        object_ref = references.object_reference(metadata['worldId'], target_id)
        candidate_ref = references.object_reference(metadata['worldId'], candidate_id)
        def build(name):
            lines = ['[[delvetalk-card ' + name + ']]', 'Adopt a proposed revision',
                     'Proposal ' + canonical(candidate_id) + ' → ' + canonical(target_id),
                     'Proposed program: ' + canonical(state['protocol'].get('name', state['protocol'].get('title', 'Untitled'))),
                     'Runs this proposal’s adoption program; installs its released program and replaces the target’s ENTIRE state.',
                     'Candidate-recorded migration: ' + canonical(state['migration']),
                     'Target permissions stay in place; checks do not grant installation rights.',
                     'Reply here to adopt, or describe your intention for us to interpret:',
                     'delvetalk ' + name + ' adopt',
                     'If refused because the world changed, ask for a fresh card. No result? Ask us to check your original reply; do not repeat it.',
                     '[[/delvetalk-card ' + name + ']]']
            body = '\n'.join(lines)
            if len(body.encode('utf-8')) > MAX_CARD_BYTES:
                raise ValueError('town adoption card exceeds 12000 bytes; migration must be reviewable inline')
            _block(body, name)
            return {'format': 'delvetalk-town-adoption-card-v1', 'alias': name,
                    'candidate': candidate_id, 'target': target_id,
                    'expectedCandidate': candidate, 'expectedTarget': target,
                    'runtime': metadata['runtime'], 'objectRef': object_ref, 'candidateRef': candidate_ref,
                    'body': body, 'textSha256': sha(body)}
        return self._capture(alias, build)

    def _capture(self, alias, build):
        if alias is not None:
            alias_name(alias)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            if alias is None:
                # Never reuse an alias, including after an explicit card-N name.
                serial = db.execute('SELECT COALESCE(MAX(rowid),0)+1 FROM cards').fetchone()[0]
                while db.execute('SELECT 1 FROM cards WHERE alias=?', ('card-' + str(serial),)).fetchone():
                    serial += 1
                alias = 'card-' + str(serial)
            value = build(alias)
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
        if captured['format'] == 'delvetalk-town-card-v1':
            if parsed.get('syntax') == 'delvetalk-town-spell-v1':
                actions = captured['card']['actions']
                chosen = next((action for action in actions if parsed['action'] in
                               (action['id'], action_word(action, actions))), None)
                if chosen is None:
                    raise ValueError('word is not offered by this captured card')
                parsed = {**parsed, 'offeredWord': parsed['action'], 'action': chosen['id'],
                          'fields': _spell_fields(chosen, parsed['fields'])}
            request = affordances.request(captured['view'], parsed['action'], author,
                                          'delve:' + source['uri'], parsed['fields'])
        elif captured['format'] == 'delvetalk-town-composite-card-v1':
            action = composite_offers.action(captured['offer'])
            if parsed['action'] not in ('a1', action['command']):
                raise ValueError('word is not offered by this captured composite card')
            fields = (_spell_fields(action, parsed['fields'])
                      if parsed.get('syntax') == 'delvetalk-town-spell-v1' else parsed['fields'])
            request = composite_offers.request(captured['offer'], author,
                                               'delve:' + source['uri'], fields)
        elif captured['format'] == 'delvetalk-town-adoption-card-v1':
            if parsed['action'] not in ('a1', 'adopt') or parsed['fields']:
                raise ValueError('adoption permits only a1 with empty fields {}')
            request = adoption.request(captured['candidate'], captured['target'], author,
                                       'delve:' + source['uri'], captured['expectedCandidate'], captured['expectedTarget'])
        else:
            raise ValueError('unknown captured card format')
        wire = {key: value for key, value in request.items() if key not in ('principal', 'intent')}
        if wire['op'] == 'transaction':
            # Clerk's transport resolves explicit descriptors before Lean admission.
            wire['reads'] = {key: {'expected': value} for key, value in wire['reads'].items()}
        if len(canonical(wire).encode('utf-8')) > MAX_REPLY_BYTES:
            raise ValueError('derived card request exceeds 64 KiB')
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
            data = receipt.get('data')
            if isinstance(data, dict) and 'result' in data:
                result = data['result']
                shown = result if isinstance(result, str) else canonical(result)
                if len(shown.encode('utf-8')) <= 2048:
                    body += '\nResult:\n' + '\n'.join('| ' + line for line in shown.split('\n'))
                else:
                    body += '\nResult exceeds the inline display limit; ask the operator for the retained result.'
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
