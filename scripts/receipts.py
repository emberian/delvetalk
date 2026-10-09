#!/usr/bin/env python3
"""Explicit publication of selected public requests, clerk receipts and roots.

The caller selects the exact file to disclose. No state directory is scanned.
This adapter transports records; Lean/clerk results remain the admission evidence.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from delve import Delve, Failure, XRPCError, DID, locked, save
import transaction_intake

REQUEST = 'org.delvetalk.request'
RECEIPT = 'org.delvetalk.receipt'
ROOT = 'org.delvetalk.root'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def exact_object(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise Failure('Expected exactly these fields: ' + ', '.join(fields))


def loads(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Failure('Duplicate JSON member: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise Failure('Non-JSON number: ' + value)
    return json.loads(text, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=pairs)


def encode(kind, text):
    """Keep exact selected UTF-8 JSON in a string: DAG-CBOR has no decimals."""
    text.encode('utf-8')
    value = loads(text)
    if kind == 'request':
        expected_key = 'expectedRootRef' if isinstance(value, dict) and 'expectedRootRef' in value else 'expected'
        operation = value.get('op', 'invoke') if isinstance(value, dict) else None
        if operation == 'transaction':
            try:
                transaction_intake.validate(value)
            except ValueError as error:
                raise Failure(str(error)) from error
            return {'$type': REQUEST, 'profile': 'delvetalk-live-v1', 'requestJson': text}
        if operation == 'invoke':
            fields = ['object', 'command', 'input', expected_key]
            if 'op' in value:
                fields.append('op')
            if 'absent' in value:
                fields.append('absent')
            exact_object(value, fields)
            if not isinstance(value['command'], str) or not value['command'] or not isinstance(value['input'], dict):
                raise Failure('Request needs a nonempty command string and input object')
            if 'absent' in value:
                try:
                    transaction_intake.validate_absent(value['absent'])
                except ValueError as error:
                    raise Failure(str(error)) from error
        elif operation == 'reprogram':
            exact_object(value, ('op', 'object', 'protocol', 'state', expected_key))
            if not isinstance(value['protocol'], dict) or not isinstance(value['state'], dict):
                raise Failure('Reprogram protocol and state must be objects')
        else:
            raise Failure('Unsupported remote operation; only invoke and reprogram are allowed')
        if not isinstance(value['object'], str) or not value['object'] or not isinstance(value[expected_key], dict):
            raise Failure('Request needs a nonempty object string and expected root object')
        if expected_key == 'expectedRootRef':
            reference = value[expected_key]
            exact_object(reference, ('uri', 'cid'))
            prefix = 'at://' + DID + '/' + ROOT + '/'
            uri, cid = reference['uri'], reference['cid']
            if not isinstance(uri, str) or not uri.startswith(prefix):
                raise Failure('Root reference must name the fixed custodian org.delvetalk.root collection')
            key = uri[len(prefix):]
            if not re.fullmatch(r'[A-Za-z0-9._~:-]{1,512}', key) or key in ('.', '..'):
                raise Failure('Root reference has an invalid record key')
            if not isinstance(cid, str) or not cid or len(cid) > 200:
                raise Failure('Root reference requires a nonempty CID of at most 200 characters')
        return {'$type': REQUEST, 'profile': 'delvetalk-live-v1', 'requestJson': text}
    if kind == 'receipt':
        if not isinstance(value, dict) or value.get('format') != 'delvetalk-clerk-receipt-v1':
            raise Failure('Expected a delvetalk-clerk-receipt-v1 envelope')
        source = value['source']
        request = value['request']
        if not all(isinstance(source[k], str) and source[k] for k in ('uri', 'cid', 'author')):
            raise Failure('Receipt source identity fields must be nonempty strings')
        if request.get('op') == 'transaction':
            reads = request.get('reads')
            if not isinstance(reads, dict) or not reads or not all(isinstance(key, str) and key for key in reads):
                raise Failure('Transaction receipt requires read object identities')
            discovery = {'objects': sorted(reads)}
        else:
            if not isinstance(request.get('object'), str) or not request['object']:
                raise Failure('Receipt object must be a nonempty string')
            discovery = {'object': request['object']}
        if request['principal'] != source['author']:
            raise Failure('Receipt principal does not match source author')
        if not isinstance(value.get('reply'), dict) or not isinstance(value.get('profile'), dict):
            raise Failure('Receipt requires reply and profile pins')
        return {'$type': RECEIPT, 'profile': 'delvetalk-live-v1',
                'requestRef': {'uri': source['uri'], 'cid': source['cid']},
                'author': source['author'], **discovery,
                'receiptJson': text, 'sha256': digest(text)}
    if kind == 'root':
        if not isinstance(value, dict) or value.get('format') != 'delvetalk-clerk-root-v1':
            raise Failure('Expected a delvetalk-clerk-root-v1 envelope')
        version = value['root']['version']
        if type(version) is not int or version < 0 or not isinstance(value.get('profile'), dict):
            raise Failure('Root requires natural version and profile pins')
        if not isinstance(value.get('object'), str) or not value['object']:
            raise Failure('Root requires a nonempty object identity')
        return {'$type': ROOT, 'profile': 'delvetalk-live-v1', 'object': value['object'],
                'version': str(version), 'rootJson': text, 'sha256': digest(text)}
    raise Failure('Unknown publication kind')


class Publisher:
    def __init__(self, client):
        self.client = client

    def publish(self, kind, text, intent, expected_cid=None):
        record = encode(kind, text)
        c = self.client
        collection = record['$type']
        key = c.key('root-object', record['object']) if kind == 'root' else c.key(kind, intent)
        # Each attempt has its own durable identity, including mutable root updates.
        path = c.state / ('publication-' + c.key(kind, intent) + '.json')
        desired = {'intent': intent, 'collection': collection, 'rkey': key,
                   'record': record, 'swapRecord': expected_cid}
        if kind != 'root' and expected_cid is not None:
            raise Failure('Immutable request/receipt records are create-only')
        with locked(c.state / '.publication.lock'):
            if path.exists():
                prepared = json.loads(path.read_text())
                if prepared['desired'] != desired:
                    raise Failure('Publication intent was prepared with different content or preimage')
            else:
                prepared = {'desired': desired}
                save(path, prepared)
            found = c.get(collection, key)
            if found and found['value'] == record:
                return self.confirm(path, prepared, found, 'reconciled')
            if prepared.get('confirmed'):
                # Root pointers can legitimately advance. Never replay an old write.
                if kind == 'root' and found and self.version(found['value']) > self.version(record):
                    return {'status': 'superseded', **prepared['confirmed'],
                            'current': {'uri': found['uri'], 'cid': found['cid']}}
                raise Failure('Confirmed publication is missing or changed; refusing resurrection')
            if kind != 'root' and found:
                raise Failure('Immutable intent key contains different content')
            if kind == 'root' and found:
                if found['value'] != encode('root', found['value'].get('rootJson', 'null')):
                    raise Failure('Existing root metadata disagrees with its snapshot')
                if found['value']['object'] != record['object']:
                    raise Failure('Root key is occupied by a different object')
                if self.version(found['value']) >= self.version(record):
                    raise Failure('Root version must increase; refusing stale or forked snapshot')
            actual_cid = found['cid'] if found else None
            if actual_cid != expected_cid:
                raise Failure('Publication preimage changed; refetch and use a new intent')
            body = {'repo': DID, 'collection': collection, 'rkey': key,
                    'record': record, 'swapRecord': expected_cid}
            # The exact body is fsynced before every attempted network mutation.
            prepared['request'] = body
            save(path, prepared)
            try:
                c.rpc('POST', 'putRecord', body=body)
            except XRPCError as error:
                if error.data.get('error') != 'InvalidSwap':
                    raise
                found = c.get(collection, key)
                if found and found['value'] == record:
                    return self.confirm(path, prepared, found, 'reconciled')
                raise Failure('Publication CAS lost; no replacement or automatic rebase') from None
            # Confirm against receiving storage, not merely a successful write reply.
            found = c.get(collection, key)
            if not found or found['value'] != record:
                raise Failure('Write reply received but readback differs; rerun same intent to reconcile')
            return self.confirm(path, prepared, found, 'created' if expected_cid is None else 'updated')

    @staticmethod
    def version(record):
        value = record.get('version')
        if record.get('$type') != ROOT or not isinstance(value, str) or not value.isascii() or not value.isdigit():
            raise Failure('Existing root record has malformed version')
        return int(value)

    @staticmethod
    def confirm(path, prepared, found, status):
        result = {'uri': found['uri'], 'cid': found['cid']}
        prepared['confirmed'] = result
        save(path, prepared)
        return {'status': status, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('request', 'receipt', 'root'))
    parser.add_argument('file', type=Path, help='exact public-derived JSON selected for disclosure')
    parser.add_argument('--intent', required=True, help='stable operation identity; reuse after uncertain outcome')
    parser.add_argument('--state', type=Path, default=Path('~/claude_state/delvetalk/publications').expanduser())
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--expected-cid', help='current root pointer CID; omit only to create an absent record')
    args = parser.parse_args()
    try:
        text = args.file.read_bytes().decode('utf-8')
        print(json.dumps(Publisher(Delve(args.state, credentials=args.credentials)).publish(
            args.kind, text, args.intent, args.expected_cid), ensure_ascii=False))
    except (Failure, ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
