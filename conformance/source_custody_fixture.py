"""One explicit source fixture for native physical receiving tests."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object

@lru_cache(maxsize=16)
def value_protocol(encoded='1.2300'):
    from decimal import Decimal
    modules = source_object.read_closure([('CustodyValue', ROOT / 'conformance/fixtures/CustodyValue.obend')])
    return source_object.load(modules, syntax='objective-bend-object', constructor='initial',
                              arguments=[source_object.value(Decimal(encoded))])

def create():
    return {'op': 'create', 'object': 'room', 'principal': 'keeper', 'intent': 'create',
            'protocol': deepcopy(value_protocol()),
            'law': {'profile': 'delvetalk-scoped-law', 'invoke': {'write': ['keeper']},
                    'reprogram': ['keeper'], 'law': ['keeper']}}

def replace_initial_number(request, encoded):
    request['protocol'] = deepcopy(value_protocol(encoded))

@lru_cache(maxsize=1)
def counter_protocol():
    return source_object.load([{'name': 'Counter', 'source': counter_source().decode()}],
                              syntax='objective-bend-object')

def counter_source():
    return (ROOT / 'conformance/fixtures/Counter.obend').read_bytes()

def scoped(actors, *, readers=None):
    return {'profile': 'delvetalk-scoped-law', 'invoke': {'add': actors},
            'reprogram': actors, 'law': actors, 'read': 'public'}

def count(root):
    return source_object.plain(source_object.state_data(root))['count']
