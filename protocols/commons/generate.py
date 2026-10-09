#!/usr/bin/env python3
"""Physical packaging of the source-owned commons and explicit configuration."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('commons_references', ROOT / 'scripts/references.py')
references = importlib.util.module_from_spec(spec)
spec.loader.exec_module(references)
import sys
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def default_participants():
    return {p: references.object_reference('commons-example', 'entities/' + p) for p in ('moss', 'iris')}


def default_places():
    return {key: {'title': title, 'description': description,
                  'reference': references.object_reference('commons-example', 'places/' + key)}
            for key, title, description in (
                ('porch', 'The porch', 'A covered threshold with a path into the garden.'),
                ('garden', 'The garden', 'A small garden with a path back to the porch.'),
                ('tower', 'The quiet tower', 'A separate authored place without a path from the garden.'))}


def bounded_name(value):
    references.component(value)
    if len(value) > 64: raise ValueError('authored name exceeds 64 scalars')
    return value


def law(participants=None, managers=('steward',)):
    participants = default_participants() if participants is None else participants
    for principal in participants: bounded_name(principal)
    for manager in managers: bounded_name(manager)
    return {'profile': 'delvetalk-scoped-law',
            'invoke': {name: list(participants) for name in ('enter', 'move', 'leave')},
            'reprogram': list(managers), 'law': list(managers)}


def linked(items):
    """Frame a typed source list; source owns its interpretation and bounds."""
    result = source_object.variant('nil', source_object.record({}))
    for item in reversed(list(items)):
        result = source_object.variant('cons', source_object.record({'head': item, 'tail': result}))
    return result


def build(participants=None, places=None, paths=None, entries=('porch',), gates=None):
    participants = default_participants() if participants is None else participants
    places = default_places() if places is None else places
    paths = [('porch', 'garden'), ('garden', 'porch')] if paths is None else paths
    gates = [] if gates is None else gates
    # Exact reference framing is a transport boundary. The source constructor
    # validates participant uniqueness, graph endpoints, capacities and gates.
    for reference in participants.values():
        references.validate_reference(reference)
    for value in places.values():
        references.validate_reference(value['reference'])
    config = source_object.record({
        'participants': linked(source_object.data({'principal': who, 'entity': reference, 'location': ''})
            for who, reference in participants.items()),
        'places': linked(source_object.data({'name': name, **value}) for name, value in places.items()),
        'paths': linked(source_object.data({'source': start, 'target': finish}) for start, finish in paths),
        'entries': linked(source_object.data(name) for name in entries),
        'gates': linked(source_object.data({'source': gate['from'], 'target': gate['to'],
            **{key: value for key, value in gate.items() if key not in ('from', 'to')}}) for gate in gates)})
    modules = source_object.read_closure([
        ('Commons', HERE / 'Commons.obend')])
    protocol = source_object.load(modules, syntax='objective-bend-object',
        constructor='initial', arguments=[config])
    if not source_object.plain(source_object.state_data(
            {'protocol': protocol, 'state': protocol['initial']}))['valid']:
        raise ValueError('Commons source refused the configured topology')
    return protocol


def locations(root):
    """Project declared source state for display/tests; this confers no authority."""
    model = source_object.plain(source_object.state_data(root))
    items = model['config']['participants']
    result = {}
    while items['variant'] == 'cons':
        item = items['payload']['head']
        result[item['principal']] = item['location']
        items = items['payload']['tail']
    return result


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
