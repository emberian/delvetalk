#!/usr/bin/env python3
"""The XRPC client for delve.town, HTTP requests and canonical JSON. Carries bytes; decides nothing.

`public_transport` serves OAuth discovery and its DPoP PAR/token/revocation POSTs, Client.read and Client.did_document
(did:web and did:plc): their destinations come from identities or discovered metadata. `http_transport` serves
Delve XRPC, Zulip and the model: those hosts are configured, not discovered.

Only the GET endpoints in READS exist, and a DID document (`did_document`: plc.directory, or a hostname-level did:web
whose host resolves only to global addresses). Non-GET methods are refused here unless
a caller constructs the client with allow_write=True (only post.py does).
"""
import http.client
import ipaddress
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

PDS = 'https://pds.delve.town'
APPVIEW = 'https://api.delve.town'
PLC = 'https://plc.directory'
TIMEOUT = 20
MAX_RESPONSE = 16 * 1024 * 1024
MAX_PARAM = 2048

PDS_READS = {
    'com.atproto.repo.listRecords': {'repo', 'collection', 'limit', 'cursor', 'reverse'},
    'com.atproto.sync.getRecord': {'did', 'collection', 'rkey'},
    'com.atproto.sync.getLatestCommit': {'did'},
}
READS = {
    **{nsid: (PDS, params) for nsid, params in PDS_READS.items()},
    'town.delve.feed.getFeed': (APPVIEW, {'feed', 'limit', 'cursor'}),
    'town.delve.feed.searchPosts': (APPVIEW, {'q', 'limit', 'cursor'}),
    'com.atproto.repo.getRecord': (PDS, {'repo', 'collection', 'rkey'}),
    'com.atproto.identity.resolveHandle': (PDS, {'handle'}),
    'com.atproto.sync.listRepos': (PDS, {'limit', 'cursor'}),
}
DID = re.compile(r'did:(plc:[a-z2-7]{24}|web:[a-z0-9.-]{1,253})\Z')
WRITES = {
    'com.atproto.server.createSession': PDS,
    'com.atproto.repo.createRecord': PDS,
    'com.atproto.repo.putRecord': PDS,  # only post.record_writer: the mirror's records in the session's own repo
    'com.atproto.repo.deleteRecord': PDS,  # post.unsend and the mirror, and only a record in the session's own repo
}
POST = 'town.delve.feed.post'  # the collection a town post is a record of
TOWN_FEED = 'at://did:plc:qzqct2rrq4u2gmy5g3mjxske/town.delve.feed.generator/town'


class Failure(Exception):
    def __init__(self, code, detail=''):
        self.code, self.detail = code, detail
        super().__init__(code + (': ' + detail if detail else ''))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class ATUri(NamedTuple):
    repo: str
    collection: str
    rkey: str


def parse_at_uri(uri):
    """A record URI as bounded repo, collection and record key; no path, query or fragment after the key."""
    parts = uri.split('/') if isinstance(uri, str) and len(uri) <= 2 * MAX_PARAM + 512 + 7 else []
    if len(parts) != 5 or parts[:2] != ['at:', '']:
        raise Failure('bad_at_uri')
    repo, collection, rkey = parts[2:]
    if (len(repo) > MAX_PARAM or len(collection) > MAX_PARAM
            or not re.fullmatch(r'did:[a-z0-9]+:[A-Za-z0-9._:%-]+|[A-Za-z0-9.-]+\.[A-Za-z]+', repo)
            or not re.fullmatch(r'[A-Za-z0-9.]+', collection)
            or not re.fullmatch(r'[A-Za-z0-9._~:-]{1,512}', rkey) or rkey in ('.', '..')):
        raise Failure('bad_at_uri')
    return ATUri(repo, collection, rkey)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_transport(method, url, headers, body, limit=MAX_RESPONSE, timeout=TIMEOUT):
    """-> (status, bytes, headers): configured hosts (Delve XRPC, Zulip, the model). A redirect is
    never followed and at most `limit` + 1 bytes are read, so a caller can tell a reply past its bound; a network failure
    is Failure('network_error')."""
    req = urllib.request.Request(url, body, headers, method=method)
    try:
        resp = urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        resp = error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise Failure('network_error', type(error).__name__) from None
    with resp:
        return resp.status, resp.read(limit + 1), dict(resp.headers)


