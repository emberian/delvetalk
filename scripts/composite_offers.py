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
    if not isinstance(offer, dict) or set(offer) not in (keys, keys | {'absentChildren'}) or offer['format'] != FORMAT:
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
        if root is None:
            continue
        if (not isinstance(root, dict) or set(root) != {'law', 'protocol', 'state', 'version'}
                or type(root['version']) is not int or root['version'] < 0):
            raise ValueError('composite reads require complete roots or explicit absence')
    if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_CALLS:
        raise ValueError('composite offer requires 1..8 invoke or observe calls')
    for index, call in enumerate(calls):
        if isinstance(call, dict) and call.get('op') == 'observe':
            if set(call) != {'op', 'object'}:
                raise ValueError('composite observe requires only fixed op and object')
            if _name(call['object']) not in reads or reads[call['object']] is None:
                raise ValueError('composite observe requires an exact existing root')
            continue
        if isinstance(call, dict) and call.get('op') == 'reprogram':
            if (set(call) != {'op', 'object', 'inputFrom'} or _name(call['object']) not in reads
                    or reads[call['object']] is None or type(call['inputFrom']) is not int
                    or not 0 <= call['inputFrom'] < index):
                raise ValueError('composite reprogram requires exact target and earlier actual result')
            continue
        if isinstance(call, dict) and call.get('op') == 'law':
            if (set(call) != {'op', 'object', 'law'} or _name(call['object']) not in reads
                    or reads[call['object']] is None or not isinstance(call['law'], (dict, list))):
                raise ValueError('composite law requires exact target and explicit law')
            continue
        if not isinstance(call, dict) or set(call) not in ({'object', 'command', 'input'}, {'object', 'command', 'inputFrom'}):
            raise ValueError('composite calls permit only fixed invokes or observations')
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
        if not isinstance(binding, dict) or set(binding) not in ({'field', 'call', 'input'}, {'field', 'call', 'path'}):
            raise ValueError('binding requires field, call and input')
        index = binding['call']
        path = binding.get('path', [binding.get('input')])
        if not isinstance(path, list) or not 1 <= len(path) <= 4:
            raise ValueError('binding path requires 1..4 record labels')
        path = [_name(key) for key in path]
        key = path[-1]
        if (not isinstance(binding['field'], str) or binding['field'] not in names
                or type(index) is not int or not 0 <= index < len(calls)):
            raise ValueError('binding must name a declared field and call')
        literal = calls[index].get('input')
        for parent in path[:-1]:
            literal = literal.get(parent) if isinstance(literal, dict) else None
        if not isinstance(literal, dict) or key not in literal or literal[key] is not None:
            raise ValueError('binding requires an explicit null literal input placeholder')
        if (index, tuple(path)) in destinations:
            raise ValueError('duplicate composite substitution destination')
        destinations.add((index, tuple(path))); consumed.add(binding['field'])
    if consumed != names:
        raise ValueError('every composite field must be consumed explicitly')
    children = offer.get('absentChildren', [])
    if not isinstance(children, list) or len(children) > 8:
        raise ValueError('absent children require at most 8 declarations')
    for child in children:
        if (not isinstance(child, dict) or set(child) != {'factory', 'field'}
                or child['factory'] not in reads or reads[child['factory']] is None):
            raise ValueError('absent child requires an existing exact factory read')
        affordances.validate_children_schema([{'field': child['field']}], fields)
    if len(reads) + len(children) > MAX_READS:
        raise ValueError('complete composite read set exceeds 8 reads')
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
        path = binding.get('path', [binding.get('input')])
        literal = calls[binding['call']]['input']
        for key in path[:-1]: literal = literal[key]
        literal[path[-1]] = copy.deepcopy(values[binding['field']])
    reads = offer['reads']
    for child in offer.get('absentChildren', []):
        name = affordances._child_name(values[child['field']])
        identity = child['factory'] + '/' + name
        if identity in reads and reads[identity] is not None:
            raise ValueError('declared absent child conflicts with an existing captured root')
        reads[identity] = None
    result = {'op': 'transaction', 'principal': principal, 'intent': intent,
              'reads': reads, 'calls': calls}
    import world
    if len(world.wire_dumps(result).encode('utf-8')) > 65536:
        raise ValueError('composite request exceeds 64 KiB')
    return result


def wire(offer, values):
    """Exact operator interpretation envelope; principal/intent remain clerk-owned."""
    result = request(offer, '', '', values)
    del result['principal']; del result['intent']
    result['reads'] = {key: {'expected': root}
                       for key, root in result['reads'].items()}
    return result
