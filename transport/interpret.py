"""The interpretation loop: pending host requests -> one model call each -> submitted verbatim.

  world-interpretations            -> {status: "interpretations", pending: [{id, object, policy, utterance, offers, attempts, next}]}
  world-interpretation {id, reply} -> the host decides: a verdict, or {status: "retrying", attempt, next} for a failure it retries.
`reply` is exactly model.py's result object, failures included; whether and when to ask again is the host's (an item
whose `next` is not null waits). Python decides nothing. The reply is cached by id before it is submitted, so a crash
resubmits it and never calls the model twice; a request the host lists as pending is submitted again from that cache
whatever happened before (a restored journal). A `retrying` answer drops the cache, so the next ask is a new call.
Run as `python3 -m transport interpret --state DIR [--world W] [--once]`.
"""
import hashlib
import json

from transport import model
from transport.delve import canonical


def cache_path(st, request_id):
    return st.interpretations / (hashlib.sha256(str(request_id).encode()).hexdigest()[:24] + '.json')


def request(item):
    """The model request: the host's policy text as the system, the utterance as the user turn, once. Policy.prompt still
    ends with `Participant: <utterance>`; that tail is cut here so it is not sent twice (FLEX.md)."""
    policy, tail = item['policy'], '\n\nParticipant: ' + item['utterance']
    system = policy.get('system', '')
    return {'model': policy.get('model'), 'system': system[:-len(tail)] if system.endswith(tail) else system, 'user': item['utterance']}


def run(st, host, ask=model.ask):
    """Ask the model for each pending request the host says may be asked now, and submit its result verbatim."""
    listed = host.send({'op': 'world-interpretations'})
    if listed.get('status') == 'error':
        return {'settled': [], 'failed': [{'message': listed.get('message')}]}
    settled, failed, retrying = [], [], []
    for item in listed.get('pending') or []:
        path = cache_path(st, item['id'])
        saved = json.loads(path.read_text()) if path.exists() else None
        if saved is None:
            if item.get('next') is not None:  # the host's backoff: not yet
                retrying.append(item['id'])
                continue
            saved = {'id': item['id'], 'object': item['object'], 'reply': ask(request(item))}
            st.write(path, saved)
        answer = host.send({'op': 'world-interpretation', 'id': item['id'], 'reply': saved['reply']})
        if answer.get('status') == 'error':
            failed.append({'id': item['id'], 'message': answer.get('message')})
        elif answer.get('status') == 'retrying':
            path.unlink()
            retrying.append(item['id'])
        else:
            st.write(path, dict(saved, answer=answer))
            settled.append(item['id'])
    return {'settled': settled, 'failed': failed, **({'retrying': retrying} if retrying else {})}


def command(st, a, out):
    """`interpret`: one round with `--once`, else a round every `poll` seconds."""
    host = st.host()
    step = lambda: out.write(canonical(run(st, host, lambda req: model.ask(req, st))) + '\n') and out.flush()
    try:
        step() if a.once else st.daemon('interpret', step)
    finally:
        host.close()
