"""Observed posts -> host turns -> reply drafts for a human to post (`python3 -m transport bridge`); observed request
records (transport/requests.py) -> the same turns -> `online.fg-goose.gsb.answer` records, which the façade serves (the
mirror would copy them; it is built and not running).

Never posts to delve.town: `post` is the only writer there. A world whose bridge row is a Zulip channel, the owner's own,
has its drafts posted by transport/zulip.py. Principals here are the observed authors' DIDs, which are UNVERIFIED.
"""
import base64
import hashlib
import ipaddress
import json
import urllib.parse
import time

from transport.delve import Client, Failure, FixtureTransport, canonical
from transport.host import CLOCK, PUBLIC, paged, painted, typed
from transport import anchors, observe
from transport.observe import Observer
from transport.mirror import ANSWER, NS
from transport.atproto.cbor import block

DELIVER_ROUNDS = 8
TELLING_LINES = 8  # the exact lines an unpainted telling before arrival leads a post with, the newest
TELLING_LINE = 120  # each of them at most, clipped
TELLING_CLIP = 700  # the telling a post leads with, at most: half of what one post holds (post.CLIP)


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


def revealed_lines(reply):
    """The host's lines an admitted reply carries (`revealed`: what it moved, what it opened or closed, where it
    stands), each on its own line; the host renders them, the transport only places them."""
    return ''.join(f'{line}\n' for line in reply.get('revealed') or [])


def offered_object(reply, addressed=None):
    """The thing whose card a turn's reply offers: the first it made (a kind's `make` offers the made thing's card),
    else the card it ran on."""
    made = [c['object'] for c in ((reply.get('receipt') or {}).get('outcome') or {}).get('creates') or [] if c.get('object')]
    return (made or [reply.get('object') or addressed])[0]


def with_paint(host, obj, text, sleep=None, speaker=None, words=None):
    """`text` with the thing's verified paint above it (docs/OVERHAUL.md section 4; the owner: posting paint is fine, it
    is what the place says), as the public reads it, when one is verified and the two fit one post; else `text`. The
    paint is the one `painted` the front's pages show: the host's, checked, cached per version and tongue, in the tongue
    the host chooses for `speaker` and their `words` (docs/VOICE.md "Tongues")."""
    from transport.post import CLIP
    paint = painted(host, PUBLIC, obj, sleep or time.sleep, speaker=speaker, words=words).get('text') if obj and text else None
    return f'{paint.rstrip()}\n\n{text}' if paint and len(paint.rstrip()) + 2 + len(text) <= CLIP else text


def telling_lead(told):
    """A place's telling as a post leads with it (docs/VOICE.md "A telling"), as `/play` shows it: the host's frame above
    the paint; unpainted before arrival, the frame above the exact lines it draws on (its making, then the newest
    TELLING_LINES, how many earlier counted, each at most TELLING_LINE, the whole within TELLING_CLIP, so the reply's own
    text starts in the post the telling leads when `post.parts` threads it); unpainted while away, nothing, the reply's
    own "While you were away" lead holding the exact lines. Then a blank line."""
    t = (told or {}).get('telling')
    if not t:
        return ''
    if (told.get('text') or '').strip():
        return f"{t['frame']}\n{told['text'].strip()}\n\n"
    exact = t.get('exact') or []
    if t.get('form') != 'before' or not exact:
        return ''
    clip = lambda line: line if len(line) <= TELLING_LINE else line[:TELLING_LINE - 1] + '…'  # noqa: E731
    head = [clip(exact[0])] if exact[0].startswith('made by ') else []
    rest = [clip(x) for x in exact[len(head):]]
    shown = rest[-TELLING_LINES:]
    while True:
        earlier = [f'… and {len(rest) - len(shown)} earlier'] if len(rest) > len(shown) else []
        text = f"{t['frame']}\n" + '\n'.join(head + earlier + shown) + '\n\n'
        if len(text) <= TELLING_CLIP or not shown:
            return text
        shown = shown[1:]


