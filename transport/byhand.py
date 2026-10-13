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
import re
from pathlib import Path

from transport import post
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
    texts, sent = post.parts(d['text']), list(d.get('sentParts') or [])
    base = d.get('intent') or f'draft-{Path(path).stem}'
    k = len(sent)
    return k, texts[min(k, len(texts) - 1)], d['text'], sent[-1]['uri'] if sent else d.get('replyTo'), base, len(texts)


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
            and not feed.is_feed(d.get('replyTo'), st.config.origin, st.world)]


def record(st, host, reader, path, d, link, clock):
    """Record the post at `link` as the next post of the draft at `path` (`expected`), or refuse by name: `wrong_author`
    (another account's), `wrong_parent` (under another post, or its thread's root another), `already_linked`,
    `no_such_post`. -> (the draft as written now, what was recorded)."""
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
    intent = base if n == 1 else f'{base}#{k + 1}'
    one = {'uri': got['uri'], 'cid': got['cid']}
    edited = norm(said) != norm(want)
    entry = {**one, 'part': k + 1, 'intent': intent, 'text': said, 'at': int(clock()), 'link': web_link(uri),
             'recorded': post.settle(host, d, one, intent, said, k == 0), **({'edited': True, 'drafted': want} if edited else {})}
    hand = list(d.get('byHand') or []) + [entry]
    if n == 1:
        d = dict(d, posted=True, sent=one, intent=base, byHand=hand, recorded=entry['recorded'],
                 **({'text': said, 'original': d.get('original', d['text'])} if edited else {}))
    else:
        sent = list(d.get('sentParts') or []) + [one]
        done = len(sent) == n
        d = dict(d, sentParts=sent, intent=base, byHand=hand, posted=done, **({'sent': one} if done else {}),
                 **({'edited': True} if edited or d.get('edited') else {}))
        if done:
            d['recorded'] = {'status': 'recorded', 'parts': n} if all((p['recorded'] or {}).get('status') != 'error' for p in hand) else \
                {'status': 'error', 'message': 'a part is not recorded yet'}
    st.write(path, d)
    return d, entry


def find(st, host, reader, clock, limit=50):
    """The posting account's newest posts (`listRecords`, read only) that no draft holds, oldest first, against the
    waiting drafts: one under the post a draft's next part goes under, whose text is exactly that part's (or the whole
    draft's), is linked (`record`); one under it whose text is near (`NEAR`) is offered. -> {linked, offers}."""
    got = reader.get('com.atproto.repo.listRecords', repo=st.config.poster, collection=POST, limit=limit)
    records = sorted(got.get('records') or [], key=lambda r: ((r.get('value') or {}).get('createdAt') or '', r.get('uri', '')))
    done, offers, held = [], [], linked(st)
    for r in records:
        if r.get('uri') in held:
            continue
        value = r.get('value') or {}
        parent, said = ((value.get('reply') or {}).get('parent') or {}).get('uri'), norm(value.get('text'))
        best = None
        for path, d in waiting(st):
            k, want, whole, under, _, n = expected(path, d)
            if parent != under:
                continue
            if said in (norm(want), norm(whole) if k == 0 else None):
                best = ('exact', path, d)
                break
            near = difflib.SequenceMatcher(None, said, norm(want)).ratio()
            if near >= NEAR and (best is None or near > best[3]):
                best = ('near', path, d, near)
        if best and best[0] == 'exact':
            try:
                _, entry = record(st, host, reader, best[1], best[2], r['uri'], clock)
            except Failure as f:  # its thread's root another, say: offered, never linked
                offers.append({'draft': best[1].stem, 'uri': r['uri'], 'link': web_link(r['uri']), 'text': value.get('text') or '', 'like': 1.0, 'why': str(f)})
                continue
            done.append({'draft': best[1].stem, 'uri': r['uri'], 'link': entry['link'], 'part': entry['part']})
            held[r['uri']] = best[1].stem
        elif best:
            offers.append({'draft': best[1].stem, 'uri': r['uri'], 'link': web_link(r['uri']), 'text': value.get('text') or '', 'like': round(best[3], 2)})
    return {'linked': done, 'offers': offers}
