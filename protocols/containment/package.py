"""Physical loading of explicit source-owned placement, rooms and route books."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def sources(name):
    if name not in ('Main', 'Room', 'Guide', 'Lamp'):
        raise ValueError('unknown containment source')
    return source_object.read_closure([
        ('Relations', HERE / 'Relations.obend'), (name, HERE / (name + '.obend'))], roots=[name])


def load(name, configuration=None):
    modules = sources(name)
    return source_object.load(modules, syntax='objective-bend-object',
        **({'constructor': 'configured', 'arguments': [configuration]} if configuration is not None else {}))