def _global_address(value):
    """Check both an address and any IPv4 destination carried by an IPv6 transition format."""
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address):
        embedded = address.ipv4_mapped or address.sixtofour
        if int(address) >> 32 == 0 or address in ipaddress.IPv6Network('64:ff9b::/96'):
            embedded = ipaddress.IPv4Address(int(address) & 0xffffffff)
        if embedded is not None and not _global_address(str(embedded)):
            return False
        if address.teredo and not all(_global_address(str(a)) for a in address.teredo):
            return False
    return address.is_global and not address.is_multicast and not address.is_reserved


def public_destination(url, *, resolve=socket.getaddrinfo):
    """One policy for metadata validation and pinned requests; validation itself never opens a socket."""
    host = ''
    try:
        if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
            raise ValueError('URL')
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ''
        port = parts.port if parts.port is not None else 443
        if parts.scheme != 'https' or not host or parts.username is not None or parts.password is not None or '%' in host:
            raise ValueError('authority')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if parts.netloc.startswith('['):
                raise ValueError('IP literal')
            host = host.encode('idna').decode('ascii')
            name = host.removesuffix('.')
            if len(name) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label, re.I)
                                         for label in name.split('.')):
                raise ValueError('hostname')
        else:
            if not _global_address(host):
                raise ValueError('address')
    except (ValueError, UnicodeError):
        raise Failure('not_public', host) from None
    try:
        found = resolve(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError) as error:
        raise Failure('network_error', type(error).__name__) from None
    try:
        if not found or not all(a[0] in (socket.AF_INET, socket.AF_INET6) and '%' not in a[4][0] and
                                _global_address(a[4][0]) for a in found):
            raise ValueError('address')
    except ValueError:
        raise Failure('not_public', host) from None
    return parts, host, port, found[0]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, address, timeout, socket_factory):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.address, self.socket_factory = address, socket_factory

    def connect(self):
        # socket.connect takes the numeric sockaddr directly: neither proxies nor another DNS lookup intervene.
        family, kind, proto, _, target = self.address
        sock = self.socket_factory(family, kind, proto)
        try:
            sock.settimeout(self.timeout)
            sock.connect(target)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def public_transport(method, url, headers, body, limit=MAX_RESPONSE, timeout=TIMEOUT, *,
                     resolve=socket.getaddrinfo, socket_factory=socket.socket):
    """-> (status, bytes, headers): HTTPS to an entirely global DNS answer, connected to its first checked address.

    TLS verifies the URL host with the default context; Host retains the URL authority. No redirects or proxies;
    at most limit + 1 response bytes. Refusals are Failure('not_public', host), network failures
    Failure('network_error', reason code). resolve and socket_factory are offline test seams.
    """
    parts, host, port, address = public_destination(url, resolve=resolve)
    authority = f'[{host}]' if ':' in host else host
    if parts.port is not None:
        authority += f':{port}'
    headers = {k: v for k, v in headers.items() if k.lower() != 'host'}
    headers['Host'] = authority
    path = urllib.parse.urlunsplit(('', '', parts.path or '/', parts.query, ''))
    connection = None
    try:
        connection = _PinnedHTTPSConnection(host, port, address, timeout, socket_factory)
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        with response:
            return response.status, response.read(limit + 1), dict(response.headers)
    except (OSError, http.client.HTTPException, UnicodeError, ValueError) as error:
        raise Failure('network_error', type(error).__name__) from None
    finally:
        if connection is not None:
            connection.close()


class FixtureTransport:
    """Offline seam: serves <dir>/<nsid>.json, or <nsid>.<cursor>.json for a cursor
    (an unknown cursor is an empty page). Records every call in .calls."""

    def __init__(self, directory):
        self.dir, self.calls = Path(directory), []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        parts = urllib.parse.urlsplit(url)
        nsid = parts.path.rsplit('/', 1)[-1]
        cursor = urllib.parse.parse_qs(parts.query).get('cursor', [None])[0]
        name = f'{nsid}.{cursor}.json' if cursor else f'{nsid}.json'
        path = self.dir / name
        if cursor and not path.exists():
            return 200, b'{"feed":[],"posts":[]}'
        if not path.exists():
            return 404, b'{"error":"NoFixture"}'
        return 200, path.read_bytes()


