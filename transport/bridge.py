"""Observed posts -> host turns -> reply drafts for a human to post (`python3 -m transport bridge`).

Never posts to delve.town: `post` is the only writer there. A world whose bridge row is a Zulip channel, the owner's own,
has its drafts posted by transport/zulip.py. Principals here are the observed authors' DIDs, which are UNVERIFIED.
"""
import hashlib
import ipaddress
import json
import urllib.parse
import time

from transport.delve import Client, FixtureTransport, canonical, http_transport
from transport.host import CLOCK, paged
from transport import observe
from transport.observe import Observer

DELIVER_ROUNDS = 8


def uri_hash(uri):
    return hashlib.sha256(uri.encode()).hexdigest()[:16]


def draft_exists(outbox, uri):
    return any(outbox.glob(f'*-{uri_hash(uri)}.json'))


def reachable(origin):
    """An origin someone else can open: not loopback (`localhost`, 127/8, ::1), whose links reach nobody but this machine."""
    host = urllib.parse.urlsplit(origin or '').hostname or ''
    try:
        return bool(host) and host != 'localhost' and not ipaddress.ip_address(host).is_loopback
    except ValueError:
        return bool(host) and host != 'localhost'


def cite(object_, version, origin=None):
    """`<object> v<n>` and, with a reachable origin, its short link on the next line. Posts never carry a hash or a blob."""
    text = f'{object_} v{version}' if version is not None else str(object_)
    link = f'\n{origin.rstrip("/")}/o/{urllib.parse.quote(str(object_), safe="")}#v{version}' if reachable(origin) and version is not None else ''
    return text, link


def turn_root(receipt, addressed=None):
    """The version a turn wrote of the object it addressed (`addressed`, else its first root: a garden's planting writes
    kind/bell first, and a card that asks the commonplace first reads it first), else that object as read, else its first
    write, else the version it read."""
    roots = receipt.get('roots') or [{}]
    writes = (receipt.get('outcome') or {}).get('writes') or []
    name = addressed or roots[0].get('object')
    return next((w for w in writes if w.get('object') == name), next((r for r in roots if r.get('object') == name), (writes or roots)[0]))


def card_name(object_, handles=None):
    """How a line names a card: a person's avatar by their handle (`kestrel's avatar`, the avatar's id being the DID), a
    DID never reaching a post; any other card by its id."""
    handles = handles or {}
    return f"{handles[object_]}'s avatar" if object_ in handles else object_


def turn_words(receipt, addressed=None, handles=None):
    """`admitted garden v1, entry 26, receipt lodif-rukuz`: VOICE's turn line, the same in the JSON `line`, the play
    page, the text view and a draft, naming the card the words were addressed to (`card_name`)."""
    root, tag = turn_root(receipt, addressed), (receipt.get('outcome') or {}).get('tag') or 'admitted'
    what = f" {card_name(root['object'], handles)}" + (f" v{root['version']}" if root.get('version') is not None else '') if root.get('object') else ''
    return f"{tag}{what}, entry {receipt.get('height')}" + (f", receipt {receipt['slug']}" if receipt.get('slug') else '')


def receipt_line(receipt, origin=None, addressed=None, handles=None):
    """The turn line with its stamp, and with a reachable origin the object's short link on the next line."""
    from transport.pages import stamp
    root = turn_root(receipt, addressed)
    link = cite(root['object'], root.get('version'), origin)[1] if root.get('object') else ''
    return f"{stamp((receipt.get('outcome') or {}).get('tag') or 'admitted', word=False)} {turn_words(receipt, addressed, handles)}{link}\n"


def refusal_line(outcome, fallback_class=None):
    """A refusal as VOICE shapes it, `refused <clause>: <reading>`; a reason that already says so is kept as it is."""
    why = outcome.get('reason') or ''
    if why.startswith(('refused ', 'turn refused')):
        return why
    head, tail = f"refused {outcome.get('clause') or outcome.get('class') or fallback_class}", why or outcome.get('object', '')
    return f'{head}: {tail}' if tail else head


