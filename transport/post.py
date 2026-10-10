#!/usr/bin/env python3
"""The ONLY writer. Without --i-am-ember-and-authorize-posting it prints the exact
request it would send and exits 2 without reading credentials or touching the network.
"""
import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from transport.delve import Client, Failure, canonical, http_transport
from transport.hostd import CLOCK
from transport.observe import MENTION

FLAG = '--i-am-ember-and-authorize-posting'
COLLECTION = 'town.delve.feed.post'
MAX_TEXT = 64 * 1024
LIMIT, WINDOW = 16, 3600
TID = '234567abcdefghijklmnopqrstuvwxyz'
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
    """The hourly cap: the host's world-status `postQuota` when it has one, else this file's constant."""
    got = host.send({'op': 'world-status'}) if host else {}
    if isinstance(got.get('postQuota'), int):
        return got['postQuota'], 'host'
    return LIMIT, 'constant'


def wiki_target(text):
    """(page, section) of an agentwiki post: `wiki: <page>` is the whole page (section ""), `edit: <page> › <section>`
    one section; None for any other text."""
    head = text.split('\n', 1)[0]
    if head.startswith('wiki: ') and head[6:].strip():
        return head[6:].strip(), ''
    if head.startswith('edit: ') and ' › ' in head:
        page, section = head[6:].split(' › ', 1)
        if page.strip() and section.strip():
            return page.strip(), section.strip()
    return None


def slot_record(text):
    """`principal:intent` -> {principal, intent}, split at the last colon (DIDs contain colons)."""
    principal, sep, intent = (text or '').rpartition(':')
    if not (principal and sep and intent):
        raise Failure('bad_slot', 'expected principal:intent')
    return {'principal': principal, 'intent': intent}


def draft_object(d):
    """The object a draft addresses: a reply's `object`, a publication's `publication.object`."""
    return d.get('object') or (d.get('publication') or {}).get('object')


def record_posted(host, result, obj, slot=None, target=None):
    """Tell the host a confirmed post exists: world-posted {principal, uri, cid, object, slot?, page?, section?},
    as the clock principal hostd opens the world with (the only one that may confirm posts).
    `target` is the (page, section) an agentwiki post carried, so a reply to it routes to the page's object."""
    req = {'op': 'world-posted', 'principal': CLOCK, 'uri': result['uri'], 'cid': result['cid'], 'object': obj}
    if slot is not None:
        req['slot'] = slot
    if target is not None:
        req['page'], req['section'] = target
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


def ledger(state, intent):
    """The posting ledger, one file per intent: what was fixed before the network was touched (the record key, or Zulip's
    anchor) and what came back. A retry reads it, so an intent is posted at most once and its quota slot taken once."""
    path = Path(state) / 'posting' / (hashlib.sha256(intent.encode()).hexdigest()[:24] + '.json')
    return path, (json.loads(path.read_text()) if path.exists() else None)


def tid(micros, clock):
    """An AT Protocol TID: 53 bits of microseconds and 10 of clock id, base32-sortable."""
    n, out = (micros << 10) | (clock & 1023), ''
    for _ in range(13):
        out, n = TID[n & 31] + out, n >> 5
    return out


def send(request, intent, state, credentials, client=None, limit=LIMIT, now=time.time):
    """Network write, at most once per intent: the record key is fixed in the ledger before the first attempt, and a
    retry that finds a record under it adopts that record. Credentials go only to the fixed PDS via Client."""
    from transport.bridge import write_atomic
    path, got = ledger(state, intent)
    if got and got.get('result'):
        return got['result']
    client, found, fresh = client or Client(http_transport, allow_write=True), None, got is None
    if fresh:
        take_slot(Path(state), now(), limit)
        got = {'intent': intent, 'rkey': tid(int(now() * 1e6), int(hashlib.sha256(intent.encode()).hexdigest()[:4], 16))}
        write_atomic(path, got)
    cred = json.loads(Path(credentials).expanduser().read_text())
    session = client.write('com.atproto.server.createSession',
                           {'identifier': cred['identifier'], 'password': cred['password']})
    if not fresh:  # an earlier attempt may have landed with its reply lost
        try:
            found = client.record(f"at://{session['did']}/{COLLECTION}/{got['rkey']}")
        except Failure as f:
            if 'RecordNotFound' not in f.detail:
                raise
    if found is None:
        found = client.write('com.atproto.repo.createRecord', dict(request['body'], repo=session['did'], rkey=got['rkey']),
                             token=session['accessJwt'])
    result = {'uri': found['uri'], 'cid': found['cid']}
    write_atomic(path, dict(got, result=result))
    return result


def record_sent(state, host):
    """Tell the host of every posted draft it has not confirmed: registration is retried on its own, never by posting
    again. -> the drafts recorded now."""
    from transport.bridge import write_atomic
    done = []
    for path in sorted((Path(state) / 'outbox').glob('*.json')):
        d = json.loads(path.read_text())
        obj = draft_object(d)
        if d.get('posted') and d.get('sent') and obj and (d.get('recorded') or {}).get('status') in (None, 'error'):
            got = record_posted(host, d['sent'], obj, slot_record(d['slot']) if d.get('slot') else None, wiki_target(d['text']))
            write_atomic(path, dict(d, recorded=got))
            done += [path.name] if got.get('status') != 'error' else []
    return done


