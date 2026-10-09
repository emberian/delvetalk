"""Bounded remote transaction wire normalization; Lean decides admission."""
import re

MAX_READS = 16
MAX_CALLS = 32


def validate_absent(absent):
    if (not isinstance(absent, list) or len(absent) > MAX_READS
            or any(not isinstance(item, str) or not item for item in absent)):
        raise ValueError('absent requires at most 16 nonempty object identities')


def exposed_absence(object_id, objects):
    """Expose a declared absence in one registered namespace, never its descendants."""
    parent, separator, name = object_id.rpartition('/')
    return bool(separator and parent in objects and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name))


def resolve_absent(absent, config):
    validate_absent(absent)
    objects = set(config['objects'])
    if any(item not in objects and not exposed_absence(item, objects) for item in absent):
        raise ValueError('absence object is not configured for remote requests')


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(label + ' has missing or unknown fields')


def validate(payload):
    exact(payload, ['op', 'reads', 'calls'], 'transaction')
    if payload['op'] != 'transaction':
        raise ValueError('expected transaction operation')
    reads, calls = payload['reads'], payload['calls']
    if not isinstance(reads, dict) or not 1 <= len(reads) <= MAX_READS:
        raise ValueError('transaction requires 1..16 read descriptors')
    if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_CALLS:
        raise ValueError('transaction requires 1..32 calls')
    for object_id, descriptor in reads.items():
        if not isinstance(object_id, str) or not object_id:
            raise ValueError('read object identity must be nonempty')
        field = 'expectedRootRef' if isinstance(descriptor, dict) and 'expectedRootRef' in descriptor else 'expected'
        exact(descriptor, [field], 'read descriptor')
        if not isinstance(descriptor[field], dict) and not (field == 'expected' and descriptor[field] is None):
            raise ValueError('read root must be an object or null; reference must be an object')
        if field == 'expectedRootRef':
            reference = descriptor[field]
            exact(reference, ['uri', 'cid'], 'root reference')
            if not isinstance(reference['uri'], str) or not isinstance(reference['cid'], str) or not 1 <= len(reference['cid']) <= 200:
                raise ValueError('root reference requires URI and CID strings')
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get('object'), str) or not call['object']:
            raise ValueError('transaction call requires object identity')
        operation = call.get('op', 'invoke')
        if operation == 'invoke':
            input_field = 'inputFrom' if 'inputFrom' in call else 'input'
            fields = ['object', 'command', input_field] + (['op'] if 'op' in call else [])
            exact(call, fields, 'invocation call')
            if not isinstance(call['command'], str) or not call['command']:
                raise ValueError('invocation command must be nonempty')
            if input_field == 'input' and not isinstance(call['input'], dict):
                raise ValueError('invocation input must be an object')
        elif operation == 'reprogram':
            exact(call, ['op', 'object', 'inputFrom'] if 'inputFrom' in call else
                  ['op', 'object', 'protocol', 'state'], 'reprogram call')
            if 'inputFrom' not in call and (not isinstance(call['protocol'], dict) or not isinstance(call['state'], dict)):
                raise ValueError('reprogram protocol and state must be objects')
        else:
            raise ValueError('transaction calls allow only invoke or reprogram')
        if 'inputFrom' in call and (type(call['inputFrom']) is not int or call['inputFrom'] < 0):
            raise ValueError('inputFrom must be a natural index')
    return payload


def resolve(payload, clerk, config):
    validate(payload)
    targets = set(payload['reads']) | {call['object'] for call in payload['calls']}
    objects = set(config['objects'])
    # A null preimage allows a potential child to participate in this transaction.
    # It does not expose arbitrary existing objects or register custody in advance.
    absent = {object_id for object_id, descriptor in payload['reads'].items()
              if 'expected' in descriptor and descriptor['expected'] is None
              and exposed_absence(object_id, objects)}
    if not targets <= objects | absent:
        raise ValueError('transaction object is not configured for remote requests')
    reads, evidence = {}, {}
    for object_id, descriptor in payload['reads'].items():
        if 'expected' in descriptor:
            reads[object_id] = descriptor['expected']
        else:
            reads[object_id], evidence[object_id] = clerk.resolve_root(descriptor['expectedRootRef'], object_id)
    # Read-set completeness, earlier-result indices, policy and transitions belong
    # to Lean. Here targets are only constrained to the operator's exposed objects.
    return {'op': 'transaction', 'reads': reads, 'calls': payload['calls']}, evidence
