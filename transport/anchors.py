"""What a spell cites, read before the spell is carried: each at:// URI in its text, read once, read-only, from
pds.delve.town (`com.atproto.repo.getRecord`, transport/delve.Client.record), and written on the town's desk as what
was read: `<uri> <cid>`, or `<uri> absent` when the repository answers RecordNotFound. Carries bytes; decides
nothing: a register (world/bodies/register.obend) holds each anchor to these lines at its admission, and the desk's
law takes lines from the transport alone (tests/test_register.py `make_desk`). A repository that cannot be reached
writes nothing, and a register then holds that anchor unresolved.

The identity of a desk line is `read:<uri>:<cid>` (or `:absent`), so a reading is journaled once, and a post
rewritten under its URI is read again at its new CID beside the old one.
"""
import re

from transport.delve import Client, Failure, parse_at_uri

AT = re.compile(r'at://[A-Za-z0-9:._%-]+/[A-Za-z0-9.]+/[A-Za-z0-9._~:-]+')
MOST = 8  # at:// URIs read for one spell; a spell citing more has the rest held unresolved


def uris(text):
    """The at:// record URIs a text cites, in order, each once, at most MOST."""
    out = []
    for uri in AT.findall(text or ''):
        try:
            parse_at_uri(uri)
        except Failure:
            continue
        if uri not in out:
            out.append(uri)
    return out[:MOST]


def reading(client, uri):
    """`<cid>` as the repository serves the record, `absent` for RecordNotFound, None when it could not be read."""
    try:
        got = client.record(uri)
    except Failure as e:
        return 'absent' if 'RecordNotFound' in str(e) else None
    cid = got.get('cid') if isinstance(got, dict) else None
    if got.get('uri') not in (uri, None) or not isinstance(cid, str) or not re.fullmatch(r'b[a-z2-7]{20,200}', cid):
        return None
    return cid


def read(host, text, desk='desk', principal='transport', client=None):
    """Read every at:// URI `text` cites and write each reading on `desk`, as `principal`; -> [(uri, cid or
    'absent' or None, status)]. Nothing is read when the text cites none or the town has no desk."""
    cited = uris(text)
    if not cited or not (host.send({'op': 'world-object', 'principal': principal, 'object': desk}).get('record')):
        return []
    client = client or Client()
    out = []
    for uri in cited:
        cid = reading(client, uri)
        if cid is None:
            out.append((uri, None, 'unread'))
            continue
        reply = host.send({'op': 'world-turn', 'principal': principal, 'object': desk, 'method': 'write',
                           'identity': f'read:{uri}:{cid}',
                           'argument': {'tag': 'record', 'fields': [{'name': 'text', 'value': {'tag': 'label', 'value': f'{uri} {cid}'}}]}})
        out.append((uri, cid, reply.get('status')))
    return out
