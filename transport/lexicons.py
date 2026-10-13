"""Prepare or publish every schema under the NSID authority; never delete a published schema (ATPROTO §5)."""
import json

from transport.atproto.cbor import block, from_json
from transport.config import Config
from transport.delve import Failure, canonical
from transport.lexicon import DIR
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


def command(st, a, out, client=None, directory=DIR):
    """One publication step. The default prints local DAG-CBOR CIDs and lengths, without credentials,
    sockets or a ledger. An authorized step authenticates the authority and writes only changed values."""
    config = st.config if st is not None else Config.load()
    now = records(directory)
    # Encode every value before opening a writer, including values beyond the first changed record.
    blocks = {key: block(from_json(value)) for key, value in now.items()}
    out.write(TXT_CHECK + '\n')
    if not a.authorized:
        for (collection, rkey), (cid, raw) in blocks.items():
            out.write(canonical({'collection': collection, 'rkey': rkey, 'cid': str(cid), 'bytes': len(raw)}) + '\n')
        out.write(canonical({'count': len(now), 'did': config.lexicon_authority}) + '\n')
        out.flush()
        return 2
    from transport import post
    writes, deletes, ledger = record_plan.plan(st.lexicon_ledger, now, delete=False)
    writer = post.record_writer(st, client, expected_did=config.lexicon_authority)
    result = record_plan.put_records(st, st.lexicon_ledger, writes, deletes, ledger, writer)
    out.write(canonical({**result, 'count': len(now), 'did': config.lexicon_authority}) + '\n')
    out.flush()
    return 0
