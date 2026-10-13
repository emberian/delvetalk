"""Posting by hand (docs/POSTING.md "Posting by hand"): the owner posts a draft from his own delve.town client and gives
the hand its link; the hand reads the post back from the PDS (`getRecord`, read only), checks it is the posting account's
(config `poster`), that it answers the post the draft answers (each part of a thread under the one before), and its text
against the draft's (a difference is recorded as the owner's edit), then tells the host as the automatic path does
(`post.settle`: the reservation, then `world-posted`), so replies under it reach its card.

`find` reads the posting account's own repository (`listRecords`, read only) for posts no draft has yet: one whose text
and parent are exactly a waiting draft's is linked and said so; a near one is only offered. Nothing here can write to
delve.town: its client is `delve.Client` without `allow_write`.
"""
import difflib
import json
import re
from pathlib import Path

from transport import post
from transport.observe import instant
from transport.delve import POST, Failure

WEB = 'https://delve.town'
LINK = re.compile(r'https://(?:www\.)?delve\.town/profile/([^/?#\s]+)/post/([A-Za-z0-9._~:-]+)/?(?:[?#]\S*)?')
AT = re.compile(r'at://([^/\s]+)/([A-Za-z0-9.]+)/([A-Za-z0-9._~:-]+)')
NEAR = 0.6  # a post under the draft's parent whose text is at least this like the draft's is offered as it


def mode(st):
    """How this world's drafts leave: `zulip` (its bot posts them), `automatic` (a credential file the hand reads at a
    Post), or `by hand` (none: the owner posts each himself and gives the hand its link)."""
    if st.bridge()['transport'] == 'zulip':
        return 'zulip'
    return 'automatic' if Path(st.config.credentials).expanduser().is_file() else 'by hand'


def web_link(uri, handle=None):
    """An at:// post as delve.town shows it: `https://delve.town/profile/<handle or did>/post/<rkey>`."""
    m = AT.fullmatch(uri or '')
    return f'{WEB}/profile/{handle or m[1]}/post/{m[3]}' if m else uri


def at_uri(link, reader):
    """A delve.town post link or an at:// URI -> the post's at:// URI, a handle resolved to its DID (`resolveHandle`)."""
    link = (link or '').strip()
    m = LINK.fullmatch(link) or AT.fullmatch(link)
    if not m or (link.startswith('at://') and m[2] != POST):
        raise Failure('not_a_post_link', f'{link[:200]!r} is neither https://delve.town/profile/<handle>/post/<rkey> nor at://<did>/{POST}/<rkey>')
    who, rkey = m[1], m[3] if link.startswith('at://') else m[2]
    if not who.startswith('did:'):
        try:
            who = reader.resolve_handle(who.lower()).get('did') or ''
        except Failure:
            who = ''
        if not who:
            raise Failure('handle_unresolved', m[1])
    return f'at://{who}/{POST}/{rkey}'


def norm(text):
    """A post's text as compared: line ends and the space a client trims at each line's end and the text's ends."""
    return '\n'.join(line.rstrip() for line in (text or '').replace('\r\n', '\n').strip().split('\n'))


def expected(path, d):
    """What the next post of this draft is: (k, its text, the whole text, the post it goes under, its intent, parts),
    k counting the parts already posted (`sentParts`), the first under the post the draft answers (None: it starts
    a thread), each next under the one before; one part's intent the draft's, a thread's `<intent>#k`."""
    texts, sent = d.get('frozenParts') or post.parts(d['text']), post.sent_parts(d)
    base = d.get('intent') or f'draft-{Path(path).stem}'
    k = len(sent)
    return k, texts[min(k, len(texts) - 1)], d.get('frozenText', d['text']), sent[-1]['uri'] if sent else d.get('replyTo'), base, len(texts)


def linked(st):
    """{uri: draft id} of every post a draft became or holds as a part."""
    out = {}
    for p, d in st.drafts():
        for one in [d.get('sent') or {}] + list(d.get('sentParts') or []) + list(d.get('byHand') or []):
            if one.get('uri'):
                out[one['uri']] = p.stem
    return out


def waiting(st):
    """[(path, draft)] of the drafts a hand may post: on delve.town, not posted or skipped, with text, oldest first."""
    from transport import feed
    return [(p, d) for p, d in st.drafts() if not d.get('posted') and not d.get('skipped') and d.get('text')
            and not d.get('unposted') and not feed.is_feed(d.get('replyTo'), st.config.origin, st.world)]


