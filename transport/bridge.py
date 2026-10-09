#!/usr/bin/env python3
"""Observed town posts -> host turns -> reply drafts for a human to post.

Never posts: post.py is the only writer. Principals here are the observed authors' DIDs,
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
import time
from pathlib import Path

from transport.delve import Client, FixtureTransport, canonical, http_transport
from transport.http import Host
from transport.observe import Observer

DELIVER_ROUNDS = 8
KINDS = ('spell', 'summon')
CLOCK = 'transport'  # the clock principal named at world-open


def uri_hash(uri):
    return hashlib.sha256(uri.encode()).hexdigest()[:16]


def draft_exists(outbox, uri):
    return any(outbox.glob(f'*-{uri_hash(uri)}.json'))


def write_atomic(path, value):
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        f.write(canonical(value) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def web_url(uri, handle):
    return f"https://delve.town/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}"


# TODO(host `publish`): when the host answers a turn with a `published` result ({page, section, body}),
# turn it into a wiki-edit draft whose text is `edit: <page> › <section>\n\n<body>` and whose replyTo is
# the page post, for post.py --wiki-edit. Until the host supports publish nothing produces one.
def draft_text(reply):
    """The only text a draft carries. A refusal names its class and receipt, nothing of state."""
    receipt = reply['receipt']
    outcome = receipt.get('outcome', {})
    if reply.get('status') == 'refused' or outcome.get('tag') == 'refused':
        return (f"proposal observed, not committed\nreason: {outcome.get('class', 'unknown')}\n"
                f"receipt: {receipt['hash']}\n")
    offers = [o['text'] for o in reply.get('offers') or []]
    if offers:
        return '\n'.join(offers)
    if receipt.get('offers'):
        return f"reply card offered but not retained by the host; receipt: {receipt['hash']}\n"
    return f"turn committed; no reply card offered\nreceipt: {receipt['hash']}\n"


def pending_observations(state):
    db = sqlite3.connect(Path(state) / 'observe.sqlite')
    rows = [json.loads(js) for (js,) in db.execute('SELECT json FROM observations ORDER BY seq')]
    db.close()
    return sorted((o for o in rows if o['kind'] in KINDS or o['replyTo']), key=lambda o: (o['createdAt'], o['uri']))


def skipped(state):
    path = Path(state) / 'skipped.txt'
    return set(path.read_text().split()) if path.exists() else set()


def route(host, obs):
    """-> (object, slot|None) or None. A reply to a journaled post goes to that post's addressee; the
    card word applies only to posts with no journaled parent. TODO(Directory): drop the summon special
    case once Directory is reachable by replying to the journaled welcome post."""
    if obs['replyTo']:
        got = host.send({'op': 'world-addressee', 'parent': obs['replyTo']})
        if got.get('object'):
            return got['object'], got.get('slot')
    if obs['kind'] == 'spell':
        return obs['spell']['card'], None
    if obs['kind'] == 'summon':
        return 'directory', None
    return None


def tick(host):
    """Time enters the journal here and nowhere else: unix minutes, as the clock principal."""
    host.send({'op': 'world-advance', 'height': int(time.time() // 60)})


def run(state, host, poll=None, rounds=DELIVER_ROUNDS):
    state = Path(state)
    outbox = state / 'outbox'
    outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    if poll:
        poll(Observer(state, poll.client))
    tick(host)
    done, failed, skip = [], [], skipped(state)
    for obs in pending_observations(state):
        if obs['uri'] in skip or draft_exists(outbox, obs['uri']):
            continue
        target = route(host, obs)
        if target is None:
            with open(state / 'skipped.txt', 'a') as f:
                f.write(obs['uri'] + '\n')
            continue
        obj, slot = target
        handle, did = obs['author']['handle'], obs['author']['did']
        fields = [{'name': 'text', 'value': {'tag': 'label', 'value': obs['text']}},
                  {'name': 'who', 'value': {'tag': 'label', 'value': did}},
                  {'name': 'post', 'value': {'tag': 'label', 'value': obs['uri']}}]
        if slot is not None:
            fields.append({'name': 'slot', 'value': {'tag': 'label', 'value': slot if isinstance(slot, str) else json.dumps(slot)}})
        reply = host.send({'op': 'world-turn', 'principal': did, 'object': obj, 'method': 'receive',
                           'argument': {'tag': 'record', 'fields': fields}, 'identity': obs['uri']})
        if 'receipt' not in reply:  # the host gave no receipt; nothing to draft, retry next run
            failed.append({'uri': obs['uri'], 'message': reply.get('message', reply.get('status'))})
            continue
        write_atomic(outbox / f"{reply['receipt']['height']}-{uri_hash(obs['uri'])}.json", {
            'replyTo': obs['uri'], 'replyHandle': handle, 'principal': did, 'principalVerified': False,
            'receipt': reply['receipt'], 'text': draft_text(reply), 'posted': False})
        done.append(obs['uri'])
    for _ in range(rounds):
        if not host.send({'op': 'world-pending'}).get('count'):
            break
        host.send({'op': 'world-deliver', 'limit': 16})
    return {'turns': done, 'failed': failed}


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
            stop.wait(interval)
    finally:
        pidfile.unlink(missing_ok=True)


def unposted(state):
    for path in sorted((Path(state) / 'outbox').glob('*.json'), key=lambda p: int(p.name.split('-')[0])):
        d = json.loads(path.read_text())
        if not d['posted']:
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
    r.add_argument('--journal', required=True)
    r.add_argument('--once', action='store_true')
    r.add_argument('--poll', type=int, metavar='SECONDS', help='daemon: observe, turn, draft every SECONDS')
    r.add_argument('--observe', action='store_true', help='read-only: observe the town before bridging (implied by --poll)')
    r.add_argument('--mock', metavar='DIR')
    o = sub.add_parser('outbox')
    o.add_argument('--state', required=True)
    m = sub.add_parser('mark-posted')
    m.add_argument('file')
    a = ap.parse_args(argv)
    if a.cmd == 'outbox':
        for path, d in unposted(a.state):
            out.write(f"=== reply to: {d['replyTo']}\n=== web: {web_url(d['replyTo'], d['replyHandle'])}\n=== as: {d['replyHandle']} {d['principal']} (unverified)  file: {path}\n{d['text'].rstrip()}\n\n")
    elif a.cmd == 'mark-posted':
        mark_posted(a.file)
    else:
        if bool(a.once) == bool(a.poll):
            ap.error('give exactly one of --once and --poll SECONDS')
        host = Host(a.journal, clock=CLOCK)
        try:
            poll = None
            if a.observe or a.poll or a.mock:
                poll = lambda ob: ob.poll()
                poll.client = Client(FixtureTransport(a.mock) if a.mock else http_transport)
            if a.once:
                out.write(canonical(run(a.state, host, poll)) + '\n')
            else:
                daemon(a.state, 'bridge', a.poll, lambda: out.write(canonical(run(a.state, host, poll)) + '\n') and out.flush())
        finally:
            host.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