def turn_line(r, addressed=None, handles=None):
    """A turn reply in one line: `admitted garden v3, entry 9, receipt <slug>`, `refused owner: <reading>`, `suspended, entry 9`
    (the front's JSON `line` and the play page)."""
    rc = r.get('receipt') or {}
    out = rc.get('outcome') or {}
    if r.get('status') == 'admitted':
        return turn_words({**rc, 'outcome': {**out, 'tag': 'admitted'}}, r.get('object') or addressed, handles)
    if r.get('status') == 'refused':
        return refusal_line(out, r.get('class')) + (f"\nnext at {out['next']}" if 'next' in out else '')
    return f"suspended, entry {rc.get('height')}" if r.get('status') == 'suspended' else f"{r.get('status')}: {r.get('message', '')}"


def spell_line(reply, origin=None, handles=None):
    """One spell's line in a reply to a post of several (a turn each): its receipt line, or its refusal and receipt;
    no card and no usage, so three fit one reply."""
    receipt = reply['receipt']
    outcome = receipt.get('outcome') or {}
    if outcome.get('tag') == 'refused':
        return refusal_line(outcome, reply.get('class')) + (f"\nreceipt {receipt['slug']}" if receipt.get('slug') else '') + '\n'
    return revealed_lines(reply) + receipt_line(receipt, origin, reply.get('object'), handles)


def revealed_lines(reply):
    """The host's lines an admitted reply carries (`revealed`: what it moved, what it opened or closed, where it
    stands), each on its own line; the host renders them, the transport only places them."""
    return ''.join(f'{line}\n' for line in reply.get('revealed') or [])


def draft_public(reply, origin=None, addressed=None, handles=None):
    """`draft_text`, or for an admitted turn that read or wrote what the public may not read (the host's `inPublic`: a
    post is read by everyone), its receipt line."""
    receipt = reply.get('receipt') or {}
    if reply.get('status') != 'admitted' or (receipt.get('outcome') or {}).get('tag') not in (None, 'admitted') or reply.get('inPublic'):
        return draft_text(reply, origin, addressed, handles)
    return receipt_line(receipt, origin, addressed, handles)


def draft_text(reply, origin=None, addressed=None, handles=None):
    """The only text a draft carries. A refusal is drafted when the host gives it a `public` projection (whether to say it
    is the host's fact; the post's wording is never read for it): the turn line, the host's hint when it gives one, and the
    receipt's name; no state, hash or CID. A usage answer is the host's text. An admitted reply carries the exact card
    only, never its paint (`world-render`): whether a post carries paint is the fourth playtest's question (OVERHAUL §4);
    one that offered nothing but changed something, its revealed lines and receipt line."""
    if reply.get('status') == 'usage':
        return str(reply.get('text', ''))
    receipt = reply['receipt']
    outcome = receipt.get('outcome', {})
    if reply.get('status') == 'refused' or outcome.get('tag') == 'refused':
        if 'public' not in reply:
            return ''
        hint = reply.get('hint') or (reply.get('public') or {}).get('hint')
        lines = [refusal_line(outcome, reply.get('class'))] + ([str(hint)] if hint else []) + ([f"receipt {receipt['slug']}"] if receipt.get('slug') else [])
        return '\n'.join(lines) + '\n'
    offers = [o['text'] for o in reply.get('offers') or []]
    if offers:  # every reply ends with the host's lines (what it moved, opened, where it stands) and its receipt's spoken name
        return '\n'.join(offers).rstrip('\n') + '\n' + revealed_lines(reply) + receipt_line(receipt, origin, addressed, handles)
    if receipt.get('offers'):
        return 'reply card offered but not retained by the host; ' + receipt_line(receipt, origin, addressed, handles)
    if outcome.get('writes') and not receipt.get('sends'):  # it changed something and handed nothing on: its receipt answers
        return revealed_lines(reply) + receipt_line(receipt, origin, addressed, handles)
    return ''  # nothing changed and nothing offered: silence


