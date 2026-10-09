"""Assemble an authored Editor and ordinary governed immutable candidate desks.

Candidate and Factory own lifecycle, approval guards, child construction and
child law in ordinary source. This file loads explicit modules/configuration.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object

HERE = Path(__file__).resolve().parent


def candidate(*, editor_mode=True):
    modules = source_object.read_modules([
        ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Candidate', HERE / 'Candidate.obend')])
    if editor_mode:
        return source_object.load(modules, syntax='objective-bend-spell@3')
    return source_object.load(modules, syntax='objective-bend-spell@3',
        constructor='ordinary', arguments=[])


def factory(compiler, makers):
    modules = source_object.read_modules([
        ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Allocation', ROOT / 'world/lib/prelude/Allocation.obend'),
        ('Factory', HERE / 'Factory.obend')])
    configuration = {'compiler': compiler, 'reporters': list(makers), 'candidate': candidate()}
    return source_object.load(modules, syntax='objective-bend-spell@3',
        constructor='initial', arguments=[source_object.value(configuration)])


def editor_source():
    return (HERE / 'Editor.obend').read_text()


def editor_artifact(target, factory):
    modules = source_object.read_modules([
        ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Editor', HERE / 'Editor.obend')])
    protocol = source_object.load(modules, syntax='objective-bend-spell@3',
        constructor='initial', arguments=[source_object.data({'target': target, 'factory': factory})])
    return {'protocol': protocol, 'source': {'modules': modules, 'entry': 'describe'}}


def editor_law(makers):
    return {'profile': 'delvetalk-scoped-law-v1',
        'invoke': {key: list(makers) for key in ('draft', 'plan', 'review', 'approve', 'finish')},
        'reprogram': list(makers), 'law': list(makers)}
