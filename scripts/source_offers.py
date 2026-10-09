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
    required = {'format', 'object', 'root', 'entry', 'observations', 'title', 'label', 'fields'}
    if (not isinstance(invitation, dict) or not required <= set(invitation)
            or set(invitation) - required - {'contributionCodec', 'definitions'}
            or invitation['format'] != FORMAT):
        raise ValueError('captured preparation requires exact invitation fields')
    if invitation.get('contributionCodec', 'value') not in ('value', 'data'):
        raise ValueError('unknown preparation contribution codec')
    if not isinstance(invitation['observations'], list) or len(invitation['observations']) > 16:
        raise ValueError('captured preparation has too many observations')
    for observation in invitation['observations']:
        if not isinstance(observation, dict) or set(observation) != {'object', 'root', 'inspectState', 'inspectLaw'}:
            raise ValueError('captured observation requires object, exact root and explicit projection flags')
        if type(observation['inspectState']) is not bool or type(observation['inspectLaw']) is not bool:
            raise ValueError('captured observation projection flags require Bool')
    if 'definitions' in invitation:
        selections = invitation['definitions']
        if not isinstance(selections, list) or len(selections) > 16:
            raise ValueError('definition selection capacity')
        seen = set()
        for selection in selections:
            if not isinstance(selection, dict) or set(selection) != {'object', 'package'}:
                raise ValueError('definition selection requires object and package')
            if not all(isinstance(selection[k], str) and selection[k] for k in ('object', 'package')):
                raise ValueError('definition selection requires identities')
            key = (selection['object'], selection['package'])
            if key in seen or selection['object'] not in {o['object'] for o in invitation['observations']}:
                raise ValueError('definition selection requires unique captured observations')
            seen.add(key)
    result = copy.deepcopy(invitation)
    result['fields'] = affordances.validate_fields_schema(result['fields'])
    return result


def capture_available(view, roots, *, database=None, references=None):
    from scene import projection
    invitations = projection.invitations(view)
    if roots.get(view['object']) != view['root']:
        raise ValueError('source view differs from its captured owner root')
    offers, unavailable = {}, {}
    retained = {}
    def captured(identity):
        if references is not None:
            if identity not in references:
                raise ValueError('native paired capture omitted root reference: ' + identity)
            return copy.deepcopy(references[identity])
        if database is None:
            return copy.deepcopy(roots[identity])
        if identity not in retained:
            retained[identity] = world.query(database, {'op': 'retained-root',
                'object': identity, 'root': roots[identity]})
        return copy.deepcopy(retained[identity])
    for key, descriptor in invitations.items():
        missing = [item['object'] for item in descriptor['observations'] if item['object'] not in roots]
        if missing:
            unavailable[key] = {'command': descriptor['prepare'], 'label': descriptor['text'],
                                'reason': 'Captured observation missing: ' + ', '.join(missing)}
            continue
        offer = {'format': FORMAT, 'object': view['object'],
            'root': captured(view['object']), 'entry': descriptor['prepare'],
            'observations': [{**item, 'root': captured(item['object'])}
                             for item in descriptor['observations']],
            'title': view['data']['title'], 'label': descriptor['text'],
            'fields': _fields(descriptor['fields'])}
        if 'contributionCodec' in descriptor:
            offer['contributionCodec'] = descriptor['contributionCodec']
        if 'definitions' in descriptor:
            offer['definitions'] = copy.deepcopy(descriptor['definitions'])
        offers[key] = validate(offer)
    return {'offers': offers, 'unavailable': unavailable}


def capture(view, roots, *, database=None, references=None):
    return capture_available(view, roots, database=database, references=references)['offers']


def capture_observations(view, owner_capture, *, database=None, receiver=None,
                         principal='reader', profile='compiled', timeout=30, capture_roots=None):
    """Bind declared observation discovery to the already projected owner.

    The native second read checks its original owner reference. Drift refuses;
    an existing invitation is never refreshed here.
    """
    from scene import projection
    owner = view['object']
    pair = owner_capture['roots'].get(owner)
    if pair is None:
        raise ValueError('captured preparation owner is absent')
    identities = {owner}
    for invitation in projection.invitations(view).values():
        identities.update(item['object'] for item in invitation['observations'])
    expected = {owner: pair['reference']}
    if capture_roots is not None:
        if database is not None or receiver is not None:
            raise ValueError('observation capture selects exactly one native transport')
        return capture_roots(sorted(identities), expected=expected)
    return world.capture_roots(database, sorted(identities), receiver=receiver,
        principal=principal, profile=profile, timeout=timeout, expected=expected)


def action(invitation):
    invitation = validate(invitation)
    result = {'id': 'a1', 'command': invitation['entry'], 'label': invitation['label'],
            'available': True, 'fields': invitation['fields'], 'preparation': True}
    if 'contributionCodec' in invitation:
        result['contributionCodec'] = invitation['contributionCodec']
    return result


def _outcome(value):
    if value.get('kind') == 'inspection' and 'document' in value:
        from scene import projection
        value = copy.deepcopy(value)
        value['document'] = projection._document_data(value['document'])
    return value


def prepare_value(invitation, principal, intent, contribution, *, binary=None, database=None, receiver=None):
    """Run bounded source interpretation data through its native preparation export."""
    invitation = validate(invitation)
    if len(world.wire_dumps(contribution).encode('utf-8')) > 65536:
        raise ValueError('authored contribution exceeds 64 KiB')
    objects = {invitation['object']: invitation['root']}
    for observation in invitation['observations']:
        objects[observation['object']] = observation['root']
    request = {'op': 'prepare', 'object': invitation['object'], 'root': invitation['root'],
        'entry': invitation['entry'], 'contribution': copy.deepcopy(contribution),
        'observations': invitation['observations'], 'principal': principal, 'intent': intent}
    if 'contributionCodec' in invitation:
        request['contributionCodec'] = invitation['contributionCodec']
    if 'definitions' in invitation:
        request['definitions'] = copy.deepcopy(invitation['definitions'])
    if database is not None or receiver is not None:
        if binary is not None:
            raise ValueError('retained preparation selects the database native receiver')
        if database is not None and receiver is not None:
            raise ValueError('retained preparation selects exactly one native transport')
        request['op'] = 'prepare-retained'
        if receiver is not None:
            if receiver.profile != 'compiled':
                raise ValueError('retained preparation requires compiled native receiver')
            return _outcome(receiver.query(request))
        return _outcome(world.query(database, request))
    job = {'world': {'objects': objects, 'receipts': []}, 'request': request}
    result = process_custody.run_native([binary or BINARY], timeout=30, cpu_seconds=30,
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
    if outcome.get('kind') not in ('ready', 'question', 'refused', 'inspection'):
        raise ValueError('unknown native preparation result')
    return _outcome(outcome)


def prepare_fields(invitation, principal, intent, contribution, *, binary=None, database=None, receiver=None):
    """Prepare a public form contribution; source still chooses questions and effects."""
    invitation = validate(invitation)
    if invitation.get('contributionCodec', 'value') != 'value':
        raise ValueError('typed preparation requires an explicit DataWire contribution')
    contribution = affordances._validate_values(invitation['fields'], contribution, complete=False)
    return prepare_value(invitation, principal, intent, contribution,
        binary=binary, database=database, receiver=receiver)


# Existing public form callers retain the explicitly validated path.
prepare = prepare_fields


def request(invitation, principal, intent, contribution, *, database=None, receiver=None):
    outcome = prepare(invitation, principal, intent, contribution, database=database, receiver=receiver)
    if outcome['kind'] != 'ready':
        raise PreparationOutcome(outcome)
    return outcome['request']
