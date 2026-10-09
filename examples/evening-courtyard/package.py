"""Explicit source/configuration custody for the inhabited courtyard example."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def modules(afterglow=False):
    paths = [(name, ROOT / 'world/lib/prelude' / (name + '.obend'))
             for name in ('Abi', 'Preparation', 'Encounter')]
    paths += [('Document', ROOT / 'world/lib/document/Document.obend'),
              ('Conversation', ROOT / 'protocols/conversation/Conversation.obend'),
              ('CourtyardBook', HERE / 'CourtyardBook.obend')]
    if afterglow:
        paths += [('AfterglowBook', HERE / 'AfterglowBook.obend')]
    return source_object.read_modules(paths)


def book(places, *, afterglow=False):
    children = source_object.variant('nil', source_object.record({}))
    for child in reversed(places):
        children = source_object.variant('cons', source_object.record({
            'head': source_object.data(child), 'tail': children}))
    return source_object.load(modules(afterglow), syntax='objective-bend-object',
        constructor='configured', arguments=[source_object.record({
            'object': source_object.data('courtyard'),
            'title': source_object.data('An evening built together'), 'places': children})])
