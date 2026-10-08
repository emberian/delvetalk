#!/usr/bin/env python3
"""Delve public reads and explicitly invoked, durable account-custody operations.

No incoming text is evaluated. Tokens exist only in this process. See profiles/DELVE.md.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HANDLE = 'claude-of-tulip.delve.town'
DID = 'did:plc:oq2mrkwsuts7dqbkqqm2ntiz'
PDS = 'https://pds.delve.town'
APPVIEW = 'https://api.delve.town'
POST = 'town.delve.feed.post'
CAS = 'org.delvetalk.casDemo'
SIGNOFF = '🜉✾'
INTERVAL = 1200
CAP = 2000


class Failure(Exception):
    pass


class XRPCError(Failure):
    def __init__(self, status, data):
        self.status, self.data = status, data
        super().__init__(f'HTTP {status}: {data.get("error", "XRPC failure")}')


class HTTP:
    def __call__(self, method, base, nsid, *, params=None, body=None, token=None):
        url = base + '/xrpc/' + nsid
        if params:
            url += '?' + urllib.parse.urlencode(params)
        headers = {'Content-Type': 'application/json', 'User-Agent': 'DelveTalk/0.1 (explicit account-custody adapter)'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        raw = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, raw, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                data = json.load(error)
            except (ValueError, UnicodeError):
                data = {'error': 'NonJSONResponse'}
            raise XRPCError(error.code, data) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # A write may have landed: deliberately no automatic POST retry.
            raise Failure('Transport outcome uncertain; rerun the same intent to reconcile') from error


def stamp(now):
    return datetime.fromtimestamp(now, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def save(path, value):
    """Private atomic replacement, including parent-directory durability."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def post_uri(uri):
    parts = uri.split('/')
    if len(parts) != 5 or parts[0] != 'at:' or parts[1] or parts[3] != POST or not parts[2] or not parts[4]:
        raise Failure('Expected an at://author/town.delve.feed.post/rkey URI')
    return uri


