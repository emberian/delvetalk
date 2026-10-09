#!/usr/bin/env python3
"""Author a bounded presence registry as ordinary Lean-admitted protocol data."""
import copy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('commons_references', ROOT / 'scripts/references.py')
references = importlib.util.module_from_spec(spec)
spec.loader.exec_module(references)
L = lambda value: ['literal', value]
S = lambda key: ['state', key]
I = lambda key: ['input', key]
P = ['principal']
label = lambda value: ['label', value]
eq = lambda x, y: ['binary', 'labelEqual', x, y]
choose = lambda condition, yes, no: ['ifBool', condition, yes, no]
record = lambda fields: ['record', [[key, value] for key, value in fields.items()]]


def term(value):
    if isinstance(value, str): return label(value)
    if isinstance(value, dict): return record({k: term(v) for k, v in value.items()})
    raise ValueError('authored term requires strings or records')


def bend(body, arguments):
    for _ in arguments: body = ['lam', body]
    return ['bend', body, arguments]


def select(key, choices, otherwise):
    for name, value in reversed(list(choices.items())):
        otherwise = choose(eq(key, label(name)), value, otherwise)
    return otherwise


def member(key, names):
    return select(key, {name: ['boolean', True] for name in names}, ['boolean', False])


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
    return {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {name: list(participants) for name in ('enter', 'move', 'leave')},
            'reprogram': list(managers), 'law': list(managers)}


def build(participants=None, places=None, paths=None, entries=('porch',)):
    participants = copy.deepcopy(default_participants() if participants is None else participants)
    places = copy.deepcopy(default_places() if places is None else places)
    paths = [('porch', 'garden'), ('garden', 'porch')] if paths is None else list(paths)
    if not isinstance(participants, dict) or not 1 <= len(participants) <= 8:
        raise ValueError('declare 1..8 principals and their entity references')
    if not isinstance(places, dict) or not 1 <= len(places) <= 8:
        raise ValueError('declare 1..8 places')
    for principal, ref in participants.items():
        bounded_name(principal)
        references.validate_reference(ref)
    identities = [(ref['world'], ref['object']) for ref in participants.values()]
    if len(set(identities)) != len(identities): raise ValueError('entity references must be distinct')
    for name, place in places.items():
        bounded_name(name)
        if not isinstance(place, dict) or set(place) != {'title', 'description', 'reference'}:
            raise ValueError('places require title, description and reference')
        for key, limit in [('title', 128), ('description', 512)]:
            value = place[key]
            if not isinstance(value, str) or len(value) > limit or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
                raise ValueError('invalid place ' + key)
        references.validate_reference(place['reference'])
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= len(places):
        raise ValueError('declare a nonempty bounded entry list')
    for entry in entries:
        if not isinstance(entry, str) or entry not in places: raise ValueError('unknown entry place')
    if len(set(entries)) != len(entries): raise ValueError('duplicate entry place')
    if len(paths) > 16: raise ValueError('declare at most 16 directed paths')
    edges = []
    for path in paths:
        if not isinstance(path, (list, tuple)) or len(path) != 2 or any(not isinstance(p, str) or p not in places for p in path):
            raise ValueError('path endpoints must be authored places')
        edges.append(tuple(path))
    if len(set(edges)) != len(edges): raise ValueError('duplicate path')
    # Three ordinary Bend arguments: principal, old locations, destination.
    principal, locations, destination = ['bound', 2], ['bound', 1], ['bound', 0]
    current = select(principal, {p: ['get', locations, p] for p in participants}, label(''))
    updated = record({p: choose(eq(principal, label(p)), destination, ['get', locations, p])
                      for p in participants})
    allowed_path = ['boolean', False]
    for source, target in reversed(edges):
        edge_matches = choose(eq(current, label(source)), eq(destination, label(target)), ['boolean', False])
        allowed_path = choose(edge_matches, ['boolean', True], allowed_path)
    infos = {name: term({**place, 'name': name, 'exits': {
                target: places[target]['reference'] for source, target in edges if source == name}})
             for name, place in places.items()}
    commands, forms = {}, {}
    for command in ('enter', 'move', 'leave'):
        arguments = [P, S('locations'), L('') if command == 'leave' else I('place')]
        guards = [member(principal, participants)]
        if command == 'enter': guards += [eq(current, label('')), member(destination, entries)]
        elif command == 'move': guards += [allowed_path]
        else: guards += [choose(eq(current, label('')), ['boolean', False], ['boolean', True])]
        commands[command] = {'require': [[bend(g, arguments), L(True)] for g in guards],
            'set': {'locations': bend(updated, arguments)}, 'outbox': [],
            'result': bend(record({'principal': principal,
                'entity': select(principal, {p: term(ref) for p, ref in participants.items()}, record({})),
                'from': current, 'to': destination, 'locations': updated,
                'place': select(destination, infos, record({}))}), arguments)}
        forms[command] = {'label': {'enter': 'Enter the commons', 'move': 'Move to a place', 'leave': 'Leave the commons'}[command],
            'fields': {} if command == 'leave' else {'place': {'type': 'enum', 'options': list(entries) if command == 'enter' else list(places)}}}
    return {'profile': 'delvetalk-local-v1', 'name': 'bounded-commons-v1',
        'description': 'Declared presence in an authored place graph. Presence grants no authority and does not report a live connection.',
        'participants': participants, 'places': places, 'paths': [list(edge) for edge in edges],
        'entries': list(entries), 'initial': {'locations': {p: '' for p in participants}},
        'commands': commands, 'affordances': forms}


if __name__ == '__main__':
    protocol = build()
    for name, value in [('protocol.json', protocol), ('migration.json', protocol['initial']), ('law.json', law())]:
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
