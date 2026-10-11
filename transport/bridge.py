"""Observed posts -> host turns -> reply drafts for a human to post (`python3 -m transport bridge`).

Never posts to delve.town: `post` is the only writer there. A world whose bridge row is a Zulip channel, the owner's own,
has its drafts posted by transport/zulip.py. Principals here are the observed authors' DIDs, which are UNVERIFIED.
"""
import hashlib
import ipaddress
import json
import re
import sqlite3
import urllib.parse
import time

from transport.delve import Client, FixtureTransport, canonical, http_transport
from transport.host import CLOCK, ON_ROOT
from transport import observe
from transport.observe import SCHEMA, Observer

DELIVER_ROUNDS = 8


def uri_hash(uri):
    return hashlib.sha256(uri.encode()).hexdigest()[:16]


def draft_exists(outbox, uri):
    return any(outbox.glob(f'*-{uri_hash(uri)}.json'))


def slot_arg(slot):
    """A route slot as post.py's --slot argument (principal:intent), or None."""
    if isinstance(slot, dict) and slot.get('principal') and slot.get('intent'):
        return f"{slot['principal']}:{slot['intent']}"
    return slot if isinstance(slot, str) and ':' in slot else None


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
    """How a line names a card: a person's own cards by their handle (`kestrel's wake`, `kestrel's env`, `kestrel's avatar`,
    the avatar's id being the DID), a DID never reaching a post; any other card by its id."""
    handles = handles or {}
    for prefix in ('wake/', 'env/'):
        if object_.startswith(prefix) and object_[len(prefix):] in handles:
            return f"{handles[object_[len(prefix):]]}'s {prefix[:-1]}"
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


def draft_text(reply, origin=None, addressed=None, handles=None):
    """The only text a draft carries. A refusal is drafted when the host gives it a `public` projection (whether to say it
    is the host's fact; the post's wording is never read for it): the turn line, the host's hint when it gives one, and the
    receipt's name; no state, hash or CID. A usage answer is the host's text."""
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
    if offers:  # every reply ends with its receipt's spoken name
        return '\n'.join(offers).rstrip('\n') + '\n' + receipt_line(receipt, origin, addressed, handles)
    if receipt.get('offers'):
        return 'reply card offered but not retained by the host; ' + receipt_line(receipt, origin, addressed, handles)
    return ''  # no offer, no draft


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
    post). One draft per (addressee, identity), so a retry never drafts twice; no offer, no draft. The draft ends
    with the receipt of the author's turn on that post, as the host names it (`world-receipt`)."""
    waiting = [json.loads(p.read_text()) for p in sorted(st.awaiting.glob('*.json'))]
    drafted, handles = [], {o['author']['did']: o['author']['handle'] for o in all_observations(st)} if waiting else {}
    for principal in dict.fromkeys(w['principal'] for w in waiting):
        mine = {(w['principal'], w['uri']): w for w in waiting if w['principal'] == principal}
        after, grouped = min(w['height'] for w in mine.values()) - 1, {}
        while True:
            got = host.send({'op': 'world-offers', 'principal': principal, 'after': max(0, after)})
            if got.get('status') != 'offers':
                break
            for o in got['offers']:
                who = o.get('from') or o['identity']  # {principal, intent}: `from` is the originating post of a handed-on turn
                if isinstance(who, dict) and (who.get('principal'), who.get('intent')) in mine:
                    grouped.setdefault((who['principal'], who['intent']), []).append(o)
            if not got.get('more') or not got['offers']:
                break
            after = got['offers'][-1]['height']
        for (_, uri), offers in grouped.items():
            key = hashlib.sha256(f'{principal}\0{uri}'.encode()).hexdigest()[:16]
            if any(st.outbox.glob(f'*-off-{key}.json')):
                continue
            w = mine[(principal, uri)]
            rc = host.send({'op': 'world-receipt', 'principal': principal, 'identity': uri}).get('receipt')
            text = '\n'.join(o['text'] for o in offers).rstrip('\n') + ('\n' + receipt_line(rc, st.config.origin, w.get('object'), handles) if rc else '')
            st.write(st.outbox / f"{offers[-1]['height']}-off-{key}.json", {
                'replyTo': uri, 'replyHandle': w['replyHandle'], 'principal': principal, 'principalVerified': False,
                'object': w.get('object'), 'slot': w.get('slot'),
                'offer': {'height': offers[-1]['height'], 'identity': uri},
                'text': text, 'posted': False})
            drafted.append(uri)
    return drafted


def all_observations(st):
    st.home.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(st.observed)
    db.executescript(SCHEMA)  # fresh state has no table yet
    rows = [json.loads(js) for (js,) in db.execute('SELECT json FROM observations ORDER BY seq')]
    db.close()
    return rows


