"""Load exact exhibition modules; behavior and configuration live in Bend/data."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
HERE = Path(__file__).resolve().parent


def modules():
    return source_object.read_closure([('Agreement', HERE / 'Agreement.obend'),
        ('Exhibition', HERE / 'Exhibition.obend')])


def build(participants=None):
    if participants is None:
        return source_object.load(modules(), syntax='objective-bend-object')
    return source_object.load(modules(), syntax='objective-bend-object', constructor='initial',
                              arguments=[source_object.data(participants)])
