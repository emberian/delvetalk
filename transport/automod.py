"""The automatic moderation's worker (docs/ROOT.md section 2.4): retroactive, never in a turn's path, its own model and budget.

Every second it asks the host, on the root socket as the opener, for the texts written since its cursor
(`world-screen {after, external}`), offering the feed's new posts beside them; the host answers the texts and has
already acted on any its wordlist names. The worker holds what is new; once it has held a text for `automod_window`
seconds, or holds `automod_batch` texts, it asks the classifier (the owner's Z.ai subscription, its Anthropic-compatible Messages endpoint, `automod_model`) about the batch in one
call, each text numbered, and gives the host the classifier's reply verbatim (`world-screen-verdicts`). The host decides
what a verdict does and journals it; nothing here hides or quiets anything. An idle worker asks the host and calls no
model. When the classifier fails, the texts wait (the cursor and the held texts are kept on disk, so a restart loses
none), the worker backs off, and its status file says so for the hand's overview; when the provider's own filter refuses
a batch, the worker asks again in halves, and a single text the provider refuses goes to the host as `blocked`.

The key is a file (`zai_key_file`), read on every call; spend is a line a call in <state>/automod-spend.jsonl, kept
apart from the Anthropic ledger (tokens only: a subscription has no per-token price), and the day's calls are capped by `automod_daily_calls`. Run as
`python3 -m transport automod --state DIR [--world W] [--once]`.
"""
import json
import sqlite3
import time

from transport import model
from transport.delve import canonical

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
    """The numbered texts, one JSON object a line."""
    return 'Texts:\n' + '\n'.join(json.dumps({'i': n, 'text': clip(i['text'])}, ensure_ascii=False) for n, i in enumerate(items))


def ask_glm(st, system, user, transport=None):
    """One Messages API call to the owner's Z.ai subscription (its Anthropic-compatible endpoint, `automod_base_url`) ->
    {status: replied, raw, model, usage, seconds} | {status: blocked} | failed(...). The wire is model.py's: its key
    reader, its HTTP, its reading of the answer (thinking blocks skipped, the text blocks joined). Thinking is off:
    left on, glm-5.3-flash spends seconds deliberating before a one-line verdict (measured 2026-10-13: 7.6 s against
    1.4 s with `thinking: disabled`)."""
    c = st.config
    secret = model.key(c.zai_key_file)
    if not secret:
        return failed('refused', 'no key: zai_key_file names none')
    body = {'model': c.automod_model, 'temperature': 0, 'max_tokens': 4096, 'thinking': {'type': 'disabled'},
            'system': system, 'messages': [{'role': 'user', 'content': user}]}
    headers = {'x-api-key': secret, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
    began = time.monotonic()
    status, raw, *_ = (transport or model.http)('POST', c.automod_base_url.rstrip('/') + '/v1/messages', headers, json.dumps(body).encode())
    seconds = round(time.monotonic() - began, 3)
    try:
        out = json.loads(raw)
    except ValueError:
        out = {}
    error = (out.get('error') or {}) if isinstance(out, dict) else {}
    if str(error.get('code')) == '1301' or (isinstance(out, dict) and out.get('stop_reason') == 'sensitive'):
        return {'status': 'blocked', 'seconds': seconds}  # the provider's content filter refused the input
    return {**model.interpret_body(status, raw, c.automod_model), 'seconds': seconds}


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
        self.note = {'glm': 'idle', 'lastError': None, 'lastCall': None, 'recent': saved.get('recent', []), 'left': saved.get('left', [])}

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
                           'quietHours': self.c.automod_quiet_hours})
            if r.get('status') != 'screen':
                self.note['lastError'] = f"host: {r.get('message') or r}"
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
        if len(self.pending) >= self.c.automod_batch:
            return True
        return now - min(i['seen'] for i in self.pending) >= self.c.automod_window

    def batch(self):
        """The newest held texts, up to the batch's count and bytes."""
        out, size = [], 0
        for i in sorted(self.pending, key=lambda i: (i['seen'], i.get('at', 0)), reverse=True):
            n = len(clip(i['text']).encode())
            if out and (len(out) >= self.c.automod_batch or size + n > BATCH_BYTES):
                break
            out.append(i)
            size += n
        return out

    def budget_left(self, now):
        if day_start(now) != self.day:
            self.day, self.calls_today = day_start(now), 0
        return self.calls_today < self.c.automod_daily_calls

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
        return result

    def settle(self, items, result):
        """Give the host the classifier's reply about `items`; drop what it settled. -> the host's status."""
        reply = {k: v for k, v in result.items() if k in ('status', 'raw', 'reason', 'detail')}
        r = self.send({'op': 'world-screen-verdicts', 'items': [{k: i[k] for k in ('key', 'text', 'source', 'author', 'at')} for i in items],
                       'reply': reply, 'quietHours': self.c.automod_quiet_hours, 'model': result.get('model') or self.c.automod_model})
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
                self.note['recent'].append({**a, 'at': now, 'by': result.get('model') or self.c.automod_model, 'afterSeconds': round(now - seen, 3)})
            self.pending = [i for i in self.pending if i['key'] not in settled]
        elif status != 'failed':
            self.note['lastError'] = f"host: {r.get('why') or r.get('message') or status}"
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
            if len(self.pending) < self.c.automod_batch:
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
            'at': now, 'world': self.st.world, 'model': self.c.automod_model, 'cursor': self.cursor, 'height': self.height,
            'pending': len(self.pending), 'oldestSeconds': round(now - oldest, 1) if oldest else 0,
            'glm': glm, 'lastError': self.note['lastError'], 'lastCall': self.note['lastCall'], 'retryAt': self.wait_until or None,
            'today': {**spent(self.st, day_start(now)), 'calls': self.calls_today, 'budget': self.c.automod_daily_calls},
            'recent': self.note['recent'][-20:], 'left': self.note['left'][-20:]})


def status(st):
    """The worker's status file, or None when it never ran; `stale` when its last write is over a minute old."""
    path = st.home / 'automod-status.json'
    if not path.exists():
        return None
    s = json.loads(path.read_text())
    s['stale'] = time.time() - s.get('at', 0) > 60
    return s


def command(st, a, out):
    """`automod`: a step every second (`--once`: one step and its status printed)."""
    if not st.config.automod:  # off: a process that does nothing, so its service stays healthy and says why
        out.write('automod: off in this config (automod = false)\n')
        out.flush()
        st.daemon('automod', lambda: None, every=30.0)
        return 0
    worker = Worker(st, st.root_host())
    try:
        if a.once:
            worker.step()
            out.write(canonical(status(st)) + '\n')
        else:
            st.daemon('automod', worker.step, every=1.0)
    finally:
        worker.host.close()
    return 0
