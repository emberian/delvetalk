"""Physical packaging for source-owned text objects and governed object creation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def object():
    return source_object.load(source_object.read_closure([
        ('Object', HERE / 'Object.obend')]), syntax='objective-bend-object')


def factory(participants=None, *, read="public"):
    modules = source_object.read_closure([
        ('Creation', HERE / 'Creation.obend'),
        ('ObjectFactory', HERE / 'Factory.obend')])
    child = source_object.value(object())
    if participants is None and read == "public":
        return source_object.load(modules, syntax='objective-bend-object',
            constructor='ordinary', arguments=[child])
    config = source_object.record({'object': child, 'participants': source_object.value(None if participants is None else list(participants)),
                                   'read': source_object.value(read)})
    return source_object.load(modules, syntax='objective-bend-object',
        constructor='initial', arguments=[config])
