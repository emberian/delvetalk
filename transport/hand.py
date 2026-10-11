"""The hand: the owner's operator console, one module with two faces.

Every operation is a method of Hand returning plain data (raising HandError to refuse). The web face is the front's
/hand/ page, served by `hand serve` on a listener of its own; the CLI face is `python3 -m transport.hand <verb> [--json]`,
for the owner's assistant over ssh. Both read the bridge's state directory and ask the host on its root socket, the
opener's (HOST-HANDOFF 5.125), which only the hand's and the ops containers mount; nothing is posted without Post (a click, or
the `post` verb), with the owner's credentials file. Every action appends a line to <state>/hand-log.jsonl.
"""
import argparse
import calendar
import hmac
import json
import os
import shutil
import sys
import time
import urllib.parse
from html import escape as e
from pathlib import Path

from deploy import spend
from deploy.genesis import OPENER as OWNER
from transport import journal as chain, post, pages, root
from transport.bridge import all_observations, awaiting_path, skipped, uri_hash, write_atomic
from transport.delve import Failure, canonical
from transport.host import CLOCK, add_host_args, connect

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
        delve = next((s for s in (st.get('posts') or {}).get('sources') or [] if s.get('source') == 'delve'), {})  # the host's count
        month = time.strftime('%Y-%m', time.gmtime(self.clock()))
        spent = spend.totals(self.state, month).get(month, {})
        waiting = self.host.send({'op': 'world-interpretations'}).get('pending') or []
        retrying = [p for p in waiting if p.get('next') is not None]  # the host's backoff
        return {'journal height': st.get('height'), 'posts this hour': f'{delve.get("used", 0)} of {delve.get("quota", "?")}',
                f'model spend {month}': f'${spent.get("dollars", 0):.4f} ({spent.get("calls", 0)} calls)',
                'interpretations pending': f'{len(waiting)} ({len(retrying)} retrying)',
                'host pid': self.host.send({'op': 'serve-status'}).get('pid', 'none'), 'shadowed': len(st.get('shadowed') or [])}

    def probe(self, backups=None, journal=None):
        """The one monitoring probe (`status --json`, docs/OPERATIONS.md section b): plain numbers, every threshold the watch's."""
        now, st = self.clock(), self.host.send({'op': 'world-status'})
        rows = [l.split() for p in (self.state / 'access.log.1', self.state / 'access.log') if p.exists() for l in p.read_text().splitlines()]
        when = lambda x: calendar.timegm(time.strptime(x[0], '%Y-%m-%dT%H:%M:%SZ'))
        recent = lambda secs: [x for x in rows if len(x) >= 4 and now - when(x) < secs]
        waiting = self.host.send({'op': 'world-interpretations'}).get('pending') or []
        journal = Path(journal) if journal else self.state / 'town.journal'
        # The newest 4,000 entries are enough for a median: each weighs its record in the block store.
        sizes = sorted(e['bytes'] for e in chain.tail(journal, 4000) if (e.get('outcome') or {}).get('tag') == 'suspended')
        backups = Path(backups or os.environ.get('DELVETALK_BACKUPS', '/var/backups/delvetalk'))
        tars = sorted(backups.glob('delvetalk-*.tar.gz')) if backups.is_dir() else []
        verify = (backups / 'last-verify').read_text().split() if (backups / 'last-verify').exists() else []
        disk = {str(p): round(shutil.disk_usage(p).free / shutil.disk_usage(p).total, 3) for p in (self.state, backups) if p.exists()}
        return {'at': int(now), 'front': {'requests5m': len(recent(300)), '5xx5m': sum(1 for x in recent(300) if x[3].startswith('5')),
                                          '5xxHour': sum(1 for x in recent(3600) if x[3].startswith('5'))},
                'hour': st.get('hour'), 'model': {'hour': spend.since(self.state, now - 3600), 'day': spend.since(self.state, now - 86400)},
                'reservations': next((s for s in (st.get('posts') or {}).get('sources') or [] if s.get('source') == 'delve'), {}),
                'interpretations': {'pending': len(waiting), 'maxAttempts': max([p.get('attempts') or 0 for p in waiting] or [0])},
                'journal': {'height': st.get('height'), 'bytes': chain.size(journal) if journal.exists() else None,
                            'medianSuspendedBytes': sizes[len(sizes) // 2] if sizes else None},
                'clock': {'world': st.get('clock'), 'behindMinutes': int(now // 60) - (st.get('clock') or 0)},
                'observed': len(self.observed()),
                'backup': {'newest': tars[-1].name if tars else None, 'ageSeconds': int(now - tars[-1].stat().st_mtime) if tars else None,
                           'verify': verify[0] if verify else None},
                'freeFraction': disk}

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
        line = f'receipt {r.get("slug")}: {outcome_of(r)}' if r else 'usage' if d.get('usage') else 'by hand' if d.get('hand') else 'a publication'
        state = 'posted' if d['posted'] else 'skipped' if d.get('skipped') else 'waiting'
        return {'id': i, 'object': post.draft_object(d), 'receipt': line, 'slug': (r or {}).get('slug') or 'by hand', 'height': (r or {}).get('height'),
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

    def unpost(self, draft_id, reason, zulip=None, client=None):
        """Delete the post this draft became (ours alone: Delve's deleteRecord in the session's repo, Zulip's DELETE of the
        bot's message) and tell the host (`world-posted {unposted: true}`, so replies stop routing to it); the draft and
        the hand's log keep the fact whatever the host answers."""
        path, d = self.draft(draft_id)
        uri = (d.get('sent') or {}).get('uri')
        if not d.get('posted') or not uri or d.get('unposted'):
            raise HandError(f'{draft_id} is no post of ours to withdraw')
        try:
            if uri.startswith('zulip://'):
                from transport.zulip import parse_uri
                if zulip is None:
                    raise HandError('a Zulip post is withdrawn with --zuliprc')
                zulip.delete(parse_uri(uri)[2])
            else:
                post.unsend(uri, self.credentials, client)
        except Failure as err:
            raise HandError(f'unpost failed: {err.code}') from None
        got = self.host.send({'op': 'world-posted', 'principal': CLOCK, 'uri': uri, 'cid': d['sent'].get('cid'), 'object': post.draft_object(d),
                              'intent': d.get('intent'), 'unposted': True, 'reason': reason})
        write_atomic(path, dict(d, unposted={'at': int(self.clock()), 'reason': reason, 'recorded': got}))
        self.log('unpost', draft_id, uri=uri, reason=reason)
        return {'unposted': uri}

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

    # ---- root and moderation (docs/ROOT.md 1.6, 2.3): one request each on the root socket, as the opener

    def act(self, face, verb, given):
        """A root act (`face` root, with a reason) or a moderation power (`mod`, with a reading); logged with its height."""
        try:
            req = root.request(face, verb, given, self.owner, self.clock)
        except (ValueError, KeyError, OSError) as err:
            raise HandError(f'{verb}: {err}') from None
        got = self.host.send(req)
        if got.get('status') == 'error':
            raise HandError(f"{verb}: {got.get('message')}")
        self.log(f'{face}:{verb}', None, reason=req.get('reason') or req.get('reading'), height=(got.get('receipt') or {}).get('height'))
        return got

    def save(self, obj, form):
        """The object editor's Save: a `set` for each field whose text changed from the dump it was shown, one entry each."""
        shown = json.loads(form.get('shown') or '{}')
        changed = [k for k in shown if k in form and json.loads(form[k]) != shown[k]]
        return {'set': [self.act('root', 'set', {'object': obj, 'field': k, 'value': form[k], 'reason': form.get('reason', '')})['status'] for k in changed]}

    def root_page(self, query):
        T, q = pages.T, lambda t: e(str(t))
        st = self.host.send({'op': 'world-status'})
        codes = ''.join(T['hand_code'].format(text=q(t)) for t in (f"entry {st.get('height')}", f"shadowed {len(st.get('shadowed') or [])}",
                                                                   f"this hour {json.dumps(st.get('hour') or {}, sort_keys=True)}"))
        editor = ''
        if query.get('object'):
            d = root.dump(self.host, self.owner, query['object'])
            fields = {'state': (d['view'].get('state')), 'law': (d['record'].get('record') or {}).get('law')}
            editor = (T['hand_card'].format(text=q(json.dumps(d, indent=1, sort_keys=True)[:6000])) +
                      f'<form method="post" action="/hand/root/save"><input type="hidden" name="object" value="{q(query["object"])}">'
                      f'<input type="hidden" name="shown" value="{q(json.dumps(fields))}">' +
                      ''.join(f'<label>{k} <textarea name="{k}" rows="6">{q(json.dumps(v, indent=1))}</textarea></label>' for k, v in fields.items()) +
                      '<input name="reason" required placeholder="reason (required)"><button class="door">Save</button></form>')
        before = int(query['before']) if query.get('before', '').isdigit() else None
        rows = root.entries(self.host, self.owner, limit=20) if before is None else \
            self.host.send({'op': 'world-entries', 'principal': self.owner, 'reverse': True, 'before': before, 'limit': 20}).get('entries') or []
        ignored = set(st.get('ignored') or [])
        entries = '<ol class="receipts">' + ''.join(T['hand_entry'].format(
            tag=q((r.get('outcome') or {}).get('tag')), height=q(r.get('height')), raw=q(json.dumps(r, indent=1, sort_keys=True)),
            line=q(f"{outcome_of(r)} · {(r.get('identity') or {}).get('principal')} · {(r.get('identity') or {}).get('intent')}" + (' · root' if r.get('root') else '')),
            verb='unignore' if r.get('height') in ignored else 'ignore') for r in rows) + '</ol>'
        form = lambda face, verb, spec, why: T['hand_form'].format(face=face, verb=verb, why=why, inputs=''.join(
            f'<label>{n} <textarea name="{n}" rows="3"></textarea></label>' if k == 'json' else f'<label>{n} <input name="{n}"></label>' for n, k in spec))
        mod = ''.join(form('mod', v, spec, 'reading') for v, (_, spec) in root.POWERS.items()) + form('mod', 'settings', root.MOD_SETTINGS, 'reading')
        note = T['hand_note'].format(text=q(query['note'])) if query.get('note') else ''
        return pages.page('root', 'owner', T['hand_root'].format(note=note, codes=codes, editor=editor, entries=entries,
                                                                  before=q(min([r.get('height') or 0 for r in rows] or [0])), mod=mod,
                                                                  root=''.join(form('root', v, spec, 'reason') for v, spec in root.ROOT.items())))

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
                note = ' '.join(str(v) for v in done.values() if isinstance(v, (str, list)))
                back = '/hand/root/?' if path.startswith(('/hand/root', '/hand/mod')) else '/hand/?'
                return 303, '', [('Location', back + urllib.parse.urlencode({'note': note}) + ('' if back == '/hand/root/?' else '#outbox'))]
        if method == 'GET' and path == '/hand':
            return 200, self.page(query), []
        if method == 'GET' and path == '/hand/root':
            return 200, self.root_page(query), []
        return 404, pages.page('not found', None, '<h1>not found</h1>'), []

    def web_action(self, path, form):
        """The POSTed form as one of the operations above; None for an unknown path or action."""
        face, _, verb = path[len('/hand/'):].partition('/')
        if path == '/hand/root/save':
            return self.save(form.get('object', ''), form)
        if face in ('root', 'mod') and (verb in root.ROOT if face == 'root' else verb in root.POWERS or verb == 'settings'):
            got = self.act(face, verb, form)
            return {'done': f"{verb}: {got.get('status')}" + (f", entry {got['receipt'].get('height')}" if got.get('receipt') else '')}
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
        codes = ''.join(T['hand_code'].format(text=q(f'entry {v}' if k == 'journal height' else f'{k} {v}')) for k, v in st.items())
        found = T['hand_card'].format(text=q(json.dumps(self.search(query['slug']), indent=1, sort_keys=True)[:3000])) if query.get('slug') else ''
        outbox = ''.join(T['hand_group'].format(
            original=T['hand_card'].format(text=q(f'{g["original"]["handle"]}\n{g["original"]["text"]}')) if g['original'] else T['hand_note'].format(text=q(g['post'])),
            drafts=''.join(T['hand_draft'].format(fate=q(d['outcome']), stamp=q(pages.stamp(d['outcome'])), height=q('-' if d['height'] is None else d['height']), name=q(d['slug']), object=q(d['object']), id=q(d['id']), text=q(d['text']))
                           for d in g['drafts'])) for g in self.outbox()) or '<p class="quiet">— no drafts waiting —</p>'
        inbox = ''.join(T['hand_row'].format(
            outcome=q(r['outcome'] or ''), kind=q(r['kind']), handle=q(r['handle']), text=q(r['text']), uri=q(r['uri']),
            stamp=q('' if r['skipped'] or not r['fate'] else pages.stamp(r['fate'])), retry=T['hand_retry'].format(uri=q(r['uri'])) if r['skipped'] else '') for r in self.inbox()) \
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


def given(a):
    """A root or moderation verb's flags as the form the web face posts; `--<name>-file` gives a JSON value or a card's text."""
    out = {k: str(v) for k, v in vars(a).items() if v is not None and not k.endswith('_file')}
    return out | {k[:-5]: Path(v).read_text() for k, v in vars(a).items() if k.endswith('_file') and v}


def cli_root(h, a):
    if a.rverb == 'dump':
        return root.dump(h.host, h.owner, a.object)
    if a.rverb == 'entries':
        return root.entries(h.host, h.owner, a.after, a.limit, a.object, a.principal)
    if a.rverb == 'edit':
        found = h.host.send({'op': 'world-entries', 'principal': h.owner, 'after': a.height - 1, 'limit': 1}).get('entries') or []
        if not found:
            raise HandError(f'no entry {a.height}')
        return {'saved': a.out, 'run': root.edit_command(found[0], a.height, a.journal, a.out)}
    return h.act('root', a.rverb, given(a))


def zulip_client(rc):
    from transport.zulip import Client
    return Client(rc)


def serve(a, host):
    """The web face on its own listener, which serves /hand/ and nothing else; never the public port."""
    from transport.http import Front
    token = Path(a.token_file).read_text().strip() if a.token_file else os.environ.get('DELVETALK_HAND_TOKEN', '')
    if not token:
        raise SystemExit('hand serve: a token, from --token-file or DELVETALK_HAND_TOKEN, is required')
    console = Front((a.bind, a.port), host, None, hand=Hand(a.state, host, token, a.credentials))
    try:
        console.serve_forever()
    finally:
        host.close()
    return 0


def main(argv=None, out=None, host=None, poster=post.post_draft):
    out = out or sys.stdout
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--state', default=os.environ.get('DELVETALK_STATE'), help='the bridge state directory (or DELVETALK_STATE)')
    add_host_args(common, root=True)
    common.add_argument('--credentials', default=os.environ.get('DELVETALK_CREDENTIALS', post.CREDENTIALS))
    common.add_argument('--json', action='store_true', help='one JSON document instead of text')
    ap = argparse.ArgumentParser(prog='hand.py', description='the owner\'s console, command-line face')
    sub = ap.add_subparsers(dest='verb', required=True)
    spec = {'inbox': [('--since', dict(type=int)), ('--kind', dict(choices=('summon', 'reply', 'post', 'wiki-page', 'wiki-edit', 'wiki-merge')))],
            'outbox': [('--all', dict(action='store_true'))], 'show': [('draft', {})],
            'edit': [('draft', {}), ('--text-file', {}), ('--stdin', dict(action='store_true'))],
            'post': [('draft', {}), ('--object', {})], 'skip': [('draft', {}), ('--reason', dict(required=True))], 'hold': [('draft', {})],
            'unpost': [('draft', {}), ('--reason', dict(required=True)), ('--zuliprc', dict(default=os.environ.get('DELVETALK_ZULIPRC')))],
            'status': [('--journal', dict(help='--json: the world journal (default <state>/town.journal)')),
                       ('--backups', dict(help='--json: the backup directory (default DELVETALK_BACKUPS or /var/backups/delvetalk)'))], 'search': [('slug', {})], 'retry': [('uri', {})],
            'reply': [('uri', {}), ('--text-file', dict(required=True)), ('--object', dict(required=True))],
            'log': [('--tail', dict(type=int, default=20))],
            'serve': [('--token-file', dict(default=os.environ.get('DELVETALK_HAND_TOKEN_FILE'), help='the file holding the secret asked once (or DELVETALK_HAND_TOKEN); never argv')),
                      ('--bind', dict(default='127.0.0.1', help='loopback, reached by an ssh forward')), ('--port', dict(type=int, default=8766))]}
    spec |= {'modlog': [('--object', {}), ('--tail', dict(type=int, default=20))], 'find': [('text', {})]}
    flags = lambda fields, why: [(f'--{n}', {}) for n, _ in fields] + [(f'--{n}-file', {}) for n, k in fields if k == 'json' or n == 'text'] + \
        [(f'--{why}', dict(required=True))]
    spec |= {v: flags(f, 'reading') for v, (_, f) in root.POWERS.items()} | {'settings': flags(root.MOD_SETTINGS, 'reading')}
    for name, args in spec.items():
        p = sub.add_parser(name, parents=[common])
        for a, k in args:
            p.add_argument(a, **k)
    rp = sub.add_parser('root', parents=[common], help='root acts and reads, one click past moderation (docs/ROOT.md 1.6)').add_subparsers(dest='rverb', required=True)
    for name, args in {**{v: flags(f, 'reason') for v, f in root.ROOT.items()}, 'dump': [('object', {})],
                       'entries': [('--after', dict(type=int)), ('--object', {}), ('--principal', {}), ('--limit', dict(type=int, default=20))],
                       'edit': [('height', dict(type=int)), ('--journal', dict(default='/data/state/town.journal')), ('--out', dict(default='entry.json'))]}.items():
        p = rp.add_parser(name, parents=[common])
        for a, k in args:
            p.add_argument(a, **k)
    a = ap.parse_args(argv)
    if not a.state:
        ap.error('--state (or DELVETALK_STATE) is required')
    if a.verb == 'serve':
        return serve(a, host or connect(a))
    h = Hand(a.state, host or connect(a), credentials=a.credentials, poster=poster, who='cli')
    try:
        read = lambda p: Path(p).read_text()
        data = {'inbox': lambda: h.inbox(a.since, a.kind), 'outbox': lambda: h.outbox(a.all), 'show': lambda: h.show(a.draft),
                'edit': lambda: h.edit(a.draft, sys.stdin.read() if a.stdin else read(a.text_file)), 'post': lambda: h.post(a.draft, object=a.object),
                'skip': lambda: h.skip(a.draft, a.reason), 'hold': lambda: h.hold(a.draft),
                'unpost': lambda: h.unpost(a.draft, a.reason, zulip_client(a.zuliprc) if a.zuliprc else None), 'status': (lambda: h.probe(a.backups, a.journal)) if a.json else h.status, 'search': lambda: h.search(a.slug),
                'retry': lambda: h.retry(a.uri), 'reply': lambda: h.reply(a.uri, read(a.text_file), a.object), 'log': lambda: h.tail(a.tail),
                'modlog': lambda: root.modlog(h.host, h.owner, a.object, a.tail), 'find': lambda: root.find(h.host, h.owner, a.text, h.observed().values()),
                'root': lambda: cli_root(h, a), **{v: (lambda: h.act('mod', a.verb, given(a))) for v in [*root.POWERS, 'settings']}}[a.verb]()
    except (HandError, OSError) as err:
        print(f'hand: {err}', file=sys.stderr)
        return 1
    out.write((json.dumps(data, indent=1, sort_keys=True) if a.json else text_of(data)) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
