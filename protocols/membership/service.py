"""Custody for a source-prepared welcome; no grant construction or world policy.

Only call this after proof-of-control verification. The configured service identity
is distinct from the newly authenticated participant and from an operator.
"""
from pathlib import Path
import fcntl
import hashlib
import json
import math
import os
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import desk
import runtime_profile
import source_offers
import world
from scene import room


def enroll(database, object_id, service_principal, verified_did, proof, intent,
           *, profile='compiled', custody=None, timeout=10):
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError('bounded welcome timeout required')
    deadline = time.monotonic() + timeout
    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError('welcome custody deadline exceeded')
        return value
    class Receiver:
        profile = 'compiled'
        def query(self, request):
            return world.query(database, request, profile=profile, timeout=remaining())
    if profile != 'compiled':
        raise ValueError('source enrollment requires the configured compiled receiver')
    if (not isinstance(verified_did, str) or not verified_did.startswith('did:')
            or not isinstance(proof, dict) or set(proof) != {'uri', 'cid', 'basis'}
            or any(not isinstance(v, str) or not v for v in proof.values())):
        raise ValueError('enrollment needs a trusted verified identity and exact proof evidence')
    if any(not isinstance(s, str) or not s for s in (object_id, service_principal, intent)):
        raise ValueError('explicit welcome object, service and intent are required')
    binding = {'did': verified_did, 'proof': proof, 'object': object_id,
               'principal': service_principal, 'intent': intent}
    evidence = hashlib.sha256(json.dumps({'did': verified_did, **proof}, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    directory = Path(custody) if custody is not None else Path(database).parent / (Path(database).name + '.enrollment')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = hashlib.sha256(world.wire_dumps({'principal': service_principal, 'intent': intent}).encode()).hexdigest()
    record_path = directory / (key + '.json')
    with (directory / (key + '.lock')).open('a') as lock:
        os.chmod(lock.name, 0o600)
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(min(0.025, remaining()))
        if record_path.exists():
            retained = world.wire_loads(record_path.read_text())
            if (not isinstance(retained, dict) or set(retained) != {'format', 'binding', 'request'}
                    or retained.get('format') != 'delvetalk-enrollment-custody-v1'):
                raise ValueError('malformed welcome custody record')
            if retained['binding'] != binding:
                raise ValueError('welcome intent already binds different proof evidence')
            request = retained['request']
        else:
            owner = world.capture_roots(database, [object_id], principal=service_principal, profile=profile, timeout=remaining())
            if owner['roots'][object_id] is None:
                return {'status': 'refused', 'message': 'The configured welcome object is unavailable.'}
            owner_root = owner['roots'][object_id]['root']
            view = room.inspect_object(owner_root, object_id,
                expected_runtime={'name': profile, 'files': runtime_profile.file_hashes(profile)})
            if view.get('mode') != 'projection':
                raise ValueError('Welcome source projection is unavailable')
            captured = source_offers.capture_observations(view, owner, database=database,
                principal=service_principal, profile=profile, timeout=remaining())
            roots = {k: v['root'] for k, v in captured['roots'].items() if v is not None}
            refs = {k: v['reference'] for k, v in captured['roots'].items() if v is not None}
            offers = source_offers.capture(view, roots, references=refs)
            if 'enroll' not in offers:
                return {'status': 'refused', 'message': 'The source welcome has no enrollment invitation.'}
            prepared = source_offers.prepare(offers['enroll'], service_principal, intent,
                {'did': verified_did, 'proof': evidence}, receiver=Receiver())
            if prepared['kind'] != 'ready':
                return {'status': prepared['kind'], 'preparation': prepared}
            request = prepared['request']
            retained = {'format': 'delvetalk-enrollment-custody-v1', 'binding': binding,
                        'request': request}
            stored = desk.immutable(record_path, retained)
            os.chmod(record_path, 0o600)
            if stored != retained:
                raise ValueError('welcome intent custody differs')
        if (not isinstance(request, dict) or request.get('principal') != service_principal
                or request.get('intent') != intent):
            raise ValueError('retained welcome request differs from its service and intent')
        reply = world.exchange(database, request, profile=profile, timeout=remaining())
        return {'status': reply['kind'], 'receipt': reply}