def preview_text(reply, handles=None):
    """A try's answer (`world-try`, docs/POSTING.md §2) as a post says it: `preview, nothing done`, then each act as it
    would go (`would be admitted bell/1 v4`, or `would be refused <clause>: <reading>`), what it would fire, open or
    close, and the card it would offer, exactly; last the `if:` line of every root it read, to put above the same
    spells so they land only if nothing moved. Never a receipt's name: a preview must never pass for one. An act
    that reads what the public may not (`inPublic` false) is said by its outcome alone."""
    turns = reply.get('turns') if reply.get('status') == 'spells' else [reply]
    out, roots = [f"preview, nothing done (as of entry {(reply.get('against') or {}).get('height')}):"], {}
    for t in turns:
        if 'receipt' not in t:
            out.append(str(t.get('text') or t.get('message') or t.get('status')).rstrip('\n'))
            continue
        receipt, outcome = t['receipt'], t['receipt'].get('outcome') or {}
        for r in receipt.get('roots') or []:
            roots.setdefault(r['object'], r.get('version'))
        if outcome.get('tag') == 'refused':
            out.append('would be ' + refusal_line(outcome, t.get('class')))
            continue
        if outcome.get('tag') == 'suspended' or t.get('status') == 'suspended':
            out.append('would wait for hob to read it; try the spell hob gives')
            continue
        root = turn_root(receipt, t.get('object'))
        out.append(f"would be admitted {card_name(root['object'], handles)}" + (f" v{root['version']}" if root.get('version') is not None else ''))
        if t.get('inPublic') is not False:
            out += [line for line in t.get('revealed') or []] + [o['text'].rstrip('\n') for o in t.get('offers') or []]
    if roots and all(t.get('inPublic') is not False for t in turns if 'receipt' in t):
        out.append('if: ' + ', '.join(f'{o} v{v}' for o, v in roots.items() if v is not None))
    return '\n'.join(out) + '\n'


def register(st, host, did, handle):
    """Tell the host an author has arrived, at their first observed post (the clock principal alone may). The call
    is idempotent at the host; the local set is the skip list and only saves the round trips."""
    if did in st.words(st.principals):
        return True
    got = host.send({'op': 'world-arrive', 'principal': CLOCK, 'did': did, 'handle': handle})
    if got.get('status') == 'error':
        return False
    st.append(st.principals, did)
    return True


def awaiting_path(st, uri):
    return st.awaiting / f'{uri_hash(uri)}.json'


