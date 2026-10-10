#!/usr/bin/env python3
"""The interpretation loop: pending host requests -> one model call each -> submitted verbatim.

  world-interpretations            -> {status: "interpretations", pending: [{id, object, policy, utterance, offers, attempts, next}]}
  world-interpretation {id, reply} -> the host decides: a verdict, or {status: "retrying", attempt, next} for a failure it retries.
`reply` is exactly model.py's result object, failures included; whether and when to ask again is the host's (an item
whose `next` is not null waits). Python decides nothing. The reply is cached by id before it is submitted, so a crash
resubmits it and never calls the model twice; a request the host lists as pending is submitted again from that cache
whatever happened before (a restored journal). A `retrying` answer drops the cache, so the next ask is a new call.
Run as `python3 -m transport.interpret run --state DIR --journal J --once`.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from transport import model
from transport.bridge import daemon, write_atomic
from transport.delve import canonical
from transport.hostproc import add_host_args, connect


def cache_path(state, request_id):
    return Path(state) / 'interpretations' / (hashlib.sha256(str(request_id).encode()).hexdigest()[:24] + '.json')


def request(item):
    """The model request: the host's policy text as the system, the utterance as the user turn, once. Policy.prompt still
    ends with `Participant: <utterance>`; that tail is cut here so it is not sent twice (FLEX.md)."""
    policy, tail = item['policy'], '\n\nParticipant: ' + item['utterance']
    system = policy.get('system', '')
    return {'model': policy.get('model'), 'system': system[:-len(tail)] if system.endswith(tail) else system, 'user': item['utterance']}


def run(state, host, ask=model.ask):
    """Ask the model for each pending request the host says may be asked now, and submit its result verbatim."""
    listed = host.send({'op': 'world-interpretations'})
    if listed.get('status') == 'error':
        return {'settled': [], 'failed': [{'message': listed.get('message')}]}
    settled, failed, retrying = [], [], []
    for item in listed.get('pending') or []:
        path = cache_path(state, item['id'])
        saved = json.loads(path.read_text()) if path.exists() else None
        if saved is None:
            if item.get('next') is not None:  # the host's backoff: not yet
                retrying.append(item['id'])
                continue
            saved = {'id': item['id'], 'object': item['object'], 'reply': ask(request(item))}
            write_atomic(path, saved)
        answer = host.send({'op': 'world-interpretation', 'id': item['id'], 'reply': saved['reply']})
        if answer.get('status') == 'error':
            failed.append({'id': item['id'], 'message': answer.get('message')})
        elif answer.get('status') == 'retrying':
            path.unlink()
            retrying.append(item['id'])
        else:
            write_atomic(path, dict(saved, answer=answer))
            settled.append(item['id'])
    return {'settled': settled, 'failed': failed, **({'retrying': retrying} if retrying else {})}


def main(argv=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='interpret.py')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--state', required=True)
    add_host_args(r)
    r.add_argument('--once', action='store_true')
    r.add_argument('--poll', type=int, metavar='SECONDS', help='daemon: settle pending requests every SECONDS')
    r.add_argument('--mock', metavar='DIR', help='answer from model fixtures instead of the network')
    a = ap.parse_args(argv)
    if bool(a.once) == bool(a.poll):
        ap.error('give exactly one of --once and --poll SECONDS')
    host = connect(a)
    step = lambda: out.write(canonical(run(a.state, host, lambda req: model.ask(req, a.mock, state=a.state))) + '\n') and out.flush()
    try:
        step() if a.once else daemon(a.state, 'interpret', a.poll, step)
    finally:
        host.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
