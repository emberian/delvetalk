"""Physical packaging for source-owned text objects and governed object creation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def object():
    return source_object.load(source_object.read_modules([
        ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('Object', HERE / 'Object.obend')]), syntax='objective-bend-spell@3')


def factory(participants=None):
    modules = source_object.read_modules([
        ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
        ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Allocation', ROOT / 'world/lib/prelude/Allocation.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('Creation', HERE / 'Creation.obend'),
        ('ObjectFactory', HERE / 'Factory.obend')])
    child = source_object.value(object())
    if participants is None:
        return source_object.load(modules, syntax='objective-bend-spell@3',
            constructor='ordinary', arguments=[child])
    config = source_object.record({'object': child, 'participants': source_object.value(list(participants))})
    return source_object.load(modules, syntax='objective-bend-spell@3',
        constructor='initial', arguments=[config])
