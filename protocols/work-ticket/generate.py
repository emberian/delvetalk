#!/usr/bin/env python3
"""Generate ordinary work-ticket source; authoring never performs admission."""
import copy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
L = lambda value: ['literal', value]
S = lambda key: ['state', key]
I = lambda key: ['input', key]
P = ['principal']
label = lambda value: ['label', value]
eq = lambda a, b: ['binary', 'labelEqual', a, b]
record = lambda values: ['record', [[key, value] for key, value in values.items()]]
choose = lambda cond, yes, no: ['ifBool', cond, yes, no]


def nonempty(key):
    term = choose(eq(['bound', 0], label('')), ['boolean', False], ['boolean', True])
    return [['bend', ['lam', term], [I(key)]], L(True)]


def law(requester='requester', workers=('moss', 'iris'), managers=('steward',)):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': {
        'post': [requester], 'claim': list(workers), 'submit': list(workers),
        'accept': [requester], 'reject': [requester]},
        'reprogram': [], 'law': list(managers)}


def build(requester='requester', links=None):
    if not isinstance(requester, str) or not requester or len(requester) > 256:
        raise ValueError('requester must be a nonempty string of at most 256 characters')
    links = {} if links is None else copy.deepcopy(links)
    if not isinstance(links, dict) or set(links) - {'context', 'about', 'replyTo'}:
        raise ValueError('links permits only context, about and replyTo')
    if links:
        spec = importlib.util.spec_from_file_location('ticket_references', HERE.parents[1] / 'scripts/references.py')
        references = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(references)
        links = {key: references.validate_reference(value) for key, value in links.items()}
    initial = {'status': 'draft', 'requester': requester, 'author': '', 'task': '',
               'claimant': '', 'result': '', 'submittedBy': '', 'review': '',
               'reviewedBy': '', 'links': links}
    commands, forms = {}, {}

    def add(name, phase, guards, writes, field=None, maximum=2048):
        commands[name] = {'require': [[S('status'), L(phase)]] + guards,
            'set': {'status': L({'post': 'open', 'claim': 'claimed', 'submit': 'submitted',
                                 'accept': 'accepted', 'reject': 'rejected'}[name]), **writes},
            'result': ['record', {'by': P, 'transition': L(name)}], 'outbox': []}
        forms[name] = {'label': {'post': 'Post this task', 'claim': 'Claim this task',
            'submit': 'Submit work for review', 'accept': 'Accept the submission',
            'reject': 'Reject the submission'}[name], 'fields': {} if field is None else {
                field: {'type': 'string', 'minLength': 1, 'maxLength': maximum}}}

    add('post', 'draft', [[P, S('requester')], nonempty('task')],
        {'author': P, 'task': I('task')}, 'task')
    add('claim', 'open', [], {'claimant': P})
    add('submit', 'claimed', [[P, S('claimant')], nonempty('result')],
        {'submittedBy': P, 'result': I('result')}, 'result')
    for name in ('accept', 'reject'):
        add(name, 'submitted', [[P, S('requester')], nonempty('review')],
            {'reviewedBy': P, 'review': I('review')}, 'review', 1024)
    state = ['bound', 1]
    get = lambda key: ['get', state, key]
    action = lambda name: record({'text': label(forms[name]['label']),
        'command': label(name), 'input': record({})})
    actions = record({})
    for phase, names in reversed([('draft', ['post']), ('open', ['claim']),
                                 ('claimed', ['submit']), ('submitted', ['accept', 'reject'])]):
        actions = choose(eq(get('status'), label(phase)), record({n: action(n) for n in names}), actions)
    title, prose = label('Work ticket'), get('task')
    for phase, body in reversed([
            ('draft', label('Post a task for another participant.')),
            ('open', get('task')), ('claimed', get('task')), ('submitted', get('result')),
            ('accepted', get('review')), ('rejected', get('review'))]):
        title = choose(eq(get('status'), label(phase)), label('Work ticket · ' + phase.capitalize()), title)
        prose = choose(eq(get('status'), label(phase)), body, prose)
    term = ['lam', ['lam', record({'title': title,
        'prose': prose,
        'actions': actions})]]
    return {'profile': 'delvetalk-local-v1', 'name': 'work-ticket-v1',
        'description': 'A claimed task and reviewed submission; acceptance acknowledges review, not external execution.',
        'initial': initial, 'commands': commands, 'affordances': forms,
        'viewProgram': {'profile': 'delvetalk-bend-view-v1', 'term': term}}


def scenarios():
    def step(who, command, data=None, kind='committed', root='current'):
        return {'principal': who, 'command': command, 'input': data or {}, 'kind': kind, 'root': root}
    happy = [step('requester', 'post', {'task': 'Describe the moth wing.'}),
             step('moss', 'claim'), step('moss', 'submit', {'result': 'The wing is aligned.'}),
             step('requester', 'accept', {'review': 'Description received.'})]
    invalid = [step('iris', 'post', {'task': 'Impersonated author'}, 'refused'), happy[0],
               step('moss', 'claim', kind='refused', root='initial'), happy[1],
               step('iris', 'claim', kind='refused'),
               step('iris', 'submit', {'result': 'I did it.', 'principal': 'moss'}, 'refused'),
               step('moss', 'submit', {'result': False}, 'refused'), happy[2],
               step('requester', 'reject', {'review': ''}, 'refused'), happy[3],
               step('requester', 'reject', {'review': 'Too late.'}, 'refused')]
    return [{'name': name, 'law': law(), 'steps': steps} for name, steps in [
        ('claim-submit-review', happy), ('roles-types-stale-terminal', invalid)]]


if __name__ == '__main__':
    for name, value in [('protocol.json', build()), ('migration.json', build()['initial']),
                        ('law.json', law()), ('scenarios.json', scenarios())]:
        (HERE / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
