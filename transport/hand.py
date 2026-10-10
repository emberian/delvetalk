"""The hand: the owner's operator console, one module with two faces.

Every operation is a method of Hand returning plain data (raising HandError to refuse). The web face is the front's
/hand/ page, served only with --hand-token; the CLI face is `python3 -m transport.hand <verb> [--json]`, for the owner's
assistant over ssh. Both read the bridge's state directory and ask hostd; nothing is posted without Post (a click, or
the `post` verb), with the owner's credentials file. Every action appends a line to <state>/hand-log.jsonl.
"""
import argparse
import hmac
import json
import os
import sys
import time
import urllib.parse
from html import escape as e
from pathlib import Path

from deploy import spend
from deploy.genesis import OPENER as OWNER
from transport import post, pages
from transport.bridge import all_observations, awaiting_path, skipped, uri_hash, write_atomic
from transport.delve import Failure, canonical
from transport.hostproc import HostClient

CLIP, HAND_COOKIE = 400, 'dt_hand'


class HandError(Exception):
    pass


def clip(text, n=CLIP):
    return text if len(text) <= n else text[:n] + ' ...'


def drafts(state):
    """[(id, path, draft)] oldest first, every outbox file."""
    paths = sorted((Path(state) / 'outbox').glob('*.json'), key=lambda p: int(p.name.split('-')[0]))
    return [(p.stem, p, json.loads(p.read_text())) for p in paths]


def outcome_of(receipt):
    o = (receipt or {}).get('outcome') or {}
    return o.get('class') or o.get('tag') or '?'


