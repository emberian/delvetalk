"""Residents act by writing `online.fg-goose.gsb.request` in their own repository (docs/ATPROTO.md §2): the poller finds those
records, proves each, and keeps it as an observation the bridge turns as it turns a post.

pds.delve.town's firehose answers 401, so the poller unions `com.atproto.sync.listRepos`, verified claim DIDs and the
owner's configured participants. Each is read at the PDS its DID document names; (PDS, rev) is the skip signal.
Documents cache for ten minutes; verification failure refreshes once before refusal. A moved pair lists the repository's
whole request collection and takes every record it has not yet
consumed or refused, whatever its key: record keys are not an insertion order. Each is fetched with
`com.atproto.sync.getRecord` and proven: the commit's signature under the `#atproto` key of the author's DID document,
the MST path from the commit to the record's CID. A record that fails is no turn. A proven one is run only when it is
addressed to this service's DID and this world, was created at or after the world's `since`, and its mode is `act` or
`plan` (no `try` by record: a preview would publish its draft). The turn's identity is its at-uri; a uri is consumed once,
under the first CID proven, and the record must stay until its answer is written.

The poller reads; it never writes to any PDS. Python carries and checks bytes: whether the act is admitted is the host's.
"""
import json
import time

from transport.atproto.cbor import decode, encode, read_car
from transport.atproto.mst import find
from transport.atproto.sign import public_key, verify
from transport.delve import DID, PDS, Failure
from transport.identity import verified_dids
from transport.repo import NS, json_of, world_did

COLLECTION = NS + 'request'
MODES = ('act', 'plan')
PLAN_CALLS = 8  # the request lexicon's calls.maxLength
PAGES = 10  # a repository's request collection read per poll, 100 records a page
PARTICIPANT_CAP = 256  # non-delve-PDS participants read per poll; overflow is a problem, with its DID
DOCUMENT_TTL = 600  # seconds; the current DID document is refreshed again on proof verification failure
PROOF_FAILURES = {'bad_signature', 'not_in_commit', 'bad_proof', 'no_atproto_key', 'did_document_mismatch'}


def atproto_key(doc, did):
    """The `#atproto` Multikey of a DID document, as a public key."""
    for vm in doc.get('verificationMethod') or []:
        if isinstance(vm, dict) and vm.get('id') in ('#atproto', did + '#atproto') and vm.get('type') == 'Multikey':
            return public_key(vm['publicKeyMultibase'])
    raise Failure('no_atproto_key', did)


def endpoint(doc, did):
    """The PDS a DID document names, without a trailing slash."""
    for s in doc.get('service') or []:
        if isinstance(s, dict) and s.get('id') in ('#atproto_pds', did + '#atproto_pds') and isinstance(s.get('serviceEndpoint'), str):
            return s['serviceEndpoint'].rstrip('/')
    raise Failure('no_pds', did)


def proven(client, did, rkey, doc, collection=COLLECTION):
    """-> (cid, record value, handle), proven from the document's PDS, #atproto key and repository MST path.
    Raises Failure naming what failed. The poller owns document freshness and the one verification retry."""
    if doc.get('id') != did:
        raise Failure('did_document_mismatch', did)
    pds = endpoint(doc, did)
    try:
        key = atproto_key(doc, did)
        roots, blocks = read_car(client.read(pds, 'com.atproto.sync.getRecord', raw=True, did=did, collection=collection, rkey=rkey))
        commit = decode(blocks[roots[0]])
        unsigned = {k: v for k, v in commit.items() if k != 'sig'}
        if commit.get('did') != did or commit.get('version') != 3 or not verify(key, encode(unsigned), commit.get('sig') or b''):
            raise Failure('bad_signature', did)
        cid = find(blocks, commit['data'], f'{collection}/{rkey}'.encode())
        if cid is None:
            raise Failure('not_in_commit', rkey)
        value = decode(blocks[cid])
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        raise Failure('bad_proof', type(e).__name__) from None
    handle = next((a[5:] for a in doc.get('alsoKnownAs') or [] if isinstance(a, str) and a.startswith('at://')), did)
    return str(cid), value, handle


