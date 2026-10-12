"""Residents act by writing `online.fg-goose.gsb.request` in their own repository (docs/ATPROTO.md §2): the poller finds those
records, proves each, and keeps it as an observation the bridge turns as it turns a post.

pds.delve.town's firehose answers 401, so the poller pages `com.atproto.sync.listRepos` and reads a repository again only
when its `rev` moved. Then it lists the repository's whole request collection and takes every record it has not yet
consumed or refused, whatever its key: record keys are not an insertion order. Each is fetched with
`com.atproto.sync.getRecord` and proven: the commit's signature under the `#atproto` key of the author's DID document,
the MST path from the commit to the record's CID. A record that fails is no turn. A proven one is run only when it is
addressed to this service's DID and this world, was created at or after the world's `since`, and its mode is `act` or
`plan` (no `try` by record: a preview would publish its draft). The turn's identity is its at-uri; a uri is consumed once,
under the first CID proven, and the record must stay until its answer is written.

The poller reads; it never writes to any PDS. Python carries and checks bytes: whether the act is admitted is the host's.
"""
import json

from transport.atproto.cbor import decode, encode, read_car
from transport.atproto.mst import find
from transport.atproto.sign import public_key, verify
from transport.delve import PDS, Failure
from transport.repo import NS, json_of, world_did

COLLECTION = NS + 'request'
MODES = ('act', 'plan')
PLAN_CALLS = 8  # the request lexicon's calls.maxLength
PAGES = 10  # a repository's request collection read per poll, 100 records a page


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


def proven(client, did, rkey, collection=COLLECTION):
    """-> (cid, record value, handle) of `at://<did>/<collection>/<rkey>`, proven from the repository's signed
    commit. The proof is read from the PDS the DID document names now, and only when that is the PDS polled: a repository
    that moved away is not read from its old host, whose copy may be stale. Raises Failure naming what failed."""
    doc = client.did_document(did)
    if doc.get('id') != did:
        raise Failure('did_document_mismatch', did)
    if endpoint(doc, did) != PDS:
        raise Failure('repository_elsewhere', endpoint(doc, did))
    key = atproto_key(doc, did)
    try:
        roots, blocks = read_car(client.get('com.atproto.sync.getRecord', raw=True, did=did, collection=collection, rkey=rkey))
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
    """One per world's bridge. `client` reads pds.delve.town and DID documents (delve.Client)."""

    def __init__(self, st, client):
        self.st, self.client = st, client
        self.service, _ = world_did(st.config.origin)  # requests are addressed to the service; `world` names the world
        self.world = st.world

    def poll(self, observer):
        """Read every repository whose rev moved, keep each new proven request as an observation. -> problems."""
        ledger = self.st.requests
        held = json.loads(ledger.read_text()) if ledger.exists() else {}
        revs, refused, problems, cursor = held.setdefault('revs', {}), held.setdefault('refused', {}), [], None
        while True:
            try:
                page = self.client.get('com.atproto.sync.listRepos', limit=1000, cursor=cursor)
            except Failure as e:
                problems.append({'listRepos': str(e)})
                break
            for repo in page.get('repos') or []:
                did, rev = repo.get('did'), repo.get('rev')
                if not isinstance(did, str) or repo.get('active') is False or revs.get(did) == rev:
                    continue
                try:
                    self.repository(observer, did, refused)
                    revs[did] = rev
                except Failure as e:  # unread: the rev is not recorded, so the next poll reads it again
                    problems.append({'did': did, 'failure': str(e)})
            cursor = page.get('cursor')
            if not cursor or not page.get('repos'):
                break
        self.st.write(ledger, held)
        return problems

    def repository(self, observer, did, refused):
        """Every request record of `did` not yet consumed or refused at its current CID."""
        cursor = None
        for _ in range(PAGES):
            page = self.client.get('com.atproto.repo.listRecords', repo=did, collection=COLLECTION, limit=100, cursor=cursor)
            for listed in page.get('records') or []:
                uri, rkey = listed.get('uri', ''), str(listed.get('uri', '')).rsplit('/', 1)[-1]
                if observer.seen(uri) or (refused.get(uri) or {}).get('cid') == listed.get('cid'):
                    continue
                try:
                    cid, value, handle = proven(self.client, did, rkey)
                except Failure as e:
                    if e.code in ('bad_signature', 'not_in_commit', 'bad_proof'):  # this CID will never prove: say so once
                        refused[uri] = {'cid': listed.get('cid'), 'why': str(e)}
                        continue
                    raise
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
                return