def offer_drafts(st, host):
    """Draft what resumed turns offered. A suspended turn leaves an `awaiting` record; once its interpretation
    settles the resumed entry's offer is in the host's outbox for the author, under the turn's identity (the
    post). One draft per (addressee, identity), so a retry never drafts twice. The draft ends with the receipt
    of the author's turn on that post, as the host names it (`world-receipt`). A resumption the host refused (hob's
    act refused by a law, a misfit hob read nothing better for) is drafted as any refusal is, from what the host
    makes public; a resumption with no offer and no refusal (hob's `none`) drafts nothing. Either is marked
    `settled` and never asked again."""
    waiting = [json.loads(p.read_text()) for p in sorted(st.awaiting.glob('*.json')) if not json.loads(p.read_text()).get('settled')]
    drafted, handles = [], {o['author']['did']: o['author']['handle'] for o in st.observations()} if waiting else {}
    for principal in dict.fromkeys(w['principal'] for w in waiting):
        mine = {(w['principal'], w['uri']): w for w in waiting if w['principal'] == principal}
        grouped = {}
        for o in paged(host, {'op': 'world-offers', 'principal': principal, 'after': max(0, min(w['height'] for w in mine.values()) - 1)}, 'offers'):
            who = o.get('from') or o['identity']  # {principal, intent}: `from` is the originating post of a handed-on turn
            if isinstance(who, dict) and (who.get('principal'), who.get('intent')) in mine:
                grouped.setdefault((who['principal'], who['intent']), []).append(o)
        for (_, uri), offers in grouped.items():
            key = hashlib.sha256(f'{principal}\0{uri}'.encode()).hexdigest()[:16]
            if any(st.outbox.glob(f'*-off-{key}.json')):
                continue
            w = mine[(principal, uri)]
            got = host.send({'op': 'world-receipt', 'principal': principal, 'identity': uri})
            rc = got.get('receipt')
            text = ('\n'.join(o['text'] for o in offers).rstrip('\n') + '\n' if got.get('inPublic') else '') + receipt_line(rc, st.config.origin, w.get('object'), handles) if rc else ''
            st.write(st.outbox / f"{offers[-1]['height']}-off-{key}.json", {
                'replyTo': w.get('post', uri), 'replyHandle': w['replyHandle'], 'principal': principal, 'principalVerified': False,
                'object': w.get('object'), 'slot': w.get('slot'),
                'offer': {'height': offers[-1]['height'], 'identity': uri},
                'text': text, 'posted': False})
            drafted.append(uri)
        for (_, uri), w in mine.items():
            key = hashlib.sha256(f'{principal}\0{uri}'.encode()).hexdigest()[:16]
            if not w.get('suspended') or (principal, uri) in grouped or any(st.outbox.glob(f'*-off-{key}.json')):
                continue
            got = host.send({'op': 'world-receipt', 'principal': principal, 'identity': uri})
            rc = got.get('receipt') or {}
            tag = (rc.get('outcome') or {}).get('tag')
            if tag in (None, 'suspended'):
                continue
            text = draft_text({'status': 'refused', 'receipt': rc, 'public': got['public']}, st.config.origin, w.get('object'), handles) \
                if tag == 'refused' and got.get('public') else ''
            if text:
                st.write(st.outbox / f"{rc['height']}-off-{key}.json", {
                    'replyTo': w.get('post', uri), 'replyHandle': w['replyHandle'], 'principal': principal, 'principalVerified': False,
                    'object': w.get('object'), 'slot': w.get('slot'), 'receipt': rc, 'text': text, 'posted': False})
                drafted.append(uri)
            st.write(awaiting_path(st, uri), {**w, 'settled': True})
    return drafted


MAX_HOPS = 32  # the host's `reachHops`: the ancestors passed with a post
def mention_turns(st, host, obs, authors, handles, addressed):
    """A mention is addressed to the mentioned: one turn per mention (a facet's DID, or an @handle that is a known
    author) to the mentioned principal's avatar, `<did>`.receive {text, post} under the author with reach `mentioned`:
    the avatar keeps it as a note, and the host never reads it as a spell (its spell lines are the author's, routed to the
    cards they name). Once per post. Only an arrived principal has an avatar: a mentioned principal the observer has seen
    is arrived first; one it has not is skipped, with a note in skipped.txt. Only the first `addressed` mentions (the
    host's `mentionsAddressed`) are turned."""
    done = st.words(st.mentioned)
    dids = list(dict.fromkeys(d for d in ((m['did'] or authors.get(m['handle'])) for m in obs['mentions'][:addressed]) if d))
    if obs['uri'] in done or not dids:
        return False
    author = obs['author']
    register(st, host, author['did'], author['handle'])
    fields = [{'name': 'text', 'value': {'tag': 'label', 'value': obs['text']}}, {'name': 'post', 'value': {'tag': 'label', 'value': obs['uri']}}]
    replies = []
    for did in dids:
        if did not in handles or not register(st, host, did, handles[did]):
            st.append(st.skipped, f"{obs['uri']}#mention:{did}")  # not arrived, so no avatar: nothing to send
            continue
        replies.append(host.send({'op': 'world-turn', 'principal': author['did'], 'object': did, 'method': 'receive',
                                  'argument': {'tag': 'record', 'fields': fields}, 'reach': 'mentioned',
                                  'identity': f"{obs['uri']}#mention:{did}"}))
    if all('receipt' in r for r in replies):  # else retry next run: the host answers a repeated identity with its first receipt
        st.append(st.mentioned, obs['uri'])
    return bool(replies)


