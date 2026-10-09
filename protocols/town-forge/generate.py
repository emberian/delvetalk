#!/usr/bin/env python3
"""Ordinary governed factories for small resident-authored doors and spells."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPELL_SYNTAX = 'objective-bend-spell@1'
L = lambda value: ['literal', value]
I = lambda key: ['input', key]
S = lambda key: ['state', key]
P = ['principal']
label = lambda text: ['label', text]
record = lambda fields: ['record', [[key, value] for key, value in fields.items()]]
eq = lambda left, right: ['binary', 'labelEqual', left, right]
choose = lambda condition, yes, no: ['ifBool', condition, yes, no]


def principals(values):
    result = list(values)
    if (not result or any(not isinstance(value, str) or not value for value in result)
            or len(set(result)) != len(result)):
        raise ValueError('explicit distinct nonempty principals required')
    return result


def scoped(invoke, reprogram=(), managers=()):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': invoke,
            'reprogram': list(reprogram), 'law': list(managers)}


def factory_law(makers, managers=()):
    return scoped({'make': principals(makers)}, managers, managers)


def form_string(label_text, maximum=4096):
    return {'type': 'string', 'label': label_text, 'minLength': 1, 'maxLength': maximum}


def action(command, text):
    return record({command: record({'text': label(text), 'command': label(command),
                                   'input': record({})})})


def view(title, prose, actions):
    return {'profile': 'delvetalk-bend-view-v1',
            'term': ['lam', ['lam', record({'title': title, 'prose': prose, 'actions': actions})]]}


def door(revision=0):
    """A waiting placeholder; authored behavior lives only in Objective Bend."""
    if revision != 0:
        raise ValueError('use spell_source for authored door revisions')
    return {'profile': 'delvetalk-local-v1', 'name': 'town-forge-chalk-door-v1',
        'initial': {}, 'commands': {'knock': {
            'require': [], 'set': {},
            'result': L('The chalk door is waiting for a spell.'), 'outbox': []}},
        'affordances': {'knock': {'label': 'Whisper to the door',
            'fields': {'word': form_string('Your word', 80)}}},
        'viewProgram': view(label('The chalk door'),
            label('A door drawn in chalk. Its maker has not given it a spell yet.'),
            action('knock', 'Whisper to the door'))}


def spell_source(revision=1):
    """Exact resident-authored Objective Bend; never serialize an AST for them."""
    names = {1: 'paper-door.obend', 2: 'moon-door.obend'}
    if revision not in names:
        raise ValueError('spell revision must be 1 or 2')
    return (HERE.parents[1] / 'syntaxes/examples' / names[revision]).read_text()


def example_source(revision=1):
    names = {1: 'paper-door.examples', 2: 'moon-door.examples'}
    if revision not in names:
        raise ValueError('spell revision must be 1 or 2')
    return (HERE / names[revision]).read_text()


def challenge_source():
    return (HERE / 'moon-challenge.examples').read_text()


def source_desk():
    protocol = json.loads((HERE.parent / 'source-desk/protocol.json').read_text())
    protocol['name'] = 'town-forge-source-desk-v1'
    protocol['description'] = 'Write a small spell, try examples, then explicitly install it with an empty state.'
    # Pure views materialize the whole state: keep empty/pending state inside
    # the existing Nat/Bool/String/record boundary. Completion keeps the base
    # compiler's actual protocol/diagnostics; its retained reply presents those.
    protocol['initial'] = {key: ('' if value is None else value)
                           for key, value in protocol['initial'].items()}
    protocol['initial'].update(proposal={'syntax': SPELL_SYNTAX, 'source': '', 'scenarios': ''},
                               migration={}, protocol={}, diagnostics={})
    submit = protocol['commands']['submit']
    for key in ('target', 'source', 'scenarios'):
        submit['require'].append([['bend', ['lam', choose(eq(['bound', 0], label('')),
            ['boolean', False], ['boolean', True])], [I(key)]], L(True)])
    submit['set'].update(proposal=['record', {'syntax': L(SPELL_SYNTAX),
        'source': I('source'), 'scenarios': I('scenarios')}], migration=L({}), target=I('target'))
    protocol['affordances'] = {'submit': {'label': 'Write a spell and its examples', 'fields': {
        'target': form_string('Exact door object name', 256),
        'source': form_string('Objective Bend spell'),
        'scenarios': form_string('Examples to try')}}}
    state, panel = ['bound', 1], ['bound', 0]
    get = lambda key: ['get', state, key]
    empty = eq(get('status'), label('empty'))
    prose = label('Write an Objective Bend spell and examples. This door keeps no memory: '
                  'installation starts with an empty state. Try the spell, then choose whether to install it.')
    for key in ('source', 'scenarios'):
        text = choose(empty, label(''), ['get', get('proposal'), key])
        prose = choose(eq(panel, label(key)), text, prose)
    prose = choose(eq(panel, label('target')), choose(empty, label(''), get('target')), prose)
    prose = choose(eq(panel, label('status')), get('status'), prose)
    protocol['viewProgram'] = view(label('The spell-writing desk'), prose,
        choose(empty, action('submit', 'Write a spell and its examples'), record({})))
    protocol['viewPanels'] = [{'id': key, 'label': title} for key, title in (
        ('status', 'Desk state'), ('target', 'Door'), ('source', 'Exact spell source'),
        ('scenarios', 'Exact examples'))]
    return protocol


def factory(kind, child, law):
    making_doors = kind == 'objects'
    title = 'The door forge' if making_doors else 'The spell-writing desks'
    invitation = ('Draw a chalk door and give it a name. Then write a spell to bring it to life.'
                  if making_doors else
                  'Make a writing desk for a new spell, a revision, or an example you want to try.')
    make_label = 'Make a door' if making_doors else 'Make a writing desk'
    last = ['get', ['bound', 1], 'last']
    last_text = choose(eq(last, label('')), label('Nothing made here yet.'), last)
    prose = choose(eq(['bound', 0], label('last')), last_text, label(invitation))
    return {'profile': 'delvetalk-local-v1', 'name': 'town-forge-' + kind + '-v1',
        'description': 'Make a chalk door.' if kind == 'objects' else 'Make a spell-writing desk.',
        'initial': {'last': ''}, 'allocation': {'limit': 16},
        'viewProgram': view(label(title), prose, action('make', make_label)),
        'viewPanels': [{'id': 'last', 'label': 'Last made'}],
        'affordances': {'make': {'label': make_label,
            'fields': {'name': form_string('A short name', 64)}, 'children': ['name']}},
        'commands': {'make': {'require': [], 'set': {'last': I('name')},
            'result': ['record', {'name': I('name'), 'maker': P}], 'outbox': [],
            'allocate': [{'name': I('name'), 'protocol': L(child), 'law': law}]}}}


def build(visitors, compiler):
    visitors = principals(visitors)
    principals([compiler])
    # These are explicit law expressions. The maker is the actual invocation principal.
    object_law = ['record', {'profile': L('delvetalk-scoped-law-v1'),
        'invoke': ['record', {'knock': ['array', [P] + [L(who) for who in visitors]]}],
        'reprogram': ['array', [P]], 'law': ['array', [P]]}]
    desk_law = ['record', {'profile': L('delvetalk-scoped-law-v1'),
        'invoke': ['record', {'submit': ['array', [P]], 'adopt': ['array', [P]],
            'compiled': L([compiler]), 'failed': L([compiler])}],
        'reprogram': L([]), 'law': L([])}]
    return {'objects': factory('objects', door(0), object_law),
            'desks': factory('desks', source_desk(), desk_law)}


def files():
    package = build(['visitor'], 'compiler')
    return {'objects-factory.json': package['objects'], 'desks-factory.json': package['desks'],
        'source-desk.json': source_desk(), 'migration.json': {}}


if __name__ == '__main__':
    for name, value in files().items():
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
