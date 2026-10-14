"""The one model worker: what the host asks of the world's model -> one call each -> submitted verbatim.

Interpretations (words read into a spell, journaled):
  world-interpretations            -> {status: "interpretations", pending: [{id, object, policy, utterance, offers, attempts, next}]}
  world-interpretation {id, reply} -> the host decides: a verdict, or {status: "retrying", attempt, next} for a failure it retries.
Paints (a card painted from its strokes, cached by the host and never journaled; docs/OVERHAUL.md section 4):
  world-renders                    -> {status: "renders", pending: [{key, object, version, attempts, request}]}
  world-render-submit {key, reply} -> the host verifies: painted, exact (refused by a clause), or retrying.
`reply` is exactly model.py's result object, failures included; whether and when to ask again is the host's (an item
whose `next` is not null waits; a render the host does not list yet is not asked). Python decides nothing. An
interpretation's reply is cached by id before it is submitted, so a crash resubmits it and never calls the model twice;
a request the host lists as pending is submitted again from that cache whatever happened before (a restored journal). A
`retrying` answer drops the cache, so the next ask is a new call. A round asks every interpretation first and then at
most PAINTS_PER_ROUND paints, so words wait on at most that many paints. A paint is not journaled, so it is not cached here:
a crash between the call and the submit costs one call. Every call is a line of the spend ledger, `use` naming which.
Run as `python3 -m transport interpret --state DIR [--world W] [--once]`: a round every second, so a
reader's paint can arrive inside the host's `patience`.
"""
import hashlib
import json

from transport import model
from transport.delve import canonical


def cache_path(st, request_id):
    return st.interpretations / (hashlib.sha256(str(request_id).encode()).hexdigest()[:24] + '.json')


def request(item):
    """The model request: the host's policy text as the system; the user turn as the host composed it (residents' writing quoted, then the utterance)."""
    policy = item['policy']
    return {'model': policy.get('model'), 'system': policy.get('system', ''), 'user': item.get('user', item['utterance'])}


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


PAINTS_PER_ROUND = 2  # a round paints at most this many, so a resident's words never wait behind a town's worth of paints


def paint(host, ask=model.ask, limit=None):
    """Submit the listed renders verbatim, up to `limit` (the worker's round: the rest next round, after the
    interpretations; playtest 5's ghost words waited); retain the host's retry/refusal verdict for diagnosis."""
    listed = host.send({'op': 'world-renders'})
    if listed.get('status') != 'renders':
        return {'painted': [], 'failed': [{'message': listed.get('message')}]}
    done = {'painted': [], 'exact': [], 'retrying': [], 'failed': [], 'verdicts': []}
    for item in (listed.get('pending') or [])[:limit]:
        answer = host.send({'op': 'world-render-submit', 'key': item['key'], 'reply': ask(dict(item['request'], use='paint'))})
        which = {'painted': 'painted', 'exact': 'exact', 'retrying': 'retrying'}.get(answer.get('status'), 'failed')
        done[which].append(item['key'] if which != 'failed' else {'key': item['key'], 'message': answer.get('message')})
        if which in ('exact', 'retrying'):
            done['verdicts'].append({k: answer[k] for k in
                                     ('status', 'object', 'version', 'key', 'reason', 'clause', 'detail', 'attempts', 'next')
                                     if k in answer})
    return {k: v for k, v in done.items() if v or k == 'painted'}


def command(st, a, out):
    """`interpret`: one round with `--once`, else a round every second: interpretations, then paints."""
    host = st.host()
    ask = lambda req: model.ask(req, st)

    def step(always=False):
        rounds = {**run(st, host, ask), 'paints': paint(host, ask, PAINTS_PER_ROUND)}
        if always or rounds['settled'] or rounds['failed'] or rounds.get('retrying') or rounds['paints'] != {'painted': []}:
            out.write(canonical(rounds) + '\n')  # a quiet round says nothing: the worker steps every second
            out.flush()
    try:
        step(True) if a.once else st.daemon('interpret', step, every=1.0)
    finally:
        host.close()
