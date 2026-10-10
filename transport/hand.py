"""The hand: the owner's operator console, mounted by the front at /hand/ when it has a --hand-token.

Reads the bridge's state directory and asks hostd; posts only on a click (Post), with the owner's credentials file.
Plain HTML, no script. Every action is a line in <state>/hand-log.jsonl.
"""
import hmac
import json
import time
import urllib.parse
from html import escape as e
from pathlib import Path

from deploy import spend
from deploy.genesis import OPENER as OWNER
from transport import post, pages
from transport.bridge import all_observations, awaiting_path, skipped, write_atomic
from transport.delve import Failure, canonical

CLIP, HAND_COOKIE = 400, 'dt_hand'


def clip(text, n=CLIP):
    return text if len(text) <= n else text[:n] + ' ...'


def drafts(state):
    """[(id, path, draft)] oldest first, every outbox file."""
    out = []
    for path in sorted((Path(state) / 'outbox').glob('*.json'), key=lambda p: int(p.name.split('-')[0])):
        out.append((path.stem, path, json.loads(path.read_text())))
    return out


def outcome_of(receipt):
    o = (receipt or {}).get('outcome') or {}
    return o.get('class') or o.get('tag') or '?'


class Hand:
    def __init__(self, state, host, token, credentials=post.CREDENTIALS, poster=post.post_draft, clock=time.time, owner=OWNER):
        self.state, self.host, self.token, self.credentials, self.poster, self.clock, self.owner = Path(state), host, token, credentials, poster, clock, owner

    # ---- request handling: (method, path, cookie header, form) -> (code, html, headers)

    def handle(self, method, target, cookie='', form=None):
        parts = urllib.parse.urlsplit(target)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
        jar = dict(c.strip().partition('=')[::2] for c in cookie.split(';'))
        given = query.get('token') or jar.get(HAND_COOKIE, '')
        if not hmac.compare_digest(given.encode(), self.token.encode()):
            return 404, pages.page('not found', None, '<h1>not found</h1>'), []
        headers = [('Set-Cookie', f'{HAND_COOKIE}={self.token}; Path=/hand/; HttpOnly; SameSite=Strict; Max-Age=2592000')] if query.get('token') else []
        if query.get('token'):
            return 302, '', headers + [('Location', '/hand/')]
        path = parts.path.rstrip('/')
        if method == 'POST' and path.startswith('/hand/draft/'):
            note = self.act(path.rsplit('/', 1)[1], form or {})
            return 303, '', [('Location', '/hand/?' + urllib.parse.urlencode({'note': note}) + '#outbox')]
        if method == 'GET' and path == '/hand':
            return 200, self.page(query), headers
        return 404, pages.page('not found', None, '<h1>not found</h1>'), []

    def log(self, what, draft, **more):
        with open(self.state / 'hand-log.jsonl', 'a') as f:
            f.write(canonical({'what': what, 'who': 'owner', 'at': int(self.clock()), 'draft': draft, **more}) + '\n')

    def act(self, draft_id, form):
        found = [(p, d) for i, p, d in drafts(self.state) if i == draft_id]
        if not found:
            return f'no draft {draft_id}'
        path, d = found[0]
        what = form.get('do', '')
        if what == 'post':
            text = form.get('text', d['text']).replace('\r\n', '\n')
            try:
                result = self.poster(path, self.state, self.host, self.credentials, text=text)
            except (Failure, OSError, KeyError, ValueError) as err:
                self.log('post-failed', draft_id, error=getattr(err, 'code', type(err).__name__))
                return f'post failed: {getattr(err, "code", type(err).__name__)}'
            self.log('post', draft_id, uri=result.get('uri'), edited=text != d['text'])
            return f'posted {result.get("uri")}'
        if what == 'skip':
            write_atomic(path, dict(d, posted=False, skipped=True, reason=form.get('reason', '').strip() or 'skipped by the owner'))
            self.log('skip', draft_id, reason=form.get('reason', ''))
            return 'skipped'
        if what == 'hold':
            self.log('hold', draft_id)
            return 'held'
        return 'unknown action'

    # ---- reading

    def status(self):
        st = self.host.send({'op': 'world-status'})
        stamps = []
        try:
            stamps = [t for t in json.loads((self.state / 'post-log.json').read_text()) if self.clock() - t < post.WINDOW]
        except (OSError, ValueError):
            pass
        month = time.strftime('%Y-%m', time.gmtime(self.clock()))
        spent = spend.totals(self.state, month).get(month, {})
        waiting = self.host.send({'op': 'world-interpretations'}).get('pending') or []
        retrying = [1 for p in (self.state / 'interpretations').glob('*.json') if json.loads(p.read_text()).get('retry')]
        pid = self.state / 'hostd.pid'
        return {'journal height': st.get('height'), 'posts this hour': f'{len(stamps)} of {st.get("postQuota", post.LIMIT)}',
                f'model spend {month}': f'${spent.get("dollars", 0):.4f} ({spent.get("calls", 0)} calls)',
                'interpretations pending': f'{len(waiting)} ({len(retrying)} retrying)',
                'hostd pid': pid.read_text().strip() if pid.exists() else 'none'}

    def inbox(self, limit=40):
        by_post = {d['replyTo']: d for _, _, d in drafts(self.state) if d.get('replyTo')}
        skip = skipped(self.state)
        rows = []
        for o in sorted(all_observations(self.state), key=lambda o: (o['createdAt'], o['uri']), reverse=True)[:limit]:
            d = by_post.get(o['uri'])
            if d:
                r = d.get('receipt') or {}
                fate = f'{d["object"]} / {r.get("slug") or "no slug"} / {outcome_of(r)}'
            elif awaiting_path(self.state, o['uri']).exists():
                fate = 'waiting on an interpretation'
            elif o['uri'] in skip:
                fate = 'skipped: addressed to nobody (no recorded parent, no card word, no summon)'
            else:
                fate = 'not yet turned'
            rows.append(f'<tr><td>{e(o["author"]["handle"])}</td><td>{e(o["kind"])}</td><td>{e(clip(o["text"], 160))}</td><td>{e(fate)}</td></tr>')
        return ('<table><tr><th>from</th><th>kind</th><th>text</th><th>fate</th></tr>' + ''.join(rows) + '</table>') if rows else '<p>nothing observed</p>'

    def outbox(self):
        texts = {o['uri']: o for o in all_observations(self.state)}
        groups = {}
        for i, _, d in drafts(self.state):
            if d['posted'] or d.get('skipped') or not d['text']:
                continue
            groups.setdefault(d.get('replyTo') or d.get('publication', {}).get('id', i), []).append((i, d))
        out = []
        for key, items in groups.items():
            o = texts.get(key)
            original = f'<blockquote><strong>{e(o["author"]["handle"])}</strong>: {e(clip(o["text"]))}</blockquote>' if o else f'<p>{e(key)}</p>'
            forms = ''
            for i, d in items:
                receipt = d.get('receipt')
                line = f'receipt {receipt.get("slug")}: {outcome_of(receipt)}' if receipt else 'a publication'
                forms += (f'<form method="post" action="/hand/draft/{e(i)}"><p>{e(line)}; to {e(str(d.get("object")))}</p>'
                          f'<textarea name="text" rows="8" cols="72">{e(d["text"])}</textarea>'
                          '<p><button name="do" value="post">Post</button> <input name="reason" placeholder="reason to skip">'
                          ' <button name="do" value="skip">Skip</button> <button name="do" value="hold">Hold</button></p></form>')
            out.append(f'<div class="draft">{original}{forms}</div>')
        return ''.join(out) or '<p>no drafts waiting</p>'

    def page(self, query):
        note = f'<p><strong>{e(query["note"])}</strong></p>' if query.get('note') else ''
        status = '<dl>' + ''.join(f'<dt>{e(k)}</dt><dd>{e(str(v))}</dd>' for k, v in self.status().items()) + '</dl>'
        found = ''
        if query.get('slug'):
            r = self.host.send({'op': 'world-resolve', 'principal': self.owner, 'slug': query['slug'].strip()})
            found = f'<pre>{e(json.dumps(r, indent=1, sort_keys=True)[:3000])}</pre>'
        search = ('<form method="get" action="/hand/"><label>Receipt slug <input name="slug" placeholder="bofab-lukid"></label>'
                  f'<button>Resolve</button></form>{found}')
        return pages.page('the hand', 'owner', f'<h1>The hand</h1>{note}<section><h2>Status</h2>{status}</section>'
                          f'<section><h2>Search</h2>{search}</section><section id="outbox"><h2>Outbox</h2>{self.outbox()}</section>'
                          f'<section><h2>Inbox</h2>{self.inbox()}</section>')
