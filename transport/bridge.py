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
import sqlite3
import sys
from pathlib import Path

from transport.delve import Client, FixtureTransport, canonical, http_transport
from transport.http import Host
from transport.observe import Observer

DELIVER_ROUNDS = 8
KINDS = ('spell', 'summon')


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
    return sorted((o for o in rows if o['kind'] in KINDS), key=lambda o: (o['createdAt'], o['uri']))


def run(state, host, poll=None, rounds=DELIVER_ROUNDS):
    state = Path(state)
    outbox = state / 'outbox'
    outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    if poll:
        poll(Observer(state, poll.client))
    done, failed = [], []
    for obs in pending_observations(state):
        if draft_exists(outbox, obs['uri']):
            continue
        handle, did = obs['author']['handle'], obs['author']['did']
        obj = 'directory' if obs['kind'] == 'summon' else obs['spell']['card']
        reply = host.send({'op': 'world-turn', 'principal': did, 'object': obj, 'method': 'receive',
                           'argument': {'tag': 'record', 'fields': [
                               {'name': 'text', 'value': {'tag': 'label', 'value': obs['text']}},
                               {'name': 'post', 'value': {'tag': 'label', 'value': obs['uri']}}]},
                           'identity': obs['uri']})
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
    r.add_argument('--once', action='store_true', required=True)
    r.add_argument('--poll', action='store_true', help='read-only: observe the town before bridging')
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
        host = Host(a.journal)
        try:
            poll = None
            if a.poll or a.mock:
                client = Client(FixtureTransport(a.mock) if a.mock else http_transport)
                poll = lambda ob: ob.poll()
                poll.client = client
            out.write(canonical(run(a.state, host, poll)) + '\n')
        finally:
            host.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
