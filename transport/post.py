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

from transport.delve import Client, Failure, canonical, http_transport
from transport.observe import MENTION

FLAG = '--i-am-ember-and-authorize-posting'
COLLECTION = 'town.delve.feed.post'
MAX_TEXT = 64 * 1024
LIMIT, WINDOW = 16, 3600
CREDENTIALS = '~/.config/delvetown/credentials.json'


def reply_ref(client, parent_uri):
    """AT Protocol reply refs: parent is the post replied to; root is the parent's own root, or the parent."""
    got = client.record(parent_uri)
    parent = {'uri': got['uri'], 'cid': got['cid']}
    root = (got.get('value') or {}).get('reply', {}).get('root') or parent
    return {'root': {'uri': root['uri'], 'cid': root['cid']}, 'parent': parent}


def wiki_text(kind, title, body):
    return f'{kind}: {title}\n\n{body}'


def mention_facets(client, text):
    """One mention facet per @handle in the text (byte offsets), resolved by the PDS. Unresolvable handles get none."""
    facets = []
    for m in MENTION.finditer(text):
        try:
            did = client.resolve_handle(m[1].lower()).get('did')
        except Failure:
            continue
        if did:
            start = len(text[:m.start()].encode())
            facets.append({'$type': 'town.delve.richtext.facet', 'index': {'byteStart': start, 'byteEnd': start + len(m[0].encode())},
                           'features': [{'$type': 'town.delve.richtext.facet#mention', 'did': did}]})
    return facets


def quota_limit(host):
    """The hourly cap: the host's world-status `postQuota` when it has one, else this file's constant.
    TODO(host quota object): the host will own this as a journaled object."""
    got = host.send({'op': 'world-status'}) if host else {}
    if isinstance(got.get('postQuota'), int):
        return got['postQuota'], 'host'
    return LIMIT, 'constant'


def record_posted(host, result, obj, slot=None):
    """Tell the host a confirmed post exists: world-posted {principal, uri, cid, object, slot?}."""
    req = {'op': 'world-posted', 'principal': result['uri'].split('/')[2], 'uri': result['uri'], 'cid': result['cid'], 'object': obj}
    if slot is not None:
        req['slot'] = slot
    return host.send(req)


def build_request(text, reply=None, facets=None):
    if not text.strip():
        raise Failure('empty_post')
    if len(text.encode()) > MAX_TEXT:
        raise Failure('post_body_too_large')
    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    record = {'$type': COLLECTION, 'text': text, 'createdAt': now}
    if reply:
        record['reply'] = reply
    if facets:
        record['facets'] = facets
    return {'method': 'POST', 'nsid': 'com.atproto.repo.createRecord',
            'body': {'repo': '<session did>', 'collection': COLLECTION, 'record': record}}


def take_slot(state, now, limit=LIMIT):
    """Record one write against the hourly budget, or refuse. Locked, persisted."""
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(state / 'post-log.json', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            stamps = [t for t in json.loads(f.read() or '[]') if now - t < WINDOW]
        except ValueError:
            stamps = []
        if len(stamps) >= limit:
            raise Failure('rate_limited', f'{limit} writes per hour')
        f.seek(0)
        f.truncate()
        f.write(json.dumps(stamps + [now]))


def send(request, intent, state, credentials, client=None, limit=LIMIT):
    """Network write. Credentials go only to the fixed PDS via Client."""
    client = client or Client(http_transport, allow_write=True)
    take_slot(state, time.time(), limit)
    cred = json.loads(Path(credentials).expanduser().read_text())
    session = client.write('com.atproto.server.createSession',
                           {'identifier': cred['identifier'], 'password': cred['password']})
    body = dict(request['body'], repo=session['did'])
    result = client.write('com.atproto.repo.createRecord', body, token=session['accessJwt'])
    with open(state / 'post-log.jsonl', 'a') as log:
        log.write(canonical({'intent': intent, 'uri': result.get('uri'), 'cid': result.get('cid')}) + '\n')
    return result


def main(argv=None, out=None, client=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='post.py')
    ap.add_argument('--state', required=True)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('post')
    p.add_argument('--text-file')
    p.add_argument('--wiki-page', metavar='TITLE')
    p.add_argument('--wiki-edit', metavar='"TITLE > SECTION"')
    p.add_argument('--body-file')
    p.add_argument('--reply-to', metavar='AT_URI', help='thread under this post (its cid is read with getRecord)')
    p.add_argument('--intent', required=True)
    p.add_argument('--credentials', default=CREDENTIALS)
    p.add_argument('--mention', action='append', default=[], metavar='HANDLE', help='deliberately ping this handle (appended to the text)')
    p.add_argument('--host-socket', metavar='PATH', help='hostd socket: read the posting quota and record posts')
    p.add_argument('--journal', help='instead of a socket: open this journal in-process (stop the stack first)')
    p.add_argument('--record', metavar='OBJECT', help='after a confirmed post, call world-posted for this object (needs --host-socket)')
    p.add_argument('--slot')
    p.add_argument(FLAG, dest='authorized', action='store_true', default=False)
    a = ap.parse_args(argv)
    try:
        if bool(a.text_file) + bool(a.wiki_page) + bool(a.wiki_edit) != 1 or (not a.text_file and not a.body_file):
            raise Failure('choose_one_of', '--text-file | --wiki-page/--wiki-edit with --body-file')
        if a.wiki_edit and not a.reply_to:
            raise Failure('wiki_edit_needs_reply_to', 'reply to the page post')
        if a.text_file:
            text = Path(a.text_file).read_text()
        else:
            text = wiki_text('wiki' if a.wiki_page else 'edit', a.wiki_page or a.wiki_edit, Path(a.body_file).read_text())
        for h in a.mention:
            text = text.rstrip('\n') + f'\n@{h.lstrip("@")}'
        if a.record and not (a.host_socket or a.journal):
            raise Failure('record_needs_journal')
        reader = client or Client(http_transport)
        reply = reply_ref(reader, a.reply_to) if a.reply_to else None
        request = build_request(text, reply, mention_facets(reader, text))
        host = None
        if a.host_socket or a.journal:
            from transport.hostproc import Host, HostClient
            host = Host(a.journal) if a.journal else HostClient(a.host_socket)
        try:
            limit, source = quota_limit(host)
            if not a.authorized:
                plan = {'dry_run': True, 'intent': a.intent, 'quota': {'limit': limit, 'source': source}, 'request': request}
                if a.record:
                    plan['record'] = {'op': 'world-posted', 'object': a.record, 'slot': a.slot}
                out.write(canonical(plan) + '\n')
                return 2
            result = send(request, a.intent, Path(a.state), a.credentials, limit=limit)
            if a.record:
                result['recorded'] = record_posted(host, result, a.record, a.slot)
        finally:
            if host:
                host.close()
    except (Failure, OSError, KeyError, ValueError) as e:
        print(canonical({'error': getattr(e, 'code', type(e).__name__)}), file=sys.stderr)
        return 1
    out.write(canonical(result) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
