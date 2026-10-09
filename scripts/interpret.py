#!/usr/bin/env python3
"""Propose an offered action from copied tokens or optional natural-language help.

This module cannot admit, execute, publish or select a principal. Source owns
prompt and interpretation policy. Native admission checks every eventual effect.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('interpret_affordances', ROOT / 'scripts/affordances.py')
affordances = importlib.util.module_from_spec(spec)
spec.loader.exec_module(affordances)
MAX_TEXT = 4096
MAX_CARD = 32768
MAX_REPLY = 16384
TOKEN = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON member')
            result[key] = value
        return result
    def invalid(_value):
        raise ValueError('nonfinite JSON number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def encoded(value, maximum):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > maximum:
        raise ValueError('input exceeds size limit')
    return raw


def string(value, maximum, *, token=False, nonempty=False):
    if not isinstance(value, str) or len(value.encode('utf-8')) > maximum or (nonempty and not value):
        raise ValueError('invalid text')
    if token and not TOKEN.fullmatch(value):
        raise ValueError('invalid copy token')


def validate_card(card):
    encoded(card, MAX_CARD)
    required = {'card', 'object', 'title', 'prose', 'actions'}
    if (not isinstance(card, dict) or not required <= set(card)
            or set(card) - required - {'objectRef'}):
        raise ValueError('card must contain only public presentation fields')
    if 'objectRef' in card:
        from references import validate_reference
        if validate_reference(card['objectRef'])['object'] != card['object']:
            raise ValueError('Object reference does not identify this card')
    string(card['card'], 128, token=True)
    string(card['object'], 512, nonempty=True)
    string(card['title'], 1024)
    string(card['prose'], 16384)
    if not isinstance(card['actions'], list) or len(card['actions']) > affordances.MAX_ACTIONS:
        raise ValueError('invalid action list')
    seen = set()
    for action in card['actions']:
        if (not isinstance(action, dict) or set(action) - {'id', 'label', 'available', 'inspectOnly', 'fields', 'children'}
                or not {'id', 'label', 'available', 'fields'} <= set(action)):
            raise ValueError('invalid action schema')
        string(action['id'], 128, token=True)
        string(action['label'], 1024)
        if action['id'] in seen or type(action['available']) is not bool or type(action.get('inspectOnly', False)) is not bool:
            raise ValueError('ambiguous action or availability')
        seen.add(action['id'])
        affordances.validate_fields_schema(action['fields'])
        affordances.validate_children_schema(action.get('children', []), action['fields'])
    return copy.deepcopy(card)


def outcome(status, message, via):
    return {'status': status, 'message': message, 'via': via}


def modules():
    import source_object
    return source_object.read_modules([
        ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('Document', ROOT / 'world/lib/document/Document.obend'),
        ('Interpretation', ROOT / 'protocols/interpretation/Interpretation.obend')])


def native(entry, arguments=(), *, modules=None):
    import source_object
    import time
    modules = modules or globals()['modules']()
    key = (entry, json.dumps(modules, sort_keys=True))
    artifact = _ARTIFACTS.get(key)
    if artifact is None:
        artifact = source_object.adapter._native({'op': 'compile', 'modules': modules,
            'entry': entry, 'limits': source_object.adapter.LIMITS}, time.monotonic() + 30)['artifact']
        if len(_ARTIFACTS) >= 32:
            _ARTIFACTS.pop(next(iter(_ARTIFACTS)))
        _ARTIFACTS[key] = artifact
    return source_object.adapter._native({'op': 'run-data-v1', 'artifact': artifact,
        'arguments': list(arguments), 'limits': source_object.adapter.LIMITS}, time.monotonic() + 30)['value']


_ARTIFACTS = {}


def unpack(wire):
    import source_object
    result = source_object.plain(wire)
    result['fields'] = source_object.values('decode', [next(f['value'] for f in wire['fields'] if f['name'] == 'fields')])[0]
    names = result.pop('unresolved')
    unresolved = []
    while names['variant'] == 'cons':
        unresolved.append(names['payload']['head'])
        names = names['payload']['tail']
    if result['status'] == 'partial':
        result['unresolved'] = unresolved
    if not result['action']:
        result.pop('action')
        result.pop('fields')
    return result


def token_input(text):
    import source_object
    return source_object.plain(native('route', [source_object.data(text)]))['literal']


def interpret(text, card, *, proposer=None):
    """Transport input to the source interpreter; return its untrusted proposal."""
    import source_object
    try:
        string(text, MAX_TEXT, nonempty=True)
        if not text.strip():
            raise ValueError('empty request')
        captured = validate_card(card)
        card_wire = source_object.value(captured)
        route_wire = native('route', [source_object.data(text)])
        route = source_object.plain(route_wire)
        if route['literal']:
            try:
                fields = loads(route['fields'])
            except (ValueError, TypeError, RecursionError):
                fields = None
            return unpack(native('literal', [card_wire, route_wire, source_object.value(fields)]))
        if proposer is None:
            return unpack(native('unavailable'))
        answer = proposer(text, copy.deepcopy(captured))
        encoded(answer, MAX_REPLY)
        result = unpack(native('propose', [card_wire, source_object.value(answer), source_object.data('model')]))
        receipt = getattr(proposer, 'last_receipt', None)
        if isinstance(receipt, dict):
            result['provenance'] = {'original': text, 'policyRevision': receipt['job']['revision'],
                'context': [{'object': captured['object'], 'card': captured['card']}],
                'request': receipt['key'], 'source': receipt['job']['source']}
        return result
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        return outcome('clarify', 'Provide a bounded public capture and valid contribution.', 'none')
    except Exception:
        return unpack(native('failed'))


class AnthropicProposer:
    """Explicit source-produced activity; repeat jobs recover the retained receipt."""
    def __init__(self, api_key, *, directory, identity_scope='local', policy=None, generation='0', provider=None, max_jobs=32, max_bytes=4 * 1024 * 1024):
        import model_service
        self.service = model_service.Service(directory, provider or model_service.AnthropicMessages(api_key),
            max_jobs=max_jobs, max_bytes=max_bytes)
        self.identity_scope = identity_scope
        self.policy = policy
        self.generation = generation
        import threading
        self._receipt_local = threading.local()

    @property
    def last_receipt(self):
        return getattr(self._receipt_local, "receipt", None)

    @last_receipt.setter
    def last_receipt(self, value):
        self._receipt_local.receipt = value

    def __call__(self, text, card):
        import source_object
        retained_modules = modules()
        policy = self.policy or native('defaultPolicy', modules=retained_modules)
        quoted = encoded({'userRequest': text, 'untrustedCard': card}, MAX_CARD + MAX_TEXT + 1024).decode()
        job = source_object.plain(native('prompt', [policy, source_object.data(quoted)], modules=retained_modules))
        return self.request_source(job, source_modules=retained_modules, policy=source_object.plain(policy))

    def request_source(self, job, *, source_modules, envelope=None, policy=None):
        """Dispatch one already source-produced prompt, retaining exact inputs."""
        import hashlib
        self.last_receipt = None
        body = {'model': job['model'], 'max_tokens': job['maxTokens'], 'stream': False,
            'system': job['system'], 'messages': [{'role': 'user', 'content': job['content']}]}
        receipt = self.service.request({'revision': job['revision'], 'generation': self.generation,
            'identityScope': self.identity_scope,
            'source': hashlib.sha256(encoded(source_modules, 512 * 1024)).hexdigest(),
            'modules': source_modules, 'policy': policy, 'envelope': envelope,
            'document': job['document'], 'body': body})
        self.last_receipt = receipt
        if receipt['status'] != 'received':
            raise RuntimeError('retained provider activity is pending or uncertain')
        message = receipt['reply']
        content = message.get('content')
        if (message.get('stop_reason') != 'end_turn' or not isinstance(content, list) or len(content) != 1
                or not isinstance(content[0], dict) or content[0].get('type') != 'text'):
            raise ValueError('provider did not return one complete text result')
        return loads(content[0]['text'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card', type=Path, help='public root-free card JSON')
    parser.add_argument('text', help='copied do CARD ACTION token or natural-language request')
    parser.add_argument('--custody', type=Path, help='explicit private directory for bounded model job custody')
    parser.add_argument('--anthropic', action='store_true', help='opt into one Haiku request using ANTHROPIC_API_KEY')
    args = parser.parse_args()
    try:
        with args.card.open('rb') as stream:
            raw = stream.read(MAX_CARD + 1)
        if len(raw) > MAX_CARD:
            raise ValueError('card too large')
        card = loads(raw)
        proposer = None
        if args.anthropic and not token_input(args.text):
            if args.custody is None:
                raise ValueError('--anthropic requires explicit --custody')
            proposer = AnthropicProposer(os.environ.get('ANTHROPIC_API_KEY'), directory=args.custody)
        result = interpret(args.text, card, proposer=proposer)
    except (ValueError, TypeError, OSError, RecursionError):
        result = outcome('clarify', 'Provide a valid public card; optional language help requires an explicitly configured API key.', 'none')
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return {'proposed': 0, 'partial': 2, 'clarify': 2, 'escalate': 3}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