def with_telling(host, principal, reply, obj, text, sleep=None, words=None):
    """`text` led by the place's telling when the turn entered the place (an admitted `enter`, `result` `entered`) and its
    draft is the reply itself, not its receipt line alone (`inPublic`), for `principal` who entered (`world-render
    {telling}`, waiting the host's patience for the paint), as `telling_lead` sets it; else `text`. -> (the text, the
    telling's characters at its head, 0 for none), which a draft notes as `told` for whoever posts or threads it. A
    receipt never carries it. A painted telling's exact history follows the complete reply as "What it draws on".
    Told in the tongue the host chooses for `principal` and their `words`."""
    obj = reply.get('object') or obj
    if reply.get('status') != 'admitted' or (reply.get('result') or {}).get('label') != 'entered' or not reply.get('inPublic') or not obj or not text:
        return text, 0
    told = painted(host, principal, obj, sleep or time.sleep, telling={}, words=words)
    lead = telling_lead(told)
    exact = (told.get('telling') or {}).get('exact') or []
    if (told.get('text') or '').strip() and exact:
        text += ('\n' if text.endswith('\n') else '\n\n') + 'What it draws on:\n' + '\n'.join(exact) + '\n'
    return lead + text, len(lead)


def told_field(told):
    """A draft's note of the telling at its head: `told: <its characters>`, or nothing."""
    return {'told': told} if told else {}


def first_move(st, did, reply, text):
    """A resident's first admitted reply teaches the next move by its spells (docs/POSTING.md build 8): try before an
    act is real, and find this one again by its receipt. Once a resident; only when it fits the post."""
    from transport.post import CLIP
    slug = (reply.get('receipt') or {}).get('slug')
    if reply.get('status') != 'admitted' or not text or not slug or did in st.words(st.taught):
        return text
    st.append(st.taught, did)
    line = f'Next, see it before it is real: delvetalk try, a spell indented under it. This act again: delvetalk receipt / of: {slug}\n'
    if len(text) + len(line) > CLIP:
        return text
    head, _, last = text.rstrip('\n').rpartition('\n')
    return f'{head}\n{line}{last}\n' if head and last.startswith('●') else line + text  # the receipt's line stays the last


def read_text(host, principal, reply, sleep=time.sleep):
    """A caller's usage reply: its text, and for a read the host says a day paints (the chronicle's
    `paint {day}`), that day's verified paint above it when there is one within the host's patience (docs/VOICE.md "The
    book, the history, the map"); the exact lines alone otherwise."""
    text = str(reply.get('whole') or reply.get('text') or '\n'.join(o['text'] for o in reply.get('offers') or []))
    if not isinstance(reply.get('paint'), dict):
        return text
    paint = painted(host, principal, None, sleep, **reply['paint']).get('text')
    return f"{paint}\n\n{text}" if paint else text


def public_reply(reply, host=None, request=None, sleep=time.sleep):
    """The host's public answer, shared by drafts, previews and answer records. Reads belong to their reader;
    turn content stands only when the host projects it publicly."""
    if reply.get('status') == 'spells':
        return {**reply, 'turns': [public_reply(t, host) for t in reply.get('turns') or []]}
    if reply.get('status') == 'usage':
        if host is not None and request is not None:
            public = host.send({**request, 'op': 'world-try', 'principal': PUBLIC,
                                'identity': 'public-read:' + uri_hash(canonical(request))})
            receipt = public.get('receipt') or {}
            outcome = receipt.get('outcome') or {}
            read = public.get('status') == 'usage' or (
                public.get('tried') and public.get('status') == 'admitted' and public.get('inPublic') and public.get('offers') and
                not any(value for key, value in outcome.items() if key != 'tag') and not (receipt.get('sends') or receipt.get('publishes')))
            if read:
                return {'status': 'usage', 'text': read_text(host, PUBLIC, public, sleep)}
        return {'status': 'usage', 'readerOnly': True,
                'text': "a `?` or a read is its reader's; read the card, book, chronicle or map on the web"}
    if reply.get('class') == 'moved':
        moved = [m for m in reply.get('moved') or [] if host is not None
                 if host.send({'op': 'world-view', 'principal': PUBLIC, 'object': m.get('object')}).get('status') == 'viewed']
        return {**reply, 'moved': moved, 'line': reply.get('line') if len(moved) == len(reply.get('moved') or []) else 'refused moved'}
    rc = reply.get('receipt') or {}
    tag = (rc.get('outcome') or {}).get('tag') or reply.get('status')
    if tag == 'refused':
        return reply
    if not reply.get('inPublic'):
        return {**reply, 'offers': [], 'revealed': [], 'receiptOnly': True}
    return reply