def reach(host, obs, known):
    """-> (object, slot|None, how) or None: where the host says the post reaches (`world-reach`, docs/FLEX.md §2). The
    bridge passes only what it observed: the post, and the ancestors it saw above it with their authors."""
    chain, above = [], obs['replyTo']
    while above in known and len(chain) < MAX_HOPS and all(a['uri'] != above for a in chain):
        seen = known[above]
        chain.append({'uri': above, 'author': seen['author']['did'], **({'replyTo': seen['replyTo']} if seen['replyTo'] else {})})
        above = seen['replyTo']
    got = host.send({'op': 'world-reach', 'uri': obs['uri'], 'text': obs['text'], 'kind': obs['kind'], 'author': obs['author']['did'],
                     **({'replyTo': obs['replyTo']} if obs['replyTo'] else {}), **({'root': obs['root']} if obs.get('root') else {}),
                     'mentions': len(obs['mentions']), 'chain': chain})
    if got.get('status') != 'reached':
        if got.get('status') != 'unreached':
            raise Unread(got.get('message', got.get('status')))  # the host did not answer: the post waits for the next run
        return None
    return got['object'], got.get('slot'), got


class Unread(Exception):
    pass


def publication_text(p):
    """agentwiki: `wiki: <page>` for a whole page, `edit: <page> › <section>` for one section."""
    header = f"wiki: {p['page']}" if not p['section'] else f"edit: {p['page']} › {p['section']}"
    return f"{header}\n\n{p['body']}"


def publication_drafts(st, host):
    """Drafts for what objects published (`world-publications`, read as the clock principal), marked
    like reply drafts and never posted here. A section edit replies to its page's recorded post; one
    drafted before that post was recorded gets it on a later run, while it is unposted."""
    after = int(st.publications.read_text()) if st.publications.exists() else 0
    waiting = [d['publication']['height'] for _, d in st.unposted() if 'publication' in d and d['section'] and not d['replyTo']]
    start = min([after] + [h - 1 for h in waiting])
    drafted = []
    while True:
        got = host.send({'op': 'world-publications', 'principal': CLOCK, 'after': start})
        if got.get('status') != 'publications':
            return drafted, got.get('message', got.get('status'))
        for p in got['publications']:
            path = st.outbox / f"{p['height']}-pub-{p['id'][:16]}.json"
            if path.exists():
                d = json.loads(path.read_text())
                if not d['posted'] and not d['replyTo'] and p.get('replyTo'):
                    st.write(path, dict(d, replyTo=p['replyTo']))
                continue
            st.write(path, {'publication': {k: p[k] for k in ('id', 'height', 'object')}, 'page': p['page'],
                                'section': p['section'], 'replyTo': p.get('replyTo'), 'text': publication_text(p),
                                'posted': False})
            drafted.append(p['id'])
        heights = [p['height'] for p in got['publications']]
        if not got['more'] or not heights:
            break
        start = heights[-1] - 1  # a page may end inside one entry's publications; drafts already written are kept
    last = max([after] + heights)
    if last > after:
        st.write(st.publications, last)
    return drafted, None


