"""The ONLY writer (`python3 -m transport post`). To delve.town, without --i-am-ember-and-authorize-posting it prints the
exact request it would send and exits 2 without reading credentials or touching the network. A world whose bridge row
is a Zulip channel, the owner's own, is posted to at once.
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from transport.atproto.sign import tid
from transport.delve import POST as COLLECTION, Client, Failure, canonical, http_transport
from transport.host import CLOCK
from transport.observe import MENTION, wiki_target

FLAG = '--i-am-ember-and-authorize-posting'
MAX_TEXT = 64 * 1024


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


def posts(host, source='delve'):
    """This hour's posting for `source` as the host counts it (`world-status.posts`): {source, used, quota?, next?}."""
    got = host.send({'op': 'world-status'})
    return next((s for s in (got.get('posts') or {}).get('sources') or [] if s.get('source') == source), {'source': source})


def reserve(host, intent, source):
    """The host admits one post of `intent` (world-post-reserve; a retry of the intent is the same reservation, no second
    slot). A delve.town post past the hour's quota is refused `rate_limited`."""
    got = host.send({'op': 'world-post-reserve', 'principal': CLOCK, 'intent': intent, 'source': source})
    if got.get('status') == 'refused':
        raise Failure('rate_limited', f"the host's quota; next at clock {got.get('next')}")
    if got.get('status') != 'reserved':
        raise Failure('reserve_failed', str(got.get('message', got.get('status'))))
    return got


def slot_record(text):
    """`principal:intent` -> {principal, intent}, split at the last colon (DIDs contain colons)."""
    principal, sep, intent = (text or '').rpartition(':')
    if not (principal and sep and intent):
        raise Failure('bad_slot', 'expected principal:intent')
    return {'principal': principal, 'intent': intent}


def draft_object(d):
    """The object a draft addresses: a reply's `object`, a publication's `publication.object`."""
    return d.get('object') or (d.get('publication') or {}).get('object')


def record_posted(host, result, obj, slot=None, target=None, intent=None):
    """Tell the host a confirmed post exists: world-posted {principal, uri, cid, object, slot?, page?, section?},
    as the clock principal serve opens the world with (the only one that may confirm posts).
    `target` is the (page, section) an agentwiki post carried, so a reply to it routes to the page's object."""
    req = {'op': 'world-posted', 'principal': CLOCK, 'uri': result['uri'], 'cid': result['cid'], 'object': obj,
           **({'intent': intent} if intent else {})}  # the intent settles its reservation
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


def ledger(st, intent):
    """The posting ledger, one file per intent: what was fixed before the network was touched (the record key, or Zulip's
    anchor) and what came back. A retry reads it, so an intent is posted at most once and its quota slot taken once."""
    path = st.posting / (hashlib.sha256(intent.encode()).hexdigest()[:24] + '.json')
    return path, (json.loads(path.read_text()) if path.exists() else None)


def send(request, intent, st, host, client=None, now=time.time):
    """Network write, at most once per intent: the host reserves it first (`delve`, counted against its quota); the record
    key is fixed in the ledger before the first attempt, and a retry that finds a record under it adopts that record. The
    reservation is released only when the post certainly did not leave (the credentials unreadable). Credentials go only to
    the fixed PDS via Client."""
    path, got = ledger(st, intent)
    if got and got.get('result'):
        return got['result']
    client, found, fresh = client or Client(http_transport, allow_write=True), None, got is None
    if fresh:
        reserve(host, intent, 'delve')
    try:
        cred = json.loads(Path(st.config.credentials).expanduser().read_text())
    except (OSError, ValueError):
        if fresh:
            host.send({'op': 'world-post-release', 'principal': CLOCK, 'intent': intent, 'reason': 'credentials unreadable'})
        raise
    if fresh:
        got = {'intent': intent, 'rkey': tid(int(now() * 1e6), int(hashlib.sha256(intent.encode()).hexdigest()[:4], 16) & 1023)}
        st.write(path, got)
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
    st.write(path, dict(got, result=result))
    return result


def unsend(uri, credentials, client=None):
    """Delete a post we made: a `town.delve.feed.post` record in the session's own repo, never anyone else's."""
    repo, _, rest = uri.removeprefix('at://').partition('/')
    collection, _, rkey = rest.partition('/')
    client = client or Client(http_transport, allow_write=True)
    cred = json.loads(Path(credentials).expanduser().read_text())
    session = client.write('com.atproto.server.createSession', {'identifier': cred['identifier'], 'password': cred['password']})
    if not uri.startswith('at://') or repo != session['did'] or collection != COLLECTION or not rkey:
        raise Failure('not_ours', uri)
    client.write('com.atproto.repo.deleteRecord', {'repo': repo, 'collection': COLLECTION, 'rkey': rkey}, token=session['accessJwt'])


