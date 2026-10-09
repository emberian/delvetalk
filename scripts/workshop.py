#!/usr/bin/env python3
"""Seed a shared workshop from explicit ordinary protocols, never copied custody."""
import argparse
from pathlib import Path
import uuid

import workspace
import references

b = workspace.bootstrap
ROOT = Path(__file__).resolve().parents[1]
commons = b.module('workshop_commons', 'protocols/commons/generate.py')
ticket = b.module('workshop_ticket', 'protocols/work-ticket/generate.py')
table = b.module('workshop_table', 'game/table/protocol.py')


def scoped(commands, people, *, programmers=(), managers=()):
    return {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {command: list(people) for command in commands},
            'reprogram': list(programmers), 'law': list(managers)}


def description(title, text):
    return {'profile': 'delvetalk-local-v1', 'name': title, 'description': text,
            'initial': {'title': title, 'description': text}, 'commands': {}}


def initialize(directory, *, builders=('moss', 'iris'), compiler='compiler', steward='steward', world_id=None):
    if len(builders) != 2 or len(set(builders)) != 2:
        raise ValueError('The workshop table requires two distinct builders')
    for principal in (*builders, compiler, steward):
        references.component(principal)
    world_id = references.component(world_id or 'urn:uuid:' + str(uuid.uuid4()))
    ref = lambda obj: references.object_reference(world_id, obj)
    seeds = []

    def add(identity, program, law):
        seeds.append({'id': identity, 'syntax': 'protocol-json@1', 'source': b.canonical(program), 'law': law})

    places = {key: {'title': title, 'description': text, 'reference': ref('places/' + key)}
              for key, title, text in (
                  ('porch', 'The workshop porch', 'Meet here. Create an object, then teach it a new program.'),
                  ('garden', 'The shared garden', 'A place to try the things you build together.'))}
    participants = {person: ref('entities/' + person) for person in builders}
    for name, place in places.items():
        add('places/' + name, description(place['title'], place['description']),
            scoped([], (), programmers=builders, managers=(steward,)))
    for person in builders:
        add('entities/' + person, description(person, 'An authored entity reference, separate from presence and authority.'),
            scoped([], (), programmers=(person,), managers=(person,)))
    add('commons', commons.build(participants, places, [('porch', 'garden'), ('garden', 'porch')]),
        commons.law(participants, managers=(steward,)))

    objects = b.loads((ROOT / 'protocols/factories/object.json').read_bytes())
    objects['description'] = 'Create objects shared by the two workshop builders.'
    objects['commands']['make']['allocate'][0]['law'] = ['literal',
        list(builders)]
    objects['commands']['make']['allocate'][0]['protocol'][1]['description'] = 'A shared object. Both workshop builders may use, reprogram and govern it.'
    add('factory:objects', objects, scoped(['make'], builders, programmers=(steward,), managers=(steward,)))
    desks = b.loads((ROOT / 'protocols/factories/source-desk.json').read_bytes())
    desks['initial']['compiler'] = compiler
    add('factory:desks', desks, scoped(['make'], builders, programmers=(steward,), managers=(steward,)))
    add('ticket:welcome', ticket.build(requester=builders[0], links={'context': ref('commons')}),
        ticket.law(requester=builders[0], workers=builders, managers=(steward,)))
    add('table:automatafl', table.protocol('table:automatafl'), table.law(*builders))
    return workspace.initialize(directory, seeds,
        entry_objects=['commons', 'factory:objects', 'factory:desks', 'ticket:welcome', 'table:automatafl'],
        default_object='commons', principal=steward, profile='compiled',
        title='DelveTalk · the shared workshop', world_id=world_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--builders', nargs=2, default=['moss', 'iris'], metavar=('FIRST', 'SECOND'))
    parser.add_argument('--compiler', default='compiler')
    parser.add_argument('--steward', default='steward')
    parser.add_argument('--world-id')
    args = parser.parse_args()
    print(b.canonical(initialize(args.directory, builders=tuple(args.builders), compiler=args.compiler,
        steward=args.steward, world_id=args.world_id)).decode())


if __name__ == '__main__':
    main()
