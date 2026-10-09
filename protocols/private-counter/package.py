"""Physical assembly of the source-owned private counter and its authority."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def counter():
    return source_object.load(source_object.read_modules([
        ('Counter', Path(__file__).with_name('Counter.obend'))]), syntax='objective-bend-object')


def authority(owner, visitor):
    modules = source_object.read_closure([
        ('ScenarioLaw', ROOT / 'world/lib/prelude/ScenarioLaw.obend'),
        ('PrivateCounterAuthority', Path(__file__).with_name('Authority.obend'))])
    authored = source_object.evaluate(modules, 'authority',
        [source_object.data(owner), source_object.data(visitor)])
    return source_object.values('decode', [authored])[0]