def draft_text(reply, origin=None, addressed=None, handles=None, compact=False, host=None, request=None, sleep=time.sleep):
    """The only text a draft carries. A refusal is drafted when the host gives it a `public` projection (whether to say it
    is the host's fact; the post's wording is never read for it): the turn line, the host's hint when it gives one, and the
    receipt's name; no state, hash or CID. A read points to the web. An admitted reply carries the public exact card
    (the paint above it is `with_paint`'s, which needs the host); one that offered nothing but changed something, its
    revealed lines and receipt line."""
    reply = public_reply(reply, host, request, sleep)
    if reply.get('status') == 'usage':
        return reply['text'] + ((f": {origin.rstrip('/')}/" if reachable(origin) else '') + '\n' if reply.get('readerOnly') else '')
    receipt = reply['receipt']
    outcome = receipt.get('outcome', {})
    if reply.get('status') == 'refused' or outcome.get('tag') == 'refused':
        if 'public' not in reply:
            return ''
        hint = reply.get('hint') or (reply.get('public') or {}).get('hint')
        act = reply['public'].get('act')  # a plan's refusal: which act, of how many (the host's `planRefusedAct`)
        lines = ([f"act {act} of {reply['public'].get('acts')} refused, so none of the plan was done:"] if act else []) + \
            [refusal_line(outcome, reply.get('class'))] + ([str(hint)] if hint else []) + ([f"receipt {receipt['slug']}"] if receipt.get('slug') else [])
        return '\n'.join(lines) + '\n'
    if compact or reply.get('receiptOnly'):
        return revealed_lines(reply) + receipt_line(receipt, origin, reply.get('object') or addressed, handles)
    offers = [o['text'] for o in reply.get('offers') or []]
    if offers:  # every reply ends with the host's lines (what it moved, opened, where it stands) and its receipt's spoken name
        return '\n'.join(offers).rstrip('\n') + '\n' + revealed_lines(reply) + receipt_line(receipt, origin, addressed, handles)
    if receipt.get('offers'):
        return 'reply card offered but not retained by the host; ' + receipt_line(receipt, origin, addressed, handles)
    if outcome.get('writes') and not receipt.get('sends'):  # it changed something and handed nothing on: its receipt answers
        return revealed_lines(reply) + receipt_line(receipt, origin, addressed, handles)
    return ''  # nothing changed and nothing offered: silence


def request_source(obs):
    """The proven strongRef that an answer names as its source."""
    return {'$type': ANSWER + '#request', 'request': {'uri': obs['uri'], 'cid': obs['cid']}}


def xrpc_source(principal, intent):
    """The service-auth issuer and idempotency key that an answer names."""
    return {'$type': ANSWER + '#provenance', 'iss': principal, 'intent': intent}


def answer_path(st, source):
    """One key per request URI or (issuer, intent), shared by bridge and front."""
    if source['$type'] == ANSWER + '#provenance':
        digest = base64.b32encode(hashlib.sha256(source['intent'].encode()).digest()).decode().lower()[:26]
        key = f"xrpc.{source['iss']}.{digest}"
    else:
        did, _, rkey = source['request']['uri'].removeprefix('at://').partition('/')
        key = f"{did}.{rkey.rsplit('/', 1)[-1]}"
    return st.answers / f'{key}.json'


def turn_content(reply):
    """The host-projected offered bytes and trace, without a receipt stamp.

    cardCid hashes the exact card as a DAG-CBOR string; it needs no reread of
    the live world, which would describe the wrong state for a preview.
    """
    rc = reply.get('receipt') or {}
    out = rc.get('outcome') or {}
    keep = lambda rows, *keys: [{k: r[k] for k in keys if k in r} for r in rows]
    writes = [{**{k: w[k] for k in ('object', 'version') if k in w}, **({'stateCid': w['cid']} if 'cid' in w else {})}
              for w in out.get('writes') or []]
    offers = [o['text'] for o in reply.get('offers') or []]
    return {**({'offers': offers, 'card': offers[0], 'cardCid': str(block(offers[0])[0])} if offers else {}),
            'trace': {'roots': keep(rc.get('roots') or [], 'object', 'version'), 'writes': writes,
                      'revealed': reply.get('revealed') or [],
                      **{k: reply.get(k, rc.get(k, out.get(k))) for k in ('fired', 'wanted', 'unwanted')
                         if reply.get(k, rc.get(k, out.get(k))) is not None}}}