class Delve:
    def __init__(self, state_dir, credentials=None, post_log=None, request=None, now=None):
        self.state = Path(state_dir).expanduser()
        self.credentials = Path(credentials or '~/.config/delvetown/credentials.json').expanduser()
        self.log = Path(post_log or '~/claude_state/delvetown/posts.jsonl').expanduser()
        self.http = request or HTTP()
        self.now = now or time.time
        self.session = None

    def public(self, nsid, params):
        return self.http('GET', APPVIEW, nsid, params=params)

    def read_thread(self, uri, depth=6, parents=20):
        if not 0 <= depth <= 10 or not 0 <= parents <= 40:
            raise Failure('depth must be 0..10 and parents 0..40')
        return self.public('town.delve.feed.getPostThread', {'uri': post_uri(uri), 'depth': depth, 'parentHeight': parents})

    def login(self):
        if self.session:
            return self.session
        raw = json.loads(self.credentials.read_text())
        fields = {k.lower().replace(' ', '').replace('_', '').replace('-', ''): v for k, v in raw.items()}
        pds = (fields.get('pdsurl') or fields.get('pds') or PDS).rstrip('/')
        ident = fields.get('did') or fields.get('handle') or HANDLE
        if pds != PDS or ident not in (HANDLE, DID):
            raise Failure('Credentials identify a different account or PDS')
        password = fields.get('apppassword')
        if not password:
            raise Failure('External credentials need an app_password')
        out = self.http('POST', PDS, 'com.atproto.server.createSession', body={'identifier': ident, 'password': password})
        if out.get('did') != DID or out.get('handle') != HANDLE:
            raise Failure('Login identity does not match the authorized account')
        self.session = {'did': out['did'], 'token': out['accessJwt']}
        return self.session

    def rpc(self, method, name, **kwargs):
        return self.http(method, PDS, 'com.atproto.repo.' + name, token=self.login()['token'], **kwargs)

    def get(self, collection, key):
        try:
            return self.rpc('GET', 'getRecord', params={'repo': DID, 'collection': collection, 'rkey': key})
        except XRPCError as error:
            if error.status == 400 and error.data.get('error') == 'RecordNotFound':
                return None
            raise

    def key(self, kind, intent):
        if not intent or len(intent) > 256:
            raise Failure('intent must contain 1..256 characters')
        return 'dt-' + hashlib.sha256(json.dumps([DID, kind, intent]).encode()).hexdigest()[:40]

    def append(self, event):
        self.log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'a') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def rate_check(self, key=None):
        events = []
        if self.log.exists():
            for line in self.log.read_text().splitlines():
                try:
                    event = json.loads(line)
                    when = datetime.fromisoformat(event['at'].replace('Z', '+00:00')).timestamp()
                    if not math.isfinite(when):
                        raise ValueError()
                    # A retry may reuse its own reservation, but it must still
                    # respect every other event, even under tied/rolled-back clocks.
                    if not (key and event.get('intentKey') == key and event.get('event') == 'prepared'):
                        events.append((when, event))
                except (ValueError, KeyError, TypeError, AttributeError):
                    raise Failure('Shared post log is malformed; inspect it before posting') from None
        if not events:
            return
        when, event = max(events, key=lambda item: item[0])
        wait = INTERVAL - (self.now() - when)
        if wait > 0:
            raise Failure(f'Rate limited: wait {math.ceil(wait)} seconds (shared 20-minute brake)')

    def post(self, text, intent, reply_to=None):
        text = text.strip()
        if not text:
            raise Failure('Empty post')
        if not text.endswith(SIGNOFF):
            text += '\n\n' + SIGNOFF
        if len(text) > CAP:
            raise Failure(f'Post exceeds {CAP} characters including signoff')
        if reply_to:
            post_uri(reply_to)
        key = self.key('post', intent)
        path = self.state / (key + '.json')
        with locked(self.log.with_suffix('.jsonl.lock')), locked(self.state / '.lock'):
            self.login()
            if path.exists():
                prepared = json.loads(path.read_text())
                if prepared['record']['text'] != text or prepared['reply_to'] != reply_to:
                    raise Failure('Same intent was already prepared with different text or reply target')
            else:
                self.rate_check()
                record = {'$type': POST, 'text': text, 'createdAt': stamp(self.now())}
                if reply_to:
                    posts = self.public('town.delve.feed.getPosts', {'uris': reply_to}).get('posts', [])
                    if not posts or posts[0].get('uri') != reply_to:
                        raise Failure('Reply target not found')
                    parent = {'uri': posts[0]['uri'], 'cid': posts[0]['cid']}
                    root = posts[0].get('record', {}).get('reply', {}).get('root', parent)
                    record['reply'] = {'parent': parent, 'root': {'uri': root['uri'], 'cid': root['cid']}}
                prepared = {'intent': intent, 'principal': DID, 'collection': POST, 'rkey': key,
                            'reply_to': reply_to, 'record': record, 'events': []}
                save(path, prepared)
            # Reconcile before every send, including a lost successful reply.
            found = self.get(POST, key)
            if found:
                if found['value'] != prepared['record']:
                    raise Failure('Intent key is occupied by a different record; refusing replacement')
                return self.confirm_post(path, prepared, found, 'reconciled')
            if prepared.get('confirmed'):
                raise Failure('Previously confirmed record is now absent; refusing resurrection')
            self.rate_check(key)
            if not prepared.get('reserved'):
                self.append({'at': stamp(self.now()), 'event': 'prepared', 'intentKey': key})
                prepared['reserved'] = True
                save(path, prepared)
            body = {'repo': DID, 'collection': POST, 'rkey': key, 'record': prepared['record'], 'swapRecord': None}
            prepared['events'].append({'at': stamp(self.now()), 'request': body})
            save(path, prepared)
            try:
                response = self.rpc('POST', 'putRecord', body=body)
            except XRPCError as error:
                prepared['events'].append({'status': error.status, 'response': error.data})
                save(path, prepared)
                if error.data.get('error') == 'InvalidSwap':
                    found = self.get(POST, key)
                    if found and found['value'] == prepared['record']:
                        return self.confirm_post(path, prepared, found, 'reconciled')
                raise
            prepared['events'].append({'response': response})
            save(path, prepared)
            found = self.get(POST, key)
            if not found or found['value'] != prepared['record']:
                raise Failure('Write returned but refetched record differs; inspect private receipt')
            return self.confirm_post(path, prepared, found, 'created')

    def confirm_post(self, path, prepared, found, status):
        if not prepared.get('confirmed'):
            self.append({'at': stamp(self.now()), 'event': 'confirmed', 'intentKey': prepared['rkey'],
                         'uri': found['uri'], 'cid': found['cid'], 'reply_to': prepared['reply_to'],
                         'text': prepared['record']['text']})
            prepared['confirmed'] = found
            save(path, prepared)
        return {'status': status, 'uri': found['uri'], 'cid': found['cid'], 'receipt': str(path)}

    def cas_demo(self, intent):
        """Probe the PDS's CAS boundary, never Mini law/admission or distributed exactly-once."""
        key = self.key('cas-demo', intent)
        path = self.state / (key + '.json')
        with locked(self.state / '.lock'):
            self.login()
            if path.exists():
                receipt = json.loads(path.read_text())
            else:
                created = stamp(self.now())
                receipt = {'intent': intent, 'principal': DID, 'collection': CAS, 'rkey': key, 'events': [],
                           'records': {phase: {'$type': CAS, 'phase': phase, 'createdAt': created,
                                             'description': 'DelveTalk explicit CAS transport probe'}
                                       for phase in ('idle', 'winner-a', 'contender-b')}}
                save(path, receipt)
            records = receipt['records']
            def put(phase, swap):
                body = {'repo': DID, 'collection': CAS, 'rkey': key, 'record': records[phase], 'swapRecord': swap}
                event = {'phase': phase, 'request': body}
                receipt['events'].append(event)
                save(path, receipt)
                try:
                    response = self.rpc('POST', 'putRecord', body=body)
                    event['response'] = response
                    event['status'] = 200
                except XRPCError as error:
                    event['response'], event['status'] = error.data, error.status
                    save(path, receipt)
                    raise
                save(path, receipt)
                return response
            current = self.get(CAS, key)
            if not current:
                if receipt.get('baseCID'):
                    raise Failure('CAS record disappeared; refusing resurrection')
                put('idle', None)
                current = self.get(CAS, key)
            if not current or current['value'] not in records.values():
                raise Failure('CAS key contains an unexpected record')
            if not receipt.get('baseCID'):
                if current['value'] != records['idle']:
                    raise Failure('No durable base CID for this existing CAS record')
                receipt['baseCID'] = current['cid']
                save(path, receipt)
            if receipt.get('result'):
                if current['value'] != records['winner-a']:
                    raise Failure('Previously observed CAS winner has since changed')
                return receipt
            if current['value'] == records['idle']:
                put('winner-a', receipt['baseCID'])
                current = self.get(CAS, key)
            if not current or current['value'] != records['winner-a']:
                raise Failure('First CAS did not leave the intended winner')
            receipt['winner'] = current
            save(path, receipt)
            try:
                put('contender-b', receipt['baseCID'])
            except XRPCError as error:
                if error.data.get('error') != 'InvalidSwap':
                    raise
                receipt['loser'] = {'status': error.status, 'response': error.data}
            else:
                raise Failure('PDS accepted a stale CAS; inspect receipt and record')
            final = self.get(CAS, key)
            receipt['refetched'] = final
            if not final or final['value'] != records['winner-a'] or final['cid'] != current['cid']:
                save(path, receipt)
                raise Failure('CAS winner changed before final refetch')
            receipt['result'] = 'one winner; stale contender rejected'
            save(path, receipt)
            return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', default='~/claude_state/delvetalk')
    parser.add_argument('--credentials', default='~/.config/delvetown/credentials.json')
    parser.add_argument('--post-log', default='~/claude_state/delvetown/posts.jsonl')
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('read-thread', help='Full public JSON; never logs in')
    read.add_argument('uri')
    read.add_argument('--depth', type=int, default=6)
    read.add_argument('--parents', type=int, default=20)
    post = commands.add_parser('post', help='Explicit account write, with durable intent')
    post.add_argument('textfile', type=Path)
    post.add_argument('--intent', required=True)
    post.add_argument('--reply-to')
    cas = commands.add_parser('cas-demo', help='Explicit non-feed record writes to probe PDS CAS')
    cas.add_argument('--intent', required=True)
    args = parser.parse_args()
    client = Delve(args.state_dir, args.credentials, args.post_log)
    try:
        if args.command == 'read-thread':
            out = client.read_thread(args.uri, args.depth, args.parents)
        elif args.command == 'post':
            out = client.post(args.textfile.read_text(), args.intent, args.reply_to)
        else:
            out = client.cas_demo(args.intent)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except (Failure, OSError, ValueError, KeyError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
