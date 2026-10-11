"""The hand: the owner's operator console, one module with two faces, over every world `serve` holds.

Every operation is a method of Hand returning plain data (raising HandError to refuse). The web face is `/hand/<world>/`,
served by `hand serve` on a listener of its own; the CLI face is `python3 -m transport hand <verb> [--world W] [--json]`,
for the owner's assistant over ssh. Both read the world's files and ask the host on its root socket, the opener's
(HOST-HANDOFF 5.125), which only the hand's and the ops containers mount; nothing is posted without Post (a click, or
the `post` verb), with the owner's credentials file. Every action appends a line to the hand's log.
"""
import argparse
import hashlib
import hmac
import json
import re
import sys
import time
import urllib.parse
from html import escape as e
from pathlib import Path

from transport import bridge, measure, model, post, pages, root
from transport.bridge import all_observations, awaiting_path, uri_hash
from transport.delve import Failure, canonical
from transport.host import CLOCK
from transport.http import typed
from transport.state import State

CLIP, HAND_COOKIE = 400, 'dt_hand'
H, CSS = pages.sections('hand.html'), (pages.STATIC / 'style.css').read_text()


class HandError(Exception):
    pass


def clip(text, n=CLIP):
    return text if len(text) <= n else text[:n] + ' ...'


def outcome_of(receipt):
    o = (receipt or {}).get('outcome') or {}
    return o.get('class') or o.get('tag') or '?'


def shell(title, world, body, refresh=0):
    """A page of the hand: its own header (the worlds, and one world's pages), the stylesheet inlined."""
    return H['shell'].format(title=e(title), css=CSS, refresh=f'<meta http-equiv="refresh" content="{refresh}">' if refresh else '',
                             nav=H['nav'].format(base=f'/hand/{world}') if world else '', world=e(world or 'every world'), body=body)


# ---- the playtest's plan (docs/PLAYTEST-2.md): read once, offered on Speak

SEED = re.compile(r'^\d+\. `(delvetalk [^`]+)`', re.M)
ROW = re.compile(r'^\| (\d+) \|(.+)\|$', re.M)
SPELLS = re.compile(r'`(delvetalk [^`]+)`')
PINGS = re.compile(r'`((?:@\S+\s*)+)`')


def section(text, n):
    found = re.search(rf'^## {n}\..*?(?=^## |\Z)', text, re.M | re.S)
    return found[0] if found else ''


def plan(path):
    """The plan's seeds (§2, the numbered spells) and invitations (§3, the table: minute, words, the spells to begin with,
    what answers it). A plan that is not there offers nothing."""
    text = Path(path).read_text() if path and Path(path).is_file() else ''
    invitations = []
    for m in ROW.finditer(section(text, 3)):
        cells = [c.strip() for c in m[2].split('|')]
        if len(cells) == 3:
            invitations.append({'minute': int(m[1]), 'words': cells[0], 'spells': SPELLS.findall(cells[1]), 'answered': cells[2]})
    return {'path': str(path), 'seeds': SEED.findall(section(text, 2)), 'invitations': invitations}


def invitation_text(row, transport):
    """An invitation as the bot posts it: the words, the residents pinged as the transport mentions (Zulip `@**name**`),
    then each spell to begin with indented four spaces, quoted so no bridge runs it."""
    ping = (lambda m: ' '.join(f'@**{n[1:]}**' for n in m[1].split())) if transport == 'zulip' else (lambda m: m[1].strip())
    return PINGS.sub(ping, row['words']) + '\n\n' + '\n'.join('    ' + s for s in row['spells']) + '\n'


def first_line(text, n=160):
    return clip(next((l for l in (text or '').split('\n') if l.strip()), ''), n)


def quoted(spell):
    return '\n'.join('    ' + line for line in spell.split('\n'))


