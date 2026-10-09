#!/usr/bin/env python3
"""The interpretation loop: pending host requests -> one model call each -> settled verbatim.

Host contract (the host2 lane adds these ops):
  world-interpretations            -> {status: "interpretations", pending: [{id, object, policy: {model, system, examples}, utterance, offers}]}
  world-interpretation {id, reply} -> settles; the host checks the reply against the offered forms.
`reply` is exactly model.py's result object. Python decides nothing. A receipt file per request id is
written before settling, so a crash re-settles the saved reply and never calls the model twice.
Run as `python3 -m transport.interpret run --state DIR --journal J --once`.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from transport import model
from transport.bridge import daemon, write_atomic
from transport.delve import canonical
from transport.hostproc import add_host_args, connect


def receipt_path(state, request_id):
    return Path(state) / 'interpretations' / (hashlib.sha256(str(request_id).encode()).hexdigest()[:24] + '.json')


def user_content(item):
    return item['utterance']  # the host's policy.system carries the lexicon, examples and forms


TRANSIENT, MAX_ATTEMPTS, BACKOFF = ('transport', 'rate'), 8, 60


def run(state, host, ask=model.ask, now=time.time):
    """Settle each pending request with the model's reply. A transient failure (transport, rate) is not
    settled: the attempt is recorded in the receipt file and retried after a backoff, until MAX_ATTEMPTS."""
    listed = host.send({'op': 'world-interpretations'})
    if listed.get('status') == 'error':
        return {'settled': [], 'failed': [{'message': listed.get('message')}]}
    settled, failed, retrying = [], [], []
    for item in listed.get('pending') or []:
        path = receipt_path(state, item['id'])
        saved = json.loads(path.read_text()) if path.exists() else None
        if saved and saved['settled']:
            continue
        if saved is None or saved.get('retry'):
            if saved and saved['next'] > now():
                retrying.append(item['id'])
                continue
            policy = item['policy']
            reply = ask({'model': policy.get('model'), 'system': policy.get('system', ''), 'user': user_content(item)})
            attempts = (saved or {}).get('attempts', 0) + 1
            transient = reply.get('status') == 'failed' and reply.get('reason') in TRANSIENT and attempts < MAX_ATTEMPTS
            saved = {'id': item['id'], 'object': item['object'], 'reply': reply, 'settled': False, 'attempts': attempts}
            if transient:
                write_atomic(path, dict(saved, retry=True, next=now() + BACKOFF * 2 ** (attempts - 1)))
                retrying.append(item['id'])
                continue
            write_atomic(path, saved)
        answer = host.send({'op': 'world-interpretation', 'id': item['id'], 'reply': saved['reply']})
        if answer.get('status') == 'error':
            failed.append({'id': item['id'], 'message': answer.get('message')})
            continue
        write_atomic(path, dict(saved, settled=True, answer=answer))
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
