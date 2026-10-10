#!/usr/bin/env python3
"""Read-only XRPC client for delve.town. Carries bytes; decides nothing.

Only the GET endpoints in READS exist. Non-GET methods are refused here unless
a caller constructs the client with allow_write=True (only post.py does).
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PDS = 'https://pds.delve.town'
APPVIEW = 'https://api.delve.town'
TIMEOUT = 20
MAX_RESPONSE = 16 * 1024 * 1024
MAX_PARAM = 2048

READS = {
    'town.delve.feed.getFeed': (APPVIEW, {'feed', 'limit', 'cursor'}),
    'town.delve.feed.searchPosts': (APPVIEW, {'q', 'limit', 'cursor'}),
    'town.delve.feed.getPostThread': (APPVIEW, {'uri', 'depth', 'parentHeight'}),
    'com.atproto.repo.getRecord': (PDS, {'repo', 'collection', 'rkey'}),
    'com.atproto.repo.listRecords': (PDS, {'repo', 'collection', 'limit', 'cursor', 'reverse'}),
    'com.atproto.identity.resolveHandle': (PDS, {'handle'}),
    'com.atproto.repo.describeRepo': (PDS, {'repo'}),
}
WRITES = {
    'com.atproto.server.createSession': PDS,
    'com.atproto.repo.createRecord': PDS,
}
TOWN_FEED = 'at://did:plc:qzqct2rrq4u2gmy5g3mjxske/town.delve.feed.generator/town'


class Failure(Exception):
    def __init__(self, code, detail=''):
        self.code, self.detail = code, detail
        super().__init__(code + (': ' + detail if detail else ''))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_transport(method, url, headers, body):
    """-> (status, bytes). Redirects are never followed; reads are size-capped."""
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, body, headers, method=method)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            status, raw = resp.status, resp.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read(MAX_RESPONSE + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise Failure('network_error', type(error).__name__) from None
    return status, raw


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
    def __init__(self, transport=http_transport, allow_write=False):
        self.transport, self.allow_write = transport, allow_write

    def _send(self, method, url, body=None, token=None):
        headers = {'Accept': 'application/json', 'User-Agent': 'DelveTalk/2 transport'}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if token:
            headers['Authorization'] = 'Bearer ' + token
        status, raw = self.transport(method, url, headers, body)
        if 300 <= status < 400:
            raise Failure('redirect_refused', str(status))
        if len(raw) > MAX_RESPONSE:
            raise Failure('response_too_large')
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if status != 200:
            err = data.get('error') if isinstance(data, dict) else None
            raise Failure('http_status', f'{status} {err or ""}'.strip())
        if not isinstance(data, dict):
            raise Failure('response_not_json_object')
        return data

    def get(self, nsid, **params):
        if nsid not in READS:
            raise Failure('endpoint_not_allowed', nsid)
        base, allowed = READS[nsid]
        params = {k: v for k, v in params.items() if v is not None}
        if set(params) - allowed:
            raise Failure('param_not_allowed', ','.join(sorted(set(params) - allowed)))
        for k, v in params.items():
            if not isinstance(v, (str, int)) or isinstance(v, bool) or len(str(v)) > MAX_PARAM:
                raise Failure('param_invalid', k)
        return self._send('GET', f'{base}/xrpc/{nsid}?{urllib.parse.urlencode(params)}')

    def write(self, nsid, body, token=None):
        if not self.allow_write or nsid not in WRITES:
            raise Failure('write_refused', nsid)
        return self._send('POST', f'{WRITES[nsid]}/xrpc/{nsid}', canonical(body).encode(), token)

    def feed(self, limit=50, cursor=None):
        return self.get('town.delve.feed.getFeed', feed=TOWN_FEED, limit=limit, cursor=cursor)

    def search(self, q, limit=50, cursor=None):
        return self.get('town.delve.feed.searchPosts', q=q, limit=limit, cursor=cursor)

    def thread(self, uri, depth=6, parent_height=20):
        return self.get('town.delve.feed.getPostThread', uri=uri, depth=depth, parentHeight=parent_height)

    def record(self, at_uri):
        m = re.fullmatch(r'at://([^/]+)/([^/]+)/([^/]+)', at_uri)
        if not m:
            raise Failure('bad_at_uri')
        return self.get('com.atproto.repo.getRecord', repo=m[1], collection=m[2], rkey=m[3])

    def resolve_handle(self, handle):
        return self.get('com.atproto.identity.resolveHandle', handle=handle)

    def describe_repo(self, repo):
        return self.get('com.atproto.repo.describeRepo', repo=repo)


def main(argv=None, transport=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='delve.py', description='read-only delve.town client')
    ap.add_argument('--mock', metavar='DIR', help='serve fixtures from DIR instead of the network')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('read-feed', 'search'):
        p = sub.add_parser(name)
        p.add_argument('--limit', type=int, default=50)
        p.add_argument('--cursor')
        if name == 'search':
            p.add_argument('--q', required=True)
    sub.add_parser('thread').add_argument('uri')
    sub.add_parser('record').add_argument('at_uri')
    a = ap.parse_args(argv)
    t = transport or (FixtureTransport(a.mock) if a.mock else http_transport)
    c = Client(t)
    try:
        if a.cmd == 'read-feed':
            data = c.feed(a.limit, a.cursor)
        elif a.cmd == 'search':
            data = c.search(a.q, a.limit, a.cursor)
        elif a.cmd == 'thread':
            data = c.thread(a.uri)
        else:
            data = c.record(a.at_uri)
    except Failure as f:
        print(canonical({'error': f.code, 'detail': f.detail}), file=sys.stderr)
        return 1
    out.write(canonical(data) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