def pending_observations(rows):
    """What may be spoken to the system: a summon, a reply, a mention, or a post the host may read as a spell."""
    return sorted((o for o in rows if o['kind'] == 'summon' or o['replyTo'] or o['mentions'] or (o['kind'] == 'post' and 'delvetalk' in o['text'])),
                  key=lambda o: (o['createdAt'], o['uri']))


def parsed(host, obs):
    """The host's reading of the post (`spell-parse`): {spell: {card, …}} or {notASpell}, with `bare` field lines; {} for
    a text the parser has nothing to read in (no `delvetalk` line, no `:`) and for a wiki post, which is a page."""
    if obs['kind'].startswith('wiki') or ('delvetalk' not in obs['text'] and ':' not in obs['text']):
        return {}
    got = host.send({'op': 'spell-parse', 'text': obs['text']})
    if got.get('status') != 'parsed':
        raise Unread(got.get('message', got.get('status')))  # the host did not read it: the post waits for the next run
    return got


class Unread(Exception):
    pass


MAX_HOPS = 32
MENTIONS = 4  # the first mentions of a post that are addressed; the rest are ignored


def mention_turns(st, host, obs, authors, handles):
    """A mention is addressed to the mentioned: one turn per mention (a facet's DID, or an @handle that is a known
    author) to env/<did>.write {text, post} under the author (Env's own method: a stranger's
    `receive` carrying a spell line is retargeted by the host, so a quoted spell would run). Once per post. Only an arrived principal has an Env:
    a mentioned principal the observer has seen is arrived first; one it has not is skipped, with a note in skipped.txt."""
    done = st.words(st.mentioned)
    dids = list(dict.fromkeys(d for d in ((m['did'] or authors.get(m['handle'])) for m in obs['mentions'][:MENTIONS]) if d))
    if obs['uri'] in done or not dids:
        return False
    author = obs['author']
    register(st, host, author['did'], author['handle'])
    fields = [{'name': 'text', 'value': {'tag': 'label', 'value': obs['text']}}, {'name': 'post', 'value': {'tag': 'label', 'value': obs['uri']}}]
    replies = []
    for did in dids:
        if did not in handles or not register(st, host, did, handles[did]):
            st.append(st.skipped, f"{obs['uri']}#mention:{did}")  # not arrived, so no Env: nothing to send
            continue
        replies.append(host.send({'op': 'world-turn', 'principal': author['did'], 'object': f'env/{did}', 'method': 'write',
                                  'argument': {'tag': 'record', 'fields': fields}, 'identity': f"{obs['uri']}#env:{did}"}))
    if all('receipt' in r for r in replies):  # else retry next run: the host answers a repeated identity with its first receipt
        st.append(st.mentioned, obs['uri'])
    return bool(replies)


def plain(data):
    """Typed data as plain JSON, for reading only (a form's fields); never sent back to the host."""
    tag = data.get('tag') if isinstance(data, dict) else None
    if tag == 'record':
        return {f['name']: plain(f['value']) for f in data['fields']}
    if tag == 'list':
        return [plain(i) for i in data['items']]
    if tag == 'variant':
        inner = plain(data['payload'])
        return {'tag': data['label'], **inner} if isinstance(inner, dict) else {'tag': data['label'], 'value': inner}
    return int(data['value']) if tag == 'natural' else data.get('value') if tag else data


def door_rows(view):
    """The doors a record cites (its `cites` list, in the owner's order), those with an object."""
    state = plain(view.get('state') or {})
    doors = (state.get('cites') if isinstance(state, dict) else None) or []
    return [d for d in doors if isinstance(d, dict) and (d.get('to') or {}).get('object')]


def route(host, obs, known=None):
    """-> (object, slot|None, how) or None: where a post reaches (FLEX.md), and how, for the host to judge: `replyTo`, the
    recorded post it answers (the host verifies a reply), or `reach`, the rule it matched (HOST-HANDOFF 118). (a) A reply reaches the card whose recorded post
    (the card's, or any of the world's replies under it) is its direct parent; on Zulip, where a topic is one thread, the
    nearest recorded message above it in the topic, unless it @-mentions only other residents. (b) A spell line reaches
    its card, as the host reads it; a summons (a mention of the world, #gsb) reaches the commonplace, whose interpreter
    may answer `none`. (c) Field lines anywhere in a thread the world opened reach that thread's card, which completes
    them, and (d) prose there that names one of the commonplace's doors reaches that door's card. Other prose deeper in a
    thread, addressed to another resident, does not reach by the thread's root."""
    zulip = obs['uri'].startswith('zulip://')
    known, ancestor = known or {}, obs['replyTo']
    hops = 0 if zulip and obs['mentions'] and obs['kind'] != 'summon' else MAX_HOPS if zulip else 1
    asked = set()
    found = walk(host, ancestor, known, hops, asked)
    if found:
        return found[0], found[1], {'replyTo': found[2]}
    read = parsed(host, obs)
    if (read.get('spell') or {}).get('card'):
        return read['spell']['card'], None, {}  # the host reads the spell itself
    if obs['kind'] == 'summon':
        return 'commonplace', None, {'reach': 'mention'}
    if zulip or not ancestor:
        return None
    root = obs.get('root')  # the thread's card: its nearest recorded ancestor, or its root
    thread = walk(host, (known.get(ancestor) or {}).get('replyTo'), known, MAX_HOPS, asked) or (lambda got: (
        got['object'], got.get('slot')) if got.get('object') else None)(host.send({'op': 'world-addressee', 'parent': root}) if root and root != ancestor else {})
    if not thread:
        return None
    if read.get('bare'):  # (c) field lines: the thread's card completes them
        return thread[0], thread[1], {'reach': 'fields'}
    door = named_door(host, obs)  # (d) prose naming a door reaches that door's card
    return (door, None, {'reach': 'door'}) if door else None


