"""Frame a small Objective Bend spell; Lean alone parses and executes its source.

This first binding is stateless: allowed(word), knock(word), and view(state,
panel) are ordinary exported Bend definitions. The protocol envelope is machine
data, not a second authoring language or a source evaluator.
"""
from copy import deepcopy


def lower(source):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Objective Bend spell requires nonempty source text')
    if len(source.encode('utf-8')) > 512 * 1024:
        raise ValueError('Objective Bend spell source exceeds 512 KiB')
    modules = [{'name': 'Main', 'source': source}]

    def package(entry):
        return {'modules': deepcopy(modules), 'entry': entry}

    def call(entry):
        return ['package', package(entry), [['input', 'word']]]

    return {
        'profile': 'delvetalk-local-v1',
        'name': 'objective-bend-spell-v1',
        'runtimeProfile': 'compiled',
        'initial': {},
        'commands': {'knock': {
            'require': [[call('allowed'), ['literal', True]]],
            'set': {}, 'result': call('knock'), 'outbox': [],
        }},
        'affordances': {'knock': {
            'label': 'Whisper to the spell',
            'fields': {'word': {
                'type': 'string', 'label': 'Your word',
                'minLength': 1, 'maxLength': 80,
            }},
        }},
        'viewProgram': {
            'profile': 'delvetalk-obend-view-v1',
            'package': package('view'),
        },
    }
