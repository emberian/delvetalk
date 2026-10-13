"""DelveTalk-custodied public request repositories (ATPROTO §4).

The front and bridge share State.hosted. Each write atomically replaces one
public snapshot under an account flock; reads rebuild its bounded sorted MST
and deterministic signed head. No journal, feed, private projection or secret
is a record. The per-account key is separate from its public snapshot.
"""
from contextlib import contextmanager
import fcntl
import json
import os
import time
import urllib.parse

from transport.atproto.cbor import CID, block, car, from_json
from transport.atproto.mst import Tree
from transport.atproto.sign import Key, tid
from transport.delve import Failure, canonical
from transport.acts import judge_call
from transport.identity import hosted_identity, verified_principals
from transport.lexicon import record_problems
from transport.repo import NS, Repo, Refusal, TID, WRITES, repository_document
from transport.state import State

COLLECTION = NS + 'request'
MAX_REQUESTS, MAX_RECORD_BYTES = 256, 64 * 1024
MAX_WRITE_BODY = 6 * MAX_RECORD_BYTES + 4096  # JSON can escape each control byte as six ASCII bytes
MAX_PAGE_BYTES = 4 * 1024 * 1024  # JSON escaping can make a bounded leaf six times larger
MAX_CAR_BYTES = 17 * 1024 * 1024  # 256 bounded leaves plus MST and commit framing
READS = {k: v for k, v in Repo.METHODS.items() if v in (
    'describe', 'list_records', 'get_record', 'sync_record', 'get_repo',
    'latest_commit', 'list_repos', 'repo_status', 'resolve_handle', 'list_blobs')}


class Accounts:
    """One world's hosted accounts; provision only from an authenticated principal."""
    def __init__(self, st):
        self.st = st
        self.host = urllib.parse.urlsplit(st.config.origin).hostname

    def provision_guests(self):
        """Accepted guests already in identity.sqlite have the same hosted address as new arrivals."""
        for principal in sorted(verified_principals(self.st)):
            if principal.startswith('guest:' + self.host + ':'):
                self.account(principal, create=True)

    def account(self, principal, create=False):
        did = hosted_identity(principal, self.host)
        # The mapping also validates the file stem; no principal supplies a path.
        name = did[8:-(len(self.host) + 1)]
        if name.endswith('.guest'):
            name = name[:-6]
        account = HostedRepo(self.st, principal, did, name)
        if create:
            account.provision()
        elif not account.snapshot.exists():
            raise Refusal(400, 'RepoNotFound', 'no such hosted account')
        return account

    def by_did(self, did):
        if not isinstance(did, str) or not did.startswith('did:web:'):
            raise Refusal(400, 'RepoNotFound', 'no such hosted account')
        try:
            return self.account(hosted_identity(did, self.host))
        except ValueError:
            raise Refusal(400, 'RepoNotFound', 'no such hosted account') from None

    def by_host(self, host):
        """Only an exact hosted hostname selects an account; no key is made by a Host header."""
        return self.by_did('did:web:' + host)

    def dids(self):
        """The fourth poller source: public snapshots in this world's state directory."""
        out = set()
        for path in sorted(self.st.hosted.glob('*.json')):
            value = json.loads(path.read_text())
            out.add(hosted_identity(value['principal'], self.host))
        return out

    def did_document(self, did):
        return self.by_did(did).did_document()

    def read(self, pds, nsid, raw=False, **params):
        """The local CAR source for requests.proven, with the same repository methods as HTTP."""
        if pds.rstrip('/') != self.st.config.origin.rstrip('/'):
            raise Failure('no_pds', pds)
        try:
            account = self.by_did(params.get('did') or params.get('repo'))
            q = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in params.items() if v is not None}
            code, value, _ = account.serve(None, 'GET', nsid, q, None)
            if code != 200:
                raise Failure(value['error'], value['message'])
            return value
        except Refusal as r:
            raise Failure(r.body['error'], r.body['message']) from None


