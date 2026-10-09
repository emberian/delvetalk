"""Captured transaction plans: field substitution only, never evaluation or refresh."""
import copy
import re

import affordances

FORMAT = 'delvetalk-composite-offer-v1'
MAX_CALLS = 8
MAX_READS = 8
WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_-]{0,127}\Z')


def _name(value):
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError('bounded nonempty object or input name required')
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError('object or input name contains invalid characters')
    return value


def validate(offer):
    """Recheck the complete retained plan, including all substitution destinations."""
    keys = {'format', 'title', 'label', 'command', 'reads', 'calls', 'fields', 'bindings'}
    if not isinstance(offer, dict) or set(offer) != keys or offer['format'] != FORMAT:
        raise ValueError('unknown composite offer shape')
    for key in ('title', 'label'):
        value = offer[key]
        if not isinstance(value, str) or not value or len(value) > 256 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError('composite title and label require bounded Unicode text')
    if not isinstance(offer['command'], str) or not WORD.fullmatch(offer['command']) or re.fullmatch(r'a[1-9][0-9]*', offer['command']):
        raise ValueError('composite command requires a stable offered word')
    reads, calls = offer['reads'], offer['calls']
    if not isinstance(reads, dict) or not 1 <= len(reads) <= MAX_READS:
        raise ValueError('composite offer requires 1..8 exact reads')
    for name, root in reads.items():
        _name(name)
        if (not isinstance(root, dict) or set(root) != {'law', 'protocol', 'state', 'version'}
                or type(root['version']) is not int or root['version'] < 0):
            raise ValueError('composite reads require complete existing roots')
    if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_CALLS:
        raise ValueError('composite offer requires 1..8 invoke calls')
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or set(call) not in ({'object', 'command', 'input'}, {'object', 'command', 'inputFrom'}):
            raise ValueError('composite calls permit only fixed invokes with input or inputFrom')
        if _name(call['object']) not in reads:
            raise ValueError('composite target missing exact read')
        _name(call['command'])
        if 'input' in call:
            if not isinstance(call['input'], dict):
                raise ValueError('composite literal input must be a record')
            for key in call['input']: _name(key)
        elif type(call['inputFrom']) is not int or not 0 <= call['inputFrom'] < index:
            raise ValueError('inputFrom must name an earlier call')
    fields = affordances.validate_fields_schema(offer['fields'])
    names = {field['name'] for field in fields}
    bindings = offer['bindings']
    if not isinstance(bindings, list) or len(bindings) > 32:
        raise ValueError('composite bindings require at most 32 entries')
    consumed, destinations = set(), set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != {'field', 'call', 'input'}:
            raise ValueError('binding requires field, call and input')
        index, key = binding['call'], _name(binding['input'])
        if (not isinstance(binding['field'], str) or binding['field'] not in names
                or type(index) is not int or not 0 <= index < len(calls)):
            raise ValueError('binding must name a declared field and call')
        literal = calls[index].get('input')
        if literal is None or key not in literal or literal[key] is not None:
            raise ValueError('binding requires an explicit null literal input placeholder')
        if (index, key) in destinations:
            raise ValueError('duplicate composite substitution destination')
        destinations.add((index, key)); consumed.add(binding['field'])
    if consumed != names:
        raise ValueError('every composite field must be consumed explicitly')
    result = copy.deepcopy(offer)
    result['fields'] = fields
    return result


def action(offer):
    offer = validate(offer)
    return {'id': 'a1', 'command': offer['command'], 'label': offer['label'],
            'available': True, 'fields': offer['fields']}


def request(offer, principal, intent, values):
    """Construct one existing transaction from fixed reads/calls and typed fields."""
    offer = validate(offer)
    values = affordances.validate_fields(action(offer), values)
    calls = offer['calls']
    for binding in offer['bindings']:
        calls[binding['call']]['input'][binding['input']] = copy.deepcopy(values[binding['field']])
    return {'op': 'transaction', 'principal': principal, 'intent': intent,
            'reads': offer['reads'], 'calls': calls}


def wire(offer, values):
    """Exact operator interpretation envelope; principal/intent remain clerk-owned."""
    result = request(offer, '', '', values)
    del result['principal']; del result['intent']
    result['reads'] = {key: {'expected': root} for key, root in result['reads'].items()}
    return result