def tick(host, now=None):
    """Time enters the journal here and nowhere else: unix minutes, as the clock principal.
    `now` (unix seconds) replaces the wall clock for an offline replay."""
    return host.send({'op': 'world-advance', 'principal': CLOCK, 'height': int((time.time() if now is None else now) // 60)})


def run(st, host, observer=None, rounds=DELIVER_ROUNDS, now=None):
    """One step: observe (when given an observer), tick the clock, turn every addressed observation, settle what the
    host has to deliver, and draft what was offered and published."""
    st.outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    if observer:
        observer.poll()
    tick(host, now)
    from transport.post import record_sent
    recorded = record_sent(st, host)  # posts whose registration failed, retried apart from sending
    done, failed, skip, origin = [], [], st.words(st.skipped), st.config.origin
    rows = st.observations()
    observed = sorted(rows, key=lambda o: (o['createdAt'], o['uri']))  # every post goes to `world-reach` once; the host says where
    known = {o['uri']: o for o in observed}
    authors = {o['author']['handle'].lower(): o['author']['did'] for o in rows}  # every author seen, so an @handle resolves
    handles = {o['author']['did']: o['author']['handle'] for o in rows}
    for did, handle in handles.items():  # a principal arrives at their first observed post, whatever its kind
        register(st, host, did, handle)
    addressed = host.send({'op': 'bounds'})['host']['mentionsAddressed'] if any(obs['mentions'] for obs in observed) else 0
    mentioned = [obs['uri'] for obs in observed if obs['mentions'] and mention_turns(st, host, obs, authors, handles, addressed)]
    for obs in observed:
        if obs['uri'] in skip or draft_exists(st.outbox, obs['uri']) or awaiting_path(st, obs['uri']).exists():
            continue
        try:
            target = reach(host, obs, known)
        except Unread as e:
            failed.append({'uri': obs['uri'], 'message': str(e)})
            continue
        if target is None:
            st.append(st.skipped, obs['uri'])
            continue
        obj, slot, how = target
        handle, did = obs['author']['handle'], obs['author']['did']
        register(st, host, did, handle)
        # A card's receive takes {text, post}; the author is the turn's principal. The slot is the host's
        # to fill (receiveArgument), so it is never sent. replyTo makes the turn the recorded post's answer.
        fields = [{'name': 'text', 'value': {'tag': 'label', 'value': obs['text']}},
                  {'name': 'post', 'value': {'tag': 'label', 'value': obs['uri']}}]
        request = {'op': 'world-turn', 'principal': did, 'object': obj, 'method': 'receive',
                   'argument': {'tag': 'record', 'fields': fields}, 'identity': obs['uri']}
        if how.get('replyTo') or obs['replyTo']:  # on Zulip the recorded message found up the topic, so the host verifies it
            request['replyTo'] = how.get('replyTo') or obs['replyTo']
        if how['how'] in ('mention', 'door', 'fields'):
            request['reach'] = how['how']  # the reach the host found; a reply and a spell it finds again at the turn
        reply = host.send(request)
        if reply.get('tried') or reply.get('class') == 'moved':  # a preview, or an act whose `if` moved: nothing journaled
            st.write(st.outbox / f"0-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': obj, 'slot': slot, 'receipt': None, 'preview': bool(reply.get('tried')), 'posted': False,
                'text': preview_text(reply, handles) if reply.get('tried') else reply['line'] + '\n'})
            done.append(obs['uri'])
            continue
        if reply.get('status') == 'spells':  # several spells at a line's start: a turn each, one reply carrying every line
            turns = reply.get('turns') or []
            lost = [t for t in turns if 'receipt' not in t and t.get('status') != 'usage']  # a `?` journals nothing: its text is its answer
            if not turns or lost:
                failed.append({'uri': obs['uri'], 'message': lost[0].get('message') if lost else 'no turns'})
                continue
            ran = [t for t in turns if 'receipt' in t]
            text = ''.join(draft_text(t).rstrip('\n') + '\n' if 'receipt' not in t else spell_line(t, origin, handles) for t in turns)
            st.write(st.outbox / f"{ran[-1]['receipt']['height'] if ran else 0}-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': turns[0].get('object') or obj, 'slot': slot,
                'receipt': ran[-1]['receipt'] if ran else None, 'posted': False, 'text': text})
            for t in ran:  # a suspended spell's own answer comes when hob has read it, as a reply to the same post
                if (t['receipt'].get('outcome') or {}).get('tag') == 'suspended':
                    intent = t['receipt']['identity']['intent']
                    st.write(awaiting_path(st, intent), {'uri': intent, 'post': obs['uri'], 'principal': did, 'replyHandle': handle,
                                                         'object': t.get('object') or obj, 'slot': slot, 'height': t['receipt']['height'], 'suspended': True})
            done.append(obs['uri'])
            continue
        if reply.get('status') == 'usage':  # a `?`: the host answers with the card's usage and journals nothing; the post is done
            st.write(st.outbox / f"0-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': obj, 'slot': slot, 'receipt': None, 'usage': True, 'posted': False, 'text': draft_text(reply)})
            done.append(obs['uri'])
            continue
        if 'receipt' not in reply:  # the host gave no receipt; nothing to draft, retry next run
            failed.append({'uri': obs['uri'], 'message': reply.get('message', reply.get('status'))})
            continue
        if reply.get('status') == 'suspended' or reply['receipt'].get('outcome', {}).get('tag') == 'suspended':
            # Nothing was committed and nothing is offered yet: no draft until the interpretation settles.
            st.write(awaiting_path(st, obs['uri']), {'uri': obs['uri'], 'principal': did, 'replyHandle': handle, 'object': obj, 'slot': slot,
                                                     'height': reply['receipt']['height'], 'suspended': True})
            continue
        obj = reply.get('object') or obj  # the card the host ran the turn on: a spell's card as it resolved it
        st.write(st.outbox / f"{reply['receipt']['height']}-{uri_hash(obs['uri'])}.json", {
            'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
            'object': obj, 'slot': slot,
            'receipt': reply['receipt'], 'posted': False, 'text': draft_public(reply, origin, obj, handles)})  # text '': journaled, hidden from outbox
        if not reply.get('offers'):  # a card may have handed the reply on: its offer arrives later, `from` this post
            st.write(awaiting_path(st, obs['uri']), {'uri': obs['uri'], 'principal': did, 'replyHandle': handle, 'object': obj, 'slot': slot, 'height': reply['receipt']['height']})
        done.append(obs['uri'])
    for _ in range(rounds):
        if not host.send({'op': 'world-pending'}).get('count'):
            break
        host.send({'op': 'world-deliver'})  # the host's own bound a call
    offered = offer_drafts(st, host)
    published, problem = publication_drafts(st, host)
    if problem:
        failed.append({'publications': problem})
    return {'turns': done, 'failed': failed, **({'recorded': recorded} if recorded else {}), **({'mentioned': mentioned} if mentioned else {}), **({'published': published} if published else {}), **({'offered': offered} if offered else {})}


def command(st, a, out):
    """`bridge`: the world's bridge row says what it observes (delve.town, or a channel of the owner's Zulip, whose drafts
    it then posts itself); one step with `--once`, else a step every `poll` seconds."""
    host, row = st.host(), st.bridge()
    since = observe.start_cursor(st, a.since, a.now)
    if row['transport'] == 'zulip':
        from transport import zulip
        client = zulip.Client(row['zuliprc'])
        observer = zulip.ZulipObserver(st, client, row['channel'], since, row.get('topic'))
        after = lambda: zulip.post_drafts(st, host, client)
    else:
        observer, after = Observer(st, Client(FixtureTransport(st.config.delve_mock) if st.config.delve_mock else http_transport), since), dict
    step = lambda: out.write(canonical({**run(st, host, observer, now=a.now), **after()}) + '\n') and out.flush()
    try:
        step() if a.once else st.daemon('bridge', step)
    finally:
        host.close()
