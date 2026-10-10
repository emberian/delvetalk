#!/usr/bin/env python3
"""Observed town posts -> host turns -> reply drafts for a human to post.

Never posts: post.py is the only writer (with `--source zulip`, the owner's own Zulip, transport/zulip.py posts drafts itself). Principals here are the observed authors' DIDs,
which are UNVERIFIED (this path serves ember's manual posting).
Run as `python3 -m transport.bridge`.
"""
import argparse
import hashlib
import json
import os
import re
import signal
import sqlite3
import sys
import threading
import urllib.parse
import time
from pathlib import Path

from transport.delve import Client, FixtureTransport, canonical, http_transport
from transport.hostd import CLOCK
from transport.identity import ORIGIN
from transport.hostproc import add_host_args, connect
from transport import observe
from transport.observe import SCHEMA, Observer

DELIVER_ROUNDS = 8
KINDS = ('spell', 'summon')


def uri_hash(uri):
    return hashlib.sha256(uri.encode()).hexdigest()[:16]


def draft_exists(outbox, uri):
    return any(outbox.glob(f'*-{uri_hash(uri)}.json'))


def write_atomic(path, value):
    tmp = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(tmp, 'w') as f:
        f.write(canonical(value) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def slot_arg(slot):
    """A route slot as post.py's --slot argument (principal:intent), or None."""
    if isinstance(slot, dict) and slot.get('principal') and slot.get('intent'):
        return f"{slot['principal']}:{slot['intent']}"
    return slot if isinstance(slot, str) and ':' in slot else None


def post_command(path, d):
    """The one command that posts a draft and records it with the host, then marks it posted."""
    obj = f" --object {d['object']}" if d.get('object') else ''
    slot = f" --slot {d['slot']}" if d.get('slot') else ''
    return (f"=== post: python3 -m transport.post --state STATE post --draft {path} --intent draft-{Path(path).stem}"
            f" --host-socket SOCKET{obj}{slot} --i-am-ember-and-authorize-posting && python3 -m transport.bridge mark-posted {path}")


def web_url(uri, handle):
    return f"https://delve.town/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}"


def cite(object_, version, origin=None):
    """`<object> v<n>` and, with an origin, its short link on the next line. Posts never carry a hash or a blob."""
    text = f'{object_} v{version}' if version is not None else str(object_)
    link = f'\n{origin.rstrip("/")}/o/{urllib.parse.quote(str(object_), safe="")}#v{version}' if origin and version is not None else ''
    return text, link


def receipt_line(receipt, origin=None):
    root = (receipt.get('roots') or [{}])[0]
    text, link = cite(root['object'], root.get('version'), origin) if root.get('object') else ('the journal', '')
    name = f"receipt {receipt['slug']}" if receipt.get('slug') else 'receipt'  # the slug is the name people and posts use
    return f"{name}: {text} at height {receipt.get('height')}{link}\n"


def refusal_line(outcome, fallback_class=None):
    """A refusal as VOICE shapes it, `refused <clause>: <reading>`; a reason that already says so is kept as it is."""
    why = outcome.get('reason') or ''
    if why.startswith(('refused ', 'turn refused')):
        return why
    head, tail = f"refused {outcome.get('clause') or outcome.get('class') or fallback_class}", why or outcome.get('object', '')
    return f'{head}: {tail}' if tail else head


def draft_text(reply, origin=None):
    """The only text a draft carries. A refusal is the turn line, the host's hint when it gives one, and the receipt's name;
    no state, hash or CID. A usage answer is the host's text."""
    if reply.get('status') == 'usage':
        return str(reply.get('text', ''))
    receipt = reply['receipt']
    outcome = receipt.get('outcome', {})
    if reply.get('status') == 'refused' or outcome.get('tag') == 'refused':
        hint = reply.get('hint') or (reply.get('public') or {}).get('hint')
        lines = [refusal_line(outcome, reply.get('class'))] + ([str(hint)] if hint else []) + ([f"receipt {receipt['slug']}"] if receipt.get('slug') else [])
        return '\n'.join(lines) + '\n'
    offers = [o['text'] for o in reply.get('offers') or []]
    if offers:
        return '\n'.join(offers)
    if receipt.get('offers'):
        return 'reply card offered but not retained by the host; ' + receipt_line(receipt, origin)
    return ''  # no offer, no draft


def register(state, host, did, handle):
    """Tell the host an author has arrived, at their first observed post (the clock principal alone may). The call
    is idempotent at the host; the local set is the skip list and only saves the round trips."""
    path = Path(state) / 'principals.txt'
    known = set(path.read_text().split()) if path.exists() else set()
    if did in known:
        return True
    got = host.send({'op': 'world-arrive', 'principal': CLOCK, 'did': did, 'handle': handle})
    if got.get('status') == 'error':
        return False
    with open(path, 'a') as f:
        f.write(did + '\n')
    return True


def awaiting_path(state, uri):
    return Path(state) / 'awaiting' / f'{uri_hash(uri)}.json'


def offer_drafts(state, host):
    """Draft what resumed turns offered. A suspended turn leaves an `awaiting` record; once its interpretation
    settles the resumed entry's offer is in the host's outbox for the author, under the turn's identity (the
    post). One draft per (addressee, identity), so a retry never drafts twice; no offer, no draft."""
    outbox = Path(state) / 'outbox'
    waiting = [json.loads(p.read_text()) for p in sorted((Path(state) / 'awaiting').glob('*.json'))]
    drafted = []
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
            if any(outbox.glob(f'*-off-{key}.json')):
                continue
            w = mine[(principal, uri)]
            write_atomic(outbox / f"{offers[-1]['height']}-off-{key}.json", {
                'replyTo': uri, 'replyHandle': w['replyHandle'], 'principal': principal, 'principalVerified': False,
                'object': w.get('object'), 'slot': w.get('slot'),
                'offer': {'height': offers[-1]['height'], 'identity': uri},
                'text': '\n'.join(o['text'] for o in offers), 'posted': False})
            drafted.append(uri)
    return drafted


def all_observations(state):
    db = sqlite3.connect(Path(state) / 'observe.sqlite')
    db.executescript(SCHEMA)  # fresh state has no table yet
    rows = [json.loads(js) for (js,) in db.execute('SELECT json FROM observations ORDER BY seq')]
    db.close()
    return rows


def pending_observations(state, rows=None):
    rows = all_observations(state) if rows is None else rows
    return sorted((o for o in rows if o['kind'] in KINDS or o['replyTo'] or o['mentions']), key=lambda o: (o['createdAt'], o['uri']))


def skipped(state):
    path = Path(state) / 'skipped.txt'
    return set(path.read_text().split()) if path.exists() else set()


MAX_HOPS = 32
FIELD_LINE = re.compile(r'^\s*[\w-]+:\s*\S', re.M)


def addressed(obs):
    """Was the observation spoken to the system: a spell or summon, or text with a `delvetalk` line or `name: value` field lines."""
    text = obs['text']
    return obs['kind'] in KINDS or 'delvetalk' in text.lower() or bool(FIELD_LINE.search(text))


def refused(reply):
    return reply.get('status') == 'refused' or reply['receipt'].get('outcome', {}).get('tag') == 'refused'
MENTIONS = 4  # the first mentions of a post that are addressed; the rest are ignored


def mention_turns(state, host, obs, authors, handles):
    """A mention is addressed to the mentioned: one turn per mention (a facet's DID, or an @handle that is a known
    author) to env/<did>.mention {text, post} under the author (Env's own method: a stranger's
    `receive` carrying a spell line is retargeted by the host, so a quoted spell would run). Once per post. Only an arrived principal has an Env:
    a mentioned principal the observer has seen is arrived first; one it has not is skipped, with a note in skipped.txt."""
    path = Path(state) / 'mentioned.txt'
    done = set(path.read_text().split()) if path.exists() else set()
    dids = list(dict.fromkeys(d for d in ((m['did'] or authors.get(m['handle'])) for m in obs['mentions'][:MENTIONS]) if d))
    if obs['uri'] in done or not dids:
        return False
    author = obs['author']
    register(state, host, author['did'], author['handle'])
    fields = [{'name': 'text', 'value': {'tag': 'label', 'value': obs['text']}}, {'name': 'post', 'value': {'tag': 'label', 'value': obs['uri']}}]
    replies = []
    for did in dids:
        if did not in handles or not register(state, host, did, handles[did]):
            with open(Path(state) / 'skipped.txt', 'a') as f:
                f.write(f"{obs['uri']}#mention:{did}\n")  # not arrived, so no Env: nothing to send
            continue
        replies.append(host.send({'op': 'world-turn', 'principal': author['did'], 'object': f'env/{did}', 'method': 'mention',
                                  'argument': {'tag': 'record', 'fields': fields}, 'identity': f"{obs['uri']}#env:{did}"}))
    if all('receipt' in r for r in replies):  # else retry next run: the host answers a repeated identity with its first receipt
        with open(path, 'a') as f:
            f.write(obs['uri'] + '\n')
    return bool(replies)


def route(host, obs, known=None):
    """-> (object, slot|None) or None. A reply to a journaled post goes to that post's addressee; the
    card word applies only to posts with no journaled parent, and a summon with none routes to the directory."""
    known, seen, ancestor = known or {}, set(), obs['replyTo']
    for _ in range(MAX_HOPS):  # the nearest recorded ancestor, walking replyTo through what the observer stored
        if not ancestor or ancestor in seen:
            break
        seen.add(ancestor)
        got = host.send({'op': 'world-addressee', 'parent': ancestor})
        if got.get('object'):
            return got['object'], got.get('slot')
        ancestor = (known.get(ancestor) or {}).get('replyTo')
    root = obs.get('root')
    if root and root not in seen:  # then the thread root
        got = host.send({'op': 'world-addressee', 'parent': root})
        if got.get('object'):
            return got['object'], got.get('slot')
    if obs['kind'] == 'spell':
        return obs['spell']['card'], None
    if obs['kind'] == 'summon':
        return 'directory', None
    return None


def publication_text(p):
    """agentwiki: `wiki: <page>` for a whole page, `edit: <page> › <section>` for one section."""
    header = f"wiki: {p['page']}" if not p['section'] else f"edit: {p['page']} › {p['section']}"
    return f"{header}\n\n{p['body']}"


def publication_drafts(state, host):
    """Drafts for what objects published (`world-publications`, read as the clock principal), marked
    like reply drafts and never posted here. A section edit replies to its page's recorded post; one
    drafted before that post was recorded gets it on a later run, while it is unposted."""
    outbox = Path(state) / 'outbox'
    cursor = Path(state) / 'publications.after'
    after = int(cursor.read_text()) if cursor.exists() else 0
    waiting = [d['publication']['height'] for _, d in unposted(state) if 'publication' in d and d['section'] and not d['replyTo']]
    start = min([after] + [h - 1 for h in waiting])
    drafted = []
    while True:
        got = host.send({'op': 'world-publications', 'principal': CLOCK, 'after': start})
        if got.get('status') != 'publications':
            return drafted, got.get('message', got.get('status'))
        for p in got['publications']:
            path = outbox / f"{p['height']}-pub-{p['id'][:16]}.json"
            if path.exists():
                d = json.loads(path.read_text())
                if not d['posted'] and not d['replyTo'] and p.get('replyTo'):
                    write_atomic(path, dict(d, replyTo=p['replyTo']))
                continue
            write_atomic(path, {'publication': {k: p[k] for k in ('id', 'height', 'object')}, 'page': p['page'],
                                'section': p['section'], 'replyTo': p.get('replyTo'), 'text': publication_text(p),
                                'posted': False})
            drafted.append(p['id'])
        heights = [p['height'] for p in got['publications']]
        if not got['more'] or not heights:
            break
        start = heights[-1] - 1  # a page may end inside one entry's publications; drafts already written are kept
    last = max([after] + heights)
    if last > after:
        write_atomic(cursor, last)
    return drafted, None


def tick(host, now=None):
    """Time enters the journal here and nowhere else: unix minutes, as the clock principal.
    `now` (unix seconds) replaces the wall clock for an offline replay."""
    return host.send({'op': 'world-advance', 'principal': CLOCK, 'height': int((time.time() if now is None else now) // 60)})


def run(state, host, poll=None, rounds=DELIVER_ROUNDS, now=None, origin=None):
    state = Path(state)
    outbox = state / 'outbox'
    outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    if poll:
        poll(getattr(poll, 'observer', Observer)(state, poll.client))
    tick(host, now)
    done, failed, skip = [], [], skipped(state)
    rows = all_observations(state)
    observed = pending_observations(state, rows)
    known = {o['uri']: o for o in observed}
    authors = {o['author']['handle'].lower(): o['author']['did'] for o in rows}  # every author seen, so an @handle resolves
    handles = {o['author']['did']: o['author']['handle'] for o in rows}
    for did, handle in handles.items():  # a principal arrives at their first observed post, whatever its kind
        register(state, host, did, handle)
    mentioned = [obs['uri'] for obs in observed if mention_turns(state, host, obs, authors, handles)]
    for obs in observed:
        if obs['uri'] in skip or draft_exists(outbox, obs['uri']) or awaiting_path(state, obs['uri']).exists():
            continue
        target = route(host, obs, known)
        if target is None:
            with open(state / 'skipped.txt', 'a') as f:
                f.write(obs['uri'] + '\n')
            continue
        obj, slot = target
        handle, did = obs['author']['handle'], obs['author']['did']
        register(state, host, did, handle)
        # A card's receive takes {text, post}; the author is the turn's principal. The slot is the host's
        # to fill (receiveArgument), so it is never sent. replyTo makes the turn the recorded post's answer.
        fields = [{'name': 'text', 'value': {'tag': 'label', 'value': obs['text']}},
                  {'name': 'post', 'value': {'tag': 'label', 'value': obs['uri']}}]
        request = {'op': 'world-turn', 'principal': did, 'object': obj, 'method': 'receive',
                   'argument': {'tag': 'record', 'fields': fields}, 'identity': obs['uri']}
        if obs['replyTo']:
            request['replyTo'] = obs['replyTo']
        reply = host.send(request)
        if reply.get('status') == 'usage':  # a `?`: the host answers with the card's usage and journals nothing; the post is done
            write_atomic(outbox / f"0-{uri_hash(obs['uri'])}.json", {
                'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
                'object': obj, 'slot': slot_arg(slot), 'receipt': None, 'usage': True, 'posted': False, 'text': draft_text(reply)})
            done.append(obs['uri'])
            continue
        if 'receipt' not in reply:  # the host gave no receipt; nothing to draft, retry next run
            failed.append({'uri': obs['uri'], 'message': reply.get('message', reply.get('status'))})
            continue
        if reply.get('status') == 'suspended' or reply['receipt'].get('outcome', {}).get('tag') == 'suspended':
            # Nothing was committed and nothing is offered yet: no draft until the interpretation settles.
            write_atomic(awaiting_path(state, obs['uri']), {'uri': obs['uri'], 'principal': did, 'replyHandle': handle, 'object': obj, 'slot': slot_arg(slot),
                                                           'height': reply['receipt']['height']})
            continue
        write_atomic(outbox / f"{reply['receipt']['height']}-{uri_hash(obs['uri'])}.json", {
            'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
            'object': obj, 'slot': slot_arg(slot),
            'receipt': reply['receipt'], 'posted': False,  # unaddressed chatter that was refused is journaled, never drafted
            'text': '' if refused(reply) and not addressed(obs) else draft_text(reply, origin)})  # offerless: text '', hidden from outbox
        if not reply.get('offers'):  # a card may have handed the reply on: its offer arrives later, `from` this post
            write_atomic(awaiting_path(state, obs['uri']), {'uri': obs['uri'], 'principal': did, 'replyHandle': handle, 'object': obj, 'slot': slot_arg(slot), 'height': reply['receipt']['height']})
        done.append(obs['uri'])
    for _ in range(rounds):
        if not host.send({'op': 'world-pending'}).get('count'):
            break
        host.send({'op': 'world-deliver', 'limit': 16})
    offered = offer_drafts(state, host)
    published, problem = publication_drafts(state, host)
    if problem:
        failed.append({'publications': problem})
    return {'turns': done, 'failed': failed, **({'mentioned': mentioned} if mentioned else {}), **({'published': published} if published else {}), **({'offered': offered} if offered else {})}


def daemon(state, name, interval, step, stop=None, sleep=None):
    """Loop step() every `interval` seconds with a pid file; SIGTERM/SIGINT finish the current step and exit."""
    stop = stop or threading.Event()
    pidfile = Path(state) / f'{name}.pid'
    pidfile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text()), 0)
            raise SystemExit(f'{name} already running (pid {pidfile.read_text().strip()})')
        except (ProcessLookupError, ValueError):
            pass
    pidfile.write_text(str(os.getpid()))
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
    try:
        while not stop.is_set():
            step()
            pidfile.touch()  # the heartbeat: the file's age is the time since the last finished step
            stop.wait(interval)
    finally:
        pidfile.unlink(missing_ok=True)


def unposted(state):
    for path in sorted((Path(state) / 'outbox').glob('*.json'), key=lambda p: int(p.name.split('-')[0])):
        d = json.loads(path.read_text())
        if not d['posted'] and not d.get('skipped'):
            yield path, d


def mark_posted(path):
    path = Path(path)
    d = json.loads(path.read_text())
    d['posted'] = True
    write_atomic(path, d)


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='bridge.py')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--state', required=True)
    add_host_args(r)
    r.add_argument('--once', action='store_true')
    r.add_argument('--poll', type=int, metavar='SECONDS', help='daemon: observe, turn, draft every SECONDS')
    r.add_argument('--observe', action='store_true', help='read-only: observe the town before bridging (implied by --poll)')
    r.add_argument('--mock', metavar='DIR')
    r.add_argument('--source', choices=('delve', 'zulip'), default='delve', help='zulip: observe a stream of the owner\'s own Zulip and post drafts back automatically')
    r.add_argument('--zuliprc', metavar='PATH', help='--source zulip: the bot\'s .zuliprc')
    r.add_argument('--stream', default='delvetalk', help='--source zulip: the stream to observe')
    r.add_argument('--origin', default=ORIGIN, help='the front\'s origin, for the short links drafts cite')
    r.add_argument('--since', metavar='ISO', help='observe posts created at or after this time (a deliberate replay). Without it a state that has observed nothing starts from now')
    r.add_argument('--now', type=float, metavar='UNIX_SECONDS', help='the clock for an offline replay (default: the wall clock)')
    o = sub.add_parser('outbox')
    o.add_argument('--state', required=True)
    o.add_argument('--all', action='store_true', help='also list turns that offered nothing (debugging)')
    m = sub.add_parser('mark-posted')
    m.add_argument('file')
    a = ap.parse_args(argv)
    if a.cmd == 'outbox':
        for path, d in unposted(a.state):
            if not d['text'] and not a.all:
                continue  # the receipt is journaled; an offerless turn has nothing to post
            if 'publication' in d:
                p = d['publication']
                where = f"--reply-to {d['replyTo']} " if d['replyTo'] else ''
                need = '' if d['replyTo'] or not d['section'] else '=== needs: the page post first (post and --record the whole page)\n'
                out.write(f"=== publish for: {p['object']}  file: {path}\n{need}=== post: python3 -m transport.post --state STATE post "
                          f"--text-file TEXT {where}--intent {p['id']} --host-socket SOCKET --object {p['object']}\n{d['text'].rstrip()}\n\n")
                continue
            out.write(f"=== reply to: {d['replyTo']}\n=== web: {web_url(d['replyTo'], d['replyHandle'])}\n=== as: {d['replyHandle']} {d['principal']} (unverified)  file: {path}\n{post_command(path, d)}\n{d['text'].rstrip()}\n\n")
    elif a.cmd == 'mark-posted':
        mark_posted(a.file)
    else:
        if bool(a.once) == bool(a.poll):
            ap.error('give exactly one of --once and --poll SECONDS')
        host = connect(a)
        try:
            poll, after = None, lambda: {}
            since = observe.start_cursor(a.state, a.since, a.now) if (a.source == 'zulip' or a.observe or a.poll or a.mock) else None
            if a.source == 'zulip':
                from transport import zulip
                if not a.zuliprc:
                    ap.error('--source zulip needs --zuliprc')
                client = zulip.Client(a.zuliprc)
                poll = lambda ob: ob.poll()
                poll.client, poll.observer = client, lambda state, c: zulip.ZulipObserver(state, c, a.stream, since)
                after = lambda: zulip.post_drafts(a.state, host, client, a.stream)
            elif a.observe or a.poll or a.mock:
                poll = lambda ob: ob.poll()
                poll.client = Client(FixtureTransport(a.mock) if a.mock else http_transport)
                poll.observer = lambda state, c: Observer(state, c, since)
            if a.once:
                out.write(canonical({**run(a.state, host, poll, now=a.now, origin=a.origin), **after()}) + '\n')
            else:
                daemon(a.state, 'bridge', a.poll, lambda: out.write(canonical({**run(a.state, host, poll, origin=a.origin), **after()}) + '\n') and out.flush())
        finally:
            host.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