def judged(value, service, world, before_start):
    """-> (run, why, call): whether a proven request is this bridge's to run, and if not why. `why` with run False is a
    refusal kept in the ledger; run True with a `why` is answered `invalid` with it, never turned. `call` is what the
    bridge turns: the act's one call, or a plan's spells as the host reads a plan (`delvetalk plan`, then each spell)."""
    if not isinstance(value, dict) or value.get('service') != service:
        return False, 'addressed to another service', None
    if value.get('world', 'town') != world:
        return False, 'addressed to another world', None
    if not isinstance(value.get('createdAt'), str) or before_start(value['createdAt']):
        return False, 'created before this world began observing', None
    if value.get('mode') not in MODES:
        return False, f"mode {str(value.get('mode'))[:20]} is never run by record", None
    calls, plan = value.get('calls'), value['mode'] == 'plan'
    if 'if' in value and not isinstance(value['if'], list):
        return True, 'if is a list of {object, version}', None
    if not isinstance(calls, list) or not calls or len(calls) > (PLAN_CALLS if plan else 1) or not all(isinstance(c, dict) for c in calls):
        return True, f'a plan has 1 to {PLAN_CALLS} calls' if plan else 'an act has exactly one call', None
    if plan:
        if not all(isinstance(c.get('spell'), str) and set(c) == {'spell'} for c in calls):
            return True, 'a plan is spells only', None
        return True, None, {'spell': 'delvetalk plan\n' + '\n'.join(c['spell'].strip('\n') for c in calls)}
    call = calls[0]
    if isinstance(call.get('spell'), str) == isinstance(call.get('object'), str) or \
            (isinstance(call.get('object'), str) and not isinstance(call.get('verb'), str)):
        return True, 'a call is a spell, or an object with a verb (and fields), not both', None
    return True, None, call


