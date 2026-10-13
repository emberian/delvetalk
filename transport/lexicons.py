"""Prepare or publish every schema under the NSID authority; never delete a published schema (ATPROTO §5)."""
import json

from transport.atproto.cbor import block, from_json
from transport.config import Config
from transport.delve import Client, Failure, canonical
from transport.lexicon import DIR
from transport import lexicon
from transport import records as record_plan

COLLECTION = 'com.atproto.lexicon.schema'
TXT_CHECK = 'dig +short TXT _lexicon.gsb.fg-goose.online'


def records(directory=DIR):
    """Fresh files, sorted by NSID: the complete document with the publication discriminant added."""
    now = {}
    for path in sorted(directory.rglob('*.json')):
        doc = json.loads(path.read_text())
        nsid = 'online.fg-goose.gsb.' + '.'.join(path.relative_to(directory).with_suffix('').parts)
        if (not isinstance(doc, dict) or doc.get('id') != nsid or type(doc.get('lexicon')) is not int
                or doc['lexicon'] != 1 or not isinstance(doc.get('defs'), dict) or not doc['defs']
                or doc.get('$type', COLLECTION) != COLLECTION):
            raise Failure('lexicon_document', f'{path}: needs Lexicon v1, path-matching id, defs and publication $type')
        now[COLLECTION, nsid] = {**doc, '$type': COLLECTION}
    return dict(sorted(now.items()))


def published(authority, fetch=None):
    """Read the authority's schemas at its discovered PDS, with no credential or write client.
    -> (rkey -> value CID, why unknown). Partial listings are never treated as complete."""
    from transport.requests import endpoint
    reader = Client(fetch)
    try:
        doc = reader.did_document(authority)
        if doc.get('id') != authority:
            raise Failure('did_document_mismatch', authority)
        pds = endpoint(doc, authority)
        found, cursors, cursor = {}, set(), None
        for _ in range(100):
            page = reader.read(pds, 'com.atproto.repo.listRecords', repo=authority,
                               collection=COLLECTION, limit=100, cursor=cursor)
            rows = page.get('records')
            if not isinstance(rows, list):
                raise Failure('published_invalid', 'listRecords needs records')
            prefix = f'at://{authority}/{COLLECTION}/'
            for row in rows:
                if (not isinstance(row, dict) or not isinstance(row.get('uri'), str)
                        or not row['uri'].startswith(prefix) or not isinstance(row.get('value'), dict)):
                    raise Failure('published_invalid', 'record needs authority URI and value')
                rkey = row['uri'][len(prefix):]
                if not rkey or '/' in rkey or rkey in found:
                    raise Failure('published_invalid', 'invalid or duplicate record key')
                found[rkey] = str(block(from_json(row['value']))[0])
            cursor = page.get('cursor')
            if cursor is None:
                return found, None
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise Failure('published_invalid', 'invalid or repeated cursor')
            cursors.add(cursor)
        raise Failure('published_invalid', 'listing exceeds 100 pages')
    except (Failure, OSError, ValueError, TypeError, KeyError, IndexError) as error:
        return {}, str(error)


def command(st, a, out, client=None, directory=DIR, fetch=None):
    """Validate all fresh files before any write, then compare with a credential-free PDS read.
    Dry runs tolerate an unavailable reference package; authorized runs require it."""
    config = st.config if st is not None else Config.load()
    try:
        now = records(directory)
        errors, unavailable, validator = lexicon.reference_problems(directory)
        if a.authorized and unavailable:
            raise Failure('lexicon_validation', 'reference validator required for --authorized: ' + unavailable)
        if errors:
            raise Failure('lexicon_validation', '\n'.join(errors))
        # Encode the entire batch before credentials, the writer or its ledger are opened.
        blocks = {key: block(from_json(value)) for key, value in now.items()}
    except (Failure, OSError, ValueError, TypeError) as error:
        out.write(canonical({'error': getattr(error, 'code', 'lexicon_validation'), 'detail': str(error)}) + '\n')
        out.flush()
        return 1
    remote, why = published(config.lexicon_authority, fetch)
    out.write(TXT_CHECK + '\n')
    for (collection, rkey), (cid, raw) in blocks.items():
        state = f'unknown ({why})' if why else ('new' if rkey not in remote else 'same' if remote[rkey] == str(cid) else 'differs')
        out.write(canonical({'collection': collection, 'rkey': rkey, 'cid': str(cid), 'bytes': len(raw),
                             'published': state}) + '\n')
    status = {'count': len(now), 'did': config.lexicon_authority,
              'reference': f'unavailable ({unavailable})' if unavailable else f'{validator}: passed'}
    if not a.authorized:
        out.write(canonical(status) + '\n')
        out.flush()
        return 2
    out.flush()  # The full comparison is visible before credentials or writes.
    from transport import post
    writes, deletes, ledger = record_plan.plan(st.lexicon_ledger, now, delete=False)
    writer = post.record_writer(st, client, expected_did=config.lexicon_authority)
    result = record_plan.put_records(st, st.lexicon_ledger, writes, deletes, ledger, writer)
    out.write(canonical({**result, **status}) + '\n')
    out.flush()
    return 0
