"""Bind source-authored plans to one captured snapshot; no workflow evaluator."""
import copy
import re

import affordances
import composite_offers

MAX_OFFERS = 16
WORD = re.compile(r'[A-Za-z_][A-Za-z0-9_-]{0,127}\Z')
KEYS = {'visible', 'title', 'label', 'command', 'reads', 'calls', 'fields',
        'bindings', 'absentChildren', 'captures'}


def _record(value, maximum, name):
    if not isinstance(value, dict) or len(value) > maximum:
        raise ValueError(name + ' requires a bounded record')
    for key in value:
        if not isinstance(key, str) or not WORD.fullmatch(key):
            raise ValueError(name + ' has an invalid record label')
    return value


def _text(value, name, maximum=256, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or (not empty and not value)
            or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError(name + ' requires bounded text')
    return value


def _path(value):
    _text(value, 'input path', 256)
    path = value.split('.')
    if not 1 <= len(path) <= 4 or any(not WORD.fullmatch(key) for key in path):
        raise ValueError('input path requires 1..4 record labels')
    return path


def _slot(value, path):
    for key in path[:-1]:
        if not isinstance(value, dict) or key not in value:
            raise ValueError('input binding path is absent')
        value = value[key]
    if not isinstance(value, dict) or path[-1] not in value:
        raise ValueError('input binding path is absent')
    return value


def _fields(value):
    fields = []
    for name, spec in sorted(_record(value, 32, 'fields').items()):
        if not isinstance(spec, dict):
            raise ValueError('source field requires a record')
        spec = copy.deepcopy(spec)
        if spec.get('type') == 'enum' and isinstance(spec.get('options'), dict):
            spec['options'] = [spec['options'][key] for key in sorted(spec['options'])]
        fields.append(affordances._normalize_field(name, spec))
    return affordances.validate_fields_schema(fields)


def validate_descriptors(offers):
    """Eagerly validate hidden plans too. Never read a snapshot or inspect phases."""
    _record(offers, MAX_OFFERS, 'offers')
    for key, offer in offers.items():
        if not isinstance(offer, dict) or set(offer) != KEYS or type(offer['visible']) is not bool:
            raise ValueError('source offer requires the exact descriptor fields')
        for name in ('title', 'label', 'command'):
            _text(offer[name], name)
        if not WORD.fullmatch(offer['command']):
            raise ValueError('source offer command must be a word')
        reads = _record(offer['reads'], 8, 'reads')
        if not reads:
            raise ValueError('source offer requires reads')
        for ref in reads.values():
            if not isinstance(ref, dict) or set(ref) != {'object', 'child'}:
                raise ValueError('read reference requires object and child')
            _text(ref['object'], 'read object')
            if ref['child'] != '':
                affordances._child_name(ref['child'])
        calls = _record(offer['calls'], 8, 'calls')
        if not calls or set(calls) != {'c' + str(i) for i in range(len(calls))}:
            raise ValueError('calls require consecutive c0..c7 slots')
        for index in range(len(calls)):
            call = calls['c' + str(index)]
            if not isinstance(call, dict) or set(call) != {'op', 'object', 'command', 'input', 'fromResult', 'inputFrom'}:
                raise ValueError('source call requires the exact slot fields')
            if call['object'] not in reads or call['op'] not in ('invoke', 'observe', 'reprogram', 'law'):
                raise ValueError('source call requires a read alias and supported op')
            _text(call['command'], 'call command', empty=True)
            if not isinstance(call['input'], dict) or type(call['fromResult']) is not bool:
                raise ValueError('source call requires literal record and result flag')
            if type(call['inputFrom']) is not int or call['inputFrom'] < 0:
                raise ValueError('inputFrom requires a Nat')
            if call['fromResult'] and not call['inputFrom'] < index:
                raise ValueError('inputFrom requires an earlier call')
            if call['op'] == 'invoke' and not call['command']:
                raise ValueError('invoke requires command')
            if call['op'] != 'invoke' and call['command']:
                raise ValueError('non-invoke command must be empty')
            if call['op'] == 'observe' and (call['input'] or call['fromResult']):
                raise ValueError('observe has no input')
            if call['op'] == 'reprogram' and (not call['fromResult'] or call['input']):
                raise ValueError('source reprogram must consume an earlier actual result')
            if call['op'] == 'law' and (call['fromResult'] or set(call['input']) != {'law'}):
                raise ValueError('source law step requires explicit literal law')
        fields = {field['name']: field for field in _fields(offer['fields'])}
        destinations, consumed = set(), set()
        for binding in _record(offer['bindings'], 32, 'bindings').values():
            if not isinstance(binding, dict) or set(binding) != {'field', 'call', 'input'}:
                raise ValueError('field binding requires field, call and input')
            if binding['field'] not in fields:
                raise ValueError('binding field is undeclared')
            _binding(offer, binding, destinations)
            consumed.add(binding['field'])
        if consumed != set(fields):
            raise ValueError('every source field must have an explicit binding')
        for binding in _record(offer['captures'], 32, 'captures').values():
            if (not isinstance(binding, dict) or set(binding) != {'read', 'call', 'input', 'rootField'}
                    or binding['read'] not in reads
                    or binding['rootField'] not in ('object', 'state', 'version', 'law', 'protocol')):
                raise ValueError('capture requires read, call, input and exact root field')
            _binding(offer, binding, destinations)
        for declaration in _record(offer['absentChildren'], 8, 'absentChildren').values():
            if (not isinstance(declaration, dict) or set(declaration) != {'factory', 'field'}
                    or declaration['factory'] not in reads or declaration['field'] not in fields):
                raise ValueError('absent child requires factory alias and declared field')
            affordances.validate_children_schema([{'field': declaration['field']}], list(fields.values()))
    return copy.deepcopy(offers)


def _binding(offer, binding, destinations):
    index = binding['call']
    if type(index) is not int or not 0 <= index < len(offer['calls']):
        raise ValueError('binding call is absent')
    call = offer['calls']['c' + str(index)]
    if call['op'] != 'invoke' or call['fromResult']:
        raise ValueError('bindings require a literal invoke input')
    path = _path(binding['input'])
    _slot(call['input'], path)
    destination = (index, tuple(path))
    if destination in destinations:
        raise ValueError('duplicate input binding destination')
    destinations.add(destination)


def capture_descriptor(view, roots, descriptor):
    """Fill only explicitly named roots and input captures from this snapshot."""
    if roots.get(view['object']) != view['root']:
        raise ValueError('source view and captured snapshot must bind the same exact owner root')
    refs, reads = {}, {view['object']: copy.deepcopy(view['root'])}
    for alias, ref in descriptor['reads'].items():
        identity = view['object'] if ref['object'] == '$self' else ref['object']
        if ref['child']:
            identity += '/' + affordances._child_name(ref['child'])
        if identity not in roots:
            raise ValueError('captured dependency missing: ' + identity)
        refs[alias] = identity
        reads[identity] = copy.deepcopy(roots[identity])
    if view['object'] not in reads or reads[view['object']] != view['root']:
        raise ValueError('source view and captured snapshot must bind the same exact owner root')
    calls = []
    for index in range(len(descriptor['calls'])):
        slot = descriptor['calls']['c' + str(index)]
        call = {'object': refs[slot['object']]}
        if slot['op'] == 'observe':
            call['op'] = 'observe'
        elif slot['op'] == 'law':
            call.update(op='law', law=copy.deepcopy(slot['input']['law']))
        else:
            if slot['op'] == 'reprogram': call['op'] = 'reprogram'
            else: call['command'] = slot['command']
            if slot['fromResult']: call['inputFrom'] = slot['inputFrom']
            else: call['input'] = copy.deepcopy(slot['input'])
        calls.append(call)
    for binding in descriptor['captures'].values():
        path = _path(binding['input'])
        root = reads[refs[binding['read']]]
        value = refs[binding['read']] if binding['rootField'] == 'object' else root[binding['rootField']]
        _slot(calls[binding['call']]['input'], path)[path[-1]] = copy.deepcopy(value)
    bindings = []
    for binding in descriptor['bindings'].values():
        path = _path(binding['input'])
        _slot(calls[binding['call']]['input'], path)[path[-1]] = None
        bindings.append({'field': binding['field'], 'call': binding['call'], 'path': path})
    offer = {'format': composite_offers.FORMAT, 'title': descriptor['title'], 'label': descriptor['label'],
             'command': descriptor['command'], 'reads': reads, 'calls': calls,
             'fields': _fields(descriptor['fields']), 'bindings': bindings}
    if descriptor['absentChildren']:
        offer['absentChildren'] = [{'factory': refs[item['factory']], 'field': item['field']}
                                  for item in descriptor['absentChildren'].values()]
    return composite_offers.validate(offer)


def capture_available(view, roots):
    import sys
    from pathlib import Path
    scene = str(Path(__file__).resolve().parents[1] / 'scene')
    if scene not in sys.path: sys.path.insert(0, scene)
    import projection
    descriptors = projection.offers(view)
    result = {'offers': {}, 'unavailable': {}}
    for key, descriptor in descriptors.items():
        try:
            result['offers'][key] = capture_descriptor(view, roots, descriptor)
        except (ValueError, KeyError, TypeError) as error:
            result['unavailable'][key] = {'label': descriptor['label'], 'command': descriptor['command'],
                                        'reason': str(error)}
    return result


def capture(view, roots):
    return capture_available(view, roots)['offers']