def named_door(host, obs):
    """The card of the first door (of the commonplace's, as the host shows them) whose label the text names as a word."""
    doors = {str(d.get('label', '')).lower(): d['to']['object'] for d in door_rows(host.send({'op': 'world-view', 'principal': CLOCK, 'object': 'commonplace'}))}
    return next((doors[w] for w in re.findall(r"[\w'-]+", obs['text'].lower()) if w in doors), None)


def walk(host, ancestor, known, hops, seen):
    """The addressee of the nearest recorded post among `hops` ancestors, walking replyTo through what was observed;
    `seen` holds the posts already asked about, so a cycle or a second walk never asks twice."""
    for _ in range(hops):
        if not ancestor or ancestor in seen:
            return None
        seen.add(ancestor)
        got = host.send({'op': 'world-addressee', 'parent': ancestor})
        if got.get('object'):
            return got['object'], got.get('slot'), ancestor
        ancestor = (known.get(ancestor) or {}).get('replyTo')
    return None


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
    rows = all_observations(st)
    observed = pending_observations(rows)
    known = {o['uri']: o for o in observed}
    authors = {o['author']['handle'].lower(): o['author']['did'] for o in rows}  # every author seen, so an @handle resolves
    handles = {o['author']['did']: o['author']['handle'] for o in rows}
    for did, handle in handles.items():  # a principal arrives at their first observed post, whatever its kind
        register(st, host, did, handle)
    mentioned = [obs['uri'] for obs in observed if mention_turns(st, host, obs, authors, handles)]
    for obs in observed:
        if obs['uri'] in skip or draft_exists(st.outbox, obs['uri']) or awaiting_path(st, obs['uri']).exists():
            continue
        try:
            target = route(host, obs, known)
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
        if how.get('reach'):
            request['reach'] = how['reach']  # what the bridge saw: mention, door or fields (HOST-HANDOFF 118)
        reply = host.send(request)
        if reply.get('status') == 'usage':  # a `?`: the host answers with the card's usage and journals nothing; the post is done
            st.write(st.outbox / f"0-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': obj, 'slot': slot_arg(slot), 'receipt': None, 'usage': True, 'posted': False, 'text': draft_text(reply)})
            done.append(obs['uri'])
            continue
        if reply.get('message') == ON_ROOT:  # the opener's own post: her authority is the root socket, which the bridge never holds
            st.append(st.skipped, obs['uri'])
            continue
        if 'receipt' not in reply:  # the host gave no receipt; nothing to draft, retry next run
            failed.append({'uri': obs['uri'], 'message': reply.get('message', reply.get('status'))})
            continue
        if reply.get('status') == 'suspended' or reply['receipt'].get('outcome', {}).get('tag') == 'suspended':
            # Nothing was committed and nothing is offered yet: no draft until the interpretation settles.
            st.write(awaiting_path(st, obs['uri']), {'uri': obs['uri'], 'principal': did, 'replyHandle': handle, 'object': obj, 'slot': slot_arg(slot),
                                                     'height': reply['receipt']['height']})
            continue
        st.write(st.outbox / f"{reply['receipt']['height']}-{uri_hash(obs['uri'])}.json", {
            'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
            'object': obj, 'slot': slot_arg(slot),
            'receipt': reply['receipt'], 'posted': False, 'text': draft_text(reply, origin, obj, handles)})  # text '': journaled, hidden from outbox
        if not reply.get('offers'):  # a card may have handed the reply on: its offer arrives later, `from` this post
            st.write(awaiting_path(st, obs['uri']), {'uri': obs['uri'], 'principal': did, 'replyHandle': handle, 'object': obj, 'slot': slot_arg(slot), 'height': reply['receipt']['height']})
        done.append(obs['uri'])
    for _ in range(rounds):
        if not host.send({'op': 'world-pending'}).get('count'):
            break
        host.send({'op': 'world-deliver', 'limit': 16})
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