class Poller:
    """One per world's bridge. A DID registry, resolved to each participant's current PDS."""

    def __init__(self, st, client, clock=time.monotonic):
        self.st, self.client, self.clock = st, client, clock
        self.documents = {}
        self.service, _ = world_did(st.config.origin)
        self.world = st.world

    def document(self, did, refresh=False):
        """An identity held for ten minutes; forced refresh discards the old document even if its fetch fails."""
        now = self.clock()
        held = self.documents.get(did)
        if not refresh and held and held[0] > now:
            return held[1]
        self.documents.pop(did, None)
        doc = self.client.did_document(did)
        if doc.get('id') != did:
            raise Failure('did_document_mismatch', did)
        endpoint(doc, did)
        self.documents[did] = (now + DOCUMENT_TTL, doc)
        return doc

    def registry(self, problems):
        """Union of active delve repositories, verified claim DIDs and the owner's explicit participants."""
        listed, cursor = {}, None
        while True:
            try:
                page = self.client.get('com.atproto.sync.listRepos', limit=1000, cursor=cursor)
            except Failure as error:
                problems.append({'listRepos': str(error)})
                break
            for repo in page.get('repos') or []:
                did = repo.get('did')
                if isinstance(did, str) and repo.get('active') is not False:
                    listed[did] = repo.get('rev')
            cursor = page.get('cursor')
            if not cursor or not page.get('repos'):
                break
        dids = set(listed) | set(self.st.config.participants.split())
        try:
            dids |= verified_dids(self.st)
        except Failure as error:
            problems.append({'identity': str(error)})
        allowed = set()
        for did in sorted(dids):
            if DID.fullmatch(did):
                allowed.add(did)
            else:
                problems.append({'did': did, 'failure': 'did_refused'})
        self.documents = {did: held for did, held in self.documents.items() if did in allowed}
        return allowed, listed

    def poll(self, observer):
        """Read moved (PDS, rev) pairs, retain consumed URIs and refused CIDs across identity changes. -> problems."""
        ledger = self.st.requests
        held = json.loads(ledger.read_text()) if ledger.exists() else {}
        revs, refused, problems = held.setdefault('revs', {}), held.setdefault('refused', {}), []
        dids, listed = self.registry(problems)
        latest, remote = {}, set()

        def revision(did, pds):
            if (did, pds) not in latest:
                if pds != PDS and did not in remote:
                    if len(remote) >= PARTICIPANT_CAP:
                        raise Failure('participant_overflow', f'limit {PARTICIPANT_CAP}')
                    remote.add(did)
                rev = listed[did] if pds == PDS and did in listed else self.client.read(
                    pds, 'com.atproto.sync.getLatestCommit', did=did).get('rev')
                if not isinstance(rev, str) or not rev:
                    raise Failure('bad_revision', did)
                latest[did, pds] = {'pds': pds, 'rev': rev}
            return latest[did, pds]

        for did in sorted(dids):
            try:
                doc = self.document(did)
                pair = revision(did, endpoint(doc, did))
                if revs.get(did) == pair:
                    continue
                doc = self.repository(observer, did, doc, refused, revision)
                revs[did] = revision(did, endpoint(doc, did))
            except Failure as error:  # unread: the pair is not recorded, so the next poll reads it again
                problems.append({'did': did, 'failure': str(error)})
        self.st.write(ledger, held)
        return problems

    def repository(self, observer, did, doc, refused, revision, refreshed=False):
        """Reconcile requests at the document's PDS. One identity refresh per participant per poll on a bad proof.

        A refresh naming another PDS restarts the collection read there; the old listing is never used with new proofs.
        """
        pds, cursor = endpoint(doc, did), None
        for _ in range(PAGES):
            page = self.client.read(pds, 'com.atproto.repo.listRecords', repo=did, collection=COLLECTION, limit=100, cursor=cursor)
            for listed in page.get('records') or []:
                uri, rkey = listed.get('uri', ''), str(listed.get('uri', '')).rsplit('/', 1)[-1]
                if observer.seen(uri) or (refused.get(uri) or {}).get('cid') == listed.get('cid'):
                    continue
                try:
                    cid, value, handle = proven(self.client, did, rkey, doc)
                except Failure as error:
                    if error.code not in PROOF_FAILURES:
                        raise
                    if not refreshed:
                        doc, refreshed = self.document(did, refresh=True), True
                        if endpoint(doc, did) != pds:
                            revision(did, endpoint(doc, did))  # the cap applies before reading the new PDS
                            return self.repository(observer, did, doc, refused, revision, refreshed=True)
                        try:
                            cid, value, handle = proven(self.client, did, rkey, doc)
                        except Failure as retry:
                            if retry.code not in PROOF_FAILURES:
                                raise
                            refused[uri] = {'cid': listed.get('cid'), 'why': str(retry)}
                            continue
                    else:
                        refused[uri] = {'cid': listed.get('cid'), 'why': str(error)}
                        continue
                run, why, call = judged(value, self.service, self.world, observer.before_start)
                if not run:
                    refused[uri] = {'cid': cid, 'why': why}
                    continue
                call = call or {}
                observer.insert({'uri': uri, 'cid': cid, 'author': {'did': did, 'handle': handle}, 'createdAt': value['createdAt'],
                                 'text': call.get('spell', ''), 'replyTo': None, 'root': None,
                                 'mentions': [], 'tags': [], 'kind': 'request',
                                 'request': {'call': call, **({'if': value['if']} if 'if' in value and not why else {}),
                                             **({'invalid': why} if why else {})}}, json_of(value))
            cursor = page.get('cursor')
            if not cursor:
                return doc
        raise Failure('request_pages_exhausted', did)
