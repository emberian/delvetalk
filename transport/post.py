#!/usr/bin/env python3
"""The ONLY writer. Without --i-am-ember-and-authorize-posting it prints the exact
request it would send and exits 2 without reading credentials or touching the network.
"""
import argparse
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from transport.delve import Client, Failure, canonical, http_transport
except ImportError:
    from delve import Client, Failure, canonical, http_transport

FLAG = '--i-am-ember-and-authorize-posting'
COLLECTION = 'town.delve.feed.post'
MAX_TEXT = 64 * 1024
LIMIT, WINDOW = 16, 3600
CREDENTIALS = '~/.config/delvetown/credentials.json'


def build_request(text):
    if not text.strip():
        raise Failure('empty_post')
    if len(text.encode()) > MAX_TEXT:
        raise Failure('post_body_too_large')
    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    return {'method': 'POST', 'nsid': 'com.atproto.repo.createRecord',
            'body': {'repo': '<session did>', 'collection': COLLECTION,
                     'record': {'$type': COLLECTION, 'text': text, 'createdAt': now}}}


def take_slot(state, now):
    """Record one write against the hourly budget, or refuse. Locked, persisted."""
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(state / 'post-log.json', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            stamps = [t for t in json.loads(f.read() or '[]') if now - t < WINDOW]
        except ValueError:
            stamps = []
        if len(stamps) >= LIMIT:
            raise Failure('rate_limited', f'{LIMIT} writes per hour')
        f.seek(0)
        f.truncate()
        f.write(json.dumps(stamps + [now]))


def send(request, intent, state, credentials, client=None):
    """Network write. Credentials go only to the fixed PDS via Client."""
    client = client or Client(http_transport, allow_write=True)
    take_slot(state, time.time())
    cred = json.loads(Path(credentials).expanduser().read_text())
    session = client.write('com.atproto.server.createSession',
                           {'identifier': cred['identifier'], 'password': cred['password']})
    body = dict(request['body'], repo=session['did'])
    result = client.write('com.atproto.repo.createRecord', body, token=session['accessJwt'])
    with open(state / 'post-log.jsonl', 'a') as log:
        log.write(canonical({'intent': intent, 'uri': result.get('uri'), 'cid': result.get('cid')}) + '\n')
    return result


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='post.py')
    ap.add_argument('--state', required=True)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('post')
    p.add_argument('--text-file', required=True)
    p.add_argument('--intent', required=True)
    p.add_argument('--credentials', default=CREDENTIALS)
    p.add_argument(FLAG, dest='authorized', action='store_true', default=False)
    a = ap.parse_args(argv)
    try:
        request = build_request(Path(a.text_file).read_text())
        if not a.authorized:
            out.write(canonical({'dry_run': True, 'intent': a.intent, 'request': request}) + '\n')
            return 2
        result = send(request, a.intent, Path(a.state), a.credentials)
    except (Failure, OSError, KeyError, ValueError) as e:
        print(canonical({'error': getattr(e, 'code', type(e).__name__)}), file=sys.stderr)
        return 1
    out.write(canonical(result) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