def record_sent(st, host):
    """Tell the host of every posted draft it has not confirmed: registration is retried on its own, never by posting
    again. -> the drafts recorded now."""
    done = []
    for path, d in st.drafts():
        obj = draft_object(d)
        if d.get('posted') and d.get('sent') and obj and (d.get('recorded') or {}).get('status') in (None, 'error'):
            got = record_posted(host, d['sent'], obj, slot_record(d['slot']) if d.get('slot') else None, wiki_target(d['text']), d.get('intent'))
            st.write(path, dict(d, recorded=got))
            done += [path.name] if got.get('status') != 'error' else []
    return done


def post_draft(path, st, host, text=None, reader=None, client=None, intent=None, object=None):
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
    intent = intent or f'draft-{path.stem}'
    result = send(request, intent, st, host, client=client)
    d = dict(d, text=body, posted=True, sent=result, intent=intent, **({} if body == d['text'] else {'original': d.get('original', d['text'])}))
    st.write(path, d)  # sent, whatever the host says next: record_sent retries the registration alone
    object = object or draft_object(d)
    if object:
        result = dict(result, recorded=record_posted(host, result, object, slot, wiki_target(body), intent))
        st.write(path, dict(d, recorded=result['recorded']))
    return result


def command(st, a, out, client=None, zulip=None):
    """`post`: one post, at most once per its intent, recorded with the host for `--object`."""
    try:
        d = {}
        if a.draft:
            d = json.loads(Path(a.draft).read_text())
            if d.get('posted'):
                raise Failure('draft_already_posted')
        reply_to, obj, slot = a.reply_to or d.get('replyTo'), a.object or draft_object(d), a.slot or d.get('slot')
        if bool(a.text_file) + bool(a.wiki_page) + bool(a.wiki_edit) + bool(a.draft) != 1 or (not (a.text_file or a.draft) and not a.body_file):
            raise Failure('choose_one_of', '--text-file | --draft | --wiki-page/--wiki-edit with --body-file')
        text = d['text'] if a.draft else Path(a.text_file).read_text() if a.text_file else \
            wiki_text('wiki' if a.wiki_page else 'edit', a.wiki_page or a.wiki_edit, Path(a.body_file).read_text())
        for h in a.mention:
            text = text.rstrip('\n') + f'\n@{h.lstrip("@")}'
        slot, host, row = slot_record(slot) if slot else None, st.host(), st.bridge()
        try:
            if row['transport'] == 'zulip':  # the owner's own Zulip: no flag and no quota, a topic of the world's channel
                from transport import zulip as z
                zc = zulip or z.Client(row['zuliprc'])
                if not a.topic:
                    raise Failure('zulip_post_needs_topic')
                result = z.deliver(st, host, zc, row['channel'], a.topic, text.replace('<bot name>', zc.me()['full_name']), a.intent, obj, slot)
            else:
                if (a.wiki_edit or (wiki_target(text) or ('', ''))[1]) and not reply_to:
                    raise Failure('wiki_edit_needs_reply_to', 'reply to the page post')
                if a.authorized and not obj:
                    raise Failure('live_post_needs_object', 'world-posted {object, intent} settles the reservation; without it the post stays counted')
                if a.authorized and a.draft:  # posted, recorded and marked posted in one
                    out.write(canonical(post_draft(a.draft, st, host, text=text, reader=client, intent=a.intent, object=obj)) + '\n')
                    return 0
                reader = client or Client(http_transport)
                request = build_request(text, reply_ref(reader, reply_to) if reply_to else None, mention_facets(reader, text))
                if not a.authorized:
                    plan = {'dry_run': True, 'intent': a.intent, 'quota': posts(host) if st.host_socket.exists() else None, 'request': request}
                    if obj:
                        plan['record'] = {'op': 'world-posted', 'object': obj, 'slot': slot}
                        if wiki_target(text):
                            plan['record']['page'], plan['record']['section'] = wiki_target(text)
                    out.write(canonical(plan) + '\n')
                    return 2
                result = send(request, a.intent, st, host)
                if obj:
                    result['recorded'] = record_posted(host, result, obj, slot, wiki_target(text), a.intent)
        finally:
            host.close()
    except (Failure, OSError, KeyError, ValueError) as e:
        print(canonical({'error': getattr(e, 'code', type(e).__name__), 'detail': getattr(e, 'detail', '')}), file=sys.stderr)
        return 1
    out.write(canonical(result) + '\n')
    return 0
