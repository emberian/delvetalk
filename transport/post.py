"""The ONLY writer (`python3 -m transport post`). To delve.town, without --i-am-ember-and-authorize-posting it prints the
exact request it would send and exits 2 without reading credentials or touching the network. A world whose bridge row
is a Zulip channel, the owner's own, is posted to at once.
"""
import contextlib
import fcntl
import hashlib
import json
import sys
import time
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

from transport.atproto.sign import tid
from transport.delve import POST as COLLECTION, Client, Failure, canonical, http_transport
from transport.host import CLOCK
from transport.observe import MENTION, wiki_target

FLAG = '--i-am-ember-and-authorize-posting'
MAX_TEXT = 64 * 1024
CLIP = 1400  # what a reader of the town reads of one post (world/lib/Card.obend `post()`)
NOTE = 64  # room each part keeps for its number, and for saying when the next part follows


def holds(st):
    """What one post holds where a world's drafts go: on a feed-only town (`State.feed_only`) its `card_room` (config),
    the room its cards are shown in, so an answer is posted whole up to it; where posts go to delve.town or Zulip, CLIP."""
    return st.config.room if st.feed_only() else CLIP


def reply_ref(client, parent_uri):
    """AT Protocol reply refs: parent is the post replied to; root is the parent's own root, or the parent."""
    got = client.record(parent_uri)
    parent = {'uri': got['uri'], 'cid': got['cid']}
    root = (got.get('value') or {}).get('reply', {}).get('root') or parent
    return {'root': {'uri': root['uri'], 'cid': root['cid']}, 'parent': parent}


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


def posts(status, source='delve'):
    """This hour's posting for `source` as the host counts it, from a `world-status` reply: {source, used, quota?, next?}."""
    return next((s for s in (status.get('posts') or {}).get('sources') or [] if s.get('source') == source), {'source': source})


def reserve(host, intent, source, resident=None):
    """The host admits one post of `intent` (world-post-reserve; a retry of the intent is the same reservation, no second
    slot), counted against `resident`'s share of the hour when it answers one. A delve.town post past the hour's quota
    or the resident's share is refused `rate_limited`."""
    got = host.send({'op': 'world-post-reserve', 'principal': CLOCK, 'intent': intent, 'source': source, **({'for': resident} if resident else {})})
    if got.get('status') == 'refused':
        raise Failure('rate_limited', f"the host's quota; next at clock {got.get('next')}")
    if got.get('status') != 'reserved':
        raise Failure('reserve_failed', str(got.get('message', got.get('status'))))
    return got


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
    got = host.send(req)
    return {**got, 'final': True} if got.get('status') == 'error' and not got.get('class') else got


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