class Hand:
    def __init__(self, state, host, token='', credentials=post.CREDENTIALS, poster=post.post_draft, clock=time.time, owner=OWNER, who='owner'):
        self.state, self.host, self.token, self.credentials = Path(state), host, token, credentials
        self.poster, self.clock, self.owner, self.who = poster, clock, owner, who

    def log(self, what, draft, **more):
        with open(self.state / 'hand-log.jsonl', 'a') as f:
            f.write(canonical({'what': what, 'who': self.who, 'at': int(self.clock()), 'draft': draft, **more}) + '\n')

    def draft(self, draft_id):
        for i, path, d in drafts(self.state):
            if i == draft_id:
                return path, d
        raise HandError(f'no draft {draft_id}')

    def observed(self):
        return {o['uri']: o for o in all_observations(self.state)}

    # ---- reading

    def status(self):
        st = self.host.send({'op': 'world-status'})
        try:
            stamps = [t for t in json.loads((self.state / 'post-log.json').read_text()) if self.clock() - t < post.WINDOW]
        except (OSError, ValueError):
            stamps = []
        month = time.strftime('%Y-%m', time.gmtime(self.clock()))
        spent = spend.totals(self.state, month).get(month, {})
        waiting = self.host.send({'op': 'world-interpretations'}).get('pending') or []
        retrying = [1 for p in (self.state / 'interpretations').glob('*.json') if json.loads(p.read_text()).get('retry')]
        pid = self.state / 'hostd.pid'
        return {'journal height': st.get('height'), 'posts this hour': f'{len(stamps)} of {st.get("postQuota", post.LIMIT)}',
                f'model spend {month}': f'${spent.get("dollars", 0):.4f} ({spent.get("calls", 0)} calls)',
                'interpretations pending': f'{len(waiting)} ({len(retrying)} retrying)',
                'hostd pid': pid.read_text().strip() if pid.exists() else 'none'}

    def search(self, slug):
        return self.host.send({'op': 'world-resolve', 'principal': self.owner, 'slug': slug.strip()})

    def inbox(self, since=None, kind=None, limit=40):
        """Observations newest first, each with what became of it. `since`: only those turned after that journal height."""
        by_post = {d['replyTo']: d for _, _, d in drafts(self.state) if d.get('replyTo')}
        skip, rows = skipped(self.state), []
        for o in sorted(self.observed().values(), key=lambda o: (o['createdAt'], o['uri']), reverse=True):
            d = by_post.get(o['uri'])
            r = (d or {}).get('receipt') or {}
            if (kind and o['kind'] != kind) or (since is not None and r.get('height') is not None and r['height'] <= since):
                continue
            if d:
                fate = f'{d["object"]} / {r.get("slug") or "no slug"} / {outcome_of(r)}'
            elif awaiting_path(self.state, o['uri']).exists():
                fate = 'waiting on an interpretation'
            elif o['uri'] in skip:
                fate = 'skipped: addressed to nobody (no recorded parent, no card word, no summon)'
            else:
                fate = 'not yet turned'
            rows.append({'uri': o['uri'], 'handle': o['author']['handle'], 'kind': o['kind'], 'text': clip(o['text'], 160), 'fate': fate,
                         'skipped': o['uri'] in skip and not d, 'object': (d or {}).get('object'), 'slug': r.get('slug'), 'outcome': outcome_of(r) if d else None})
        return rows[:limit]

    def outbox(self, all=False):
        """Drafts grouped by the post they answer: [{post, original: {handle, text}|None, drafts: [...]}]."""
        seen, groups = self.observed(), {}
        for i, _, d in drafts(self.state):
            if not all and (d['posted'] or d.get('skipped') or not d['text']):
                continue
            groups.setdefault(d.get('replyTo') or d.get('publication', {}).get('id', i), []).append(self.summary(i, d))
        return [{'post': k, 'original': {'handle': seen[k]['author']['handle'], 'text': clip(seen[k]['text'])} if k in seen else None, 'drafts': v}
                for k, v in groups.items()]

    def summary(self, i, d):
        r = d.get('receipt')
        line = f'receipt {r.get("slug")}: {outcome_of(r)}' if r else 'by hand' if d.get('hand') else 'a publication'
        state = 'posted' if d['posted'] else 'skipped' if d.get('skipped') else 'waiting'
        return {'id': i, 'object': d.get('object'), 'receipt': line, 'slug': (r or {}).get('slug') or 'by hand', 'height': (r or {}).get('height'),
                'outcome': outcome_of(r) if r else 'drafted', 'text': d['text'], 'state': state,
                **({'original': d['original']} if d.get('original') else {}), **({'reason': d['reason']} if d.get('reason') else {})}

    def show(self, draft_id):
        _, d = self.draft(draft_id)
        o = self.observed().get(d.get('replyTo'))
        return {**self.summary(draft_id, d), 'post': d.get('replyTo'), 'original post': o and {'handle': o['author']['handle'], 'text': o['text']}}

    def tail(self, n=20):
        try:
            return [json.loads(l) for l in (self.state / 'hand-log.jsonl').read_text().splitlines()][-n:]
        except OSError:
            return []

    # ---- acting

    def edit(self, draft_id, text):
        path, d = self.draft(draft_id)
        if d['posted']:
            raise HandError(f'{draft_id} is already posted')
        write_atomic(path, dict(d, text=text, original=d.get('original', d['text'])))
        self.log('edit', draft_id)
        return {'edited': draft_id}

    def post(self, draft_id, text=None, object=None):
        path, d = self.draft(draft_id)
        text = d['text'] if text is None else text.replace('\r\n', '\n')
        try:
            result = self.poster(path, self.state, self.host, self.credentials, text=text, **({'object': object} if object else {}))
        except (Failure, OSError, KeyError, ValueError) as err:
            code = getattr(err, 'code', type(err).__name__)
            self.log('post-failed', draft_id, error=code)
            raise HandError(f'post failed: {code}') from None
        self.log('post', draft_id, uri=result.get('uri'), edited=text != d['text'])
        return result

    def skip(self, draft_id, reason=''):
        path, d = self.draft(draft_id)
        write_atomic(path, dict(d, posted=False, skipped=True, reason=reason.strip() or 'skipped by the owner'))
        self.log('skip', draft_id, reason=reason)
        return {'skipped': draft_id}

    def hold(self, draft_id):
        self.draft(draft_id)
        self.log('hold', draft_id)
        return {'held': draft_id}

    def retry(self, uri):
        """Forget that the bridge skipped this observation, so its next run routes it again."""
        if uri not in self.observed():
            raise HandError(f'{uri} is not an observed post')
        path = self.state / 'skipped.txt'
        keep = [u for u in (path.read_text().split() if path.exists() else []) if u != uri]
        path.write_text(''.join(u + '\n' for u in keep))
        self.log('retry', uri)
        return {'requeued': uri}

    def reply(self, uri, text, object):
        """A hand-written reply to an observed post, drafted as if `object` had offered it, to be posted and recorded as any draft."""
        o = self.observed().get(uri)
        if o is None or not text.strip() or not object:
            raise HandError('reply needs an observed post, a text and an object')
        name = f'{int(self.clock())}-hand-{uri_hash(uri)}'
        write_atomic(self.state / 'outbox' / f'{name}.json', {
            'replyTo': uri, 'replyHandle': o['author']['handle'], 'principal': o['author']['did'], 'principalVerified': False,
            'object': object, 'slot': None, 'text': text.replace('\r\n', '\n'), 'posted': False, 'hand': True})
        self.log('reply', name, post=uri, object=object)
        return {'drafted': name}

    # ---- the web face: (method, path, cookie header, form) -> (code, html, headers)

    def handle(self, method, target, cookie='', form=None):
        parts = urllib.parse.urlsplit(target)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
        jar = dict(c.strip().partition('=')[::2] for c in cookie.split(';'))
        given = query.get('token') or jar.get(HAND_COOKIE, '')
        if not hmac.compare_digest(given.encode(), self.token.encode()):
            return 404, pages.page('not found', None, '<h1>not found</h1>'), []
        if query.get('token'):
            return 302, '', [('Set-Cookie', f'{HAND_COOKIE}={self.token}; Path=/hand/; HttpOnly; SameSite=Strict; Max-Age=2592000'), ('Location', '/hand/')]
        path = parts.path.rstrip('/')
        if method == 'POST':
            try:
                done = self.web_action(path, form or {})
            except HandError as err:
                done = {'note': str(err)}
            if done is not None:
                note = ' '.join(str(v) for v in done.values() if isinstance(v, str))
                return 303, '', [('Location', '/hand/?' + urllib.parse.urlencode({'note': note}) + '#outbox')]
        if method == 'GET' and path == '/hand':
            return 200, self.page(query), []
        return 404, pages.page('not found', None, '<h1>not found</h1>'), []

    def web_action(self, path, form):
        """The POSTed form as one of the operations above; None for an unknown path or action."""
        if path.startswith('/hand/draft/'):
            i = path.rsplit('/', 1)[1]
            acts = {'post': lambda: self.post(i, form.get('text')), 'skip': lambda: self.skip(i, form.get('reason', '')), 'hold': lambda: self.hold(i)}
            act = acts.get(form.get('do'))
        else:
            act = {'/hand/retry': lambda: self.retry(form.get('uri', '')), '/hand/reply': lambda: self.reply(form.get('uri', ''), form.get('text', ''), form.get('object', ''))}.get(path)
        return act and act()

    def page(self, query):
        T, q = pages.T, lambda t: e(str(t))
        st = self.status()
        codes = ''.join(T['hand_code'].format(text=q(f'ht.{v}' if k == 'journal height' else f'{k} {v}')) for k, v in st.items())
        found = T['hand_card'].format(text=q(json.dumps(self.search(query['slug']), indent=1, sort_keys=True)[:3000])) if query.get('slug') else ''
        outbox = ''.join(T['hand_group'].format(
            original=T['hand_card'].format(text=q(f'{g["original"]["handle"]}\n{g["original"]["text"]}')) if g['original'] else T['hand_note'].format(text=q(g['post'])),
            drafts=''.join(T['hand_draft'].format(fate=q(d['outcome']), height=q('-' if d['height'] is None else d['height']), name=q(d['slug']), object=q(d['object']), id=q(d['id']), text=q(d['text']))
                           for d in g['drafts'])) for g in self.outbox()) or '<p class="quiet">— no drafts waiting —</p>'
        inbox = ''.join(T['hand_row'].format(
            outcome=q(r['outcome'] or ''), kind=q(r['kind']), handle=q(r['handle']), text=q(r['text']), uri=q(r['uri']),
            fate=q('' if r['skipped'] else r['fate']), retry=T['hand_retry'].format(uri=q(r['uri'])) if r['skipped'] else '') for r in self.inbox()) \
            or '<p class="quiet">— nothing observed —</p>'
        note = T['hand_note'].format(text=q(query['note'])) if query.get('note') else ''
        return pages.page('the hand', 'owner', T['hand'].format(note=note, codes=codes, found=found, outbox=outbox, inbox=inbox))