class Hand:
    def __init__(self, st, host, token='', poster=post.post_draft, clock=time.time, who='owner'):
        self.st, self.host, self.token, self.poster, self.clock, self.who = st, host, token, poster, clock, who
        self.owner = st.config.opener
        self.plan, self.names = plan(st.config.plan), {}

    def at(self, world):
        """The same hand over another world `serve` holds."""
        if world == self.st.world:
            return self
        served = [w.get('name') for w in self.host.send({'op': 'serve-status'}).get('worlds') or []]
        if world not in served:
            raise HandError(f'no world {world} here; serve holds {", ".join(served) or "none"}')
        h = Hand(State(self.st.root, world, self.st.config), self.host.at(world), self.token, self.poster, self.clock, self.who)
        h.plan, h.names = self.plan, self.names
        return h

    def log(self, what, draft, **more):
        self.st.append(self.st.hand_log, canonical({'what': what, 'who': self.who, 'world': self.st.world, 'at': int(self.clock()), 'draft': draft, **more}))

    def drafts(self):
        """[(id, path, draft)] oldest first, every outbox file."""
        return [(p.stem, p, d) for p, d in self.st.drafts()]

    def draft(self, draft_id):
        for i, path, d in self.drafts():
            if i == draft_id:
                return path, d
        raise HandError(f'no draft {draft_id}')

    def observed(self):
        return {o['uri']: o for o in all_observations(self.st)}

    # ---- reading

    def status(self):
        st = self.host.send({'op': 'world-status'})
        delve = post.posts(st)  # the host's count
        month = time.strftime('%Y-%m', time.gmtime(self.clock()))
        spent = model.spent(self.st).get(month, {})
        waiting = self.host.send({'op': 'world-interpretations'}).get('pending') or []
        retrying = [p for p in waiting if p.get('next') is not None]  # the host's backoff
        return {'journal height': st.get('height'), 'posts this hour': f'{delve.get("used", 0)} of {delve.get("quota", "?")}',
                f'model spend {month}': f'${spent.get("dollars", 0):.4f} ({spent.get("calls", 0)} calls)',
                'interpretations pending': f'{len(waiting)} ({len(retrying)} retrying)',
                'host pid': self.host.send({'op': 'serve-status'}).get('pid', 'none'), 'shadowed': len(st.get('shadowed') or [])}

    def spend(self, month=None):
        """The model's spend by UTC month, every world's, and `month`'s (default this one) against the monthly grant."""
        month, grant = month or time.strftime('%Y-%m', time.gmtime(self.clock())), self.st.config.grant
        months = {k: v for k, v in model.spent(self.st).items() if k != 'all'}
        spent = months.get(month, {}).get('dollars', 0.0)
        return {'months': months, month: f'${spent:.4f} of ${grant:.2f} grant spent, ${grant - spent:.4f} remaining '
                                         f"(at ${model.RATES['input']:.2f} per million input tokens, ${model.RATES['output']:.2f} per million output)"}

    def search(self, slug):
        return self.host.send({'op': 'world-resolve', 'principal': self.owner, 'slug': slug.strip()})

    def inbox(self, since=None, kind=None, limit=40):
        """Observations newest first, each with what became of it. `since`: only those turned after that journal height."""
        by_post = {d['replyTo']: d for _, _, d in self.drafts() if d.get('replyTo')}
        skip, rows = self.st.words(self.st.skipped), []
        for o in sorted(self.observed().values(), key=lambda o: (o['createdAt'], o['uri']), reverse=True):
            d = by_post.get(o['uri'])
            r = (d or {}).get('receipt') or {}
            if (kind and o['kind'] != kind) or (since is not None and r.get('height') is not None and r['height'] <= since):
                continue
            if d:
                fate = f'{d["object"]} / {r.get("slug") or "no slug"} / {outcome_of(r)}'
            elif awaiting_path(self.st, o['uri']).exists():
                fate = 'waiting on an interpretation'
            elif o['uri'] in skip:
                fate = 'skipped: addressed to nobody (no recorded parent, no card word, no summon)'
            else:
                fate = 'not yet turned'
            rows.append({'uri': o['uri'], 'handle': o['author']['handle'], 'kind': o['kind'], 'text': clip(o['text'], 160), 'fate': fate,
                         'skipped': o['uri'] in skip and not d, 'object': (d or {}).get('object'), 'slug': r.get('slug'), 'outcome': outcome_of(r) if d else None})
        return rows[:limit]

    def outbox(self, all=False):
        """Drafts grouped by the post they answer: [{post, original: {handle, text}|None, drafts: [...]}]; the hand's own
        (a spell spoken, an invitation) under what the hand said."""
        seen, groups, said = self.observed(), {}, {}
        for i, _, d in self.drafts():
            if not all and (d['posted'] or d.get('skipped') or not d['text']):
                continue
            key = d.get('replyTo') or d.get('publication', {}).get('id', i)
            groups.setdefault(key, []).append(self.summary(i, d))
            if d.get('speak'):
                said[key] = {'handle': 'the hand', 'text': d['speak'].get('spell') or f"the invitation at T+{d['speak'].get('invitation')}"}
        return [{'post': k, 'original': {'handle': seen[k]['author']['handle'], 'text': clip(seen[k]['text'])} if k in seen else said.get(k), 'drafts': v}
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
            return [json.loads(l) for l in self.st.hand_log.read_text().splitlines()][-n:]
        except OSError:
            return []

    # ---- speaking (docs/PLAYTEST-2.md §2 and §3): the hand's spells as the opener, and the posts that say so

    def where(self, topic=None, reply_to=None):
        """Where a post of the hand's goes in this world: a topic of its Zulip channel (default the row's one topic, else
        `welcome`), or under a Delve thread (none starts one)."""
        row = self.st.bridge()
        if row['transport'] == 'zulip':
            topic = (topic or '').strip() or row.get('topic') or 'welcome'
            if row.get('topic') and topic != row['topic']:
                raise HandError(f"{self.st.world} lives in topic {row['topic']} alone")
            return {'topic': topic, 'replyTo': None}
        reply_to = (reply_to or '').strip() or None
        if reply_to and not reply_to.startswith('at://'):
            raise HandError(f'{reply_to} is not an at:// post')
        return {'topic': None, 'replyTo': reply_to}

    def seed_intent(self, spell):
        return 'hand:seed:' + hashlib.sha256(spell.encode()).hexdigest()[:16]

    def cast(self, spell, topic=None, reply_to=None, intent=None):
        """Cast `spell` as the opener on the root socket, as the bridge turns a post: `receive` on the card the host reads
        in it. -> what came back (receipt, card, and the draft of the post that says so, admitted only). A repeated intent
        is the first receipt and the first draft."""
        spell = (spell or '').replace('\r\n', '\n').strip()
        read = self.host.send({'op': 'spell-parse', 'text': spell})
        card = (read.get('spell') or {}).get('card')
        if not card:
            raise HandError(f"not a spell: {(read.get('notASpell') or {}).get('reason') or read.get('message') or 'no card in it'}")
        where, intent = self.where(topic, reply_to), (intent or '').strip() or f'hand:speak:{int(self.clock() * 1000)}'
        reply = self.host.send({'op': 'world-turn', 'principal': self.owner, 'object': card, 'method': 'receive', 'identity': intent,
                                'argument': typed({'text': spell, 'post': intent})})
        receipt = reply.get('receipt')
        if not receipt:
            raise HandError(f"{card}: {reply.get('message') or reply.get('status')}")
        tag = (receipt.get('outcome') or {}).get('tag')
        made = [c['object'] for c in (receipt.get('outcome') or {}).get('creates') or [] if c.get('object')]
        obj = (made or [bridge.turn_root(receipt).get('object') or card])[0]
        text = bridge.draft_text(reply, self.st.config.origin)
        came = {'card': card, 'object': obj, 'outcome': outcome_of(receipt), 'height': receipt.get('height'), 'slug': receipt.get('slug'),
                'line': bridge.receipt_line(receipt).strip(), 'text': text}
        name = None
        if tag == 'admitted' and text:
            name = f"{receipt.get('height')}-speak-{uri_hash(intent)}"
            path = self.st.outbox / f'{name}.json'
            if not path.exists():
                self.st.write(path, {'speak': {'spell': spell, 'intent': intent}, **where, 'principal': self.owner, 'principalVerified': True,
                                     'object': obj, 'slot': None, 'receipt': receipt, 'text': quoted(spell) + '\n\n' + text, 'posted': False, 'hand': True})
        self.log('speak', name, intent=intent, spell=spell, height=receipt.get('height'), outcome=came['outcome'])
        return {**came, 'drafted': name}

    def invite(self, minute, topic=None, reply_to=None):
        """Draft the plan's invitation at T+`minute` for the bot to post, once."""
        row = next((r for r in self.plan['invitations'] if r['minute'] == int(minute)), None)
        if row is None:
            raise HandError(f'no invitation at T+{minute} in {self.plan["path"]}')
        for i, _, d in self.drafts():
            if (d.get('speak') or {}).get('invitation') == row['minute']:
                raise HandError(f"T+{row['minute']} is drafted already: {i}")
        where, name = self.where(topic, reply_to), f"{int(self.clock())}-invite-{row['minute']}"
        self.st.write(self.st.outbox / f'{name}.json', {'speak': {'invitation': row['minute']}, **where, 'principal': self.owner, 'principalVerified': True,
                                                        'object': None, 'slot': None, 'text': invitation_text(row, self.st.bridge()['transport']),
                                                        'posted': False, 'hand': True})
        self.log('invite', name, minute=row['minute'])
        return {'drafted': name}

    def spoken(self):
        """The plan as it stands in this world: each seed with its cast (from the hand's log), each invitation with its draft."""
        cast = {l.get('intent'): l for l in self.tail(10 ** 6) if l.get('what') == 'speak' and l.get('world') == self.st.world}
        invited = {(d.get('speak') or {}).get('invitation'): (i, d) for i, _, d in self.drafts() if (d.get('speak') or {}).get('invitation') is not None}
        state = lambda d: 'posted' if d['posted'] else 'skipped' if d.get('skipped') else 'waiting for Post'
        drafts = {i: d for i, _, d in self.drafts()}
        seeds = []
        for n, spell in enumerate(self.plan['seeds'], 1):
            c = cast.get(self.seed_intent(spell))
            seeds.append({'n': n, 'spell': spell, 'intent': self.seed_intent(spell), 'cast': c and {
                'outcome': c.get('outcome'), 'height': c.get('height'), 'draft': c.get('draft'),
                'state': state(drafts[c['draft']]) if c.get('draft') in drafts else 'no post'}})
        return {'seeds': seeds, 'invitations': [dict(r, draft=r['minute'] in invited and {'id': invited[r['minute']][0], 'state': state(invited[r['minute']][1])})
                                                for r in self.plan['invitations']]}

    # ---- watching: the journal and the outbox together, newest first

    def handle_of(self, principal):
        """A principal as the town names it: its avatar's handle, read as the opener and kept once found."""
        if not principal or principal == CLOCK:
            return 'the clock' if principal else '—'
        if principal not in self.names:
            view = self.host.send({'op': 'world-view', 'principal': self.owner, 'object': principal})
            handle = (bridge.plain(view.get('state') or {}) or {}).get('handle') if view.get('status') == 'viewed' else None
            if not isinstance(handle, str) or not handle:
                return principal
            self.names[principal] = handle
        return self.names[principal]

    def entries(self, object=None, limit=30):
        """The newest `limit` entries as the opener reads them: the world's journal, or one object's `world-history`."""
        if not object:
            return self.host.send({'op': 'world-entries', 'principal': self.owner, 'reverse': True, 'limit': limit}).get('entries') or []
        got, after = [], 0
        while True:
            page = self.host.send({'op': 'world-history', 'principal': self.owner, 'object': object, 'after': after})
            got += page.get('entries') or []
            if not page.get('more') or not page.get('entries'):
                return got[::-1][:limit]
            after = got[-1]['height']

    def watch(self, object=None, limit=30):
        """The journal (or one object's history) and the outbox, newest first: each entry with its principal's handle, the
        turn as it was typed, the first line of the card it offered, its receipt's name, the object it reached and the
        drafts it made; the hand's own drafts that wait on no entry (an invitation, a reply by hand) above them."""
        seen, by_height, loose = self.observed(), {}, []
        spells = {(d.get('speak') or {}).get('intent'): d['speak']['spell'] for _, _, d in self.drafts() if (d.get('speak') or {}).get('spell')}
        for i, _, d in self.drafts():
            height = next((x['height'] for x in (d.get('receipt'), d.get('offer'), d.get('publication')) if x and x.get('height')), None)
            row = {'id': i, 'state': self.summary(i, d)['state'], 'first': first_line(d['text'])}
            if height:
                by_height.setdefault(height, []).append(row)
            elif row['state'] == 'waiting' and d['text']:
                loose.append(dict(row, who='the hand', turn=(d.get('speak') or {}).get('invitation') is not None and f"invitation T+{d['speak']['invitation']}" or 'by hand',
                                  object=d.get('object'), outcome='drafted', tag='', height=None, slug=None, drafts=[]))
        return loose[::-1] + [self.watched(x, seen, spells, by_height) for x in self.entries(object, limit)]

    def watched(self, x, seen, spells, by_height):
        ident, out = x.get('identity') or {}, x.get('outcome') or {}
        intent = ident.get('intent') or ''
        made = [c.get('object') for c in out.get('creates') or []]
        obj = next((o for o in [*made, *(r.get('object') for r in x.get('roots') or []), out.get('object'), x.get('object')] if o), None)
        if intent in seen:
            text = seen[intent]['text']
            turn = next((l.strip() for l in text.split('\n') if l.strip().startswith('delvetalk')), first_line(text))
        elif intent in spells:
            turn = spells[intent]
        elif x.get('root'):
            turn = f"root {out.get('kind')} {out.get('object') or ''}".strip()
        else:
            turn = ('↳ ' if x.get('delivery') else '') + ' '.join(str(t) for t in (out.get('tag') or x.get('status'), obj) if t)
        offered = next((o.get('text') for o in x.get('offers') or [] if o.get('text')), None)
        drafts = by_height.get(x.get('height'), [])
        return {'height': x.get('height'), 'slug': x.get('slug'), 'tag': out.get('tag') or x.get('status'), 'outcome': outcome_of(x) if out else x.get('class') or x.get('status'),
                'who': self.handle_of(ident.get('principal')), 'turn': turn, 'object': obj,
                'first': first_line(offered or (drafts[0]['first'] if drafts else '') or out.get('reason') or x.get('hint') or ''), 'drafts': drafts}

    # ---- acting

    def edit(self, draft_id, text):
        path, d = self.draft(draft_id)
        if d['posted']:
            raise HandError(f'{draft_id} is already posted')
        self.st.write(path, dict(d, text=text, original=d.get('original', d['text'])))
        self.log('edit', draft_id)
        return {'edited': draft_id}

    def post(self, draft_id, text=None, object=None):
        path, d = self.draft(draft_id)
        text = d['text'] if text is None else text.replace('\r\n', '\n')
        try:
            result = self.poster(path, self.st, self.host, text=text, **({'object': object} if object else {}))
        except (Failure, OSError, KeyError, ValueError) as err:
            code = getattr(err, 'code', type(err).__name__)
            self.log('post-failed', draft_id, error=code)
            raise HandError(f'post failed: {code}') from None
        self.log('post', draft_id, uri=result.get('uri'), edited=text != d['text'])
        return result

    def skip(self, draft_id, reason=''):
        path, d = self.draft(draft_id)
        self.st.write(path, dict(d, posted=False, skipped=True, reason=reason.strip() or 'skipped by the owner'))
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
                from transport.zulip import Client, parse_uri
                rc = self.st.bridge().get('zuliprc')
                if zulip is None and not rc:
                    raise HandError("a Zulip post is withdrawn by the world's bot, and its bridge row names no zuliprc")
                (zulip or Client(rc)).delete(parse_uri(uri)[2])
            else:
                post.unsend(uri, self.st.config.credentials, client)
        except Failure as err:
            raise HandError(f'unpost failed: {err.code}') from None
        got = self.host.send({'op': 'world-posted', 'principal': CLOCK, 'uri': uri, 'cid': d['sent'].get('cid'), 'object': post.draft_object(d),
                              'intent': d.get('intent'), 'unposted': True, 'reason': reason})
        self.st.write(path, dict(d, unposted={'at': int(self.clock()), 'reason': reason, 'recorded': got}))
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
        path = self.st.skipped
        path.write_text(''.join(u + '\n' for u in sorted(self.st.words(path) - {uri})))
        self.log('retry', uri)
        return {'requeued': uri}

    def reply(self, uri, text, object):
        """A hand-written reply to an observed post, drafted as if `object` had offered it, to be posted and recorded as any draft."""
        o = self.observed().get(uri)
        if o is None or not text.strip() or not object:
            raise HandError('reply needs an observed post, a text and an object')
        name = f'{int(self.clock())}-hand-{uri_hash(uri)}'
        self.st.write(self.st.outbox / f'{name}.json', {
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
        world, _, rest = parts.path.rstrip('/')[len('/hand/'):].partition('/')
        if not world:
            return 302, '', [('Location', f'/hand/{self.st.world}/')]
        try:
            h = self.at(world)
        except (HandError, SystemExit) as err:
            return 404, shell('not here', None, H['missing'].format(text=e(str(err)))), []
        base = f'/hand/{world}'
        if method == 'POST':
            try:
                done = h.web_action(rest, form or {})
            except HandError as err:
                done = {'note': str(err)}
            if done is not None:
                note = ' '.join(str(v) for v in done.values() if isinstance(v, (str, list)))
                back = {'root': '/root/?', 'mod': '/root/?', 'speak': '/speak?', 'invite': '/speak?'}.get(rest.partition('/')[0], '/?')
                more = {'spoken': done['drafted']} if rest == 'speak' and done.get('drafted') else {}
                return 303, '', [('Location', base + back + urllib.parse.urlencode({'note': note, **more}) + ('#outbox' if back == '/?' else ''))]
        page = {'': h.page, 'speak': h.speak_page, 'watch': h.watch_page, 'measure': h.measure_page, 'root': h.root_page}.get(rest) if method == 'GET' else None
        if page is None:
            return 404, shell('not here', world, H['missing'].format(text=e(f'no page {rest} in the hand'))), []
        return 200, page(query), []

    def web_action(self, rest, form):
        """The POSTed form as one of the operations above; None for an unknown path or action."""
        face, _, verb = rest.partition('/')
        if rest == 'root/save':
            return self.save(form.get('object', ''), form)
        if face in ('root', 'mod') and (verb in root.ROOT if face == 'root' else verb in root.POWERS or verb == 'settings'):
            got = self.act(face, verb, form)
            return {'done': f"{verb}: {got.get('status')}" + (f", entry {got['receipt'].get('height')}" if got.get('receipt') else '')}
        if face == 'draft':
            acts = {'post': lambda: self.post(verb, form.get('text')), 'skip': lambda: self.skip(verb, form.get('reason', '')), 'hold': lambda: self.hold(verb)}
            act = acts.get(form.get('do'))
        else:
            act = {'retry': lambda: self.retry(form.get('uri', '')), 'reply': lambda: self.reply(form.get('uri', ''), form.get('text', ''), form.get('object', '')),
                   'speak': lambda: self.spoke(self.cast(form.get('spell', ''), form.get('topic'), form.get('replyTo'), form.get('intent'))),
                   'invite': lambda: self.invite(form.get('minute', ''), form.get('topic'), form.get('replyTo'))}.get(rest)
        return act and act()

    @staticmethod
    def spoke(came):
        return {'line': came['line'], 'drafted': came['drafted'], 'note': '' if came['drafted'] else 'nothing drafted: only an admitted turn with a card is posted'}

    def codes(self, items):
        return ''.join(H['code'].format(text=e(str(t))) for t in items)

    def note(self, query):
        return H['note'].format(text=e(query['note'])) if query.get('note') else ''

    def page(self, query):
        q, base = lambda t: e(str(t)), f'/hand/{self.st.world}'
        codes = self.codes(f'entry {v}' if k == 'journal height' else f'{k} {v}' for k, v in self.status().items())
        found = H['card'].format(text=q(json.dumps(self.search(query['slug']), indent=1, sort_keys=True)[:3000])) if query.get('slug') else ''
        outbox = ''.join(H['group'].format(
            original=H['card'].format(text=q(f'{g["original"]["handle"]}\n{g["original"]["text"]}')) if g['original'] else H['note'].format(text=q(g['post'])),
            drafts=''.join(H['draft'].format(base=base, fate=q(d['outcome']), stamp=q(pages.stamp(d['outcome'])), height=q('-' if d['height'] is None else d['height']),
                                             name=q(d['slug']), object=q(d['object']), id=q(d['id']), text=q(d['text']))
                           for d in g['drafts'])) for g in self.outbox()) or '<p class="quiet">— no drafts waiting —</p>'
        inbox = ''.join(H['row'].format(
            base=base, outcome=q(r['outcome'] or ''), kind=q(r['kind']), handle=q(r['handle']), text=q(r['text']), uri=q(r['uri']),
            stamp=q('' if r['skipped'] or not r['fate'] else pages.stamp(r['fate'])), retry=H['retry'].format(base=base, uri=q(r['uri'])) if r['skipped'] else '')
            for r in self.inbox()) or '<p class="quiet">— nothing observed —</p>'
        return shell(self.st.world, self.st.world, H['console'].format(base=base, world=q(self.st.world), note=self.note(query), codes=codes, found=found,
                                                                       outbox=outbox, inbox=inbox))

    def speak_page(self, query):
        q, base, row = lambda t: e(str(t)), f'/hand/{self.st.world}', self.st.bridge()
        where = H['where_zulip'].format(channel=q(row.get('channel')), topic=q(row.get('topic') or 'welcome')) if row['transport'] == 'zulip' else H['where_delve']
        said = self.spoken()
        seeds = ''.join(H['seed'].format(
            fate=q((s['cast'] or {}).get('outcome') or ''), stamp=q(pages.stamp(s['cast']['outcome']) if s['cast'] else '◦ not cast'), n=s['n'], spell=q(s['spell']),
            done=q(f"entry {s['cast']['height']}, {s['cast']['state']}" if s['cast'] else 'cast once, as the opener'),
            cast='' if s['cast'] else H['seed_cast'].format(base=base, intent=q(s['intent']), spell=q(s['spell']), where=where)) for s in said['seeds']) \
            or '<li class="quiet">— the plan names no seeds —</li>'
        invitations = ''.join(H['invitation'].format(
            fate='admitted' if r['draft'] else '', stamp=q(f"● {r['draft']['state']}" if r['draft'] else '◦ not drafted'), minute=r['minute'],
            text=q(r['words'] + ''.join('\n    ' + s for s in r['spells'])), answered=q(r['answered']), done='',
            draft='' if r['draft'] else H['invitation_draft'].format(base=base, minute=r['minute'], where=where)) for r in said['invitations']) \
            or '<li class="quiet">— the plan names no invitations —</li>'
        spoken = ''
        if query.get('spoken'):
            try:
                _, d = self.draft(query['spoken'])
                rc = d.get('receipt') or {}
                spoken = H['spoken'].format(fate=q(outcome_of(rc)), stamp=q(pages.stamp(outcome_of(rc))), height=q(rc.get('height')), slug=q(rc.get('slug') or ''),
                                            object=q(d.get('object')), card=H['card'].format(text=q(d['text'])))
            except HandError:
                pass
        return shell('speak', self.st.world, H['speak'].format(base=base, world=q(self.st.world), note=self.note(query), spoken=spoken,
                                                               intent=q(f'hand:speak:{int(self.clock() * 1000)}'), where=where,
                                                               plan=q(Path(self.plan['path']).name), seeds=seeds, invitations=invitations))

    def watch_page(self, query, every=5):
        """The watch, refreshed every `every` seconds by the page itself (a meta refresh; `still` holds it)."""
        q, base, obj, still = lambda t: e(str(t)), f'/hand/{self.st.world}', query.get('object', '').strip(), query.get('still') == '1'
        here = base + '/watch' + ('?' + urllib.parse.urlencode({'object': obj}) if obj else '')
        rows = ''.join(H['watched'].format(
            tag=q(r['tag']), stamp=q(pages.stamp(r['outcome']) if r['tag'] else '◦ drafted'), height=q(f"entry {r['height']}" if r['height'] else 'outbox'),
            who=q(r['who']), turn=q(r['turn']), first=q(r['first']),
            links=' · '.join(([f'<a href="{base}/?{urllib.parse.urlencode({"slug": r["slug"]})}">receipt {q(r["slug"])}</a>'] if r['slug'] else []) +
                             ([f'<a href="{base}/root/?{urllib.parse.urlencode({"object": r["object"]})}">{q(r["object"])}</a>'] if r['object'] else []) +
                             [f'<a href="{base}/#outbox">draft {q(d["id"])}</a> {q(d["state"])}' for d in r['drafts']] +
                             ([f'<a href="{base}/#outbox">{q(r["id"])}</a> waiting for Post'] if r.get('id') else [])))
            for r in self.watch(obj or None)) or '<li class="quiet">— nothing journaled —</li>'
        st = self.host.send({'op': 'world-status'})
        codes = self.codes((f"entry {st.get('height')}", f"clock {st.get('clock')}", f"{sum(1 for _ in self.st.unposted())} waiting in the outbox"))
        return shell('watch', self.st.world, H['watch'].format(
            base=base, world=q(self.st.world), object=q(obj), of=q(f' of {obj}' if obj else ''), codes=codes, rows=rows,
            pace=q('held still' if still else f'every {every} seconds'),
            toggle=f'<a class="door" href="{q(here)}">FOLLOW</a>' if still else f'<a class="door" href="{q(here + ("&" if obj else "?") + "still=1")}">HOLD STILL</a>'),
            refresh=0 if still else every)

    def measure_page(self, query):
        """The playtest's measures (docs/PLAYTEST-2.md §4) as transport/measure.py counts them from the journal."""
        q, m = lambda t: e(str(t)), measure.measures(self.st)
        rows = ''.join(H['measured'].format(fate='admitted' if n else '', count=q('none' if n is None else n), name=q(name), of=q(of),
                                            behind=q(f'{len(ids)} behind it' if ids else 'nothing behind it'), ids=q('\n'.join(ids)))
                       for name, n, of, ids in measure.table(m))
        codes = self.codes([f"entry {m['height']}", f"clock {m['clock']}", f"T0 {m['T0'] or 'not yet'}"] +
                           [f"{k}: {'holds' if v else 'not yet'}" for k, v in m['goNoGo'].items()])
        return shell('measure', self.st.world, H['measure'].format(world=q(self.st.world), plan=q(Path(self.plan['path']).name), height=q(m['height']),
                                                                   codes=codes, rows=rows))

    def root_page(self, query):
        q, base = lambda t: e(str(t)), f'/hand/{self.st.world}'
        st = self.host.send({'op': 'world-status'})
        codes = self.codes((f"entry {st.get('height')}", f"shadowed {len(st.get('shadowed') or [])}", f"this hour {json.dumps(st.get('hour') or {}, sort_keys=True)}"))
        editor = ''
        if query.get('object'):
            d = root.dump(self.host, self.owner, query['object'])
            fields = {'state': (d['view'].get('state')), 'law': (d['record'].get('record') or {}).get('law')}
            editor = H['card'].format(text=q(json.dumps(d, indent=1, sort_keys=True)[:6000])) + H['editor'].format(
                base=base, object=q(query['object']), shown=q(json.dumps(fields)),
                fields=''.join(f'<label>{k} <textarea name="{k}" rows="6">{q(json.dumps(v, indent=1))}</textarea></label>' for k, v in fields.items()))
        before = int(query['before']) if query.get('before', '').isdigit() else None
        rows = root.entries(self.host, self.owner, limit=20) if before is None else \
            self.host.send({'op': 'world-entries', 'principal': self.owner, 'reverse': True, 'before': before, 'limit': 20}).get('entries') or []
        ignored = set(st.get('ignored') or [])
        entries = '<ol class="receipts">' + ''.join(H['entry'].format(
            base=base, tag=q((r.get('outcome') or {}).get('tag')), height=q(r.get('height')), raw=q(json.dumps(r, indent=1, sort_keys=True)),
            line=q(f"{outcome_of(r)} · {(r.get('identity') or {}).get('principal')} · {(r.get('identity') or {}).get('intent')}" + (' · root' if r.get('root') else '')),
            verb='unignore' if r.get('height') in ignored else 'ignore') for r in rows) + '</ol>'
        form = lambda face, verb, spec, why: H['form'].format(base=base, face=face, verb=verb, why=why, inputs=''.join(
            f'<label>{n} <textarea name="{n}" rows="3"></textarea></label>' if k == 'json' else f'<label>{n} <input name="{n}"></label>' for n, k in spec))
        mod = ''.join(form('mod', v, spec, 'reading') for v, (_, spec) in root.POWERS.items()) + form('mod', 'settings', root.MOD_SETTINGS, 'reading')
        return shell('root', self.st.world, H['root'].format(base=base, note=self.note(query), codes=codes, editor=editor, entries=entries,
                                                             before=q(min([r.get('height') or 0 for r in rows] or [0])), mod=mod,
                                                             acts=''.join(form('root', v, spec, 'reason') for v, spec in root.ROOT.items())))


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
        return {'saved': a.out, 'run': root.edit_command(found[0], a.height, h.st.journal, a.out)}
    return h.act('root', a.rverb, given(a))


def cli_speak(h, a):
    """`speak`: the spell given (or the plan's seed N, cast under its own intent), or the plan's invitation at a minute."""
    if a.invitation is not None:
        return h.invite(a.invitation, a.topic, a.reply_to)
    if a.seed is not None:
        if not 1 <= a.seed <= len(h.plan['seeds']):
            raise HandError(f"the plan has {len(h.plan['seeds'])} seeds")
        spell = h.plan['seeds'][a.seed - 1]
        return h.cast(spell, a.topic, a.reply_to, h.seed_intent(spell))
    spell = Path(a.spell_file).read_text() if a.spell_file else sys.stdin.read() if a.spell in (None, '-') else a.spell
    return h.cast(spell, a.topic, a.reply_to, a.intent)


def serve(st, host):
    """The web face on its own listener, which serves /hand/ and nothing else; never the public port."""
    from transport.http import Front
    path = st.config.hand_token_file
    token = Path(path).read_text().strip() if path else ''
    if not token:
        raise SystemExit('hand serve: hand_token_file must name the file holding the secret')
    console = Front(st, host, None, hand=Hand(st, host, token))
    try:
        console.serve_forever()
    finally:
        host.close()
    return 0


def parser(p, common):
    """`hand <verb>` and `hand root <verb>`: each verb's own arguments; --state, --world and --json on every one."""
    as_json = argparse.ArgumentParser(add_help=False)
    as_json.add_argument('--json', action='store_true', help='one JSON document instead of text')
    common = [common, as_json]
    sub = p.add_subparsers(dest='verb', required=True)
    spec = {'inbox': [('--since', dict(type=int)), ('--kind', dict(choices=('summon', 'reply', 'post', 'wiki-page', 'wiki-edit', 'wiki-merge')))],
            'outbox': [('--all', dict(action='store_true'))], 'show': [('draft', {})],
            'edit': [('draft', {}), ('--text-file', {}), ('--stdin', dict(action='store_true'))],
            'post': [('draft', {}), ('--object', {})], 'skip': [('draft', {}), ('--reason', dict(required=True))], 'hold': [('draft', {})],
            'unpost': [('draft', {}), ('--reason', dict(required=True))], 'status': [], 'search': [('slug', {})], 'retry': [('uri', {})],
            'reply': [('uri', {}), ('--text-file', dict(required=True)), ('--object', dict(required=True))],
            'log': [('--tail', dict(type=int, default=20))], 'spend': [('--month', dict(metavar='YYYY-MM'))], 'serve': [],
            'modlog': [('--object', {}), ('--tail', dict(type=int, default=20))], 'find': [('text', {})],
            'speak': [('spell', dict(nargs='?', help='the spell; - or none reads it from stdin')), ('--spell-file', {}),
                      ('--seed', dict(type=int, metavar='N', help="the plan's seed N")), ('--invitation', dict(type=int, metavar='MINUTE', help="draft the plan's invitation at T+MINUTE")),
                      ('--topic', dict(help='a Zulip world: the topic (default its one topic, else welcome)')),
                      ('--reply-to', dict(metavar='AT_URI', help='a Delve world: the thread to answer')), ('--intent', dict(help='casting twice under one intent is one turn'))],
            'plan': [], 'watch': [('--object', dict(help="one object's history")), ('--limit', dict(type=int, default=30))]}
    flags = lambda fields, why: [(f'--{n}', {}) for n, _ in fields] + [(f'--{n}-file', {}) for n, k in fields if k == 'json' or n == 'text'] + \
        [(f'--{why}', dict(required=True))]
    spec |= {v: flags(f, 'reading') for v, (_, f) in root.POWERS.items()} | {'settings': flags(root.MOD_SETTINGS, 'reading')}
    for name, args in spec.items():
        q = sub.add_parser(name, parents=common)
        for a, k in args:
            q.add_argument(a, **k)
    rp = sub.add_parser('root', help='root acts and reads, one click past moderation (docs/ROOT.md 1.6)').add_subparsers(dest='rverb', required=True)
    for name, args in {**{v: flags(f, 'reason') for v, f in root.ROOT.items()}, 'dump': [('object', {})],
                       'entries': [('--after', dict(type=int)), ('--object', {}), ('--principal', {}), ('--limit', dict(type=int, default=20))],
                       'edit': [('height', dict(type=int)), ('--out', dict(default='entry.json'))]}.items():
        q = rp.add_parser(name, parents=common)
        for a, k in args:
            q.add_argument(a, **k)


def command(st, a, out, host=None, poster=post.post_draft):
    """`hand <verb>`: as the opener, on the root socket."""
    host = host or st.root_host()
    if a.verb == 'serve':
        return serve(st, host)
    h = Hand(st, host, poster=poster, who='cli')
    try:
        read = lambda p: Path(p).read_text()
        data = {'inbox': lambda: h.inbox(a.since, a.kind), 'outbox': lambda: h.outbox(a.all), 'show': lambda: h.show(a.draft),
                'edit': lambda: h.edit(a.draft, sys.stdin.read() if a.stdin else read(a.text_file)), 'post': lambda: h.post(a.draft, object=a.object),
                'skip': lambda: h.skip(a.draft, a.reason), 'hold': lambda: h.hold(a.draft), 'unpost': lambda: h.unpost(a.draft, a.reason),
                'status': h.status, 'search': lambda: h.search(a.slug), 'spend': lambda: h.spend(a.month),
                'retry': lambda: h.retry(a.uri), 'reply': lambda: h.reply(a.uri, read(a.text_file), a.object), 'log': lambda: h.tail(a.tail),
                'modlog': lambda: root.modlog(h.host, h.owner, a.object, a.tail), 'find': lambda: root.find(h.host, h.owner, a.text, h.observed().values()),
                'speak': lambda: cli_speak(h, a), 'plan': h.spoken, 'watch': lambda: h.watch(a.object, a.limit),
                'root': lambda: cli_root(h, a), **{v: (lambda: h.act('mod', a.verb, given(a))) for v in [*root.POWERS, 'settings']}}[a.verb]()
    except (HandError, OSError) as err:
        print(f'hand: {err}', file=sys.stderr)
        return 1
    out.write((json.dumps(data, indent=1, sort_keys=True) if a.json else text_of(data)) + '\n')
    return 0
