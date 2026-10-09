"""Assemble an authored Editor and ordinary governed immutable candidate desks.

The source owns editing decisions; these functions only frame reviewed program
and authority data. No Python transition evaluator exists.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import translate

HERE = Path(__file__).resolve().parent
L = lambda value: ['literal', value]
I = lambda key: ['input', key]
S = lambda key: ['state', key]
P = ['principal']
G = lambda value, key: ['bend', ['lam', ['get', ['bound', 0], key]], [value]]


def candidate():
    protocol = json.loads((ROOT / 'protocols/source-desk/protocol.json').read_bytes())
    protocol['name'] = 'editor-candidate-v1'
    protocol['initial'].update(editor='', generation=0, baselineVersion=0)
    submit = protocol['commands']['submit']
    submit['set'].update(editor=I('editor'), generation=I('generation'), baselineVersion=I('baselineVersion'))
    protocol['commands']['report'] = {'require': [], 'set': {}, 'outbox': [],
        'result': ['record', {'candidate': ['object'], 'editor': S('editor'),
            'generation': S('generation'), 'target': S('target'),
            'baselineVersion': S('baselineVersion'), 'status': S('status'), 'program': ['program-digest', S('protocol')]}]}
    # A real immediately preceding Editor approval is required; the candidate's
    # own law still authorizes this maker independently.
    origin = ['input-origin']
    protocol['commands']['adopt']['require'].extend([
        [G(origin, 'present'), L(True)],
        [G(origin, 'object'), S('editor')],
        [G(origin, 'command'), L('approve')],
        [G(origin, 'immediatelyPrevious'), L(True)],
        [I('editor'), S('editor')], [I('generation'), S('generation')],
        [I('candidate'), ['object']]])
    return protocol


def factory(compiler, makers):
    if not makers or any(not isinstance(who, str) or not who for who in makers):
        raise ValueError('explicit maker grants required')
    protocol = json.loads((ROOT / 'protocols/factories/source-desk.json').read_bytes())
    protocol['name'] = 'editor-candidates-v1'
    protocol['description'] = 'Each planned generation gets a fresh immutable candidate; old work remains.'
    protocol['initial'] = {'last': '', 'compiler': compiler}
    protocol['allocation']['limit'] = 32
    protocol['commands']['make']['allocate'][0]['protocol'] = L(candidate())
    origin = ['input-origin']
    protocol['commands']['make']['require'].extend([
        [G(origin, 'present'), L(True)],
        [G(origin, 'object'), I('editor')],
        [G(origin, 'command'), L('plan')],
        [G(origin, 'immediatelyPrevious'), L(True)],
        [I('factory'), ['object']]])
    protocol['commands']['make']['result'] = ['record', {key: I(key) for key in
        ('factory', 'name', 'editor', 'generation', 'target', 'baselineVersion')}]
    protocol['commands']['make']['allocate'][0]['law'][1]['invoke'][1]['report'] = L(list(makers))
    return protocol


def editor_source(target, factory):
    source = (HERE / 'Editor.obend').read_text()
    return source.replace('\"EDITOR_TARGET\"', json.dumps(target)).replace('\"EDITOR_FACTORY\"', json.dumps(factory))


def editor_artifact(target, factory):
    return translate.translate('objective-bend-spell@3', editor_source(target, factory).encode())


def editor_law(makers):
    return {'profile': 'delvetalk-scoped-law-v1',
        'invoke': {key: list(makers) for key in ('draft', 'plan', 'review', 'approve', 'finish')},
        'reprogram': list(makers), 'law': list(makers)}


if __name__ == '__main__':
    (HERE / 'candidate.json').write_text(json.dumps(candidate(), ensure_ascii=False, separators=(',', ':')) + '\n')