# ---- the command-line face

def text_of(data, indent=''):
    """Readable text for plain data: lists one item per block, dicts as `key: value` lines."""
    if isinstance(data, list):
        return '\n'.join(text_of(x, indent) + ('\n' if isinstance(x, dict) else '') for x in data) or '(nothing)'
    if isinstance(data, dict):
        return '\n'.join(f'{indent}{k}: ' + (text_of(v, indent + '  ').lstrip() if isinstance(v, (dict, list)) and v else str(v)) if not isinstance(v, str) or '\n' not in v
                         else f'{indent}{k}:\n' + '\n'.join(indent + '  ' + l for l in v.split('\n')) for k, v in data.items())
    return indent + str(data)


def main(argv=None, out=None, host=None, poster=post.post_draft):
    out = out or sys.stdout
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--state', default=os.environ.get('DELVETALK_STATE'), help='the bridge state directory (or DELVETALK_STATE)')
    common.add_argument('--host-socket', metavar='PATH')
    common.add_argument('--credentials', default=os.environ.get('DELVETALK_CREDENTIALS', post.CREDENTIALS))
    common.add_argument('--json', action='store_true', help='one JSON document instead of text')
    ap = argparse.ArgumentParser(prog='hand.py', description='the owner\'s console, command-line face')
    sub = ap.add_subparsers(dest='verb', required=True)
    spec = {'inbox': [('--since', dict(type=int)), ('--kind', dict(choices=('spell', 'summon', 'reply', 'post')))],
            'outbox': [('--all', dict(action='store_true'))], 'show': [('draft', {})],
            'edit': [('draft', {}), ('--text-file', {}), ('--stdin', dict(action='store_true'))],
            'post': [('draft', {}), ('--object', {})], 'skip': [('draft', {}), ('--reason', dict(required=True))], 'hold': [('draft', {})],
            'status': [], 'search': [('slug', {})], 'retry': [('uri', {})],
            'reply': [('uri', {}), ('--text-file', dict(required=True)), ('--object', dict(required=True))],
            'log': [('--tail', dict(type=int, default=20))]}
    for name, args in spec.items():
        p = sub.add_parser(name, parents=[common])
        for a, k in args:
            p.add_argument(a, **k)
    a = ap.parse_args(argv)
    if not a.state:
        ap.error('--state (or DELVETALK_STATE) is required')
    h = Hand(a.state, host or HostClient(a.host_socket or Path(a.state) / 'host.sock'), credentials=a.credentials, poster=poster, who='cli')
    try:
        read = lambda p: Path(p).read_text()
        data = {'inbox': lambda: h.inbox(a.since, a.kind), 'outbox': lambda: h.outbox(a.all), 'show': lambda: h.show(a.draft),
                'edit': lambda: h.edit(a.draft, sys.stdin.read() if a.stdin else read(a.text_file)), 'post': lambda: h.post(a.draft, object=a.object),
                'skip': lambda: h.skip(a.draft, a.reason), 'hold': lambda: h.hold(a.draft), 'status': h.status, 'search': lambda: h.search(a.slug),
                'retry': lambda: h.retry(a.uri), 'reply': lambda: h.reply(a.uri, read(a.text_file), a.object), 'log': lambda: h.tail(a.tail)}[a.verb]()
    except (HandError, OSError) as err:
        print(f'hand: {err}', file=sys.stderr)
        return 1
    out.write((json.dumps(data, indent=1, sort_keys=True) if a.json else text_of(data)) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
