"""Physical custody of source preparation invitations and read-only native calls.

No operation recipes, field substitutions, participant choice or workflow rules.
"""
import copy
from pathlib import Path
import sys

import affordances
import process_custody
import world

FORMAT = 'delvetalk-source-invitation-v1'
ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-compiled'
sys.path.insert(0, str(ROOT))


class PreparationOutcome(ValueError):
    def __init__(self, outcome):
        self.outcome = copy.deepcopy(outcome)
        super().__init__(outcome.get('message', 'Source preparation did not produce a turn'))


def _fields(value):
    fields = []
    for name, spec in sorted(value.items()):
        spec = copy.deepcopy(spec)
        if spec.get('type') == 'enum' and isinstance(spec.get('options'), dict):
            spec['options'] = [spec['options'][key] for key in sorted(spec['options'])]
        fields.append(affordances._normalize_field(name, spec))
    return affordances.validate_fields_schema(fields)


def validate(invitation):
    if (not isinstance(invitation, dict) or set(invitation) !=
            {'format', 'object', 'root', 'entry', 'observations', 'title', 'label', 'fields'}
            or invitation['format'] != FORMAT):
        raise ValueError('captured preparation requires exact invitation fields')
    if not isinstance(invitation['observations'], list) or len(invitation['observations']) > 16:
        raise ValueError('captured preparation has too many observations')
    for observation in invitation['observations']:
        if not isinstance(observation, dict) or set(observation) != {'object', 'root'}:
            raise ValueError('captured observation requires object and exact root')
    result = copy.deepcopy(invitation)
    result['fields'] = affordances.validate_fields_schema(result['fields'])
    return result


def capture_available(view, roots, *, database=None):
    from scene import projection
    invitations = projection.invitations(view)
    if roots.get(view['object']) != view['root']:
        raise ValueError('source view differs from its captured owner root')
    offers, unavailable = {}, {}
    retained = {}
    def captured(identity):
        if database is None:
            return copy.deepcopy(roots[identity])
        if identity not in retained:
            retained[identity] = world.query(database, {'op': 'retained-root',
                'object': identity, 'root': roots[identity]})
        return copy.deepcopy(retained[identity])
    for key, descriptor in invitations.items():
        missing = [identity for identity in descriptor['observations'] if identity not in roots]
        if missing:
            unavailable[key] = {'command': descriptor['prepare'], 'label': descriptor['text'],
                                'reason': 'Captured observation missing: ' + ', '.join(missing)}
            continue
        offers[key] = validate({'format': FORMAT, 'object': view['object'],
            'root': captured(view['object']), 'entry': descriptor['prepare'],
            'observations': [{'object': identity, 'root': captured(identity)}
                             for identity in descriptor['observations']],
            'title': view['data']['title'], 'label': descriptor['text'],
            'fields': _fields(descriptor['fields'])})
    return {'offers': offers, 'unavailable': unavailable}


def capture(view, roots, *, database=None):
    return capture_available(view, roots, database=database)['offers']


def action(invitation):
    invitation = validate(invitation)
    return {'id': 'a1', 'command': invitation['entry'], 'label': invitation['label'],
            'available': True, 'fields': invitation['fields'], 'preparation': True}


def prepare(invitation, principal, intent, contribution, *, binary=None, database=None):
    invitation = validate(invitation)
    if len(world.wire_dumps(contribution).encode('utf-8')) > 65536:
        raise ValueError('authored contribution exceeds 64 KiB')
    objects = {invitation['object']: invitation['root']}
    for observation in invitation['observations']:
        objects[observation['object']] = observation['root']
    request = {'op': 'prepare', 'object': invitation['object'], 'root': invitation['root'],
        'entry': invitation['entry'], 'contribution': copy.deepcopy(contribution),
        'observations': invitation['observations'], 'principal': principal, 'intent': intent}
    if database is not None:
        if binary is not None:
            raise ValueError('retained preparation selects the database native receiver')
        request['op'] = 'prepare-retained'
        return world.query(database, request)
    job = {'world': {'objects': objects, 'receipts': []}, 'request': request}
    result = process_custody.run([binary or BINARY], timeout=30, cpu_seconds=30,
        stdout_limit=2 * 1024 * 1024, stderr_limit=65536,
        input=(world.wire_dumps(job) + '\n').encode('utf-8'), cwd=ROOT)
    if result.returncode:
        raise ValueError('native preparation process failed: ' + result.stderr.decode('utf-8', errors='replace'))
    frame = world.wire_loads(result.stdout.decode('utf-8'))
    if 'error' in frame:
        raise ValueError(frame['error'])
    if frame.get('world') != job['world']:
        raise ValueError('pure preparation attempted to change captured custody')
    outcome = frame['reply']
    if outcome.get('kind') not in ('ready', 'question', 'refused'):
        raise ValueError('unknown native preparation result')
    return outcome


def request(invitation, principal, intent, contribution, *, database=None):
    outcome = prepare(invitation, principal, intent, contribution, database=database)
    if outcome['kind'] != 'ready':
        raise PreparationOutcome(outcome)
    return outcome['request']