class Client:
    def __init__(self, transport=None, allow_write=False):
        self.transport, self.allow_write = transport or http_transport, allow_write
        self.document_transport = self.read_transport = transport or public_transport

    def _send(self, method, url, body=None, token=None, raw=False, *, transport=None):
        headers = {'Accept': 'application/vnd.ipld.car' if raw else 'application/json', 'User-Agent': 'DelveTalk/2 transport'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if token:
            headers['Authorization'] = 'Bearer ' + token
        status, got, *_ = (transport or self.transport)(method, url, headers, body)
        if 300 <= status < 400:
            raise Failure('redirect_refused', str(status))
        if len(got) > MAX_RESPONSE:
            raise Failure('response_too_large')
        if raw and status == 200:
            return got
        try:
            data = json.loads(got)
        except ValueError:
            data = None
        if status != 200:
            err = data.get('error') if isinstance(data, dict) else None
            raise Failure('http_status', f'{status} {err or ""}'.strip())
        if not isinstance(data, dict):
            raise Failure('response_not_json_object')
        return data

    def get(self, nsid, raw=False, **params):
        if nsid not in READS:
            raise Failure('endpoint_not_allowed', nsid)
        base, allowed = READS[nsid]
        return self._read(base, nsid, allowed, raw, params)

    def read(self, pds, nsid, raw=False, **params):
        """Participant repository reads at its discovered PDS, through pinned public HTTPS.

        Only listRecords, sync.getRecord and getLatestCommit exist; parameter and response bounds are get's.
        An injected transport supplies the offline seam for both these reads and DID documents.
        """
        if nsid not in PDS_READS:
            raise Failure('endpoint_not_allowed', nsid)
        return self._read(pds, nsid, PDS_READS[nsid], raw, params, transport=self.read_transport)

    def _read(self, base, nsid, allowed, raw, params, *, transport=None):
        params = {k: v for k, v in params.items() if v is not None}
        if set(params) - allowed:
            raise Failure('param_not_allowed', ','.join(sorted(set(params) - allowed)))
        for k, v in params.items():
            if not isinstance(v, (str, int)) or isinstance(v, bool) or len(str(v)) > MAX_PARAM:
                raise Failure('param_invalid', k)
        return self._send('GET', f'{base.rstrip("/")}/xrpc/{nsid}?{urllib.parse.urlencode(params)}', raw=raw, transport=transport)

    def did_document(self, did):
        """A DID's document via pinned public HTTPS: did:plc from plc.directory, hostname-level did:web from its host.
        Any other DID is refused. An injected Client transport supplies both documents and XRPC in offline tests."""
        if not isinstance(did, str) or not DID.fullmatch(did):
            raise Failure('did_refused', str(did)[:100])
        if did.startswith('did:plc:'):
            return self._send('GET', f'{PLC}/{did}', transport=self.document_transport)
        host = did[len('did:web:'):]
        return self._send('GET', f'https://{host}/.well-known/did.json', transport=self.document_transport)

    def write(self, nsid, body, token=None):
        if not self.allow_write or nsid not in WRITES:
            raise Failure('write_refused', nsid)
        return self._send('POST', f'{WRITES[nsid]}/xrpc/{nsid}', canonical(body).encode(), token)

    def feed(self, limit=50, cursor=None):
        return self.get('town.delve.feed.getFeed', feed=TOWN_FEED, limit=limit, cursor=cursor)

    def search(self, q, limit=50, cursor=None):
        return self.get('town.delve.feed.searchPosts', q=q, limit=limit, cursor=cursor)

    def record(self, at_uri):
        parsed = parse_at_uri(at_uri)
        return self.get('com.atproto.repo.getRecord', repo=parsed.repo, collection=parsed.collection, rkey=parsed.rkey)

    def resolve_handle(self, handle):
        return self.get('com.atproto.identity.resolveHandle', handle=handle)
