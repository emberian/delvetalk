"""Physical custody framing for native source-selected invitation preparation.

Source views select exports and dependencies inside Lean; these helpers only
retain references and transport contribution data.
"""
import copy
import affordances
import source_object
import source_offers
import world


def _query(database, request, profile, receiver):
    if receiver is not None:
        if database is not None or receiver.profile != profile:
            raise ValueError('invitation capture selects exactly one matching native transport')
        return receiver.query(request)
    return world.query(database, request, profile=profile)


def capture(database, object_id, projection, principal, profile='compiled', *, receiver=None):
    invitations = projection['result'].get('invitations', {})
    if not isinstance(invitations, dict) or len(invitations) > 16:
        raise ValueError('source invitations require a bounded record')
    result = {}
    for key, item in invitations.items():
        if item.get('visible') is not True:
            continue
        request = {'op': 'opaque-invitation', 'object': object_id,
            'principal': principal, 'panel': projection['panel'],
            'expected': projection['reference'], 'key': key}
        if projection.get('audience') == 'public':
            request['audience'] = 'public'
        try:
            reply = _query(database, request, profile, receiver)
        except ValueError:
            result[key] = {'available': False, 'label': item['text'],
                'fields': source_offers._fields(item['fields']),
                'reason': 'This invitation is unavailable under current authority.'}
            continue
        invitation = source_object.plain(reply['invitation'])
        result[key] = {'available': True, 'selection': copy.deepcopy(reply['selection']),
            'label': invitation['text'], 'fields': source_offers._fields(invitation['fields']),
            'contributionCodec': invitation.get('contributionCodec', 'value')}
    return result


def prepare(database, captured_descriptor, principal, intent, fields, profile='compiled', *, receiver=None):
    if captured_descriptor.get('available') is not True:
        raise ValueError('This invitation is unavailable under current authority.')
    if captured_descriptor.get('contributionCodec', 'value') != 'value':
        raise ValueError('typed preparation requires explicit DataWire contribution')
    contribution = affordances.physical_values(fields)
    request = {**copy.deepcopy(captured_descriptor['selection']),
        'op': 'opaque-prepare', 'principal': principal, 'intent': intent,
        'contribution': contribution}
    outcome = _query(database, request, profile, receiver)
    if outcome.get('kind') != 'ready':
        raise source_offers.PreparationOutcome(outcome)
    return outcome['request']
