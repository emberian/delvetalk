"""Load source-owned membership policy with explicit configuration data."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
HERE = Path(__file__).resolve().parent


def policy_modules():
    return source_object.read_closure([
        ('GrantPolicy', HERE / 'GrantPolicy.obend')])


def amendment(service, commands, *, reprogram=False):
    return {'profile': 'delvetalk-source-amendment-v1',
            'package': {'modules': policy_modules(), 'entry': 'amend'},
            'config': {'service': service, 'commands': list(commands), **({'reprogram': True} if reprogram else {})}}


def welcome(service, targets, *, capacity=64, opened=True):
    modules = source_object.read_closure([
        ('GrantPolicy', HERE / 'GrantPolicy.obend'),
        ('Welcome', HERE / 'Welcome.obend')])
    framed = source_object.variant('nil', source_object.record({}))
    for item in reversed(list(targets)):
        framed = source_object.variant('cons', source_object.record({
            'head': source_object.value(item), 'tail': framed}))
    return source_object.load(modules, syntax='objective-bend-object', constructor='initial',
        arguments=[source_object.record({'service': source_object.data(service), 'targets': framed,
                                       'capacity': source_object.data(capacity), 'open': source_object.data(opened)})])