def caller_view(reply, preview=False):
    """The caller's host projection. A preview carries no entry or receipt identity."""
    if reply.get('status') == 'spells':
        turns = [caller_view(t, preview) for t in reply.get('turns') or []]
        return {'$type': NS + 'defs#' + ('previewView' if preview else 'answerView'),
                'outcome': {'status': 'previewed' if preview else 'spells',
                            'line': '\n'.join(t['outcome']['line'] for t in turns)}, 'turns': turns}
    rc = reply.get('receipt') or {}
    out = rc.get('outcome') or {}
    status = 'previewed' if preview else reply.get('status', out.get('tag', 'refused'))
    line = ('would be ' + (reply.get('line') or 'refused moved') if reply.get('class') == 'moved' else
            would_line(reply) if rc else str(reply.get('message') or reply.get('status'))) if preview else reply.get('line') or turn_line(reply)
    outcome = {'status': status, 'line': line,
               **{k: out[k] for k in ('class', 'clause', 'reason') if isinstance(out.get(k), str)},
               **({'class': reply['class']} if reply.get('class') else {}),
               **({'moved': reply['moved']} if 'moved' in reply else {})}
    receipt = {'slug': rc['slug'], 'height': rc['height'], 'entry': {'$link': rc['hash']}} if not preview and {'slug', 'height', 'hash'} <= set(rc) else None
    return {'$type': NS + 'defs#' + ('previewView' if preview else 'answerView'), 'outcome': outcome,
            **({'receipt': receipt} if receipt else {}), **turn_content(reply)}


def public_view(host, reply):
    """What the anonymous reader may read of a turn reply (an answerView, lexicons/online/fg-goose/gsb/defs.json): the line,
    receipt and, only when everything the turn read and wrote is public (the host's `inPublic`), its offers and trace; a
    refusal's words only from the host's `public` projection; a `moved` object's versions only when the public views it."""
    if reply.get('status') == 'spells':
        views = [public_view(host, t) for t in reply.get('turns') or []]
        return {'outcome': {'status': 'spells', 'line': '\n'.join(v['outcome']['line'] for v in views)}, 'turns': views}
    reply = public_reply(reply, host)
    if reply.get('class') == 'moved':
        return {'outcome': {'status': 'moved', 'line': reply['line'], 'moved': reply['moved']}}
    if reply.get('status') == 'usage':
        return {'outcome': {'status': 'usage', 'line': reply['text']}}
    rc = reply.get('receipt') or {}
    tag = (rc.get('outcome') or {}).get('tag') or reply.get('status')
    receipt = {'slug': rc['slug'], 'height': rc['height'], 'entry': {'$link': rc['hash']}} if {'hash', 'slug', 'height'} <= set(rc) else None
    view = {'receipt': receipt} if receipt else {}
    if tag == 'refused':
        out = reply.get('public')
        return {'outcome': {'status': 'refused', 'line': refusal_line(out, reply.get('class')),
                            **{k: out[k] for k in ('class', 'clause', 'reason') if isinstance(out.get(k), str)}} if out else
                {'status': 'refused', 'line': 'refused'}, **view}
    if tag == 'suspended':
        return {'outcome': {'status': 'suspended', 'line': f"suspended, entry {rc.get('height')}"}, **view}
    if not rc:
        return {'outcome': {'status': tag, 'line': tag}}
    if reply.get('receiptOnly'):
        return {'outcome': {'status': tag, 'line': f"{tag}, entry {rc.get('height')}, receipt {rc.get('slug')}"}, **view}
    return {'outcome': {'status': tag, 'line': turn_line({**reply, 'status': 'admitted'} if tag == 'admitted' else reply)}, **view,
            **turn_content(reply)}


def write_answer(st, source, view):
    """One public answer writer for proven request references and XRPC provenance."""
    path = answer_path(st, source)
    height = ((view.get('receipt') or {}).get('height') or max([(t.get('receipt') or {}).get('height') or 0 for t in view.get('turns') or []] + [0]))
    st.write(path, {'source': source, **view, '$type': ANSWER,
                                           **({'height': height} if height else {})})