@contextlib.contextmanager
def held(st):
    """The posting ledger held by this process alone, from an intent's first read to its last write: two posts of one
    intent at once are one post (another waits, then finds the first's record)."""
    st.posting.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(st.posting / '.lock', 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def ledger(st, intent):
    """The posting ledger, one file per intent: what was fixed before the network was touched (the record key, or Zulip's
    anchor) and what came back. A retry reads it, so an intent is posted at most once and its quota slot taken once."""
    path = st.posting / (hashlib.sha256(intent.encode()).hexdigest()[:24] + '.json')
    return path, (json.loads(path.read_text()) if path.exists() else None)


def answering(d):
    """The resident a draft answers, whose share of the hour its posts count against: its author, unless the hand
    wrote it (a spell the hand spoke, the morning card, an invitation) or it is a publication."""
    return None if d.get('hand') or 'publication' in d else d.get('principal')


def send(request, intent, st, host, client=None, now=time.time, resident=None):
    """Network write, at most once per intent: the host reserves it first (`delve`, counted against its quota); the record
    key is fixed in the ledger before the first attempt, and a retry that finds a record under it adopts that record. The
    reservation is released only when the post certainly did not leave (the credentials unreadable). Credentials go only to
    the fixed PDS via Client."""
    with held(st):
        path, got = ledger(st, intent)
        if got and got.get('result'):
            return got['result']
        client, found, fresh = client or Client(http_transport, allow_write=True), None, got is None
        if fresh:
            reserve(host, intent, 'delve', resident)
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


def record_writer(st, client=None, expected_did=None):
    """-> write(collection, rkey, value): put a record or delete it (None) in the session's own repo;
    never a feed post or host post quota. One session, made at the first write unless `expected_did`
    requires an immediate authority check. Credentials go only to the fixed PDS via Client."""
    client, session = client or Client(http_transport, allow_write=True), {}

    def authenticate():
        if not session:
            cred = json.loads(Path(st.config.credentials).expanduser().read_text())
            got = client.write('com.atproto.server.createSession', {'identifier': cred['identifier'], 'password': cred['password']})
            if expected_did is not None and got.get('did') != expected_did:
                raise Failure('lexicon_authority', f"session DID {got.get('did')!r} is not {expected_did}")
            session.update(got)

    if expected_did is not None:
        authenticate()

    def write(collection, rkey, value):
        if collection == COLLECTION:
            raise Failure('not_a_mirror_record', 'a feed post is posted, never mirrored')
        authenticate()
        where = {'repo': session['did'], 'collection': collection, 'rkey': rkey}
        if value is None:
            return client.write('com.atproto.repo.deleteRecord', where, token=session['accessJwt'])
        return client.write('com.atproto.repo.putRecord', {**where, 'record': value, 'validate': False}, token=session['accessJwt'])
    return write


def settle(host, d, one, intent, said, first):
    """A post the owner made by hand (transport/byhand.py), told to the host as `send` and `record_posted` tell one made
    here: its reservation under `intent`, against the hour and the resident it answers, then `world-posted` for the
    draft's object. The post has left already, so a full hour is no refusal of it: -> the host's answer, or an error the
    bridge's next run (`record_sent`) asks again."""
    try:
        reserve(host, intent, 'delve', answering(d))
    except Failure as f:
        return {'status': 'error', 'message': f'{f.code}: {f.detail}'}
    obj = draft_object(d)
    return record_posted(host, one, obj, d.get('slot'), wiki_target(said) if first else None, intent) if obj else {'status': 'reserved'}


def sent_parts(d):
    """The confirmed posts a draft holds, including a single post."""
    distinct = {}
    for one in list(d.get('sentParts') or []) + list(d.get('byHand') or []) + ([d['sent']] if d.get('sent') else []):
        if one.get('uri'):
            distinct.setdefault(one['uri'], one)
    return list(distinct.values())


def summarize(d):
    """Derive completion and registration from the durable part records."""
    sent = d['sentParts']
    d['posted'] = len(sent) == len(d['frozenParts'])
    if d['posted']:
        d['sent'] = {k: sent[-1][k] for k in ('uri', 'cid')}
    manual = {p['uri'] for p in d.get('byHand') or []}
    if manual or any(p.get('link') for p in sent):
        d['byHand'] = [p for p in sent if p.get('link') or p['uri'] in manual]
    if sent:
        if len(d['frozenParts']) == 1:
            d['recorded'] = sent[0].get('recorded') or {'status': 'error', 'message': 'a part is not recorded yet'}
        else:
            d['recorded'] = {'status': 'recorded', 'parts': len(sent)} if all(registered(p) for p in sent) else {'status': 'error', 'message': 'a part is not recorded yet'}
    return d


def registered(one):
    """Whether a sent part's registration is settled: recorded, or refused by the host (`final`), which asking again
    never changes; a host that did not answer (a `class` of the transport's: timeout, unavailable) is asked again."""
    got = one.get('recorded') or {}
    return got.get('status') in ('posted', 'recorded', 'reserved') or bool(got.get('final'))


def register_part(d, one, host):
    if one.get('link') or one in (d.get('byHand') or []):
        return settle(host, d, one, one['intent'], one['text'], one['part'] == 1)
    obj = draft_object(d)
    return record_posted(host, one, obj, d.get('slot'), wiki_target(one['text']) if one['part'] == 1 else None, one['intent']) if obj else {'status': 'reserved'}


def record_sent(st, host):
    """Retry each sent part's registration independently of sending and thread completion."""
    done = []
    for path, _ in st.drafts():
        with st.draft_lock(path):
            d = json.loads(path.read_text())
            if d.get('unposted') or not sent_parts(d):
                continue
            sent = sent_parts(d)
            base = d.get('intent') or f'draft-{path.stem}'
            d.update(sentParts=sent, frozenText=d.get('frozenText', d['text']), frozenParts=d.get('frozenParts') or parts(d['text']))
            changed = False
            for k, one in enumerate(sent):
                one.setdefault('part', k + 1)
                one.setdefault('intent', base if len(d['frozenParts']) == 1 else f'{base}#{k + 1}')
                one.setdefault('text', d['frozenParts'][min(k, len(d['frozenParts']) - 1)])
                if one.get('unposted') or registered(one):
                    continue
                one['recorded'] = register_part(d, one, host)
                st.write(path, summarize(d))
                changed = True
            if changed and all(registered(p) for p in sent):
                done.append(path.name)
    return done


class LineIndex:
    """Offsets, quoting prefixes and fence context computed in one pass."""
    def __init__(self, text):
        self.starts, self.ends, self.indents, self.quotes, self.delimiters, self.fences = [], [], [], [], [], []
        offset, fence = 0, None
        for line in text.splitlines(keepends=True):
            marker = line.lstrip(' \t').rstrip('\r\n')
            self.starts.append(offset)
            self.ends.append(offset + len(line.rstrip('\r\n')))
            self.indents.append(line[:len(line) - len(line.lstrip(' \t'))])
            self.quotes.append(line.lstrip().startswith('>'))
            self.delimiters.append(marker.startswith('```'))
            self.fences.append(fence)
            if self.delimiters[-1]:
                fence = None if fence else (marker if marker[3:].strip() else None)
            offset += len(line)
        self.starts.append(offset)
        self.ends.append(offset)
        self.indents.append('')
        self.quotes.append(False)
        self.delimiters.append(False)
        self.fences.append(fence)

    def at(self, offset):
        return bisect_right(self.starts, offset) - 1

    def fence_at(self, offset):
        k = self.at(offset)
        return self.fences[k + 1] if self.delimiters[k] and offset >= self.ends[k] else self.fences[k]


def continuation(index, start):
    k = index.at(start)
    prefix = index.fences[k] + '\n' if index.fences[k] else ''
    if start > index.starts[k]:
        indent = index.indents[k]
        prefix += ('> ' if index.quotes[k] else indent if len(indent) <= NOTE else ' ') or ' '
    return prefix


def split_point(text, index, start, available):
    end = min(len(text), start + available)
    if end < len(text):
        end = next((c for c in (text.rfind('\n\n', start, end), text.rfind('\n', start, end), text.rfind(' ', start, end)) if c >= start + available // 2), end)
    k = index.at(end)
    if index.delimiters[k] and end < index.ends[k]:
        if index.starts[k] <= start:
            raise Failure('unsafe_split', 'a fence delimiter exceeds the part limit')
        end = index.starts[k]
    return end


def close_fence(index, end):
    return '\n```' if index.fence_at(end) else ''


def next_chunk(text, end, line_start):
    start = end
    while start < len(text) and text[start] == '\n':
        start += 1
    return start + 1 if end < len(text) and text[end] == ' ' and end > line_start else start


def parts(text, limit=CLIP):
    """Number bounded parts, preserving line indentation and literal fence context at every boundary."""
    if len(text.encode()) > MAX_TEXT:
        raise Failure('post_body_too_large')
    if len(text) <= limit:
        return [text]
    index, start, chunks = LineIndex(text), 0, []
    while start < len(text):
        prefix = continuation(index, start)
        available = limit - NOTE - len(prefix) - 4
        if available <= 0:
            raise Failure('unsafe_split', 'the quoting prefix exceeds the part limit')
        end = split_point(text, index, start, available)
        chunks.append(prefix + text[start:end].rstrip() + close_fence(index, end))
        start = next_chunk(text, end, index.starts[index.at(start)])
    return [f'{c}\n({k}/{len(chunks)})' for k, c in enumerate(chunks, 1)]


def room(host, source='delve', resident=None):
    """Posts the host's quota leaves this hour (and `resident`'s share of it), None when it counts none."""
    s = posts(host.send({'op': 'world-status'}), source)
    if s.get('quota') is None:
        return None
    left = max(0, s['quota'] - (s.get('used') or 0))
    return min(left, max(0, s['share'] - (s.get('residents') or {}).get(resident, 0))) if resident and s.get('share') else left


def progress(path, d, st, host, body, texts, intent, source, deliver, count=None):
    """Persist the posting plan, then each confirmed part before its registration; all channels advance here."""
    if (sent_parts(d) or d.get('frozenParts')) and body != d.get('frozenText', d['text']):
        raise Failure('partly_posted', 'its first parts are posted: the rest is the same text, never another')
    texts = d.get('frozenParts') or texts
    sent = sent_parts(d)
    if d.get('unposted') or d.get('skipped') or d.get('posted'):
        raise Failure('draft_already_posted')
    left = room(host, source, answering(d)) if source == 'delve' and len(texts) > 1 and count is None else None
    if left == 0 and not count:
        raise Failure('rate_limited', "the host's quota: no post left this hour for this reply")
    if body != d['text']:
        d.setdefault('original', d['text'])
    d.update(text=body, frozenText=d.get('frozenText', body), frozenParts=texts, intent=intent, sentParts=sent)
    st.write(path, d)
    stop = len(texts) if count is None else min(len(texts), len(sent) + count)
    for k in range(len(sent), stop):
        if left == 0 and count is None:
            break
        key = intent if len(texts) == 1 else f'{intent}#{k + 1}'
        said = texts[k]
        if source == 'delve' and count is None and left == 1 and k < len(texts) - 1:
            said = said[:said.rindex('(')] + f'({k + 1}/{len(texts)}; the next part follows when the hour turns)'
        under = sent[-1]['uri'] if sent else d.get('replyTo')
        try:
            one = deliver(said, under, key)
        except Failure as err:
            if err.code != 'rate_limited' or not sent:
                raise
            break
        entry = dict(one, part=k + 1, intent=key, source=source, text=one.get('text', said))
        sent.append(entry)
        st.write(path, summarize(d))
        entry['recorded'] = register_part(d, entry, host)
        st.write(path, summarize(d))
        left = None if left is None else left - 1
    result = {k: sent[-1][k] for k in ('uri', 'cid')} if sent else {}
    if len(texts) > 1:
        result.update(parts=len(texts), sent=len(sent))
    elif sent:
        result['recorded'] = sent[-1]['recorded']
    return result


def post_draft(path, st, host, text=None, reader=None, client=None, intent=None, object=None, zulip=None):
    """Send a locked draft through the durable progression, using its world's channel adapter."""
    path = Path(path)
    with st.draft_lock(path):
        d = json.loads(path.read_text())
        body, row = d['text'] if text is None else text, st.bridge()
        if object:
            d['object'] = object
        if row['transport'] == 'zulip':
            from transport import zulip as z
            stream, topic = z.target(d, row)
            intent = d.get('intent') or intent or f'zulip-{path.stem}'
            said = f"@**{d['replyHandle']}**\n{body}" if d.get('replyTo') and 'publication' not in d else body
            def deliver(text, under, key):
                return z.deliver(st, host, zulip or z.Client(row['zuliprc']), stream, topic, text, key)
            return progress(path, d, st, host, body, [said], intent, 'zulip', deliver)
        reader = reader or Client(http_transport)
        intent = d.get('intent') or intent or f'draft-{path.stem}'
        def deliver(said, under, key):
            return send(build_request(said, reply_ref(reader, under) if under else None, mention_facets(reader, said)), key, st, host,
                        client=client, resident=answering(d))
        return progress(path, d, st, host, body, parts(body), intent, 'delve', deliver)


def command(st, a, out, client=None, zulip=None):
    """`post`: one post, at most once per its intent, recorded with the host for `--object`. A draft is posted where its
    world lives; a text to delve.town is a dry run without the authorizing flag; to a Zulip world, a message in `--topic`."""
    try:
        d = json.loads(Path(a.draft).read_text()) if a.draft else {}
        reply_to, obj, slot = a.reply_to or d.get('replyTo'), a.object or draft_object(d), json.loads(a.slot) if a.slot else d.get('slot')
        if bool(a.text_file) == bool(a.draft):
            raise Failure('choose_one_of', '--text-file | --draft')
        text = d['text'] if a.draft else Path(a.text_file).read_text()
        for h in a.mention:
            text = text.rstrip('\n') + f'\n@{h.lstrip("@")}'
        host, row = st.host(), st.bridge()
        zulip_world = row['transport'] == 'zulip'  # the owner's own Zulip: no flag and no quota
        try:
            if d.get('posted'):
                raise Failure('draft_already_posted')
            if not zulip_world and (wiki_target(text) or ('', ''))[1] and not reply_to:  # `edit: <page> › <section>`
                raise Failure('wiki_edit_needs_reply_to', 'reply to the page post')
            if a.authorized and not obj:
                raise Failure('live_post_needs_object', 'world-posted {object, intent} settles the reservation; without it the post stays counted')
            if a.draft and (a.authorized or zulip_world):
                out.write(canonical(post_draft(a.draft, st, host, text, client, client, a.intent, obj, zulip)) + '\n')
                return 0
            if zulip_world:
                from transport import zulip as z
                zc = zulip or z.Client(row['zuliprc'])
                if not a.topic:
                    raise Failure('zulip_post_needs_topic')
                result = z.deliver(st, host, zc, row['channel'], a.topic, text.replace('<bot name>', zc.me()['full_name']), a.intent)
            else:
                reader = client or Client(http_transport)
                request = build_request(text, reply_ref(reader, reply_to) if reply_to else None, mention_facets(reader, text))
                if not a.authorized:
                    plan = {'dry_run': True, 'intent': a.intent, 'quota': posts(host.send({'op': 'world-status'})) if st.host_socket.exists() else None, 'request': request}
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
