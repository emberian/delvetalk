"""The automatic moderation's worker (docs/ROOT.md section 2.4): retroactive, never in a turn's path, its own model and budget.

Every second it asks the host, on the root socket as the opener, for the texts written since its cursor
(`world-screen {after, external}`), offering the feed's new posts beside them; the host answers the texts and has
already acted on any its wordlist names. The worker holds what is new; once it has held a text for 5 seconds, or holds
24 texts, it asks the classifier (glm-5.3-flash on the owner's Z.ai subscription, its Anthropic-compatible Messages
endpoint) about the batch in one call, each text numbered, and gives the host the classifier's reply verbatim
(`world-screen-verdicts`). The host decides
what a verdict does and journals it; nothing here hides or quiets anything. An idle worker asks the host and calls no
model. When the classifier fails, the texts wait (the cursor and the held texts are kept on disk, so a restart loses
none), the worker backs off, and its status file says so for the hand's overview; when the provider's own filter refuses
a batch, the worker asks again in halves, and a single text the provider refuses goes to the host as `blocked`.

The key is a file (`zai_key_file`), read on every call; spend is a line a call in <state>/automod-spend.jsonl, kept
apart from the Anthropic ledger (tokens only: a subscription has no per-token price), and the day's calls are capped
at 2,000. Run as
`python3 -m transport automod --state DIR [--world W] [--once]`.
"""
import json
import sqlite3
import sys
import time

from transport import model
from transport.delve import canonical

MODEL = 'glm-5.3-flash'  # the Z.ai subscription's classifier, with thinking disabled
BASE_URL = 'https://api.z.ai/api/anthropic'  # the subscription endpoint, not pay-per-token paas
WINDOW = 5.0  # seconds a new text waits for others to join its batch
BATCH = 24  # texts per classifier call (also bounded by BATCH_BYTES)
DAILY_CALLS = 2000  # classifier calls per UTC day per world
QUIET_HOURS = 24  # hours the host quiets a high-confidence flag's author

CLIP = 2048  # bytes of one text the classifier reads: a verdict on its opening hides it whole
BATCH_BYTES = 32 * 1024  # bytes of clipped text in one call, so a batch of long posts is cut short of the cap
SCAN_ROUNDS = 8  # world-screen calls a step makes catching up (512 entries each)
HELD = 512  # texts held at most: past it the cursor waits, so a backlog (the first run's history) is the cursor's lag, not a file
PASSED = 20000  # keys of texts that passed, remembered so a repeated handle or line is not asked about again
TRIES = 3  # unreadable answers about one text before it is left, said in the status
BACKOFF_MAX = 300


def failed(reason, detail=''):
    return {'status': 'failed', 'reason': reason, 'detail': detail}


def clip(text, n=CLIP):
    raw = text.encode()
    return text if len(raw) <= n else raw[:n].decode(errors='ignore') + ' …'


def user_text(items):
    """The numbered texts, one JSON object a line; a name recorded at arrival (the host's `source` `name:<principal>`)
    marked `kind: name`, which the policy reads as an account's name (gsb 10-14: four of five flags were handles such as
    hy3.delve.town, read as bare links, and siliconsupremacy.delve.town, as a supremacist name)."""
    return 'Texts:\n' + '\n'.join(json.dumps({'i': n, **({'kind': 'name'} if str(i.get('source', '')).startswith('name:') else {}),
                                                'text': clip(i['text'])}, ensure_ascii=False) for n, i in enumerate(items))


