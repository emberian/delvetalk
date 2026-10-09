#!/usr/bin/env python3
"""Explicit single-operator Delve request receiver; Lean owns admission."""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

world = module('clerk_world', 'scripts/world.py')
delve = module('clerk_delve', 'scripts/delve.py')
transaction_intake = module('clerk_transaction_intake', 'scripts/transaction_intake.py')
manual_intake = module('clerk_manual_intake', 'scripts/manual_intake.py')
runtime_profiles = module('clerk_runtime_profiles', 'scripts/runtime_profile.py')
PDS = 'https://pds.delve.town'
COLLECTION = 'org.delvetalk.request'
FEED = 'town.delve.feed.post'
ROOT_COLLECTION = 'org.delvetalk.root'
PROFILE = 'delvetalk-pds-clerk-v1'
TRANSPORT_PIN_PATHS = ['scripts/worker.py', 'scripts/process_custody.py', 'scripts/manual_intake.py', 'scripts/delve.py', 'scripts/clerk.py', 'scripts/transaction_intake.py',
                       'scripts/town_cards.py', 'scripts/source_offers.py', 'scripts/composite_offers.py', 'scripts/adoption.py', 'scripts/translate.py', 'scripts/affordances.py', 'scripts/references.py',
                       'scene/room.py', 'scene/lower.py', 'scene/projection.py']
UNCHANGED = object()
RUNTIME_CHOICES = tuple(world.PROFILES)
DID = re.compile(r'did:plc:[a-z2-7]{24}\Z')
RKEY = re.compile(r'[A-Za-z0-9._~:-]{1,512}\Z')


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON member: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('non-JSON number: ' + value)
    return json.loads(raw, parse_float=Decimal, parse_constant=invalid, object_pairs_hook=pairs)


def exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(label + ' has missing or unknown fields')


def canonical(value):
    if isinstance(value, dict):
        value = {key: canonical_value(value[key]) for key in sorted(value)}
    return world.wire_dumps(value).encode('utf-8')