def verify(st, reader, path, d, link, clock):
    """Read and check the next part's author, parent, root and edit; return evidence and the posting plan."""
    if d.get('posted'):
        raise Failure('already_posted', f'{path.stem} is posted already')
    if d.get('skipped'):
        raise Failure('skipped', f'{path.stem} was skipped; nothing of it is posted')
    uri = at_uri(link, reader)
    repo = uri.split('/')[2]
    if repo != st.config.poster:
        raise Failure('wrong_author', f'{web_link(uri)} is by {repo}, not the posting account {st.config.poster}')
    other = linked(st).get(uri)
    if other:
        raise Failure('already_linked', f'{web_link(uri)} is {other}\'s already')
    try:
        got = reader.record(uri)
    except Failure as f:
        raise Failure('no_such_post', f'{web_link(uri)}: {f.detail or f.code}') from None
    value = got.get('value') or {}
    k, want, whole, under, base, n = expected(path, d)
    said = value.get('text') or ''
    if k == 0 and n > 1 and norm(said) == norm(whole):  # the whole text as one post: the thread is that one post
        want, n = whole, 1
    reply = value.get('reply') or {}
    parent, root = (reply.get('parent') or {}).get('uri'), (reply.get('root') or {}).get('uri')
    if parent != under:
        where = f'under {web_link(parent)}' if parent else 'a thread of its own'
        should = f'under {web_link(under)}' if under else 'a thread of its own'
        raise Failure('wrong_parent', f'{web_link(uri)} is {where}; {path.stem}' + (f' part {k + 1}' if n > 1 else '') + f' goes {should}')
    if under:
        want_root = post.reply_ref(reader, under)['root']['uri']
        if root != want_root:
            raise Failure('wrong_parent', f'{web_link(uri)} names the thread {root}, not {want_root}, the thread of {web_link(under)}')
    one = {'uri': got['uri'], 'cid': got['cid'], 'text': said, 'at': int(clock()), 'link': web_link(uri)}
    if norm(said) != norm(want):
        one.update(edited=True, drafted=want)
    return one, ([whole] if n == 1 else d.get('frozenParts') or post.parts(whole)), base


def candidates(path, d, records, held):
    """Exact, unheld posts after the draft's creation, under its next parent."""
    k, want, whole, under, _, _ = expected(path, d)
    created = instant(d.get('createdAt')) if d.get('createdAt') else path.stat().st_mtime
    found = []
    for r in records:
        value = r.get('value') or {}
        try:
            after = instant(value.get('createdAt')) > created
        except (ValueError, TypeError, AttributeError):
            after = False
        if after and r.get('uri') not in held and ((value.get('reply') or {}).get('parent') or {}).get('uri') == under and norm(value.get('text')) in (norm(want), norm(whole) if k == 0 else None):
            found.append(r)
    return found


def record(st, host, reader, path, link, clock, records=None):
    """Lock and verify evidence, then let post.progress persist and register the next part."""
    path = Path(path)
    with st.draft_lock(path):
        d = json.loads(path.read_text())
        if records is not None:
            matches = candidates(path, d, records, linked(st))
            if d.get('posted') or len(matches) != 1 or matches[0]['uri'] != link:
                raise Failure('ambiguous_match')
        one, texts, base = verify(st, reader, path, d, link, clock)
        body = d.get('frozenText', d['text'])
        if len(texts) == 1 and one.get('edited'):
            d.setdefault('original', d['text'])
            body, texts = one['text'], [one['text']]
        if one.get('edited'):
            d['edited'] = True
        post.progress(path, d, st, host, body, texts, base, 'delve', lambda *args: one, count=1)
        d = json.loads(path.read_text())
        return d, d['sentParts'][-1]


def find(st, host, reader, clock, limit=50):
    """The posting account's newest posts (`listRecords`, read only) that no draft holds, oldest first, against the
    waiting drafts: one under the post a draft's next part goes under, whose text is exactly that part's (or the whole
    draft's), is linked (`record`); one under it whose text is near (`NEAR`) is offered. -> {linked, offers}."""
    got = reader.get('com.atproto.repo.listRecords', repo=st.config.poster, collection=POST, limit=limit)
    records = sorted(got.get('records') or [], key=lambda r: ((r.get('value') or {}).get('createdAt') or '', r.get('uri', '')))
    done, offers, held = [], [], linked(st)
    for path, _ in waiting(st):
        while True:
            d = json.loads(path.read_text())
            if d.get('posted') or d.get('skipped') or d.get('unposted'):
                break
            exact = candidates(path, d, records, held)
            if len(exact) != 1:
                k, want, _, under, _, _ = expected(path, d)
                for r in records:
                    value = r.get('value') or {}
                    if r.get('uri') in held or ((value.get('reply') or {}).get('parent') or {}).get('uri') != under:
                        continue
                    like = difflib.SequenceMatcher(None, norm(value.get('text')), norm(want)).ratio()
                    if like >= NEAR:
                        offers.append({'draft': path.stem, 'uri': r['uri'], 'link': web_link(r['uri']), 'text': value.get('text') or '', 'like': round(like, 2)})
                break
            r = exact[0]
            try:
                _, entry = record(st, host, reader, path, r['uri'], clock, records=records)
            except Failure as err:
                if err.code != 'ambiguous_match':
                    offers.append({'draft': path.stem, 'uri': r['uri'], 'link': web_link(r['uri']), 'text': (r.get('value') or {}).get('text') or '', 'like': 1.0, 'why': str(err)})
                break
            done.append({'draft': path.stem, 'uri': r['uri'], 'link': entry['link'], 'part': entry['part']})
            held[r['uri']] = path.stem
    return {'linked': done, 'offers': offers}