def ask_glm(st, system, user, transport=None):
    """One Messages API call to the owner's Z.ai subscription (its Anthropic-compatible endpoint) ->
    {status: replied, raw, model, usage, seconds} | {status: blocked} | failed(...). The wire is model.py's: its key
    reader, its HTTP, its reading of the answer (thinking blocks skipped, the text blocks joined). Thinking is off:
    left on, glm-5.3-flash spends seconds deliberating before a one-line verdict (measured 2026-10-13: 7.6 s against
    1.4 s with `thinking: disabled`)."""
    c = st.config
    secret = model.key(c.zai_key_file)
    if not secret:
        return failed('refused', 'no key: zai_key_file names none')
    body = {'model': MODEL, 'temperature': 0, 'max_tokens': 4096, 'thinking': {'type': 'disabled'},
            'system': system, 'messages': [{'role': 'user', 'content': user}]}
    headers = {'x-api-key': secret, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
    began = time.monotonic()
    status, raw, *_ = (transport or model.http)('POST', BASE_URL.rstrip('/') + '/v1/messages', headers, json.dumps(body).encode())
    seconds = round(time.monotonic() - began, 3)
    try:
        out = json.loads(raw)
    except ValueError:
        out = {}
    error = (out.get('error') or {}) if isinstance(out, dict) else {}
    if str(error.get('code')) == '1301' or (isinstance(out, dict) and out.get('stop_reason') == 'sensitive'):
        return {'status': 'blocked', 'seconds': seconds}  # the provider's content filter refused the input
    return {**model.interpret_body(status, raw, MODEL), 'seconds': seconds}


def log(line):
    """One line of the container's log (stderr): counts, outcomes and error classes; never a text, a reason's words or a key."""
    print(line, file=sys.stderr, flush=True)


def spend_path(st):
    return st.root / 'automod-spend.jsonl'


def spent(st, start=0):
    """{calls, inputTokens, outputTokens} of this world's classifier calls at or after unix time `start`."""
    t = {'calls': 0, 'inputTokens': 0, 'outputTokens': 0}
    for row in st.lines(spend_path(st)) if spend_path(st).exists() else ():
        if row.get('at', 0) >= start and row.get('world') == st.world:
            t['calls'] += 1
            t['inputTokens'] += row.get('inputTokens') or 0
            t['outputTokens'] += row.get('outputTokens') or 0
    return t


def day_start(now):
    return now - now % 86400


class Worker:
    """One world's moderation worker: `step()` once a second."""

    def __init__(self, st, host, ask=None, clock=time.time):
        self.st, self.host, self.clock = st, host, clock
        self.ask = ask or (lambda system, user: ask_glm(st, system, user))
        self.path, self.status_path = st.home / 'automod.json', st.home / 'automod-status.json'
        saved = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.cursor, self.feed_seq = saved.get('cursor', 0), saved.get('feed', 0)
        self.pending = saved.get('pending', [])  # items as the host gave them, with `seen` (unix time)
        self.passed = saved.get('passed', [])
        self.tries = saved.get('tries', {})
        self.passed_set = set(self.passed)
        self.policy, self.height, self.backoff, self.wait_until = '', 0, 0, 0.0
        self.calls_today = spent(st, day_start(clock()))['calls']
        self.day = day_start(clock())
        self.complained = None
        self.note = {'glm': 'idle', 'lastError': None, 'lastCall': None, 'recent': saved.get('recent', []), 'left': saved.get('left', [])}

    def complain(self, kind):
        """An error as a log line, once until it changes or a batch succeeds (the step runs every second)."""
        if kind != self.complained:
            self.complained = kind
            log(f'automod: error {kind}')

    def save(self):
        self.st.write(self.path, {'cursor': self.cursor, 'feed': self.feed_seq, 'pending': self.pending, 'passed': self.passed[-PASSED:],
                                  'tries': self.tries, 'recent': self.note['recent'][-50:], 'left': self.note['left'][-50:]})

    @property
    def c(self):
        return self.st.config

    def send(self, request):
        return self.host.send({'principal': self.c.opener, **request})

    # ---- the texts

    def offered(self):
        """The feed's residents' posts after the worker's feed cursor, as texts to screen (the store read only)."""
        path = self.st.home / 'feed.sqlite'
        if not path.exists():
            return [], self.feed_seq
        db = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
        try:
            rows = db.execute('SELECT seq, uri, did, text, town FROM feed WHERE seq>? ORDER BY seq LIMIT 64', (self.feed_seq,)).fetchall()
        except sqlite3.Error as err:
            self.note['lastError'] = f'feed: {err}'
            self.complain(f'feed {type(err).__name__}')
            return [], self.feed_seq
        finally:
            db.close()
        return ([{'source': f'feed:{uri}', 'author': did, 'text': text} for _, uri, did, text, town in rows if not town],
                rows[-1][0] if rows else self.feed_seq)

    def collect(self):
        """Ask the host for every text written since the cursor; hold what it answers."""
        held = {i['key'] for i in self.pending}
        for _ in range(SCAN_ROUNDS):
            if len(self.pending) >= HELD:
                return
            external, seq = self.offered()
            r = self.send({'op': 'world-screen', 'after': self.cursor, 'limit': 128, 'external': external,
                           'quietHours': QUIET_HOURS})
            if r.get('status') != 'screen':
                self.note['lastError'] = f"host: {r.get('message') or r}"
                self.complain(f"host {r.get('status') or 'silent'}")
                return
            now = self.clock()
            for i in r.get('items') or []:
                if i['key'] in held or i['key'] in self.passed_set:
                    continue
                held.add(i['key'])
                self.pending.append({**i, 'seen': now})
            for a in r.get('acted') or []:
                self.note['recent'].append({**a, 'at': now, 'by': 'wordlist'})
            self.policy, self.height = r.get('policy') or self.policy, r.get('height', self.height)
            moved = r['through'] != self.cursor or seq != self.feed_seq
            self.cursor, self.feed_seq = r['through'], seq
            self.save()
            if not moved or (r['through'] >= r.get('height', 0) and not external):
                return

    # ---- the classifier

    def due(self, now):
        if not self.pending or now < self.wait_until:
            return False
        if len(self.pending) >= BATCH:
            return True
        return now - min(i['seen'] for i in self.pending) >= WINDOW

    def batch(self):
        """The newest held texts, up to the batch's count and bytes."""
        out, size = [], 0
        for i in sorted(self.pending, key=lambda i: (i['seen'], i.get('at', 0)), reverse=True):
            n = len(clip(i['text']).encode())
            if out and (len(out) >= BATCH or size + n > BATCH_BYTES):
                break
            out.append(i)
            size += n
        return out

    def budget_left(self, now):
        if day_start(now) != self.day:
            self.day, self.calls_today = day_start(now), 0
        return self.calls_today < DAILY_CALLS

    def call(self, items):
        """One call about `items` -> its result, the spend journaled to the ledger."""
        result = self.ask(self.policy, user_text(items))
        self.calls_today += 1
        if result.get('status') == 'replied':
            usage = result.get('usage') or {}
            self.st.append(spend_path(self.st), canonical({'at': self.clock(), 'world': self.st.world, 'model': result.get('model'),
                                                           'inputTokens': usage.get('input_tokens'), 'outputTokens': usage.get('output_tokens'),
                                                           'texts': len(items), 'seconds': result.get('seconds')}))
        self.note['lastCall'] = {'at': self.clock(), 'texts': len(items), 'status': result.get('status'), 'seconds': result.get('seconds')}
        log(f"automod: batch texts={len(items)} status={result.get('status')} seconds={result.get('seconds')}")
        if result.get('status') != 'failed':
            self.complained = None
        return result

    def settle(self, items, result):
        """Give the host the classifier's reply about `items`; drop what it settled. -> the host's status."""
        reply = {k: v for k, v in result.items() if k in ('status', 'raw', 'reason', 'detail')}
        r = self.send({'op': 'world-screen-verdicts', 'items': [{k: i[k] for k in ('key', 'text', 'source', 'author', 'at')} for i in items],
                       'reply': reply, 'quietHours': QUIET_HOURS, 'model': result.get('model') or MODEL})
        status = r.get('status')
        if status == 'verdicts':
            unanswered = set(r.get('unanswered') or [])
            settled = {i['key'] for i in items} - unanswered
            acted = {a['key'] for a in r.get('acted') or []}
            for i in items:
                if i['key'] in settled and i['key'] not in acted:
                    self.passed.append(i['key'])
                    self.passed_set.add(i['key'])
                if i['key'] in unanswered:
                    self.tried(i)
            now = self.clock()
            for a in r.get('acted') or []:
                seen = next((i['seen'] for i in items if i['key'] == a['key']), now)
                self.note['recent'].append({**a, 'at': now, 'by': result.get('model') or MODEL, 'afterSeconds': round(now - seen, 3)})
            self.pending = [i for i in self.pending if i['key'] not in settled]
        elif status != 'failed':
            self.note['lastError'] = f"host: {r.get('why') or r.get('message') or status}"
            self.complain(f'settle {status}')
        return status

    def tried(self, item):
        n = self.tries[item['key']] = self.tries.get(item['key'], 0) + 1
        if n >= TRIES:
            self.pending = [i for i in self.pending if i['key'] != item['key']]
            self.note['left'].append({'key': item['key'], 'source': item['source'], 'at': self.clock()})
            self.tries.pop(item['key'], None)

    def classify(self, items):
        """Ask about `items`; a batch the provider refuses or answers unreadably is asked again in halves."""
        if not self.budget_left(self.clock()):
            self.note['glm'] = 'budget'
            return False
        result = self.call(items)
        status = result.get('status')
        if status == 'failed':
            self.note.update(glm='down', lastError=f"{result.get('reason')}: {result.get('detail')}")
            self.complain('classifier failed')
            self.backoff = min(BACKOFF_MAX, max(5, self.backoff * 2))
            self.wait_until = self.clock() + self.backoff
            return False
        self.backoff, self.note['glm'] = 0, 'ok'
        if status == 'blocked' and len(items) > 1:
            half = len(items) // 2
            return self.classify(items[:half]) and self.classify(items[half:])
        answer = self.settle(items, result)
        if answer == 'unreadable':
            if len(items) > 1:
                half = len(items) // 2
                return self.classify(items[:half]) and self.classify(items[half:])
            self.tried(items[0])
        return True

    def step(self):
        self.collect()
        now = self.clock()
        while self.due(now):
            if not self.classify(self.batch()):
                break
            self.save()
            now = self.clock()
            if len(self.pending) < BATCH:
                break  # a short batch waits its window again
        self.save()
        self.write_status()

    def write_status(self):
        now = self.clock()
        oldest = min((i['seen'] for i in self.pending), default=None)
        glm = self.note['glm']
        if not self.c.zai_key_file:
            glm = 'no key'
        self.st.write(self.status_path, {
            'at': now, 'world': self.st.world, 'model': MODEL, 'cursor': self.cursor, 'height': self.height,
            'pending': len(self.pending), 'oldestSeconds': round(now - oldest, 1) if oldest else 0,
            'glm': glm, 'lastError': self.note['lastError'], 'lastCall': self.note['lastCall'], 'retryAt': self.wait_until or None,
            'today': {**spent(self.st, day_start(now)), 'calls': self.calls_today, 'budget': DAILY_CALLS},
            'recent': self.note['recent'][-20:], 'left': self.note['left'][-20:]})


def status(st):
    """The worker's status file, or None when it never ran; `stale` when its last write is over a minute old."""
    path = st.home / 'automod-status.json'
    if not path.exists():
        return None
    s = json.loads(path.read_text())
    s['stale'] = time.time() - s.get('at', 0) > 60
    return s


# ---- the past: a carried town's history before its carried genesis (the edition-16 deploy: never screened)

def chunks(items, n, size=BATCH_BYTES):
    """`items` in batches of at most `n` texts and `size` clipped bytes, in order."""
    out, now, used = [], [], 0
    for i in items:
        k = len(clip(i['text']).encode())
        if now and (len(now) >= n or used + k > size):
            out.append(now)
            now, used = [], 0
        now.append(i)
        used += k
    return out + ([now] if now else [])


def backfill(st, host, ask=None, act=False, entries=4096, clock=time.time):
    """One bounded, resumable pass over the town's past: the entries the host reads before its own journal (`start` to
    `base` of `world-screen`: the ancestor journals the carried genesis cites, when the host was given them), each
    text asked of the classifier as the worker asks it, its share of the day's calls, and given to the host with
    `dryRun` unless `act` (the owner's word, after reading the dry run): then what it hides is hidden, and nobody is
    quieted for a past text. Every would-be (or done) act is a line of <state>/automod-backfill.jsonl; the cursor is
    <state>/automod-backfill.json, so a pass resumes where the last stopped. -> a summary."""
    w = Worker(st, host, ask, clock)
    path, report = st.home / 'automod-backfill.json', st.home / 'automod-backfill.jsonl'
    saved = json.loads(path.read_text()) if path.exists() else {}
    head = w.send({'op': 'world-screen', 'after': 0, 'limit': 0, 'dryRun': True})
    if head.get('status') != 'screen':
        return {'status': 'failed', 'message': head.get('message') or head}
    start, base = head['start'], head['base']
    cursor = max(saved.get('cursor', start - 1), start - 1)
    summary = {'status': 'dryRun' if not act else 'acted', 'start': start, 'base': base, 'scanned': 0, 'texts': 0,
               'hidden': 0, 'review': 0, 'unanswered': 0}
    if start > base:
        return {**summary, 'status': 'nothing', 'cursor': cursor,
                'reading': 'the host reads no journal before its own: it was not given the ancestor journals its carried genesis cites'}
    w.policy = head.get('policy') or ''
    seen = set()  # a text twice in the past is asked about once (a dry run journals nothing, so the host repeats it)
    line = lambda a, by: st.append(report, canonical({**a, 'by': by, 'would': not act, 'at': clock()}))  # noqa: E731
    while cursor < base and summary['scanned'] < entries:
        r = w.send({'op': 'world-screen', 'after': cursor, 'until': base, 'limit': 128, 'dryRun': not act, 'quietHours': 0})
        if r.get('status') != 'screen':
            return {**summary, 'status': 'failed', 'cursor': cursor, 'message': r.get('message') or r}
        texts = {i['key']: i['text'] for i in r.get('items') or []}
        fresh = [i for i in r.get('items') or [] if i['key'] not in seen]
        for a in r.get('acted') or []:
            if a['key'] in seen:
                continue
            seen.add(a['key'])
            summary['hidden'] += 1
            line({**a, 'text': a.get('text') or texts.get(a['key'], '')}, 'wordlist')
        seen.update(i['key'] for i in fresh)
        for items in chunks(fresh, BATCH):
            if not w.budget_left(clock()):
                st.write(path, {'cursor': cursor, 'base': base})
                return {**summary, 'status': 'budget', 'cursor': cursor}
            result = w.call(items)
            if result.get('status') not in ('replied', 'blocked'):
                st.write(path, {'cursor': cursor, 'base': base})
                return {**summary, 'status': 'failed', 'cursor': cursor, 'message': f"{result.get('reason')}: {result.get('detail')}"}
            given = items if result.get('status') == 'replied' or len(items) == 1 else []
            for one in ([[i] for i in items] if not given else [given]):  # a blocked batch is read one text at a time
                reply = result if given else w.call(one)
                v = w.send({'op': 'world-screen-verdicts', 'items': [{k: i[k] for k in ('key', 'text', 'source', 'author', 'at')} for i in one],
                            'reply': {k: x for k, x in reply.items() if k in ('status', 'raw', 'reason', 'detail')}, 'quietHours': 0,
                            'model': reply.get('model') or MODEL, 'dryRun': not act})
                summary['unanswered'] += len(v.get('unanswered') or [])
                for a in v.get('acted') or []:
                    summary['hidden' if a.get('state') == 'hidden' else 'review'] += 1
                    line({**a, 'text': texts.get(a['key'], '')}, reply.get('model') or MODEL)
            summary['texts'] += len(items)
        summary['scanned'] += r['through'] - cursor
        if r['through'] == cursor:
            break
        cursor = r['through']
        st.write(path, {'cursor': cursor, 'base': base})
    return {**summary, 'cursor': cursor, 'done': cursor >= base, 'report': str(report)}


def command(st, a, out):
    """`automod`: a step every second (`--once`: one step and its status printed)."""
    if getattr(a, 'backfill', False):
        host = st.root_host()
        try:
            out.write(canonical(backfill(st, host, act=a.act, entries=a.entries)) + '\n')
        finally:
            host.close()
        return 0
    worker = Worker(st, st.root_host())
    log(f'automod: started world={st.world}')
    try:
        if a.once:
            worker.step()
            out.write(canonical(status(st)) + '\n')
        else:
            st.daemon('automod', worker.step, every=1.0)
    finally:
        worker.host.close()
    return 0