class HostedRepo(Repo):
    """Repo's query framing over one public mutable account, never over the world host."""
    METHODS = READS

    def __init__(self, st, principal, did, name):
        self.st, self.principal, self.did, self.handle = st, principal, did, did[8:]
        self.origin = st.config.origin.rstrip('/')
        self.key_path, self.snapshot, self.lock_path = st.hosted_paths(name)

    @contextmanager
    def locked(self):
        self.st.hosted.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.lock_path, 'a+b') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def provision(self):
        with self.locked():
            if self.snapshot.exists():
                Key.load(self.key_path)  # lost keys are never silently replaced
                return
            if not self.key_path.exists():
                key = Key.generate()
                fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
                with os.fdopen(fd, 'wb') as f:
                    f.write(key.pem())
                    f.flush()
                    os.fsync(f.fileno())
            State.write(self.snapshot, {'principal': self.principal, 'counter': 0, 'prev': None, 'records': {}})
            self.sync_directory()

    def sync_directory(self):
        fd = os.open(self.st.hosted, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def stored(self):
        value = json.loads(self.snapshot.read_text())
        if value['principal'] != self.principal:
            raise ValueError('hosted snapshot principal mismatch')
        return value

    def did_document(self):
        return repository_document(self.did, self.handle, self.origin, Key.load(self.key_path))

    def collection(self, q):
        if q.get('collection') != COLLECTION:
            raise Refusal(400, 'InvalidRequest', 'hosted accounts hold only ' + COLLECTION)
        return 'request'

    def built(self, stored):
        """A complete current tree, sorted independently of insertion order, including the empty tree."""
        tree, records = Tree(), {}
        for rkey, value in sorted(stored['records'].items()):
            records[rkey] = block(from_json(value))
            tree.append(f'{COLLECTION}/{rkey}'.encode(), records[rkey][0])
        commit = Key.load(self.key_path).commit(self.did, tree.root(), tid(stored['counter']),
                                              CID.parse(stored['prev']) if stored['prev'] else None)
        return tree, records, commit

    def serve(self, host, method, nsid, query, principal):
        try:
            if nsid in WRITES:
                if method != 'POST':
                    raise Refusal(405, 'InvalidRequest', 'a repository write uses POST')
                if not principal:
                    raise Refusal(401, 'AuthRequired', 'hosted writes require an invitation credential')
                if principal != self.principal:
                    raise Refusal(403, 'Denied', 'credential belongs to another principal')
                with self.locked():
                    out = self.write_record(WRITES[nsid], query)
                return 200, out, 'application/json'
            return super().serve(host, method, nsid, query, principal)
        except Refusal as r:
            return r.code, r.body, 'application/json'

    def write_record(self, verb, q):
        allowed = {'repo', 'collection', 'rkey', 'swapCommit', 'swapRecord'}
        if verb != 'deleteRecord':
            allowed |= {'record', 'validate'}
        if set(q) - allowed or ('validate' in q and q['validate'] is not True):
            raise Refusal(400, 'InvalidRequest', 'unexpected fields or validation disabled')
        self.repo(q)
        self.collection(q)
        stored = self.stored()
        _, records, previous = self.built(stored)
        counter = max(stored['counter'] + 1, time.time_ns() // 1000)
        if counter >= 1 << 53:
            raise Refusal(400, 'InvalidRequest', 'repository revision counter exhausted')
        rkey = q.get('rkey', tid(counter) if verb == 'createRecord' else None)
        if not isinstance(rkey, str) or not TID.fullmatch(rkey):
            raise Refusal(400, 'InvalidRequest', 'request rkey must be a TID')
        old = records.get(rkey)
        if 'swapCommit' in q and q['swapCommit'] != str(previous[0]):
            raise Refusal(400, 'InvalidSwap', 'repository head moved')
        if 'swapRecord' in q and q['swapRecord'] != (str(old[0]) if old else None):
            raise Refusal(400, 'InvalidSwap', 'record moved')
        if verb == 'createRecord' and old:
            raise Refusal(400, 'RecordAlreadyExists', 'use putRecord to replace this request')
        if verb == 'deleteRecord':
            if not old:
                return {}  # deleting an absent record is idempotent
            del stored['records'][rkey]
        else:
            value = q.get('record')
            if not isinstance(value, dict) or value.get('$type') != COLLECTION:
                raise Refusal(400, 'InvalidRequest', 'record $type must be ' + COLLECTION)
            try:
                problems = record_problems(value)
                record = block(from_json(value))
            except (ValueError, TypeError, KeyError, IndexError, AttributeError, UnicodeError, RecursionError) as e:
                raise Refusal(400, 'InvalidRequest', 'invalid record: ' + type(e).__name__) from None
            why, _ = judge_call(value.get('mode'), value.get('calls'), value.get('if', []))
            if why:
                problems.append(why)
            if problems:
                raise Refusal(400, 'InvalidRequest', '; '.join(problems))
            if len(record[1]) > MAX_RECORD_BYTES:
                raise Refusal(400, 'InvalidRequest', f'record exceeds {MAX_RECORD_BYTES} DAG-CBOR bytes')
            if not old and len(records) >= MAX_REQUESTS:
                raise Refusal(400, 'RepoFull', f'{MAX_REQUESTS} requests retained oldest first; delete one before creating another')
            stored['records'][rkey] = value
        stored.update(counter=counter, prev=str(previous[0]))
        _, values, commit = self.built(stored)
        State.write(self.snapshot, stored)
        self.sync_directory()
        out = {'commit': {'cid': str(commit[0]), 'rev': tid(counter)}}
        if verb != 'deleteRecord':
            out.update(uri=f'at://{self.did}/{COLLECTION}/{rkey}', cid=str(values[rkey][0]), validationStatus='valid')
        return out

    def describe(self, host, q, who):
        self.repo(q)
        return {'did': self.did, 'handle': self.handle, 'didDoc': self.did_document(),
                'collections': [COLLECTION], 'handleIsCorrect': True}

    def listing(self, rkey, value):
        return {'uri': f'at://{self.did}/{COLLECTION}/{rkey}', 'cid': str(block(from_json(value))[0]), 'value': value}

    def list_records(self, host, q, who):
        self.repo(q)
        self.collection(q)
        cursor, limit, reverse = self.paging(q)
        stored = self.stored()
        keys = sorted(stored['records'], reverse=reverse)
        # An exclusive key cursor remains usable after deletion/replacement.
        keys = [k for k in keys if not cursor or (k < cursor if reverse else k > cursor)]
        rows, size = [], 128  # envelope, separators and cursor
        for k in keys[:limit]:
            row = self.listing(k, stored['records'][k])
            n = len(canonical(row).encode())
            if size + n > MAX_PAGE_BYTES:
                break
            rows.append(row)
            size += n + 1
        return {'records': rows, **({'cursor': rows[-1]['uri'].rsplit('/', 1)[-1]} if len(rows) < len(keys) else {})}

    def get_record(self, host, q, who):
        self.repo(q)
        self.collection(q)
        rkey = q.get('rkey')
        value = self.stored()['records'].get(rkey)
        if value is None:
            raise Refusal(400, 'RecordNotFound', 'no such request')
        out = self.listing(rkey, value)
        if q.get('cid') and q['cid'] != out['cid']:
            raise Refusal(400, 'RecordNotFound', 'request cid differs')
        return out

    def get_repo(self, host, q, who):
        self.repo(q, 'did')
        tree, records, commit = self.built(self.stored())
        # A bounded full export reconciles arbitrary puts/deletes; no append-only delta is claimed.
        return car(commit[0], [commit, *tree.blocks(since=-1), *records.values()])

    def sync_record(self, host, q, who):
        self.repo(q, 'did')
        self.collection(q)
        rkey = q.get('rkey')
        tree, records, commit = self.built(self.stored())
        if rkey not in records:
            raise Refusal(400, 'RecordNotFound', 'no such request')
        keys = sorted(records)
        return car(commit[0], [commit, *tree.proof(keys.index(rkey)), records[rkey]])

    def latest_commit(self, host, q, who):
        self.repo(q, 'did')
        stored = self.stored()
        commit = self.built(stored)[2]
        return {'cid': str(commit[0]), 'rev': tid(stored['counter'])}

    def repo_status(self, host, q, who):
        return {'did': self.did, 'active': True, 'rev': self.latest_commit(host, q, who)['rev']}

    def list_repos(self, host, q, who):
        stored = self.stored()
        commit = self.built(stored)[2]
        return {'repos': [{'did': self.did, 'head': str(commit[0]), 'rev': tid(stored['counter']), 'active': True}]}
