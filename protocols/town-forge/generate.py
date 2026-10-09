"""Physical packaging of source-owned forge objects and writing participants."""
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import translate

SPELL_SYNTAX = 'objective-bend-object'
_spec = importlib.util.spec_from_file_location('forge_source_desk', ROOT / 'protocols/source-desk/package.py')
source_desks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(source_desks)


def principals(values):
    result = list(values)
    if (not result or any(not isinstance(value, str) or not value for value in result)
            or len(set(result)) != len(result)):
        raise ValueError('explicit distinct nonempty principals required')
    return result


def scoped(invoke, reprogram=(), managers=()):
    return {'profile': 'delvetalk-scoped-law', 'invoke': invoke,
            'reprogram': list(reprogram), 'law': list(managers)}


def factory_law(makers, managers=()):
    return scoped({'make': principals(makers)}, managers, managers)


def door(revision=0):
    if revision != 0:
        raise ValueError('use spell_source for authored door revisions')
    return translate.translate(SPELL_SYNTAX, (HERE / 'Chalk.obend').read_bytes())['lowered']


def spell_source(revision=1):
    names = {1: 'paper-door.obend', 2: 'moon-door.obend'}
    return (ROOT / 'syntaxes/examples' / names[revision]).read_text()


def example_source(revision=1):
    return (HERE / {1: 'paper-door.examples', 2: 'moon-door.examples'}[revision]).read_text()


def challenge_source():
    return (HERE / 'moon-challenge.examples').read_text()


def source_desk():
    return source_desks.candidate()


def object_factory(child, visitors, methods, *, managers=(), read="public"):
    modules = source_object.read_modules([
        ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
        ('List', ROOT / 'world/lib/prelude/List.obend'), ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Allocation', ROOT / 'world/lib/prelude/Allocation.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('Factory', ROOT / 'protocols/editor/Factory.obend'),
        ('Creation', ROOT / 'protocols/factories/Creation.obend'),
        ('ObjectFactory', HERE / 'ObjectFactory.obend')])
    config = {'child': child, 'visitors': principals(visitors), 'methods': principals(methods), 'managers': list(managers), 'read': read}
    return source_object.load(modules, syntax='objective-bend-object',
        constructor='initial', arguments=[source_object.value(config)])


def build(visitors, compiler):
    return {'objects': object_factory(door(), visitors, ['knock']),
            'desks': source_desks.factory(compiler, visitors),
            'writers': source_desks.writing_factory()}


def build_stateful(visitors, compiler, *, methods, initial_program=None):
    if initial_program is None:
        initial_program = translate.translate('objective-bend-object',
            (ROOT / 'protocols/stateful-workshop/Instrument.obend').read_bytes())['lowered']
    return {'objects': object_factory(initial_program, visitors, methods),
            'desks': source_desks.factory(compiler, visitors),
            'writers': source_desks.writing_factory()}
