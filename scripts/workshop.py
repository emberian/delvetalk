#!/usr/bin/env python3
"""Seed a shared workshop from explicit ordinary protocols, never copied custody."""
import argparse
from pathlib import Path
import uuid

import workspace
import references
import source_object

b = workspace.bootstrap
ROOT = Path(__file__).resolve().parents[1]
commons = b.module('workshop_commons', 'protocols/commons/generate.py')
ticket = b.module('workshop_ticket', 'protocols/work-ticket/package.py')
table = b.module('workshop_table', 'game/table/protocol.py')
writing = b.module('workshop_source_desks', 'protocols/source-desk/package.py')
objects = b.module('workshop_objects', 'protocols/factories/package.py')


def scoped(commands, people, *, programmers=(), managers=()):
    modules = source_object.read_closure([('Authority', ROOT / 'world/lib/prelude/Authority.obend')])
    names = lambda values: source_object.list_data(source_object.data(item) for item in values)
    config = source_object.record({'commands': names(commands), 'participants': names(people),
        'managers': names(programmers), 'stewards': names(managers), 'publicPanels': names(['main'])})
    return source_object.values('decode', [source_object.evaluate(modules, 'configured', [config])])[0]


def ticket_authority(builders, steward):
    modules = source_object.read_closure([('Authority', ROOT / 'world/lib/prelude/Authority.obend')])
    names = lambda values: source_object.list_data(source_object.data(item) for item in values)
    grants = [('post', builders[:1]), ('claim', builders), ('submit', builders),
              ('accept', builders[:1]), ('reject', builders[:1])]
    policy = source_object.record({'reading': source_object.value('public'),
        'invocation': source_object.list_data(source_object.record({'command': source_object.data(command),
            'principals': names(people)}) for command, people in grants),
        'reprogramming': names([]), 'management': names([steward]), 'publicPanels': names(['main'])})
    return source_object.values('decode', [source_object.evaluate(modules, 'assemble', [policy])])[0]


def description(title, text):
    modules = source_object.read_closure([('Description', ROOT / 'protocols/workshop/Description.obend')])
    return source_object.load(modules, syntax='objective-bend-object', constructor='configured',
        arguments=[source_object.data({'title': title, 'prose': text})])


def initialize(directory, *, builders=('moss', 'iris'), compiler='compiler', steward='steward', world_id=None):
    if len(builders) != 2 or len(set(builders)) != 2:
        raise ValueError('The workshop table requires two distinct builders')
    for principal in (*builders, compiler, steward):
        references.component(principal)
    world_id = references.component(world_id or 'urn:uuid:' + str(uuid.uuid4()))
    ref = lambda obj: references.object_reference(world_id, obj)
    seeds = []

    def add(identity, program, law):
        seeds.append({'id': identity, 'syntax': 'objective-bend-object',
                      **source_object.seed_material(program), 'law': law})

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

    add('factory:objects', objects.factory(builders), scoped(['make'], builders, programmers=(steward,), managers=(steward,)))
    desks = writing.factory(compiler, builders, reviewers=(steward,))
    add('factory:desks', desks, scoped(['make'], builders, programmers=(steward,), managers=(steward,)))
    add('factory:writing', writing.writing_factory(), scoped(['make'], builders, programmers=(steward,), managers=(steward,)))
    add('ticket:welcome', ticket.build(requester=builders[0], links={'context': ref('commons')}),
        ticket_authority(builders, steward))
    add('table:automatafl', table.protocol('table:automatafl', *builders), table.law(*builders))
    return workspace.initialize(directory, seeds,
        entry_objects=['commons', 'factory:objects', 'factory:desks', 'factory:writing', 'ticket:welcome', 'table:automatafl'],
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