def retained_reply(host, principal, intent, transient):
    """The current identity receipt and its offers, or no bound answer to retain."""
    got = host.send({'op': 'world-receipt', 'principal': principal, 'identity': intent})
    if got.get('class') in ('hostUnavailable', 'hostTimeout') or got.get('status') == 'error':
        return got
    rc = got.get('receipt') or {}
    if not rc:
        return None
    outcome = rc.get('outcome') or {}
    if outcome.get('tag') == 'refused' and outcome.get('class') in transient:
        return None
    reply = {**got, 'status': outcome.get('tag', 'refused'), 'object': (rc.get('roots') or [{}])[0].get('object')}
    if reply['status'] != 'suspended':
        reply['offers'] = [o for o in paged(host, {'op': 'world-offers', 'principal': principal, 'after': rc['height'] - 1}, 'offers')
                           if (o.get('from') or o.get('identity') or {}).get('intent') == intent]
    return reply


def answer_turn(st, host, obs, reply):
    """Answer a request's turn as its record (no draft, no post). -> None when answered or waiting on hob, else why not yet."""
    if reply.get('status') == 'spells':
        turns = reply.get('turns') or []
        if not turns or any('receipt' not in t and t.get('status') != 'usage' for t in turns):
            return 'a spell of it has no receipt'
    if reply.get('status') == 'looked':  # `delvetalk receipt / of:`: whose receipt is the caller's, not the public's
        return write_answer(st, request_source(obs), {'outcome': {'status': 'invalid', 'line': f'a receipt is read from the repository ({NS}receipt), not by request'}})
    if 'receipt' not in reply and reply.get('class') != 'moved' and reply.get('status') not in ('usage', 'spells'):
        return reply.get('message', reply.get('status'))  # the host gave no answer: read again next run
    turns = reply.get('turns') if reply.get('status') == 'spells' else [reply]
    suspended = [t for t in turns if t.get('status') == 'suspended' or ((t.get('receipt') or {}).get('outcome') or {}).get('tag') == 'suspended']
    if suspended:
        st.write(awaiting_path(st, obs['uri']), {'uri': obs['uri'], 'principal': obs['author']['did'], 'request': obs,
                                                 'height': min(t['receipt']['height'] for t in suspended), 'suspended': True,
                                                 **({'turns': turns} if reply.get('status') == 'spells' else {})})
        return None
    return write_answer(st, request_source(obs), public_view(host, reply))


def would_line(t, handles=None):
    """One turn of a try as it would go: `would be admitted bell/1 v1`, `would be refused <clause>: <reading>`, or
    waiting on hob; never a receipt's name."""
    outcome = (t.get('receipt') or {}).get('outcome') or {}
    if outcome.get('tag') == 'refused' or t.get('status') == 'refused':
        return 'would be ' + refusal_line(outcome, t.get('class'))
    if outcome.get('tag') == 'suspended' or t.get('status') == 'suspended':
        return 'would wait for hob to read it; try the spell hob gives'
    root = turn_root(t['receipt'], t.get('object'))
    name = root.get('object') or t.get('object')  # a delivery answered by a receipt already bound reads and writes nothing here
    return 'would be admitted' + (f' {card_name(name, handles)}' if name else '') + (f" v{root['version']}" if root.get('version') is not None else '')


def preview_text(reply, handles=None, host=None, request=None):
    """A try's answer (`world-try`, docs/POSTING.md §2) as a post says it: `preview, nothing done`, then each act as it
    would go (`would_line`), what it would fire, open or close, and the card it would offer, exactly; then what the
    host would settle in the same write (`then …`) and what it would leave for later, counted, not foreseen; last the
    `if:` line of every root's state and supplied behaviour revisions, to put above the same spells so they land only
    if none has moved. An act that reads what the public may not (`inPublic` false) is said by its outcome alone."""
    against = reply.get('against') or {}
    reply = public_reply(reply, host, request)
    turns = reply.get('turns') if reply.get('status') == 'spells' else [reply]
    out, roots = [f"preview, nothing done (as of entry {against.get('height')}):"], {}
    for t in turns:
        if 'receipt' not in t:
            out.append(str(t.get('text') or t.get('message') or t.get('status')).rstrip('\n'))
            continue
        for r in t['receipt'].get('roots') or []:
            roots.setdefault(r['object'], r)
        out.append(would_line(t, handles))
        if not t.get('receiptOnly') and (t['receipt'].get('outcome') or {}).get('tag') not in ('refused', 'suspended'):
            out += [line for line in t.get('revealed') or []] + [o['text'].rstrip('\n') for o in t.get('offers') or []]
    # What the host would settle in the same write, each receipt once: a delivery answered again with a receipt already
    # bound (its identity's) did one thing, however often the settling pass met it.
    settled = set()
    for t in (reply.get('delivered') or []) + (reply.get('resumed') or []):
        key = (t.get('receipt') or {}).get('hash')
        if 'receipt' in t and (key is None or key not in settled):
            settled.add(key)
            out.append('then ' + would_line(t, handles))
    later = reply.get('unresolved') or {}
    if later.get('pending') or later.get('suspended'):
        out.append(f"left for later, not foreseen: {later.get('pending', 0)} sends, {later.get('suspended', 0)} waiting on hob")
    if later.get('answered'):  # sends whose receipt the world binds already: never run again (Ops.answered)
        out.append(f"{later['answered']} sends answered already by their receipts, never run again")
    if roots and all(not t.get('receiptOnly') for t in turns if 'receipt' in t):
        out.append('if: ' + ', '.join(f"{o} v{r['version']}" + (f"/b{r['behaviour']}" if 'behaviour' in r else '')
                                    for o, r in roots.items() if r.get('version') is not None))
    return '\n'.join(out) + '\n'


