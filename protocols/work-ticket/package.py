"""Physical source/configuration loading; ticket behavior is ordinary Bend."""
import copy
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import references
import source_object
HERE = Path(__file__).resolve().parent


def modules():
    return source_object.read_modules([('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
        ('List', ROOT / 'world/lib/prelude/List.obend'), ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('ReviewableWork', HERE / 'ReviewableWork.obend'), ('Ticket', HERE / 'Ticket.obend')])


def build(*, requester=None, links=None):
    config = json.loads((HERE / 'configuration.json').read_bytes())
    if requester is not None:
        config['fields'][0]['value'] = source_object.data(requester)
    if links is not None:
        if not isinstance(links, dict) or set(links) - {'context', 'about', 'replyTo'}:
            raise ValueError('links are the declared configuration reference fields')
        fields = config['fields'][1]['value']['fields']
        for field in fields:
            if field['name'] in links:
                ref = references.validate_reference(links[field['name']])
                field['value'] = source_object.variant('present', source_object.data(ref))
    return source_object.load(modules(), syntax='objective-bend-spell@3', constructor='initial', arguments=[config])


def law():
    return copy.deepcopy(json.loads((HERE / 'law.json').read_bytes()))
