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
    modules = source_object.read_closure([
        ('Candidate', HERE / 'Candidate.obend')])
    if editor_mode:
        return source_object.load(modules, syntax='objective-bend-object')
    return source_object.load(modules, syntax='objective-bend-object',
        constructor='ordinary', arguments=[])


def factory(compiler, makers):
    modules = source_object.read_closure([
        ('Factory', HERE / 'Factory.obend')])
    configuration = source_object.record({'compiler': source_object.data(compiler),
        'reporters': source_object.value(list(makers)), 'candidate': source_object.value(candidate())})
    return source_object.load(modules, syntax='objective-bend-object',
        constructor='initial', arguments=[configuration])


def editor_source():
    return (HERE / 'Editor.obend').read_text()


def editor_artifact(target, factory):
    modules = source_object.read_closure([
        ('Editor', HERE / 'Editor.obend')])
    protocol = source_object.load(modules, syntax='objective-bend-object',
        constructor='initial', arguments=[source_object.data({'target': target, 'factory': factory})])
    return {'protocol': protocol, 'source': {'modules': modules, 'entry': 'describe'}}


def editor_law(makers):
    return {'profile': 'delvetalk-scoped-law',
        'invoke': {key: list(makers) for key in ('draft', 'plan', 'review', 'approve', 'finish')},
        'reprogram': list(makers), 'law': list(makers)}
