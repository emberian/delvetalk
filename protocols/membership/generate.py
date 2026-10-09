"""Load source-owned membership policy with explicit configuration data."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
HERE = Path(__file__).resolve().parent


def policy_modules():
    return source_object.read_modules([
        ('List', ROOT / 'world/lib/prelude/List.obend'), ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('GrantPolicy', HERE / 'GrantPolicy.obend')])


def amendment(service, commands, *, reprogram=False):
    return {'profile': 'delvetalk-source-amendment-v1',
            'package': {'modules': policy_modules(), 'entry': 'amend'},
            'config': {'service': service, 'commands': list(commands), **({'reprogram': True} if reprogram else {})}}


def welcome(service, targets, *, capacity=64, opened=True):
    modules = source_object.read_modules([
        ('List', ROOT / 'world/lib/prelude/List.obend'), ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('GrantPolicy', HERE / 'GrantPolicy.obend'),
        ('Welcome', HERE / 'Welcome.obend')])
    return source_object.load(modules, syntax='objective-bend-spell@3', constructor='initial',
        arguments=[source_object.value({'service': service, 'targets': targets,
                                       'capacity': capacity, 'open': opened})])
