"""Authenticated scratch responses. The host resolves each world under the issuer.

No session state, response cache, signing box or reader policy lives here.
"""
from transport import mirror
from transport.atproto.cbor import block, from_json
from transport.repo import NS, Refusal
from transport.state import NAME

QUERIES = {NS + name for name in ('getSession', 'listSessionRecords')}
OPEN = NS + 'openSession'


def scratch_world(value):
    """Whether the wire names one caller-relative scratch world."""
    return isinstance(value, str) and value.startswith('scratch/') and NAME.fullmatch(value[8:]) is not None


def open_scratch(host, principal, data):
    """The shared HTTP/XRPC creation path; the host judges name, fork and capacity."""
    return host.send({'op': 'world-scratch', 'principal': principal, 'name': data.get('name'),
                      **({'from': data['from']} if 'from' in data else {})})


def check_reply(reply):
    """Unavailable transport and unknown/expired scratches have stable XRPC errors."""
    if reply.get('class') in ('hostUnavailable', 'hostTimeout'):
        raise Refusal(503, 'HostUnavailable', 'host unavailable')
    message = reply.get('message', '')
    if reply.get('status') == 'error' and (message.startswith('no scratch/') or
                                          (message.startswith('scratch/') and ' expired at clock ' in message)):
        raise Refusal(404, 'RecordNotFound', 'no such session')
    return reply


class ScratchHost:
    """Forward to an addressed host, propagating expiry during a multi-op read."""
    def __init__(self, host):
        self.host = host

    def send(self, request):
        return check_reply(self.host.send(request))

    def close(self):
        self.host.close()


def status(host, principal):
    """Admission is the addressed host's, before any metadata or contents are read."""
    reply = check_reply(host.send({'op': 'world-status', 'principal': principal}))
    if reply.get('status') != 'world':
        raise Refusal(400, 'InvalidRequest', reply.get('message') or 'no world status')
    return reply


def opened(host, principal, data):
    if set(data) - {'name', 'from'} or not isinstance(data.get('name'), str):
        raise Refusal(400, 'InvalidRequest', 'openSession takes name and optional from')
    if 'from' in data:
        source = data['from']
        if (not isinstance(source, dict) or set(source) - {'world', 'height'} or
                ('world' in source and not isinstance(source['world'], str)) or
                ('height' in source and (type(source['height']) is not int or source['height'] < 1))):
            raise Refusal(400, 'InvalidRequest', 'from is {world?, height?}, height a positive integer')
    reply = check_reply(open_scratch(host, principal, data))
    if reply.get('status') != 'scratch':
        raise Refusal(400, 'InvalidRequest', reply.get('message') or reply.get('reason') or 'scratch refused')
    return {'session': reply['world'], 'expires': reply['expires']}


def get_session(home, host, principal, session):
    reply = status(host, principal)
    rows = check_reply(home.send({'op': 'serve-status'})).get('scratches', [])
    row = next((r for r in rows if r['principal'] == principal and r['world'] == session), None)
    if row is None:
        raise Refusal(404, 'RecordNotFound', 'no such session')
    return {'session': session, 'status': reply['status'], 'expires': row['expires']}


def session_record(key, value):
    """Response-local key and value CID, without an at-uri or signed membership."""
    return {'key': key, 'cid': str(block(from_json(value))[0]), 'value': value}


def list_records(host, principal, query):
    collection = query.get('collection')
    if collection not in (NS + 'card', NS + 'entry'):
        raise Refusal(400, 'InvalidRequest', 'served session collections: ' + NS + 'card, ' + NS + 'entry')
    raw_limit = query.get('limit', '50')
    digits = raw_limit.lstrip('0')
    if not raw_limit.isascii() or not raw_limit.isdigit() or len(digits) > 3 or not 1 <= int(digits or '0') <= 100:
        raise Refusal(400, 'InvalidRequest', 'limit is 1..100')
    limit, cursor = int(digits), query.get('cursor')
    if collection == NS + 'entry':
        if cursor is not None and (len(cursor) > 20 or not cursor.isascii() or not cursor.isdigit() or int(cursor) < 1 or str(int(cursor)) != cursor):
            raise Refusal(400, 'InvalidRequest', 'cursor is an entry height')
        after = int(cursor or '0')
        if cursor is not None:
            seen = check_reply(host.send({'op': 'world-entries', 'principal': principal, 'after': after - 1, 'limit': 1}))
            if not any(e['height'] == after for e in seen.get('entries', [])):
                raise Refusal(400, 'InvalidRequest', 'cursor: not one this listing gave')
        reply = check_reply(host.send({'op': 'world-entries', 'principal': principal, 'after': after, 'limit': limit}))
        if reply.get('status') != 'entries':
            raise Refusal(400, 'InvalidRequest', 'host did not list entries')
        records = [session_record(str(e['height']), {'$type': NS + 'entry', 'entry': {'$link': e['hash']},
                                                   'height': e['height']}) for e in reply['entries']]
        return {'records': records, **({'cursor': records[-1]['key']} if reply.get('more') and records else {})}
    # Use the shared record renderer with paint disabled: no model or paint cache.
    keys = [mirror.card_key(oid) for oid in mirror.ids(host, principal)]
    if cursor is not None and cursor not in keys:
        raise Refusal(400, 'InvalidRequest', 'cursor: not one this listing gave')
    at, records = keys.index(cursor) + 1 if cursor is not None else 0, []
    while at < len(keys) and len(records) < limit:
        value = mirror.card_record(host, keys[at].replace('~', '/'), principal, paint=False)
        if value is not None:
            records.append(session_record(keys[at], value))
        at += 1
    return {'records': records, **({'cursor': keys[at - 1]} if at < len(keys) else {})}
