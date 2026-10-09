#!/usr/bin/env python3
"""Author a small two-voice garden; all actions are ordinary host commands."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
L = lambda value: ['literal', value]
S = lambda key: ['state', key]
I = lambda key: ['input', key]
P = ['principal']
label = lambda value: ['label', value]
eq = lambda a, b: ['binary', 'labelEqual', a, b]
choose = lambda cond, yes, no: ['ifBool', cond, yes, no]
record = lambda values: ['record', [[key, value] for key, value in values.items()]]


def nonempty(key):
    return [['bend', ['lam', choose(eq(['bound', 0], label('')), ['boolean', False],
                                   ['boolean', True])], [I(key)]], L(True)]


def law(participants, builders=(), managers=()):
    def principals(values):
        values = list(values)
        if not values or any(not isinstance(v, str) or not v for v in values) or len(set(values)) != len(values):
            raise ValueError('explicit distinct nonempty principals required')
        return values
    members = principals(participants)
    return {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'plant': members, 'rain': list(members)},
            'reprogram': principals(builders) if builders else [],
            'law': principals(managers) if managers else []}


def build():
    colours = ['amber', 'violet', 'silver']
    colour = ['boolean', False]
    for value in reversed(colours):
        colour = choose(eq(['bound', 0], label(value)), ['boolean', True], colour)
    distinct = ['lam', ['lam', choose(eq(['bound', 1], ['bound', 0]),
                                      ['boolean', False], ['boolean', True])]]
    commands = {
        'plant': {'require': [[['bend', ['lam', choose(eq(['bound', 0], label('waiting')),
            ['boolean', True], choose(eq(['bound', 0], label('blooming')),
                ['boolean', True], ['boolean', False]))], [S('phase')]], L(True)], nonempty('seed'),
            [['bend', ['lam', colour], [I('colour')]], L(True)]],
            'set': {'phase': L('planted'), 'seed': I('seed'), 'colour': I('colour'), 'planter': P,
                    'rain': L(''), 'rainmaker': L('')},
            'result': ['record', {'by': P, 'seed': I('seed'), 'colour': I('colour')}], 'outbox': []},
        'rain': {'require': [[S('phase'), L('planted')], nonempty('line'),
            [['bend', distinct, [S('planter'), P]], L(True)]],
            'set': {'phase': L('blooming'), 'rain': I('line'), 'rainmaker': P,
                    'lastCompleted': ['record', {'seed': S('seed'), 'colour': S('colour'),
                        'planter': S('planter'), 'rain': I('line'), 'rainmaker': P}]},
            'result': ['record', {'by': P, 'line': I('line')}], 'outbox': []}}
    forms = {
        'plant': {'label': 'Plant an imaginary seed', 'fields': {
            'seed': {'type': 'string', 'label': 'What might grow here?', 'minLength': 1, 'maxLength': 80},
            'colour': {'type': 'enum', 'label': 'Its light', 'options': colours}}},
        'rain': {'label': 'Give the seed its first rain', 'fields': {
            'line': {'type': 'string', 'label': 'One line of rain', 'minLength': 1, 'maxLength': 240}}}}
    state = ['bound', 1]
    get = lambda key: ['get', state, key]
    waiting = eq(get('phase'), label('waiting'))
    blooming = eq(get('phase'), label('blooming'))
    action = lambda name: record({name: record({'text': label(forms[name]['label']),
        'command': label(name), 'input': record({})})})
    title = choose(waiting, label('The Night Garden · an empty patch'), get('seed'))
    rain_invitation = label('A seed is resting here. Someone other than its planter: give it one line of rain.')
    prose = choose(waiting, label('Behind the last lit window is a patch of dark soil. Plant something that could only grow here.'),
                   choose(blooming, get('rain'), rain_invitation))
    # Each colour changes the scene's image. Participant prose remains a separate readable panel.
    image = label('   .       *\n      /\\\n  ___/  \\___\n /  SILVER  \\\n |  BLOOM   |\n  \\__  __/\n     ||\n  ___||___')
    image = choose(eq(get('colour'), label('amber')), label('   *     .\n    \\ | /\n  -- AMBER --\n    / | \\\n      |\n  ____|____'), image)
    image = choose(eq(get('colour'), label('violet')), label('     .   *\n    (\\ /)\n   (VIOLET)\n    (/ \\)\n      |\n  ____|____'), image)
    image = choose(waiting, label('  .        *\n       .\n  __________\n /          \\\n |   soil   |\n \\__________/'),
                   choose(blooming, image, label('  .        *\n      .\n      v\n  ____|_____\n /   seed   \\\n \\__________/')))
    panel = ['bound', 0]
    prose = choose(eq(panel, label('image')), image, prose)
    prose = choose(eq(panel, label('seed')), get('seed'), prose)
    prose = choose(eq(panel, label('rain')), get('rain'), prose)
    for key in ('planter', 'rainmaker', 'colour'):
        prose = choose(eq(panel, label(key)), get(key), prose)
    actions = choose(waiting, action('plant'), choose(blooming, action('plant'), action('rain')))
    return {'profile': 'delvetalk-local-v1', 'name': 'town-garden-v1',
        'description': 'Two different participants grow one imaginary flower together.',
        'initial': {'phase': 'waiting', 'seed': '', 'colour': '', 'planter': '', 'rain': '', 'rainmaker': '',
                    'lastCompleted': {}},
        'commands': commands, 'affordances': forms,
        'viewPanels': [{'id': key, 'label': text} for key, text in [
            ('image', 'Garden'), ('seed', 'Seed'), ('planter', 'Planted by'),
            ('rain', 'Rain'), ('rainmaker', 'Rain by'), ('colour', 'Light')]],
        'viewProgram': {'profile': 'delvetalk-bend-view-v1',
            'term': ['lam', ['lam', record({'title': title, 'prose': prose, 'actions': actions})]]}}


def scenarios():
    def step(who, command, data, kind='committed', root='current'):
        return {'principal': who, 'command': command, 'input': data, 'kind': kind, 'root': root}
    plant = step('moss', 'plant', {'seed': 'A bell for lost moths', 'colour': 'amber'})
    rain = step('iris', 'rain', {'line': 'Rain arrives carrying the names of forgotten stars.'})
    return [{'name': 'two-voices-one-bloom', 'law': law(['moss', 'iris']), 'steps': [plant, rain]},
        {'name': 'different-author-current-reading', 'law': law(['moss', 'iris']), 'steps': [
            step('iris', 'rain', {'line': 'Too soon.'}, 'refused'),
            step('moss', 'plant', {'seed': '', 'colour': 'amber'}, 'refused'),
            step('moss', 'plant', {'seed': 'Moon', 'colour': 'green'}, 'refused'), plant,
            step('moss', 'rain', {'line': 'Both voices are mine.', 'principal': 'iris'}, 'refused'),
            step('iris', 'rain', {'line': 'An old reading.'}, 'refused', 'initial'), rain,
            step('iris', 'rain', {'line': 'Overwrite the other voice.'}, 'refused')]}]


if __name__ == '__main__':
    for name, value in [('protocol.json', build()), ('migration.json', build()['initial']),
                        ('scenarios.json', scenarios())]:
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
