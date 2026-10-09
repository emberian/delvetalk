"""Physical compilation of the ordinary source directory/session packages."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def modules(session=False, factory=False):
    paths = [('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
             ('List', ROOT / 'world/lib/prelude/List.obend'), ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
             ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
             ('Document', ROOT / 'world/lib/document/Document.obend'),
             ('Directory', HERE / 'Directory.obend'), ('GSBWelcome', HERE / 'GSBWelcome.obend')]
    if session or factory:
        paths.append(('SessionEntry', HERE / 'SessionEntry.obend'))
    if factory:
        paths.extend([('Allocation', ROOT / 'world/lib/prelude/Allocation.obend'),
                      ('Creation', ROOT / 'protocols/factories/Creation.obend'),
                      ('SessionFactory', HERE / 'SessionFactory.obend')])
    return source_object.read_modules(paths)


def entry():
    return source_object.load(modules(session=True), syntax='objective-bend-spell@3')


def factory(entry_protocol, doors=(), welcome=""):
    # Physical framing of an explicit typed list; all configuration/admission
    # behavior remains in the supplied source constructor and methods.
    framed = source_object.variant('nil', source_object.record({}))
    for item in reversed(list(doors)):
        framed = source_object.variant('cons', source_object.record({
            'head': source_object.data(item), 'tail': framed}))
    return source_object.load(modules(factory=True), syntax='objective-bend-spell@3',
        constructor='initial', arguments=[source_object.record({'entry': source_object.value(entry_protocol), 'doors': framed, 'welcome': source_object.data(welcome)})])
