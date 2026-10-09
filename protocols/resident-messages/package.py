"""Physical source assembly for the independent courtyard residents."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from syntaxes import obend_object
sys.path.insert(0, str(ROOT / "scripts"))
import source_object


def sources(name):
    if name not in ('Bell', 'Door', 'Lantern', 'Loop'):
        raise ValueError('unknown resident source')
    return source_object.read_closure([(name, HERE / (name + '.obend'))])


def load(name, configuration=None):
    if configuration is None:
        return obend_object.lower_data_modules(sources(name))
    return source_object.load(sources(name), syntax='objective-bend-object',
        constructor='configured', arguments=[source_object.data(configuration)])