def post_draft(path, state, host, credentials=CREDENTIALS, text=None, reader=None, client=None, intent=None, object=None):
    """Post a bridge outbox draft (its replyTo, object and slot; `text` replaces its text), record it with the host, and
    mark it posted: what `post --draft ... --i-am-ember-and-authorize-posting` does, callable. -> the post result."""
    path = Path(path)
    d = json.loads(path.read_text())
    if d.get('posted') or d.get('skipped'):
        raise Failure('draft_already_posted')
    body = d['text'] if text is None else text
    reader = reader or Client(http_transport)
    slot = slot_record(d['slot']) if d.get('slot') else None
    request = build_request(body, reply_ref(reader, d['replyTo']) if d.get('replyTo') else None, mention_facets(reader, body))
    limit, _ = quota_limit(host)
    result = send(request, intent or f'draft-{path.stem}', Path(state), credentials, client=client, limit=limit)
    from transport.bridge import write_atomic
    d = dict(d, text=body, posted=True, sent=result, **({} if body == d['text'] else {'original': d.get('original', d['text'])}))
    write_atomic(path, d)  # sent, whatever the host says next: record_sent retries the registration alone
    object = object or draft_object(d)
    if object:
        result = dict(result, recorded=record_posted(host, result, object, slot, wiki_target(body)))
        write_atomic(path, dict(d, recorded=result['recorded']))
    return result


def main(argv=None, out=None, client=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='post.py')
    ap.add_argument('--state', required=True)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('post')
    p.add_argument('--text-file')
    p.add_argument('--draft', metavar='FILE', help='a bridge outbox draft: its text, reply-to, object and slot')
    p.add_argument('--wiki-page', metavar='TITLE')
    p.add_argument('--wiki-edit', metavar='"TITLE > SECTION"')
    p.add_argument('--body-file')
    p.add_argument('--reply-to', metavar='AT_URI', help='thread under this post (its cid is read with getRecord)')
    p.add_argument('--intent', required=True)
    p.add_argument('--credentials', default=CREDENTIALS)
    p.add_argument('--mention', action='append', default=[], metavar='HANDLE', help='deliberately ping this handle (appended to the text)')
    p.add_argument('--host-socket', metavar='PATH', help='hostd socket: read the posting quota and record posts')
    p.add_argument('--object', '--record', dest='record', metavar='OBJECT', help='the object this card addresses: after a confirmed post, world-posted is called for it (needs --host-socket)')
    p.add_argument('--slot', metavar='PRINCIPAL:INTENT', help='the slot the post settles, as principal:intent')
    p.add_argument(FLAG, dest='authorized', action='store_true', default=False)
    a = ap.parse_args(argv)
    try:
        if a.draft:
            d = json.loads(Path(a.draft).read_text())
            if d.get('posted'):
                raise Failure('draft_already_posted')
            a.reply_to, a.record, a.slot = a.reply_to or d.get('replyTo'), a.record or draft_object(d), a.slot or d.get('slot')
        if bool(a.text_file) + bool(a.wiki_page) + bool(a.wiki_edit) + bool(a.draft) != 1 or (not (a.text_file or a.draft) and not a.body_file):
            raise Failure('choose_one_of', '--text-file | --wiki-page/--wiki-edit with --body-file')
        if a.draft:
            text = d['text']
        elif a.text_file:
            text = Path(a.text_file).read_text()
        else:
            text = wiki_text('wiki' if a.wiki_page else 'edit', a.wiki_page or a.wiki_edit, Path(a.body_file).read_text())
        if (a.wiki_edit or (wiki_target(text) or ('', ''))[1]) and not a.reply_to:
            raise Failure('wiki_edit_needs_reply_to', 'reply to the page post')
        for h in a.mention:
            text = text.rstrip('\n') + f'\n@{h.lstrip("@")}'
        if a.record and not a.host_socket:
            raise Failure('record_needs_journal')
        slot = slot_record(a.slot) if a.slot else None
        reader = client or Client(http_transport)
        reply = reply_ref(reader, a.reply_to) if a.reply_to else None
        request = build_request(text, reply, mention_facets(reader, text))
        host = None
        if a.host_socket:
            from transport.hostproc import HostClient
            host = HostClient(a.host_socket)
        try:
            limit, source = quota_limit(host)
            if not a.authorized:
                plan = {'dry_run': True, 'intent': a.intent, 'quota': {'limit': limit, 'source': source}, 'request': request}
                if a.record:
                    plan['record'] = {'op': 'world-posted', 'object': a.record, 'slot': slot}
                    if wiki_target(text):
                        plan['record']['page'], plan['record']['section'] = wiki_target(text)
                out.write(canonical(plan) + '\n')
                return 2
            result = send(request, a.intent, Path(a.state), a.credentials, limit=limit)
            if a.record:
                result['recorded'] = record_posted(host, result, a.record, slot, wiki_target(text))
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