def lookup_text(reply, handles=None):
    """`delvetalk receipt / of: …` answered (`Serve.receiptAsked`): the receipt's line as the turn's reply said it, or
    that no host issued one by that name (a receipt typed by hand never resolves)."""
    of, found = reply.get('of') or '', reply.get('found') or {}
    receipt = found.get('receipt')
    if found.get('status') == 'resolved' and found.get('carried'):
        return f"receipt {of}: {found.get('message')}\n"
    if found.get('status') == 'resolved' and not receipt:
        return f"{of} names a {found.get('kind')} here, not a receipt\n"
    if receipt and (receipt.get('outcome') or {}).get('tag') == 'refused':
        return f"receipt {receipt.get('slug') or of}: " + refusal_line(receipt['outcome']) + '\n'
    if receipt:
        return receipt_line(receipt, None, None, handles)
    if found.get('status') == 'ambiguous':
        return f"{of} names {found.get('matches')} things here; a receipt by post: delvetalk receipt / of: <your post's at:// address>\n"
    return (f"no turn of yours is {of}\n" if of.startswith('at://') else
            f"no receipt here is named {of}: no host issued it, so it records nothing\n")


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
    seen = st.observations() if waiting else []
    drafted, handles = [], {o['author']['did']: o['author']['handle'] for o in seen}
    said = {o['uri']: o.get('text') or '' for o in seen}  # the words hob read, so the paint is in their tongue
    for principal in dict.fromkeys(w['principal'] for w in waiting):
        for w in [w for w in waiting if w['principal'] == principal and w.get('request')]:  # a request: its answer, once settled
            turns, pending = [], False
            for t in w.get('turns') or [{'status': 'suspended', 'receipt': {'identity': {'intent': w['uri']}}}]:
                if t.get('status') != 'suspended' and ((t.get('receipt') or {}).get('outcome') or {}).get('tag') != 'suspended':
                    turns.append(t)
                    continue
                intent = t['receipt']['identity']['intent']
                got = host.send({'op': 'world-receipt', 'principal': principal, 'identity': intent})
                tag = ((got.get('receipt') or {}).get('outcome') or {}).get('tag')
                if tag in (None, 'suspended'):
                    pending = True
                    break
                offers = [o for o in paged(host, {'op': 'world-offers', 'principal': principal, 'after': w['height'] - 1}, 'offers')
                          if (o.get('from') or o.get('identity') or {}).get('intent') == intent] if got.get('inPublic') else []
                turns.append({**got, 'object': t.get('object'), 'status': tag, 'offers': offers})
            if pending:
                continue
            write_answer(st, request_source(w['request']), public_view(host, {'status': 'spells', 'turns': turns} if w.get('turns') else turns[0]))
            st.write(awaiting_path(st, w['uri']), {**w, 'settled': True})
            drafted.append(w['uri'])
        mine = {(w['principal'], w['uri']): w for w in waiting if w['principal'] == principal and not w.get('request')}
        if not mine:
            continue
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
            if rc and got.get('inPublic'):
                text = with_paint(host, offered_object({'receipt': rc, 'object': w.get('object')}), text,
                                  speaker=principal, words=said.get(w.get('post', uri)))
            st.new_draft(st.outbox / f"{offers[-1]['height']}-off-{key}.json", {
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
                st.new_draft(st.outbox / f"{rc['height']}-off-{key}.json", {
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
            st.new_draft(path, {'publication': {k: p[k] for k in ('id', 'height', 'object')}, 'page': p['page'],
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
    from transport import feed
    failed = []
    heard = feed.observe_feed(st) if feed.exists(st) else []  # the town's own feed: observed as any post, whatever the world's row
    if observer:
        try:
            observer.poll()
        except (Failure, OSError) as error:
            failed.append({'source': st.bridge()['transport'], 'message': str(error)})
    tick(host, now)
    from transport.post import record_sent
    recorded = record_sent(st, host)  # posts whose registration failed, retried apart from sending
    done, skip, origin = [], st.words(st.skipped), st.config.origin
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
        if obs['uri'] in skip or draft_exists(st.outbox, obs['uri']) or awaiting_path(st, obs['uri']).exists() or \
                (obs['kind'] == 'request' and answer_path(st, request_source(obs)).exists()):
            continue
        asked = obs.get('request')  # a proven request record: the same turn as a post's spell, answered by a record
        if asked and asked.get('invalid'):
            write_answer(st, request_source(obs), {'outcome': {'status': 'invalid', 'line': asked['invalid']}})
            done.append(obs['uri'])
            continue
        try:
            target = (asked['call']['object'], None, {'how': 'direct'}) if asked and 'object' in asked['call'] else reach(host, obs, known)
        except Unread as e:
            failed.append({'uri': obs['uri'], 'message': str(e)})
            continue
        if target is None and asked:
            write_answer(st, request_source(obs), {'outcome': {'status': 'unreached', 'line': 'no card reached: a call is a spell, `delvetalk <card> <verb>` '
                                                                             'and its field lines, or {object, verb, fields}'}})
            done.append(obs['uri'])
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
        if how['how'] in ('mention', 'door', 'fields', 'direct'):
            request['reach'] = how['how']  # the reach the host found; a reply and a spell it finds again at the turn
        if asked and 'object' in asked['call']:  # the front's _actions form: the verb on the object, its fields typed
            request.update(method=asked['call']['verb'], argument=typed(asked['call'].get('fields') or {}))
        if asked and 'if' in asked:
            request['if'] = asked['if']  # the host's commit-if-unchanged, verbatim: refused `moved` with what moved
        anchors.before(anchors.reader_for(st), host, obj, request['argument'], did)  # what it cites, on its card's desk first
        reply = host.send(request)
        if asked and reply.get('tried'):  # a `delvetalk try` spell by record: never answered, a preview would publish its draft
            st.append(st.skipped, obs['uri'])
            continue
        if asked:
            why = answer_turn(st, host, obs, reply)
            if why:
                failed.append({'uri': obs['uri'], 'message': why})
            else:
                done.append(obs['uri'])
            continue
        if reply.get('status') == 'looked':  # a receipt looked up: nothing journaled, its line is the answer
            st.new_draft(st.outbox / f"0-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': 'commonplace', 'slot': slot, 'receipt': None, 'posted': False, 'text': lookup_text(reply, handles)})
            done.append(obs['uri'])
            continue
        if reply.get('tried') or reply.get('class') == 'moved':  # a preview, or an act whose `if` moved: nothing journaled
            st.new_draft(st.outbox / f"0-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': obj, 'slot': slot, 'receipt': None, 'preview': bool(reply.get('tried')), 'posted': False,
                'text': preview_text(reply, handles, host, request) if reply.get('tried') else public_reply(reply, host)['line'] + '\n'})
            done.append(obs['uri'])
            continue
        if reply.get('status') == 'spells':  # several spells at a line's start: a turn each, one reply carrying every line
            turns = reply.get('turns') or []
            lost = [t for t in turns if 'receipt' not in t and t.get('status') != 'usage']  # a read journals nothing
            if not turns or lost:
                failed.append({'uri': obs['uri'], 'message': lost[0].get('message') if lost else 'no turns'})
                continue
            ran = [t for t in turns if 'receipt' in t]
            text, told = ''.join(draft_text(t, origin, t.get('object'), handles, compact=True) for t in turns), 0
            for t in ran:  # the first spell that entered a place leads the reply with its telling
                text, told = with_telling(host, did, t, t.get('object') or obj, text, words=obs['text'])
                if told:
                    break
            # A reply answering several cards is no one card's: a bare verb under it would reach whichever came first,
            # so its address is the commonplace, where words go to hob and a spell names its card.
            cards = {t.get('object') or obj for t in turns}
            st.new_draft(st.outbox / f"{ran[-1]['receipt']['height'] if ran else 0}-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': cards.pop() if len(cards) == 1 else 'commonplace', 'slot': slot,
                'receipt': ran[-1]['receipt'] if ran else None, 'posted': False, **told_field(told), 'text': text})
            for t in ran:  # a suspended spell's own answer comes when hob has read it, as a reply to the same post
                if (t['receipt'].get('outcome') or {}).get('tag') == 'suspended':
                    intent = t['receipt']['identity']['intent']
                    st.write(awaiting_path(st, intent), {'uri': intent, 'post': obs['uri'], 'principal': did, 'replyHandle': handle,
                                                         'object': t.get('object') or obj, 'slot': slot, 'height': t['receipt']['height'], 'suspended': True})
            done.append(obs['uri'])
            continue
        if reply.get('status') == 'usage':  # a `?`: the host answers with the card's usage and journals nothing; the post is done
            st.new_draft(st.outbox / f"0-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': obj, 'slot': slot, 'receipt': None, 'usage': True, 'posted': False,
                'text': draft_text(reply, origin, host=host, request=request)})
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
        text = draft_text(reply, origin, obj, handles)
        if reply.get('status') == 'admitted' and reply.get('offers') and reply.get('inPublic') is not False:
            text = with_paint(host, offered_object(reply, obj), text, speaker=did, words=obs['text'])  # the place speaking, above its exact card
        text = first_move(st, did, reply, text)
        text, told = with_telling(host, did, reply, obj, text, words=obs['text'])  # entering a place: what happened there, above it all
        st.new_draft(st.outbox / f"{reply['receipt']['height']}-{uri_hash(obs['uri'])}.json", {
            'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
            'object': obj, 'slot': slot,
            'receipt': reply['receipt'], 'posted': False, **told_field(told), 'text': text})  # text '': journaled, hidden from outbox
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
    failed += [{'requests': p} for p in getattr(observer, 'problems', None) or []]
    answered = feed.post_drafts(st, host) if feed.exists(st) else []  # the town's replies in its own feed: posted now, no hand
    return {**({'feed': heard} if heard else {}), **({'answered': answered} if answered else {}), 'turns': done, 'failed': failed, **({'recorded': recorded} if recorded else {}), **({'mentioned': mentioned} if mentioned else {}), **({'published': published} if published else {}), **({'offered': offered} if offered else {})}


def delve_observer(st, since):
    """The observer of a delve.town world: its posts, and residents' request records only when the config's `requests`
    is on (participant DIDs at their current PDS; it is the owner's to start) and the posts are not fixtures."""
    from transport.requests import Poller
    client = Client(FixtureTransport(st.config.delve_mock) if st.config.delve_mock else None)
    return Observer(st, client, since, Poller(st, client) if st.config.requests and not st.config.delve_mock else None)


def command(st, a, out):
    """`bridge`: the world's row names delve.town, an owner's Zulip channel, or the local feed alone;
    one step with `--once`, else a step every `poll` seconds."""
    host, row = st.host(), st.bridge()
    since = observe.start_cursor(st, a.since, a.now)
    if row['transport'] == 'zulip':
        from transport import zulip
        client = zulip.Client(row['zuliprc'])
        observer = zulip.ZulipObserver(st, client, row['channel'], since, row.get('topic'))
        after = lambda: zulip.post_drafts(st, host, client)
    elif row['transport'] == 'feed':
        observer, after = None, dict
    else:
        observer, after = delve_observer(st, since), dict
    from transport import feed
    full = lambda: out.write(canonical({**run(st, host, observer, now=a.now), **after()}) + '\n') and out.flush()
    last = [0.0]

    def step():
        """A whole step every `poll` seconds, and at once (within FEED_POLL) when someone has posted in the town's feed."""
        if time.monotonic() - last[0] >= st.config.poll or feed.waiting(st):
            last[0] = time.monotonic()
            full()
    try:
        full() if a.once else st.daemon('bridge', step, every=min(st.config.poll, feed.FEED_POLL))
    finally:
        host.close()