def canonical_value(value):
    if isinstance(value, dict):
        return {key: canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonical_value(item) for item in value]
    return value


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def pins(runtime_profile='world'):
    if runtime_profile not in RUNTIME_CHOICES:
        raise ValueError('unsupported clerk runtime profile')
    profiles = ('world', 'transactions') if runtime_profile == 'world' else (runtime_profile,)
    result = {}
    for profile in profiles:
        result.update(runtime_profiles.file_hashes(profile))
    result.update({path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in TRANSPORT_PIN_PATHS})
    return result


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(canonical(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary:
            os.unlink(temporary)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('PDS redirects are forbidden')


class PublicHTTP(delve.HTTP):
    """Pinned public GET-only XRPC transport, bounded and lossless."""
    def __call__(self, method, base, nsid, *, params=None, **kwargs):
        if method != 'GET' or base != PDS or nsid not in (
                'com.atproto.repo.describeRepo', 'com.atproto.repo.getRecord') or kwargs:
            raise ValueError('receiver transport permits only pinned public repository reads')
        url = base + '/xrpc/' + nsid + '?' + delve.urllib.parse.urlencode(params or {})
        request = urllib.request.Request(url, headers={'User-Agent': 'DelveTalk/0.1 clerk'})
        with urllib.request.build_opener(NoRedirect).open(request, timeout=25) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('PDS response exceeds 1 MiB')
        return loads(raw.decode('utf-8'))


def parse_uri(uri, collections=(COLLECTION, FEED)):
    if not isinstance(uri, str):
        raise ValueError('record URI must be a string')
    parts = uri.split('/')
    if (len(parts) != 5 or parts[:2] != ['at:', ''] or not DID.fullmatch(parts[2])
            or parts[3] not in collections or not RKEY.fullmatch(parts[4]) or parts[4] in ('.', '..')):
        raise ValueError('expected an at://did:plc:.../supported-collection/rkey URI')
    return parts[2], parts[3], parts[4]


def feed_request(record):
    if not isinstance(record, dict) or record.get('$type') != FEED:
        raise ValueError('unsupported feed record')
    text = record.get('text')
    if not isinstance(text, str) or len(text.encode('utf-8')) > 64 * 1024:
        raise ValueError('feed request text must be at most 64 KiB')
    match = re.fullmatch(r'delvetalk-request v1\n[ \t\n]*```delvetalk-request\n(.*?)\n```([^`]*)', text, re.S)
    if not match or '```' in match.group(1):
        raise ValueError('feed request needs exact marker and one delvetalk-request fence')
    return match.group(1)


class Clerk:
    def __init__(self, state, request=None):
        self.state = Path(state).expanduser().resolve()
        self.http = request or PublicHTTP()

    @property
    def database(self):
        path = self.state / 'clerk.json'
        binding = loads(path.read_bytes()).get('database') if path.exists() else None
        if binding is None:
            return (self.state / 'world.json').resolve()
        if (not isinstance(binding, str) or not Path(binding).is_absolute()
                or str(Path(binding).resolve()) != binding):
            raise ValueError('clerk database binding must remain an exact canonical path')
        return Path(binding)

    def config(self):
        result = loads((self.state / 'clerk.json').read_text())
        if (result['profile']['name'] != PROFILE or result['pds'] != PDS
                or result.get('runtimeProfile', 'world') not in RUNTIME_CHOICES):
            raise ValueError('unsupported clerk profile')
        return result

    def execution_profile(self, request, config=None):
        config = self.config() if config is None else config
        if config.get('runtimeProfile', 'world') != 'world':
            return config['runtimeProfile']
        return 'transactions' if request['op'] == 'transaction' else 'world'

    def bootstrap(self, object_id, protocol, law, repositories, runtime_profile='world'):
        if not isinstance(object_id, str) or not object_id:
            raise ValueError('object ID must be nonempty')
        if not repositories or any(not isinstance(repo, str) or not DID.fullmatch(repo) for repo in repositories):
            raise ValueError('repositories must be an explicit nonempty did:plc allowlist')
        config = {'format': PROFILE, 'pds': PDS, 'repositories': sorted(set(repositories)),
                  'objects': [object_id], 'profile': {'name': PROFILE, 'pins': pins(runtime_profile)},
                  'bootstrap': {'op': 'create', 'principal': 'local-clerk-operator',
                                'intent': 'bootstrap:' + object_id, 'object': object_id,
                                'protocol': protocol, 'law': law}}
        if runtime_profile != 'world':
            config['runtimeProfile'] = runtime_profile
        with delve.locked(self.state / 'clerk.lock'):
            path = self.state / 'clerk.json'
            if path.exists():
                if canonical(loads(path.read_text())) != canonical(config):
                    raise ValueError('clerk already configured differently')
            else:
                # Retain bootstrap preimage before admission so interruption is replayable.
                save(path, config)
            return world.exchange(self.database, config['bootstrap'], profile=self.execution_profile(config['bootstrap'], config))

    def attach(self, workspace, expected_roots, repositories, *, expected_genesis,
               expected_seed_head, runtime_profile):
        """Enroll an existing workspace after exact anchors and Lean reconstruction."""
        directory = Path(workspace).expanduser().resolve()
        database = (directory / 'world.json').resolve()
        if runtime_profile not in world.PROFILES:
            raise ValueError('unknown attachment runtime profile')
        if (not isinstance(expected_roots, dict) or not expected_roots
                or any(not isinstance(key, str) or not key or not isinstance(root, dict)
                       for key, root in expected_roots.items())):
            raise ValueError('expected roots must explicitly map object IDs to full roots')
        if not repositories or any(not isinstance(repo, str) or not DID.fullmatch(repo) for repo in repositories):
            raise ValueError('repositories must be an explicit nonempty did:plc allowlist')
        for anchor in (expected_genesis, expected_seed_head):
            if not isinstance(anchor, str) or not re.fullmatch('[0-9a-f]{64}', anchor):
                raise ValueError('attachment requires exact genesis and seed head SHA256 anchors')
        selection = {'workspace': str(directory), 'database': str(database), 'roots': expected_roots,
                     'repositories': sorted(set(repositories)), 'runtimeProfile': runtime_profile,
                     'genesis': expected_genesis, 'seedHead': expected_seed_head}
        with delve.locked(self.state / 'clerk.lock'):
            path = self.state / 'clerk.json'
            if path.exists():
                configured = self.config()
                if canonical(configured.get('attachment', {}).get('selection')) != canonical(selection):
                    raise ValueError('clerk already configured with a different attachment or bootstrap')
                if self.database != database:
                    raise ValueError('clerk database differs from retained attachment')
                return {'status': 'already-attached', 'attachment': configured['attachment']}
            local = self.state / 'world.json'
            if (local.exists() or local.is_symlink()) and local.resolve() != database:
                raise ValueError('clerk state already contains a different world')
            if any((self.state / 'requests').glob('*.json')):
                raise ValueError('existing request journals cannot be rebound to another world')
            # Capture one atomic backend snapshot; replay uses independent custody.
            # A resident daemon owns its writer lock throughout its lifetime.
            snapshot = world.snapshot(database)
            bootstrap = module('clerk_attach_bootstrap', 'scripts/bootstrap.py')
            history = bootstrap.history
            metadata = loads((directory / 'manifest.json').read_bytes())
            seed = loads((directory / 'seed.json').read_bytes())
            seed_manifest = loads((directory / 'seed-history/manifest.json').read_bytes())
            runtime = history.runtime(runtime_profile)
            if (metadata.get('format') != 'delvetalk-workspace-v1'
                    or canonical(metadata.get('runtime')) != canonical(runtime)
                    or canonical(metadata.get('genesis')) != canonical(seed_manifest.get('genesis'))
                    or metadata['genesis'].get('id') != expected_genesis
                    or seed.get('format') != 'delvetalk-workspace-seed-v1'
                    or seed.get('genesis') != expected_genesis or seed.get('head') != expected_seed_head
                    or seed.get('worldId') != bootstrap.world_id(metadata)
                    or seed.get('entryObjects') != bootstrap.entry_objects(metadata)
                    or seed.get('defaultObject') != bootstrap.default_object(metadata)):
                raise ValueError('workspace manifest, runtime or seed anchors mismatch')
            exact(snapshot, ['objects', 'receipts'] + (['messages'] if 'messages' in snapshot else []), 'workspace world')
            prefix = [{'request': entry['request'], 'receipt': entry['reply']}
                      for entry in seed_manifest['entries']]
            if (not isinstance(snapshot['receipts'], list)
                    or canonical({'receipts': snapshot['receipts'][:len(prefix)]}) != canonical({'receipts': prefix})):
                raise ValueError('workspace world does not extend its exact seed prefix')
            bootstrap.validate_workspace_identity(metadata, snapshot['receipts'])
            selected_runtime = runtime_profile
            profile = {'name': PROFILE, 'pins': pins(selected_runtime)}
            with tempfile.TemporaryDirectory(prefix='clerk-attach-') as temporary:
                replay = Path(temporary) / 'world.json'
                evidence = history.verify_history(directory / 'seed-history', expected_genesis=expected_genesis,
                                                  expected_head=expected_seed_head, output=replay)
                if any(seed.get(key) != evidence[key] for key in ('entries', 'worldSha256')):
                    raise ValueError('workspace seed evidence mismatch')
                for retained in snapshot['receipts'][len(prefix):]:
                    exact(retained, ['request', 'receipt'], 'retained admission')
                    reply = world.exchange(replay, retained['request'], profile=runtime_profile)
                    if canonical(reply) != canonical(retained['receipt']):
                        raise ValueError('workspace retained receipt does not replay under selected runtime')
                if canonical(world.snapshot(replay)) != canonical(snapshot):
                    raise ValueError('workspace world cannot be reconstructed from retained admissions')
            for object_id, expected in expected_roots.items():
                if canonical(snapshot['objects'].get(object_id)) != canonical(expected):
                    raise ValueError('attachment expected root mismatch: ' + object_id)
            if (canonical(history.runtime(runtime_profile)) != canonical(runtime)
                    or pins(selected_runtime) != profile['pins']):
                raise ValueError('attachment implementation changed during verification')
            attachment = {'selection': selection, 'worldSha256': digest(snapshot),
                          'worldId': metadata['worldId'], 'entries': len(snapshot['receipts'])}
            attachment['id'] = digest(attachment)
            config = {'format': PROFILE, 'pds': PDS, 'repositories': selection['repositories'],
                      'objects': sorted(expected_roots), 'profile': profile, 'database': str(database),
                      'attachment': attachment}
            if selected_runtime != 'world':
                config['runtimeProfile'] = selected_runtime
            save(path, config)
            return {'status': 'attached', 'attachment': attachment}

    def verify_repository(self, author):
        description = self.http('GET', PDS, 'com.atproto.repo.describeRepo', params={'repo': author})
        if not isinstance(description, dict) or not isinstance(description.get('didDoc'), dict):
            raise ValueError('malformed repository description')
        document = description['didDoc']
        if description.get('did') != author or document.get('id') != author:
            raise ValueError('repository description identity mismatch')
        services = document.get('service', [])
        if not isinstance(services, list) or not any(
                isinstance(service, dict) and service.get('id') in ('#atproto_pds', author + '#atproto_pds')
                and service.get('type') == 'AtprotoPersonalDataServer'
                and service.get('serviceEndpoint') == PDS for service in services):
            raise ValueError('DID service does not name the pinned Delve PDS')

    def fetch_record(self, uri, cid, collections):
        author, collection, key = parse_uri(uri, collections)
        if not isinstance(cid, str) or not cid or len(cid) > 200:
            raise ValueError('expected source CID is required')
        record = self.http('GET', PDS, 'com.atproto.repo.getRecord',
                           params={'repo': author, 'collection': collection, 'rkey': key, 'cid': cid})
        if not isinstance(record, dict) or record.get('uri') != uri or record.get('cid') != cid:
            raise ValueError('record URI or CID mismatch')
        return record.get('value')

    def resolve_root(self, reference, object_id):
        exact(reference, ['uri', 'cid'], 'expectedRootRef')
        author, _, _ = parse_uri(reference['uri'], (ROOT_COLLECTION,))
        if author != delve.DID:
            raise ValueError('root reference must belong to configured custodian DID')
        self.verify_repository(author)
        record = self.fetch_record(reference['uri'], reference['cid'], (ROOT_COLLECTION,))
        exact(record, ['$type', 'profile', 'object', 'version', 'rootJson', 'sha256'], 'root record')
        if record['$type'] != ROOT_COLLECTION or record['profile'] != 'delvetalk-live-v1':
            raise ValueError('unsupported root record profile')
        raw = record['rootJson']
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > 512 * 1024:
            raise ValueError('rootJson must be a string of at most 512 KiB')
        if hashlib.sha256(raw.encode('utf-8')).hexdigest() != record['sha256']:
            raise ValueError('rootJson SHA256 mismatch')
        envelope = loads(raw)
        exact(envelope, ['format', 'object', 'root', 'profile', 'id'], 'root envelope')
        if envelope['format'] != 'delvetalk-clerk-root-v1' or envelope['object'] != object_id or record['object'] != object_id:
            raise ValueError('root envelope object or format mismatch')
        if envelope['id'] != digest({key: value for key, value in envelope.items() if key != 'id'}):
            raise ValueError('root envelope ID mismatch')
        profile = envelope['profile']
        if (not isinstance(profile, dict) or profile.get('name') != PROFILE
                or not isinstance(profile.get('pins'), dict) or not profile['pins']
                or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
                       for value in profile['pins'].values())):
            raise ValueError('unsupported root envelope profile')
        root = envelope['root']
        if (not isinstance(root, dict) or type(root.get('version')) is not int or root['version'] < 0
                or record['version'] != str(root['version'])):
            raise ValueError('root version mismatch')
        return root, {'source': {'uri': reference['uri'], 'cid': reference['cid'],
                                 'author': author, 'pds': PDS}, 'record': record}

    def card_configuration(self, selection, runtime_profile):
        """Explicit local display custody; no additional admission authority."""
        exact(selection, ['path', 'issuers', 'metadata'], 'town cardbook selection')
        path, issuers = selection['path'], selection['issuers']
        if (not isinstance(path, str) or not Path(path).is_absolute()
                or str(Path(path).resolve()) != path):
            raise ValueError('town cardbook must retain its exact canonical path')
        if (not isinstance(issuers, list) or not issuers
                or any(not isinstance(did, str) or not DID.fullmatch(did) for did in issuers)
                or issuers != sorted(set(issuers))):
            raise ValueError('town card issuers require an explicit sorted DID allowlist')
        cards = module('clerk_town_cards', 'scripts/town_cards.py')
        metadata = cards.CardBook(path).metadata()
        if canonical(metadata) != canonical(selection['metadata']) or metadata['issuerDid'] not in issuers:
            raise ValueError('town cardbook identity or issuer mismatch')
        expected_runtime = {'name': runtime_profile,
                            'platform': {'system': platform.system(), 'machine': platform.machine()},
                            'files': runtime_profiles.file_hashes(runtime_profile)}
        if canonical(metadata['runtime']) != canonical(expected_runtime):
            raise ValueError('town cardbook runtime does not match selected clerk runtime')
        config = self.config()
        if 'attachment' in config and metadata['worldId'] != config['attachment']['worldId']:
            raise ValueError('town cardbook belongs to a different attached workspace')
        return selection

    def resolve_card(self, record, author, source, config):
        selection = config.get('townCards')
        if selection is None:
            raise ValueError('short town replies require explicit cardbook configuration')
        if config['profile'].get('townCards') != digest(selection):
            raise ValueError('town cardbook configuration differs from its pinned profile')
        self.card_configuration(selection, config.get('runtimeProfile', 'world'))
        cards = module('clerk_town_cards', 'scripts/town_cards.py')
        def fetch_publication(uri, cid):
            issuer, _, _ = parse_uri(uri, (FEED,))
            if issuer not in selection['issuers']:
                raise ValueError('card publication issuer is not configured')
            self.verify_repository(issuer)
            return self.fetch_record(uri, cid, (FEED,))
        return cards.CardBook(selection['path']).resolve(record, author, source,
                                                       fetch_publication, selection['issuers'])

    def observe(self, uri, cid, config):
        author, collection, _ = parse_uri(uri)
        if author not in config['repositories']:
            raise ValueError('repository is not configured for this clerk')
        self.verify_repository(author)
        value = self.fetch_record(uri, cid, (COLLECTION, FEED))
        inline_card = None
        if collection == FEED and isinstance(value, dict) and isinstance(value.get('text'), str) and value['text'].strip().startswith('delvetalk '):
            payload, inline_card = self.resolve_card(value, author, {'uri': uri, 'cid': cid,
                                                                   'author': author, 'pds': PDS}, config)
            raw = world.wire_dumps(payload)
        elif collection == FEED:
            raw = feed_request(value)
        else:
            exact(value, ['$type', 'profile', 'requestJson'], 'request record')
            if value['$type'] != COLLECTION or value['profile'] != 'delvetalk-live-v1':
                raise ValueError('unsupported request record profile')
            raw = value['requestJson']
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > 64 * 1024:
            raise ValueError('requestJson must be a string of at most 64 KiB')
        payload = loads(raw)
        entry = self.normalize_payload(payload, author, uri, cid, value, config)
        if inline_card is not None:
            entry['inlineCard'] = inline_card
        return entry

    def normalize_payload(self, payload, author, uri, cid, value, config):
        expected_key = 'expectedRootRef' if isinstance(payload, dict) and 'expectedRootRef' in payload else 'expected'
        operation = payload.get('op', 'invoke') if isinstance(payload, dict) else None
        resolved_transaction = None
        if operation == 'transaction':
            payload, resolved_transaction = transaction_intake.resolve(payload, self, config)
        elif operation == 'invoke':
            fields = ['object', 'command', 'input', expected_key]
            if 'op' in payload:
                fields.append('op')
            if 'absent' in payload:
                fields.append('absent')
            exact(payload, fields, 'requestJson')
            if not isinstance(payload['command'], str) or not isinstance(payload['input'], dict):
                raise ValueError('command must be a string and input an object')
            if 'absent' in payload:
                transaction_intake.resolve_absent(payload['absent'], config)
        elif operation == 'reprogram':
            exact(payload, ['op', 'object', 'protocol', 'state', expected_key], 'requestJson')
            if not isinstance(payload['protocol'], dict) or not isinstance(payload['state'], dict):
                raise ValueError('reprogram protocol and state must be objects')
        elif operation == 'law':
            exact(payload, ['op', 'object', 'law', expected_key], 'requestJson')
            if not isinstance(payload['law'], (list, dict)):
                raise ValueError('law must be an array or object')
        else:
            raise ValueError('unsupported remote operation; only invoke, reprogram, law and transaction are allowed')
        if operation != 'transaction' and (not isinstance(payload['object'], str) or payload['object'] not in config['objects']):
            raise ValueError('object is not configured for remote requests')
        resolved = None
        if operation != 'transaction' and expected_key == 'expectedRootRef':
            expected, resolved = self.resolve_root(payload['expectedRootRef'], payload['object'])
            payload = {key: value for key, value in payload.items() if key != 'expectedRootRef'}
            payload['expected'] = expected
        request = {'op': operation, 'principal': author, 'intent': 'delve:' + uri, **payload}
        # Root references and derived identity can expand a small source envelope.
        # Host transport-envelope errors have no retained terminal receipt.
        if len(canonical(request)) > 65536:
            raise ValueError('derived request exceeds 64 KiB')
        entry = {'source': {'uri': uri, 'cid': cid, 'author': author, 'pds': PDS},
                 'record': value, 'request': request, 'profile': config['profile'],
                 'admissionProfile': self.execution_profile(request, config)}
        if resolved is not None:
            entry['resolvedRoot'] = resolved
        if resolved_transaction is not None:
            entry['resolvedRoots'] = resolved_transaction
        return entry

    def finish(self, path, entry, retained=None):
        if 'receipt' not in entry:
            selected = self.execution_profile(entry['request'])
            if entry.get('admissionProfile', selected) != selected:
                raise ValueError('retained admission profile does not match request')
            reply = retained if retained is not None else world.exchange(self.database, entry['request'], profile=selected)
            receipt = {'format': 'delvetalk-clerk-receipt-v1', 'source': entry['source'],
                       'request': entry['request'], 'reply': reply, 'profile': entry['profile']}
            if 'interpretation' in entry:
                receipt['interpretation'] = entry['interpretation']
            if reply['kind'] == 'committed':
                request, data = entry['request'], reply['data']
                if request['op'] == 'transaction':
                    allocated = {object_id for object_id, expected in request['reads'].items()
                                 if expected is None and data['roots'].get(object_id) is not None}
                else:
                    allocated = set(data.get('allocated', {}))
                if allocated:
                    config = self.config()
                    config['objects'] = sorted(set(config['objects']) | allocated)
                    # Before the terminal journal receipt: replay of the same Lean
                    # receipt repairs a crash between admission and registration.
                    save(self.state / 'clerk.json', config)
            receipt['id'] = digest(receipt)
            entry['receipt'] = receipt
            save(path, entry)
        return entry['receipt']

    def receive_interpreted(self, uri, cid, decision):
        return self.receive(uri, cid, interpretation=manual_intake.validate(decision))

    def receive(self, uri, cid, *, interpretation=None):
        parse_uri(uri, (FEED,) if interpretation is not None else (COLLECTION, FEED))
        if interpretation is not None:
            interpretation = manual_intake.validate(interpretation)
            if len(canonical(interpretation)) > 70000:
                raise ValueError('interpretation exceeds custody envelope')
        with delve.locked(self.state / 'clerk.lock'):
            config = self.config()
            path = self.state / 'requests' / (hashlib.sha256(uri.encode()).hexdigest() + '.json')
            if path.exists():
                entry = loads(path.read_text())
                if entry['source']['uri'] != uri or entry['source']['cid'] != cid:
                    raise ValueError('request URI was already bound to a different CID; use a new rkey')
                if interpretation is not None:
                    retained = entry.get('interpretation', {}).get('decision')
                    if canonical(retained) != canonical(interpretation):
                        raise ValueError('request URI already bound to a different interpretation or machine request')
                if 'receipt' in entry:
                    return entry['receipt']
            else:
                if interpretation is None:
                    entry = self.observe(uri, cid, config)
                else:
                    author, _, _ = parse_uri(uri, (FEED,))
                    if author not in config['repositories']:
                        raise ValueError('repository is not configured for this clerk')
                    self.verify_repository(author)
                    record = self.fetch_record(uri, cid, (FEED,))
                    if (not isinstance(record, dict) or record.get('$type') != FEED
                            or not isinstance(record.get('text'), str)
                            or len(canonical(record)) > 1024 * 1024):
                        raise ValueError('interpretation requires an exact bounded public post record')
                    source = {'uri': uri, 'cid': cid, 'author': author, 'pds': PDS}
                    evidence = manual_intake.attestation(interpretation, source, digest(record))
                    if interpretation['status'] != 'act':
                        result = {'format': 'delvetalk-manual-review-v1', 'status': interpretation['status'],
                                  'source': source, 'record': record, 'interpretation': evidence,
                                  'message': interpretation['message'], 'publication': 'paused'}
                        result['id'] = digest(result)
                        # No semantic intent or pending admission is reserved.
                        save(self.state / 'interpretations' / (result['id'] + '.json'), result)
                        return result
                    entry = self.normalize_payload(interpretation['request'], author, uri, cid, record, config)
                    entry['interpretation'] = evidence
                # Binding is durable before Lean admission, not after its reply.
                if config['profile']['pins'] != pins(config.get('runtimeProfile', 'world')):
                    raise ValueError('clerk implementation pins changed; use the pinned checkout')
                save(path, entry)
            retained = world.retained_reply(self.database, entry['request'])
            if retained is None and entry['profile']['pins'] != pins(config.get('runtimeProfile', 'world')):
                raise ValueError('pending request implementation pins changed')
            return self.finish(path, entry, retained)

    def profile(self):
        with delve.locked(self.state / 'clerk.lock'):
            config = self.config()
            profile = config['profile']
            return {'profile': profile, 'sha256': digest(profile), 'runtimeProfile': config.get('runtimeProfile', 'world')}

    def upgrade(self, from_profile, runtime_profile=None, *, town_cards=UNCHANGED):
        """Explicit local custody transition; never changes or reinterprets a world."""
        if not isinstance(from_profile, str) or not re.fullmatch('[0-9a-f]{64}', from_profile):
            raise ValueError('from-profile must be the exact prior profile SHA256')
        with delve.locked(self.state / 'clerk.lock'):
            # The backend supplies an atomic observation; clerk custody serializes configuration.
            config = self.config()
            old = config['profile']
            prior_runtime = config.get('runtimeProfile', 'world')
            selected_runtime = prior_runtime if runtime_profile is None else runtime_profile
            new = {'name': PROFILE, 'pins': pins(selected_runtime)}
            cards = config.get('townCards') if town_cards is UNCHANGED else town_cards
            if cards is not None:
                new['townCards'] = digest(self.card_configuration(cards, selected_runtime))
            history = config.get('upgrades', [])
            if not isinstance(history, list):
                raise ValueError('malformed upgrade history')
            if digest(old) != from_profile:
                last = history[-1] if history else None
                if (isinstance(last, dict) and last.get('fromSha256') == from_profile
                        and canonical(last.get('to')) == canonical(old)
                        and canonical(old) == canonical(new) and prior_runtime == selected_runtime):
                    return {'format': 'delvetalk-clerk-upgrade-v1',
                            'status': 'already-upgraded', 'upgrade': last}
                raise ValueError('prior profile SHA256 mismatch')
            for path in sorted((self.state / 'requests').glob('*.json')):
                entry = loads(path.read_text())
                if not isinstance(entry, dict) or not isinstance(entry.get('receipt'), dict):
                    raise ValueError('pending request journal prevents upgrade: ' + path.name)
            if canonical(old) == canonical(new) and prior_runtime == selected_runtime:
                return {'format': 'delvetalk-clerk-upgrade-v1',
                        'status': 'unchanged', 'profileSha256': digest(old)}
            world_sha = hashlib.sha256(world.snapshot_bytes(self.database)).hexdigest()
            transition = {'from': old, 'to': new, 'fromSha256': from_profile,
                          'toSha256': digest(new), 'worldSha256': world_sha,
                          'fromRuntime': prior_runtime, 'toRuntime': selected_runtime}
            transition['id'] = digest(transition)
            config['profile'] = new
            if cards is None:
                config.pop('townCards', None)
            else:
                config['townCards'] = cards
            if selected_runtime == 'world':
                config.pop('runtimeProfile', None)
            else:
                config['runtimeProfile'] = selected_runtime
            config['upgrades'] = history + [transition]
            save(self.state / 'clerk.json', config)
            return {'format': 'delvetalk-clerk-upgrade-v1',
                    'status': 'upgraded', 'upgrade': transition}

    def snapshot(self, object_id):
        with delve.locked(self.state / 'clerk.lock'):
            config = self.config()
            if object_id not in config['objects']:
                raise ValueError('object is not configured for this clerk')
            if config['profile']['pins'] != pins(config.get('runtimeProfile', 'world')):
                raise ValueError('clerk implementation pins changed')
            root = world.exchange(self.database, {'op': 'inspect', 'object': object_id,
                                                  'principal': 'local-clerk-operator'}, profile=self.execution_profile({'op': 'inspect'}, config))
            result = {'format': 'delvetalk-clerk-root-v1', 'object': object_id,
                      'root': root, 'profile': config['profile']}
            result['id'] = digest(result)
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    commands = parser.add_subparsers(dest='op', required=True)
    init = commands.add_parser('bootstrap')
    init.add_argument('--object', required=True)
    init.add_argument('--protocol', type=Path, required=True)
    authority = init.add_mutually_exclusive_group()
    authority.add_argument('--law', action='append', default=[])
    authority.add_argument('--law-file', type=Path, help='complete law JSON; validated by Lean')
    init.add_argument('--repository', action='append', required=True)
    init.add_argument('--runtime-profile', choices=RUNTIME_CHOICES, default='world')
    attach = commands.add_parser('attach', help='enroll an existing verified workspace without creating objects')
    attach.add_argument('--workspace', required=True, type=Path)
    attach.add_argument('--expected-roots', required=True, type=Path, help='JSON object mapping selected IDs to exact full roots')
    attach.add_argument('--repository', action='append', required=True)
    attach.add_argument('--genesis', required=True)
    attach.add_argument('--seed-head', required=True)
    attach.add_argument('--runtime-profile', choices=world.PROFILES, required=True)
    receive = commands.add_parser('receive')
    receive.add_argument('uri')
    receive.add_argument('--cid', required=True)
    receive.add_argument('--interpretation', type=Path, help='explicit local operator decision JSON; no automatic prose interpretation')
    snapshot = commands.add_parser('snapshot')
    snapshot.add_argument('object')
    commands.add_parser('profile')
    upgrade = commands.add_parser('upgrade')
    upgrade.add_argument('--from-profile', required=True)
    upgrade.add_argument('--runtime-profile', choices=RUNTIME_CHOICES)
    cards = upgrade.add_mutually_exclusive_group()
    cards.add_argument('--cardbook', type=Path, help='explicit existing captured-card database')
    cards.add_argument('--disable-cards', action='store_true')
    upgrade.add_argument('--card-issuer', action='append', help='allowed publication DID; repeat as needed')
    args = parser.parse_args()
    try:
        clerk = Clerk(args.state)
        if args.op == 'bootstrap':
            law = loads(args.law_file.read_bytes()) if args.law_file else args.law
            result = clerk.bootstrap(args.object, loads(args.protocol.read_text()), law, args.repository, args.runtime_profile)
        elif args.op == 'attach':
            result = clerk.attach(args.workspace, loads(args.expected_roots.read_bytes()), args.repository,
                                  expected_genesis=args.genesis, expected_seed_head=args.seed_head,
                                  runtime_profile=args.runtime_profile)
        elif args.op == 'receive':
            result = (clerk.receive_interpreted(args.uri, args.cid, loads(args.interpretation.read_bytes()))
                      if args.interpretation else clerk.receive(args.uri, args.cid))
        elif args.op == 'profile':
            result = clerk.profile()
        elif args.op == 'upgrade':
            selection = UNCHANGED
            if args.cardbook:
                if not args.card_issuer:
                    raise ValueError('--cardbook requires explicit --card-issuer')
                cards = module('clerk_town_cards', 'scripts/town_cards.py')
                path = str(args.cardbook.expanduser().resolve())
                selection = {'path': path, 'issuers': sorted(set(args.card_issuer)),
                             'metadata': cards.CardBook(path).metadata()}
            elif args.card_issuer:
                raise ValueError('--card-issuer requires --cardbook')
            elif args.disable_cards:
                selection = None
            result = clerk.upgrade(args.from_profile, args.runtime_profile, town_cards=selection)
        else:
            result = clerk.snapshot(args.object)
        print(world.wire_dumps(result))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, RecursionError, delve.Failure) as error:
        print('clerk: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
