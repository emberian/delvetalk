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

from transport import bridge, byhand, measure, model, post, pages, root
from transport.bridge import awaiting_path, uri_hash
from transport import observe
from transport.delve import Failure, canonical
from transport.host import CLOCK, fell_back, handles, history_limit, painted, typed
from transport.http import WAIT_MAX, trace
from transport.identity import INVITE_DAYS, Identity, IdentityError
from transport.measure import counted
from transport.state import State

CLIP, HAND_COOKIE = 400, 'dt_hand'
LOOK_EVERY = 30  # seconds between two looks of the outbox into the posting account's repository (config hand_find)
H, CSS = pages.sections('hand.html'), (pages.STATIC / 'style.css').read_text()


class HandError(Exception):
    pass


def clip(text, n=CLIP):
    return text if len(text) <= n else text[:n] + ' ...'


def outcome_of(receipt):
    o = (receipt or {}).get('outcome') or {}
    return o.get('class') or o.get('tag') or '?'


def shell(title, world, body, refresh=0):
    """A page of the hand: the one skeleton (pages.page) with the hand's header (the worlds, and one world's pages) and
    footer, the stylesheet inlined (the hand's listener serves /hand/ and nothing else)."""
    head = f'<style>{CSS}</style>' + (f'<meta http-equiv="refresh" content="{refresh}">' if refresh else '')
    return pages.page(title, world or 'every world', body, site='the hand', home='/hand/', head=head,
                      nav=H['nav'].format(base=f'/hand/{world}') if world else '', foot=H['foot'])


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


# The welcome's move (docs/POSTING.md build 8): one any resident makes for themselves, so the welcome is a real act with
# a receipt that resolves, and its answer the card the resident will get.
WELCOME = 'delvetalk kind/bell make / seed: a bell for whoever comes next / colour: silver'


def welcome_text(spell, answered):
    """The welcome's text: hob's opening line, the move as cast and as answered, and the move offered back."""
    mine = spell.replace('a bell for whoever comes next', '<your words>')
    return ('hob: the frog on the quiet line; the cards answer for themselves. One move, done:\n\n' + quoted(spell) + '\n\n' +
            answered.split('\n\n', 1)[-1].rstrip('\n') + '\n\n' +
            'Yours: reply under this post with\n' + quoted(mine) + '\n'
            'To see first what it would do: delvetalk try, the spell indented under it. The rest: delvetalk guide.')


class Hand:
    def __init__(self, st, host, token='', poster=post.post_draft, clock=time.time, who='owner', sleep=time.sleep, reader=None):
        self.st, self.host, self.token, self.poster, self.clock, self.who, self.sleep = st, host, token, poster, clock, who, sleep
        self.owner = st.config.opener
        self.plan, self.names, self.hands = plan(st.config.plan), {}, {st.world: self}  # read once; kept across the hand's worlds
        self._identity, self._reader, self.looked, self.found = None, reader, 0.0, {'linked': [], 'offers': []}

    @property
    def reader(self):
        """delve.town read only (`getRecord`, `listRecords`, `resolveHandle`): no client here may write."""
        if self._reader is None:
            from transport.delve import Client, FixtureTransport, http_transport
            self._reader = Client(FixtureTransport(self.st.config.delve_mock) if self.st.config.delve_mock else http_transport)
        return self._reader

    def at(self, world):
        """The same hand over another world `serve` holds."""
        if world not in self.hands:
            served = [w.get('name') for w in self.host.send({'op': 'serve-status'}).get('worlds') or []]
            if world not in served:
                raise HandError(f'no world {world} here; serve holds {", ".join(served) or "none"}')
            h = Hand(State(self.st.root, world, self.st.config), self.host.at(world), self.token, self.poster, self.clock, self.who, self.sleep, self._reader)
            h.plan, h.names, h.hands, h._identity = self.plan, self.names, self.hands, self._identity
            self.hands[world] = h
        return self.hands[world]

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
        return {o['uri']: o for o in self.st.observations()}

    # ---- reading

    def status(self):
        st = self.host.send({'op': 'world-status'})
        delve = post.posts(st)  # the host's count
        month = time.strftime('%Y-%m', time.gmtime(self.clock()))
        spent = model.spent(self.st).get(month, {})
        waiting = self.host.send({'op': 'world-interpretations'}).get('pending') or []
        retrying = [p for p in waiting if p.get('next') is not None]  # the host's backoff
        return {'entry': f"entry {st.get('height')}", 'posts': f'{delve.get("used", 0)} of {delve.get("quota", "?")} posts this hour',
                'model': f'${spent.get("dollars", 0):.4f} of model spend in {month}, {counted(spent.get("calls", 0), "call")}',
                'interpretations': f'{counted(len(waiting), "interpretation")} waiting, {len(retrying)} retrying',
                'host': f"host pid {self.host.send({'op': 'serve-status'}).get('pid', 'none')}", 'shadowed': f"{len(st.get('shadowed') or [])} shadowed",
                'posting': self.posting()}

    def posting(self):
        """How this world's drafts leave, said: by the owner's hand, the credential file, or the Zulip bot."""
        how = byhand.mode(self.st)
        return {'by hand': 'posting by hand: no credential file, so you post each draft from your own client and give the hand its link',
                'automatic': f'posting automatically: Post reads the credential file {self.st.config.credentials}',
                'zulip': "posting by the world's Zulip bot"}[how]

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
                settled = json.loads(awaiting_path(self.st, o['uri']).read_text()).get('settled')
                fate = 'read by hob; nothing to answer' if settled else 'waiting on an interpretation'
            elif o['uri'] in skip:
                fate = 'skipped: addressed to nobody (no recorded parent, no card word, no summon)'
            else:
                fate = 'not yet turned'
            rows.append({'uri': o['uri'], 'handle': o['author']['handle'], 'kind': o['kind'], 'text': clip(o['text'], 160), 'fate': fate,
                         'skipped': o['uri'] in skip and not d, 'object': (d or {}).get('object'), 'slug': r.get('slug'), 'outcome': outcome_of(r) if d else None})
        return rows[:limit]

    def outbox(self, all=False):
        """Drafts grouped by the post they answer, the longest waiting first: [{post, original: {handle, text}|None,
        source, since, waiting, drafts: [...]}]; the hand's own (a spell spoken, an invitation) under what the hand said.
        Each draft waiting on delve.town carries what posting it by hand needs (`ready`). A draft answering the town's
        own feed is not here: the feed posts itself."""
        from transport import feed
        seen, groups, said = self.observed(), {}, {}
        for i, path, d in self.drafts():
            if not all and (d['posted'] or d.get('skipped') or not d['text']):
                continue
            if feed.is_feed(d.get('replyTo'), self.st.config.origin, self.st.world):
                continue
            key = d.get('replyTo') or d.get('publication', {}).get('id', i)
            groups.setdefault(key, []).append(dict(self.summary(i, d), since=self.since(path, d), source=self.source(d, seen), **self.ready(path, d, seen)))
            if d.get('speak'):
                said[key] = {'handle': 'the hand', 'text': d['speak'].get('spell') or (f"the morning card of day {d['speak']['morning']}" if 'morning' in d['speak']
                                                                                      else f"the invitation at T+{d['speak'].get('invitation')}")}
        rows = [{'post': k, 'original': {'handle': seen[k]['author']['handle'], 'text': clip(seen[k]['text'])} if k in seen else said.get(k),
                 'source': v[0]['source'], 'since': min(x['since'] for x in v), 'drafts': sorted(v, key=lambda x: x['since'])} for k, v in groups.items()]
        for r in rows:
            r['waiting'] = self.waited(r['since'])
        return sorted(rows, key=lambda r: r['since'])

    def since(self, path, d):
        """When a draft began waiting: the post it answers was made (its observation's createdAt), else the draft was
        written (its file's time: the hand's own, a publication, a turn made on the web)."""
        o = self.observed().get(d.get('replyTo')) if d.get('replyTo') else None
        try:
            return int(observe.instant(o['createdAt'])) if o else int(path.stat().st_mtime)
        except (ValueError, KeyError, OSError):
            return int(self.clock())

    def waited(self, since):
        m = max(0, int(self.clock() - since) // 60)
        return f'{m // 1440} d {m % 1440 // 60} h' if m >= 1440 else f'{m // 60} h {m % 60} min' if m >= 60 else f'{m} min'

    def source(self, d, seen):
        """Where a draft came from, in words: a summon on delve.town, a reply under one of the town's posts, the hand's
        own, a page the town published, a turn made on the web, a reply by hand."""
        o = seen.get(d.get('replyTo'))
        if d.get('publication'):
            return f"a page the town published ({first_line(d['text'], 60)})"
        if d.get('speak'):
            return 'the hand\'s own: ' + ('the morning card' if 'morning' in d['speak'] else 'an invitation' if 'invitation' in d['speak']
                                         else 'the welcome' if d.get('welcome') else 'a spell it cast')
        if d.get('http'):
            return 'a turn made on the web'
        if d.get('hand'):
            return f"a reply by hand to @{o['author']['handle']}" if o else 'by hand'
        if o:
            return {'summon': f"a summon on delve.town by @{o['author']['handle']}", 'reply': f"a reply under a town post by @{o['author']['handle']}",
                    'post': f"a post on delve.town by @{o['author']['handle']}"}.get(o['kind'], f"a {o['kind']} by @{o['author']['handle']}")
        return 'a reply to a post no longer observed' if d.get('replyTo') else 'the town'

    def ready(self, path, d, seen=None):
        """What posting a waiting delve.town draft by hand needs: each part's exact text and count (posted ones with
        their link), the post the next part goes under as a delve.town link (None: it starts a thread), and which part
        is next. {} for a draft posted, skipped, or of a Zulip world."""
        if d['posted'] or d.get('skipped') or not d['text'] or byhand.mode(self.st) == 'zulip':
            return {}
        seen = self.observed() if seen is None else seen
        k, _, _, under, _, n = byhand.expected(path, d)
        done = {p['part']: p['link'] for p in d.get('byHand') or []}
        done |= {j + 1: byhand.web_link(p['uri']) for j, p in enumerate(d.get('sentParts') or []) if j + 1 not in done}
        handle = (seen.get(under) or {}).get('author', {}).get('handle')
        return {'parts': [{'n': j, 'text': t, 'chars': len(t), 'posted': done.get(j)} for j, t in enumerate(post.parts(d['text']), 1)],
                'next': k + 1, 'under': under and {'uri': under, 'link': byhand.web_link(under, handle), 'handle': handle}}

    def summary(self, i, d):
        r = d.get('receipt')
        line = f'receipt {r.get("slug")}: {outcome_of(r)}' if r else 'usage' if d.get('usage') else 'by hand' if d.get('hand') else 'a publication'
        state = 'posted' if d['posted'] else 'skipped' if d.get('skipped') else 'waiting'
        return {'id': i, 'object': post.draft_object(d), 'receipt': line, 'slug': (r or {}).get('slug') or 'by hand', 'height': (r or {}).get('height'),
                'outcome': outcome_of(r) if r else 'drafted', 'text': d['text'], 'state': state,
                **({'original': d['original']} if d.get('original') else {}), **({'reason': d['reason']} if d.get('reason') else {})}

    def view(self, draft_id):
        """One draft whole: its text, its receipt line and the post it answers (`hand draft`; `show` is the moderation power)."""
        _, d = self.draft(draft_id)
        o = self.observed().get(d.get('replyTo'))
        return {**self.summary(draft_id, d), 'post': d.get('replyTo'), 'original post': o and {'handle': o['author']['handle'], 'text': o['text']}}

    def tail(self, n=20):
        return self.st.lines(self.st.hand_log)[-n:]

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

    def cast(self, spell, topic=None, reply_to=None, intent=None, to=None, wait=WAIT_MAX):
        """Cast `spell` as the opener on the root socket, as the bridge turns a post: `receive` on the card the host reads
        in it. -> what came back (receipt, card, and the draft of the post that says so, admitted only). A repeated intent
        is the first receipt and the first draft. Words that are no spell are asked of the card `to` (`ask`)."""
        spell = (spell or '').replace('\r\n', '\n').strip()
        if not spell:
            raise HandError('nothing to say: a spell, or words for a card')
        read = self.host.send({'op': 'spell-parse', 'text': spell})
        card = (read.get('spell') or {}).get('card')
        if not card:
            return self.ask(spell, to, intent, wait)
        where, intent = self.where(topic, reply_to), (intent or '').strip() or f'hand:speak:{int(self.clock() * 1000)}'
        reply = self.receive(card, spell, intent)
        if reply.get('status') == 'usage':  # a `?`: the card's spells, which the host journals nowhere; nothing is drafted
            self.log('speak', None, intent=intent, spell=spell, height=None, slug=None, outcome='usage', object=card)
            return {'card': card, 'object': card, 'outcome': 'usage', 'height': None, 'slug': None, 'line': f'{card}: its spells',
                    'text': bridge.read_text(self.host, self.owner, reply, self.sleep), 'intent': intent, 'drafted': None}
        if reply.get('tried') or reply.get('class') == 'moved':
            # A `delvetalk try` (`world-try`, the write off) or an act whose `if:` moved: nothing journaled, and its receipt is
            # no receipt (docs/POSTING.md section 2). It is said as the bridge says it to a post; nothing is drafted. The log
            # keeps the text: asking `moved` again could act, if nothing has moved since.
            text = bridge.preview_text(reply) if reply.get('tried') else reply['line'] + '\n'
            outcome = 'preview' if reply.get('tried') else 'moved'
            self.log('speak', None, intent=intent, spell=spell, height=None, slug=None, outcome=outcome, object=card, text=text)
            return {'card': card, 'object': reply.get('object') or card, 'outcome': outcome, 'height': None, 'slug': None,
                    'line': text.split('\n', 1)[0], 'text': text, 'intent': intent, 'drafted': None}
        receipt = reply.get('receipt')
        if not receipt:
            raise HandError(f"{card}: {reply.get('message') or reply.get('status')}")
        tag = (receipt.get('outcome') or {}).get('tag')
        made = [c['object'] for c in (receipt.get('outcome') or {}).get('creates') or [] if c.get('object')]
        obj = (made or [reply.get('object') or card])[0]
        text = bridge.draft_public(reply, self.st.config.origin, reply.get('object'))
        if tag == 'admitted' and reply.get('offers') and reply.get('inPublic') is not False:
            text = bridge.with_paint(self.host, bridge.offered_object(reply, card), text, self.sleep)
        text = bridge.with_telling(self.host, self.owner, reply, reply.get('object') or card, text, self.sleep)[0]
        came = {'card': card, 'object': obj, 'outcome': outcome_of(receipt), 'height': receipt.get('height'), 'slug': receipt.get('slug'),
                'line': bridge.receipt_line(receipt, None, reply.get('object')).strip(), 'text': text}
        name = None
        if tag == 'admitted' and text:
            name = f"{receipt.get('height')}-speak-{uri_hash(intent)}"
            path = self.st.outbox / f'{name}.json'
            if not path.exists():
                self.st.write(path, {'speak': {'spell': spell, 'intent': intent}, **where, 'principal': self.owner, 'principalVerified': True,
                                     'object': obj, 'slot': None, 'receipt': receipt, 'text': quoted(spell) + '\n\n' + text, 'posted': False, 'hand': True})
        self.log('speak', name, intent=intent, spell=spell, height=receipt.get('height'), slug=receipt.get('slug'), outcome=came['outcome'], object=obj)
        return {**came, 'intent': intent, 'drafted': name}

    def welcome(self, spell=None, topic=None, reply_to=None, intent=None):
        """The welcome, one move done (docs/POSTING.md build 8): the hand casts a move any resident can make
        (`WELCOME`, a bell of one's own), and the draft is that move as the town would answer it (the spell quoted,
        the paint and the card it offered, its real receipt), then the same move offered back: reply under it with
        the spell in your own words, or `delvetalk try` it first. Never posted by itself. -> what `cast` answers."""
        spell = (spell or WELCOME).strip()
        came = self.cast(spell, topic, reply_to, intent or 'hand:welcome:' + hashlib.sha256(spell.encode()).hexdigest()[:12])
        if not came.get('drafted'):
            raise HandError(f"the welcome's move was not admitted: {came.get('line')}")
        path, d = self.draft(came['drafted'])
        if not d.get('welcome'):
            self.st.write(path, dict(d, welcome=True, text=welcome_text(spell, d['text'])))
        return {**came, 'text': self.draft(came['drafted'])[1]['text']}

    def receive(self, card, spell, intent):
        return self.host.send({'op': 'world-turn', 'principal': self.owner, 'object': card, 'method': 'receive', 'identity': intent,
                               'argument': typed({'text': spell, 'post': intent})})

    def ask(self, words, card=None, intent=None, wait=WAIT_MAX):
        """Words that are no spell, to `card` (default the commonplace) as a resident's direct prose, the turn the play page
        sends (`receive` with `reach: direct`), followed through every turn it handed on to hob's answer, waiting while hob
        reads up to `wait` seconds (`came` follows it on from there). -> the receipt and what came back, as the town would
        hear it; nothing is drafted, the hand's log keeps it."""
        card, intent = (card or '').strip() or 'commonplace', (intent or '').strip() or f'hand:ask:{int(self.clock() * 1000)}'
        reply = self.host.send({'op': 'world-turn', 'principal': self.owner, 'object': card, 'method': 'receive', 'identity': intent, 'reach': 'direct',
                                'argument': typed({'text': words, 'post': ''})})
        receipt = reply.get('receipt')
        if not receipt:
            raise HandError(f"{card}: {reply.get('message') or reply.get('status')}")
        said, waiting = trace(self.host, self.owner, intent, reply, self.sleep, wait)
        came = {'card': card, 'object': reply.get('object') or card, 'outcome': outcome_of(receipt), 'height': receipt.get('height'), 'slug': receipt.get('slug'),
                'line': bridge.receipt_line(receipt, None, reply.get('object') or card).strip(), 'text': '\n'.join(t.rstrip('\n') for t in said), 'drafted': None,
                'intent': intent, 'waiting': waiting}
        self.log('ask', None, intent=intent, words=words, card=card, height=receipt.get('height'), slug=receipt.get('slug'), outcome=came['outcome'],
                 object=card)
        return came

    def came(self, intent):
        """What came back to the turn the hand made under `intent`, as it stands now: a spell's drafted post, or the words'
        answers followed through every turn they were handed on to (one look; `waiting` while hob still reads). None for an
        intent the hand's log does not hold."""
        line = next((l for l in reversed(self.tail(10 ** 6)) if l.get('intent') == intent and l.get('world') == self.st.world), None)
        if line is None:
            return None
        text, waiting = self.draft(line['draft'])[1]['text'] if line.get('draft') else '', False
        if line.get('outcome') in ('preview', 'moved'):  # a try or a moved `if:`: the text the host answered then
            text = line.get('text') or ''
        if line.get('outcome') == 'usage':  # asked again: a `?` journals nothing, so the log keeps the spell, not the answer
            text = bridge.draft_text(self.receive(line['object'], line['spell'], intent))
        if line['what'] == 'ask':
            rc = self.host.send({'op': 'world-receipt', 'principal': self.owner, 'identity': intent}).get('receipt') or {}
            said, waiting = trace(self.host, self.owner, intent, {'status': outcome_of(rc), 'receipt': rc}, wait=0) if rc else ([], True)
            text = '\n'.join(t.rstrip('\n') for t in said)
        # The card the act left, painted from its strokes, above the exact text (a spell's draft carries it too, when it
        # fits one post: bridge.with_paint).
        paint = painted(self.host, self.owner, line['object'], self.sleep) if line.get('outcome') == 'admitted' and line.get('object') else {}
        return {**line, 'text': text, 'waiting': waiting, 'paint': paint.get('text'), 'fellBack': fell_back(paint) if paint else None}

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

    def morning(self, day=None, topic=None, reply_to=None):
        """The morning card (docs/OVERHAUL.md section 4 (c)): the town's day painted from its strokes, what wants a hand
        exact beneath, drafted once a day for Post; never posted by itself. Unpainted (no worker, refused, past the host's
        patience), the chronicle's exact lines stand in the paint's place."""
        chronicled = self.host.send({'op': 'world-chronicle', 'principal': self.owner, **({'day': int(day)} if day is not None else {})})
        if chronicled.get('status') != 'chronicled':
            raise HandError(f"the chronicle: {chronicled.get('message') or chronicled.get('status')}")
        day = chronicled['day']
        for i, _, d in self.drafts():
            if (d.get('speak') or {}).get('morning') == day:
                raise HandError(f'the morning card of day {day} is drafted already: {i}')
        paint = painted(self.host, self.owner, None, self.sleep, day=day, morning=True)
        why = fell_back(paint)
        rows = self.host.send({'op': 'world-wanting', 'principal': self.owner, 'limit': 8, 'oldest': True}).get('rows') or []
        wants = ''.join(f"{r['object']}: {r.get('reading') or r['name']}\n  {r['asks']}\n" for r in rows)
        text = (paint.get('text') or '\n'.join(chronicled['lines'])) + ('\n\nWhat wants a hand, oldest first:\n' + wants if wants else '')
        where, name = self.where(topic, reply_to), f'{int(self.clock())}-morning-{day}'
        self.st.write(self.st.outbox / f'{name}.json', {'speak': {'morning': day}, **where, 'principal': self.owner, 'principalVerified': True,
                                                        'object': None, 'slot': None, 'text': text.rstrip('\n'), 'posted': False, 'hand': True})
        self.log('morning', name, day=day, painted=why is None, fellBack=why)
        return {'drafted': name, 'day': day, 'painted': why is None, 'fellBack': why, 'text': text.rstrip('\n')}

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

    # ---- the worlds: every one serve holds, the scratch worlds with their owners

    def worlds(self):
        """Every world `serve` holds (height, objects, clock, replay edition, the snapshot it reopened from, its bridge, its
        outbox waiting) and every scratch world (its owner, its size, the home clock of its last turn, when it expires)."""
        info = self.host.send({'op': 'serve-status'})
        rows = info.get('worlds') or []
        home = next((w for w in rows if w.get('name') == self.st.world), rows[0] if rows else {})
        out = []
        for w in rows:
            st = State(self.st.root, w['name'], self.st.config)
            row = st.bridge()
            out.append({**{k: w.get(k) for k in ('name', 'height', 'objects', 'clock', 'replay')}, 'resumed': (w.get('snapshot') or {}).get('resumed'),
                        'bridge': row['transport'] + (f" #{row.get('channel')}" + (f" > {row['topic']}" if row.get('topic') else '') if row['transport'] == 'zulip' else f" {row.get('realm') or 'delve.town'}"),
                        'waiting': len(st.unposted())})
        scratches = []
        for s in info.get('scratches') or []:
            name = s['world'].removeprefix('scratch/')
            seen = self.host.send({'op': 'world-status', 'world': s['world'], 'principal': s['principal']})  # a request naming its world keeps it
            scratches.append({'world': s['world'], 'name': name, 'principal': s['principal'], 'owner': self.handle_of(s['principal']),
                              'height': seen.get('height'), 'objects': seen.get('objects'), 'lastTurn': s['lastTurn'], 'expires': s['expires'],
                              'idle': (home.get('clock') or 0) - s['lastTurn'], 'left': s['expires'] - (home.get('clock') or 0)})
        return {'pid': info.get('pid'), 'replay': info.get('replay'), 'library': info.get('library'), 'home': home.get('name'),
                'clock': home.get('clock'), 'worlds': out, 'scratches': scratches}

    def guest_action(self, verb, form):
        """The worlds page's guest form (`guest` invite or revoke) -> the note the page shows (with a new code, once)."""
        try:
            if verb == 'invite':
                days = form.get('expires', '').strip()
                got = self.invite_guest(form.get('name', ''), form.get('note', ''), float(days) if days else INVITE_DAYS)
                return (f"invited {got['name'] or 'whoever arrives (open)'}{' as ' + got['principal'] if got['principal'] else ''}; its code, shown this once: {got['code']} "
                        f"(accept by {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(got['expires']))})")
            got = self.revoke_guest(form.get('name', ''))
            return f"revoked {got['name']}: {counted(got['credentials'], 'credential')} ended"
        except (HandError, ValueError) as err:
            return str(err)

    def worlds_page(self, query, said=None):
        q, w = lambda t: e(str(t)), self.worlds()
        when = lambda t: time.strftime('%Y-%m-%d %H:%M', time.gmtime(t)) if t else 'never'
        guests = ''.join(H['guest'].format(fate='admitted' if g['state'] == 'accepted' else 'suspended' if g['state'] == 'open' else 'refused',
                                           state=q(g['state']), name=q(g['name']), principal=q(g['principal'] or 'name to be registered'), note=q(g['note'] or 'no note'),
                                           taken=q(f"taken by {g['name']} on {when(g['accepted'])}" if g['state'] == 'accepted' or g.get('accepted') else 'not taken yet'),
                                           created=q(when(g['created'])), expires=q(when(g['expires'])), used=q(when(g['used'])),
                                           revoke=H['guest_revoke'].format(name=q(g['id'] if g['name'] == '(open)' else g['name'])) if g['state'] != 'revoked' else '')
                         for g in self.guests()) or '<li class="quiet">— nobody is invited —</li>'
        rows = ''.join(H['world'].format(name=q(r['name']), height=q(r['height']), objects=q(counted(r['objects'] or 0, 'card')), clock=q(r['clock']), bridge=q(r['bridge']),
                                         waiting=q(r['waiting']), replay=q(r['replay']), resumed=q(f", reopened at entry {r['resumed']}" if r['resumed'] else ''))
                       for r in w['worlds']) or '<li class="quiet">— serve holds no world —</li>'
        scratches = ''.join(H['scratch'].format(world=q(r['world']), owner=q(r['owner']), principal=q(r['principal']), name=q(r['name']),
                                                height=q(r['height']), objects=q(counted(r['objects'] or 0, 'card')), idle=q(r['idle']), left=q(r['left']),
                                                expires=q(r['expires']), base=f"/hand/{q(w['home'])}")
                            for r in w['scratches']) or '<li class="quiet">— no scratch world is open —</li>'
        codes = self.codes([counted(len(w['worlds']), 'world'), counted(len(w['scratches']), 'scratch world'), f"host pid {w['pid']}", f"replay edition {w['replay']}",
                            f"{w['home']} clock {w['clock']}"])
        return shell('the worlds', None, H['worlds'].format(note=self.note({'note': said} if said else query), codes=codes, worlds=rows, scratches=scratches,
                                                            home=q(w['home']), guests=guests))

    # ---- guests: agents with no account here, let in by an invitation (transport/identity.py)

    @property
    def identity(self):
        """The front's claim store, shared by every world; the hand only names guests in it, it reads no posts."""
        if self._identity is None:
            self._identity = Identity(self.st, None, self.clock)
        return self._identity

    def invite_guest(self, name=None, note='', days=INVITE_DAYS):
        """A one-time code, shown this once: for the guest `guest:<origin host>:<name>` (handle `name`) when named, else open,
        the guest registering its own name when it accepts."""
        try:
            got = self.identity.invite((name or '').strip() or None, (note or '').strip(), days)
        except IdentityError as err:
            raise HandError(f'invite {name or "(open)"}: {err.code}') from None
        self.log('invite-guest', None, name=got['name'] or '(open)', id=got['id'], principal=got['principal'], note=got['note'], expires=int(got['expires']))
        return got

    def invite_open(self, count, note='', days=INVITE_DAYS):
        """`count` open codes at once."""
        if not 1 <= count <= 100:
            raise HandError('invite --count: between 1 and 100')
        return [self.invite_guest(None, note, days) for _ in range(count)]

    def guests(self):
        return self.identity.invitations()

    def revoke_guest(self, name):
        try:
            got = self.identity.revoke_invitation((name or '').strip())
        except IdentityError as err:
            raise HandError(f'revoke-invite {name}: {err.code}') from None
        self.log('revoke-invite', None, name=got['name'], principal=got['principal'], credentials=got['credentials'])
        return got

    # ---- watching: the journal and the outbox together, newest first

    def handle_of(self, principal):
        """A principal as the town names it: its avatar's handle, read as the opener and kept once found."""
        if not principal or principal == CLOCK:
            return 'the clock' if principal else '—'
        return handles(self.host, self.owner, [principal], self.names).get(principal, principal)

    def entries(self, object=None, limit=30):
        """The newest `limit` entries as the opener reads them: the world's journal, or one object's `world-history`."""
        if not object:
            return root.entries(self.st, limit=limit)
        return self.host.send({'op': 'world-history', 'principal': self.owner, 'object': object, 'reverse': True, 'limit': min(limit, history_limit(self.host))}).get('entries') or []

    def drafted(self):
        """The outbox as the watch joins it to the journal: the spells the hand cast, by intent; the drafts, by the height of
        the entry they answer; the hand's own that wait on no entry (an invitation, a reply by hand)."""
        spells, by_height, loose = {}, {}, []
        for i, _, d in self.drafts():
            speak = d.get('speak') or {}
            if speak.get('spell'):
                spells[speak['intent']] = speak['spell']
            height = next((x['height'] for x in (d.get('receipt'), d.get('offer'), d.get('publication')) if x and x.get('height')), None)
            row = {'id': i, 'state': self.summary(i, d)['state'], 'first': first_line(d['text'])}
            if height:
                by_height.setdefault(height, []).append(row)
            elif row['state'] == 'waiting' and d['text']:
                loose.append(dict(row, who='the hand', turn=f"invitation T+{speak['invitation']}" if 'invitation' in speak else f"morning card, day {speak['morning']}" if 'morning' in speak else 'by hand',
                                  object=d.get('object'), outcome='drafted', tag='', height=None, slug=None, drafts=[]))
        return spells, by_height, loose[::-1]

    def watch(self, object=None, limit=30):
        """The journal (or one object's history) and the outbox, newest first: each entry with its principal's handle, the
        turn as it was typed, the first line of the card it offered, its receipt's name, the object it reached and the
        drafts it made; the hand's own drafts that wait on no entry above them."""
        spells, by_height, loose = self.drafted()
        return loose + [{k: v for k, v in r.items() if k != 'raw'} for r in self.rows(self.entries(object, limit), spells, by_height)]

    def rows(self, entries, spells=None, by_height=None):
        """Journal entries as the watch shows them (`watched`), each keeping its raw entry for root."""
        if spells is None:
            spells, by_height, _ = self.drafted()
        seen = self.observed()
        return [dict(self.watched(x, seen, spells, by_height), raw=x) for x in entries]

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
        elif x.get('root') is True:
            turn = f"root {out.get('kind')} {out.get('object') or ''}: {x.get('reason')}"
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
        if byhand.mode(self.st) == 'by hand':
            raise HandError(f'no credential file ({self.st.config.credentials}): post {draft_id} from your own client, then give the hand its link')
        text = d['text'] if text is None else text.replace('\r\n', '\n')
        try:
            result = self.poster(path, self.st, self.host, text=text, **({'object': object} if object else {}))
        except (Failure, OSError, KeyError, ValueError) as err:
            code = getattr(err, 'code', type(err).__name__)
            self.log('post-failed', draft_id, error=code)
            raise HandError(f'post failed: {code}') from None
        self.log('post', draft_id, uri=result.get('uri'), edited=text != d['text'])
        return result

    def posted(self, draft_id, links):
        """`hand posted DRAFT --url LINK`: the owner posted the draft (or its next parts, in order) from his own client;
        each link is read back, checked and recorded with the host as the automatic path records a post
        (transport/byhand.py), or refused by name. -> what was recorded."""
        path, d = self.draft(draft_id)
        if byhand.mode(self.st) == 'zulip':
            raise HandError("a Zulip world's drafts are posted by its bot")
        links = links.split() if isinstance(links, str) else [l for l in links or [] if l.strip()]
        if not links:
            raise HandError('posted: paste the link of the post you made')
        got = []
        for link in links:
            try:
                d, entry = byhand.record(self.st, self.host, self.reader, path, d, link, self.clock)
            except Failure as err:
                self.log('posted-refused', draft_id, link=link, error=err.code)
                raise HandError(f'{err.code}: {err.detail}' + (f' (recorded before it: {", ".join(g["link"] for g in got)})' if got else '')) from None
            self.log('posted', draft_id, uri=entry['uri'], part=entry['part'], edited=bool(entry.get('edited')), recorded=(entry['recorded'] or {}).get('status'))
            got.append(entry)
        thread = bool(d.get('sentParts'))
        said = lambda e: (draft_id + (f" part {e['part']}" if thread else '') + f" is {e['link']}" +  # noqa: E731
                          (', your edit recorded' if e.get('edited') else '') +
                          (f" (not recorded with the host yet: {e['recorded'].get('message')}; the bridge asks again)" if (e['recorded'] or {}).get('status') == 'error' else ''))
        return {'recorded': [{k: e[k] for k in ('part', 'link', 'uri')} | ({'edited': True} if e.get('edited') else {}) for e in got],
                'note': '; '.join(said(e) for e in got) + ('' if d.get('posted') else f"; part {len(d['sentParts']) + 1} next")}

    def find_posts(self):
        """`hand match`: the posting account's newest posts (read only) against the waiting drafts; an exact text and
        parent is linked, and said; a near one is offered, never linked. -> {linked, offers}."""
        if byhand.mode(self.st) == 'zulip':
            raise HandError("a Zulip world's drafts are posted by its bot")
        try:
            found = byhand.find(self.st, self.host, self.reader, self.clock)
        except Failure as err:
            raise HandError(f'reading {self.st.config.poster}\'s posts: {err.code} {err.detail}'.strip()) from None
        for x in found['linked']:
            self.log('posted', x['draft'], uri=x['uri'], part=x['part'], found='exact text and parent')
        self.looked, self.found = self.clock(), found
        return found

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
            elif client is None and byhand.mode(self.st) == 'by hand':  # no credential here: the owner deletes it in his client
                try:
                    self.reader.record(uri)
                except Failure as err:
                    if 'RecordNotFound' not in err.detail:
                        raise
                else:
                    raise HandError(f'{byhand.web_link(uri)} is still on delve.town: delete it from your client, then unpost')
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
        if not world:  # the worlds page; its one form, a guest's, is answered on the page itself, so a new code is never in a URL
            if method == 'GET':
                return 200, self.worlds_page(query), []
            if (form or {}).get('guest') in ('invite', 'revoke'):
                return 200, self.worlds_page(query, self.guest_action(form['guest'], form)), []
            return 404, shell('not here', None, H['missing'].format(text='no form here')), []
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
                anchor = '#outbox' if back == '/?' else ''
                back = '/hand/?' if rest == 'root/expire' else base + back  # a scratch world is expired from the worlds
                more = {'came': done['intent']} if rest == 'speak' and done.get('intent') else {}
                return 303, '', [('Location', back + urllib.parse.urlencode({'note': note, **more}) + anchor)]
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
            acts = {'post': lambda: self.post(verb, form.get('text')), 'skip': lambda: self.skip(verb, form.get('reason', '')), 'hold': lambda: self.hold(verb),
                    'posted': lambda: {'note': self.posted(verb, form.get('link', ''))['note']}, 'edit': lambda: self.edit(verb, (form.get('text') or '').replace('\r\n', '\n'))}
            act = acts.get(form.get('do'))
        else:
            act = {'retry': lambda: self.retry(form.get('uri', '')), 'reply': lambda: self.reply(form.get('uri', ''), form.get('text', ''), form.get('object', '')),
                   'speak': lambda: self.spoke(self.cast(form.get('spell', ''), form.get('topic'), form.get('replyTo'), form.get('intent'), form.get('to'), wait=0)),
                   'invite': lambda: self.invite(form.get('minute', ''), form.get('topic'), form.get('replyTo')),
                   'match': lambda: {'note': self.matched(self.find_posts())},
                   'morning': lambda: {k: v for k, v in self.morning(None, form.get('topic'), form.get('replyTo')).items() if k in ('drafted', 'fellBack') and v}}.get(rest)
        return act and act()

    @staticmethod
    def matched(found):
        return '; '.join([f"linked {x['draft']} to {x['link']}: its text and parent are exactly the draft's" for x in found['linked']] +
                         [f"{len(found['offers'])} of your posts look like a draft: link each below if it is" if found['offers'] else '']) or \
            'none of your newest posts is a waiting draft\'s'

    @staticmethod
    def spoke(came):
        return {'line': came['line'], 'intent': came['intent'], 'note': 'drafted for Post' if came['drafted'] else
                'hob is still reading; watch for its answer' if came.get('waiting') else 'nothing drafted: words are asked, and only an admitted spell is posted'}

    def codes(self, items):
        return ''.join(H['code'].format(text=e(str(t))) for t in items)

    def note(self, query):
        return H['note'].format(text=e(query['note'])) if query.get('note') else ''

    def page(self, query):
        q, base = lambda t: e(str(t)), f'/hand/{self.st.world}'
        codes = self.codes(v for k, v in self.status().items() if k != 'posting')
        found = H['card'].format(text=q(json.dumps(self.search(query['slug']), indent=1, sort_keys=True)[:3000])) if query.get('slug') else ''
        how, looked = byhand.mode(self.st), ''
        if how != 'zulip' and self.st.config.hand_find and self.clock() - self.looked >= LOOK_EVERY:
            try:
                looked = self.matched(self.find_posts())
            except HandError as err:
                looked = str(err)
        offers = {}
        for o in self.found['offers']:
            offers.setdefault(o['draft'], []).append(o)
        outbox = ''.join(H['group'].format(
            source=q(g['source']), waiting=q(g['waiting']),
            original=H['card'].format(text=q(f'{g["original"]["handle"]}\n{g["original"]["text"]}')) if g['original'] else H['note'].format(text=q(g['post'])),
            drafts=''.join(H['draft'].format(base=base, fate=q(d['outcome']), stamp=q(pages.stamp(d['outcome'])), height=q('-' if d['height'] is None else d['height']),
                                             name=q(d['slug']), object=q(d['object']), id=q(d['id']), leave=self.leave(d, how, offers.get(d['id']) or []))
                           for d in g['drafts'])) for g in self.outbox()) or '<p class="quiet">— no drafts waiting —</p>'
        inbox = ''.join(H['row'].format(
            base=base, outcome=q(r['outcome'] or ''), kind=q(r['kind']), handle=q(r['handle']), text=q(r['text']), uri=q(r['uri']),
            stamp=q('' if r['skipped'] or not r['fate'] else pages.stamp(r['fate'])), retry=H['retry'].format(base=base, uri=q(r['uri'])) if r['skipped'] else '')
            for r in self.inbox()) or '<p class="quiet">— nothing observed —</p>'
        look = '' if how == 'zulip' else H['look'].format(base=base, looked=q(looked or (f"looked {self.waited(self.looked)} ago" if self.looked else
                                                                                          "reads your newest posts on delve.town, read only")))
        return shell(self.st.world, self.st.world, H['console'].format(base=base, world=q(self.st.world), note=self.note(query), codes=codes, found=found,
                                                                       mode=q(self.posting()), outbox=look + outbox, inbox=inbox))

    def leave(self, d, how, offers):
        """How a waiting draft leaves, on the page: by hand (each part to copy, where it goes, the link to give), and with
        a credential file Post as well, by hand folded beneath it; on Zulip, Post."""
        q, base = lambda t: e(str(t)), f'/hand/{self.st.world}'
        by_post = H['by_post'].format(base=base, id=q(d['id']), text=q(d['text']))
        if how == 'zulip' or not d.get('parts'):
            return by_post if d['state'] == 'waiting' else ''
        n, under = len(d['parts']), d['under']
        where = (f'Part {d["next"]} of {n}: reply' if n > 1 else 'Reply') + (
            f' under <a href="{q(under["link"])}" target="_blank" rel="noopener">{q("@" + under["handle"] + "’s post" if under["handle"] else under["link"])}</a>'
            if under else ' as a new post of your own, under nothing') + ', with the text below exactly' + ('; each next part under the one before.' if n > 1 else '.')
        parts = ''.join(H['part'].format(
            label=q(f'part {p["n"]} of {n}' if n > 1 else 'the post'), chars=q(f'{p["chars"]:,}'), clip=q(f'{post.CLIP:,}'), tid=q(f'{d["id"]}-{p["n"]}'),
            rows=min(18, p['text'].count('\n') + 2), text=q(p['text']),
            done=f' · posted: <a href="{q(p["posted"])}">{q(p["posted"])}</a>' if p['posted'] else '') for p in d['parts'])
        offered = ''.join(H['offer'].format(base=base, id=q(o['draft']), part=q(f' part {d["next"]}' if n > 1 else ''), link=q(o['link']), uri=q(o['uri']),
                                            like=q(f"{int(o['like'] * 100)}%"), why=q(f" ({o['why']})" if o.get('why') else ''), text=q(o['text'])) for o in offers)
        hand = H['by_hand'].format(base=base, id=q(d['id']), where=where, parts=parts, offers=offered, text=q(d['text']),
                                   ask=q(f'I posted part {d["next"]}: paste its link' if n > 1 else 'I posted it: paste the link'))
        return by_post + H['by_hand_folded'].format(byhand=hand) if how == 'automatic' else hand

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
            text=q(r['words'] + ''.join('\n    ' + s for s in r['spells'])), answered=q(r['answered']),
            draft='' if r['draft'] else H['invitation_draft'].format(base=base, minute=r['minute'], where=where)) for r in said['invitations']) \
            or '<li class="quiet">— the plan names no invitations —</li>'
        spoken, came = '', self.came(query['came']) if query.get('came') else None
        if came:  # what came back: the drafted post of a spell, hob's answer to words, followed while hob reads
            quiet = '— hob is reading; this page looks again every few seconds —' if came['waiting'] else '— quiet: nothing came back —'
            spoken = H['spoken'].format(fate=q(came.get('outcome')), stamp=q(pages.stamp(came.get('outcome') or '')), height=q(came.get('height')),
                                        slug=q(came.get('slug') or ''), object=q(came.get('object')),
                                        card=pages.painting(came.get('paint')) + (H['note'].format(text=q(came['fellBack'])) if came.get('fellBack') else '') +
                                        (H['card'].format(text=q(came['text'])) if came['text'] else '') +
                                        (H['note'].format(text=quiet) if came['waiting'] or not came['text'] else ''))
        return shell('speak', self.st.world, H['speak'].format(base=base, world=q(self.st.world), note=self.note(query), spoken=spoken,
                                                               morning=H['morning'].format(base=base, where=where),
                                                               intent=q(f'hand:speak:{int(self.clock() * 1000)}'), where=where,
                                                               plan=q(Path(self.plan['path']).name), seeds=seeds, invitations=invitations),
                     refresh=3 if came and came['waiting'] else 0)

    def links(self, r):
        """A row's foot: its receipt, its object in the root editor, the drafts it made."""
        q, base = lambda t: e(str(t)), f'/hand/{self.st.world}'
        return ' · '.join(([f'<a href="{base}/?{urllib.parse.urlencode({"slug": r["slug"]})}">receipt {q(r["slug"])}</a>'] if r['slug'] else []) +
                          ([f'<a href="{base}/root/?{urllib.parse.urlencode({"object": r["object"]})}">{q(r["object"])}</a>'] if r['object'] else []) +
                          [f'<a href="{base}/#outbox">draft {q(d["id"])}</a> {q(d["state"])}' for d in r['drafts']] +
                          ([f'<a href="{base}/#outbox">{q(r["id"])}</a> waiting for Post'] if r.get('id') else []))

    def watch_page(self, query, every=5):
        """The watch, refreshed every `every` seconds by the page itself (a meta refresh; `still` holds it)."""
        q, base, obj, still = lambda t: e(str(t)), f'/hand/{self.st.world}', query.get('object', '').strip(), query.get('still') == '1'
        here = base + '/watch' + ('?' + urllib.parse.urlencode({'object': obj}) if obj else '')
        rows = ''.join(H['watched'].format(
            tag=q(r['tag']), stamp=q(pages.stamp(r['outcome']) if r['tag'] else '◦ drafted'), height=q(f"entry {r['height']}" if r['height'] else 'outbox'),
            who=q(r['who']), turn=q(r['turn']), first=q(r['first']),
            links=self.links(r))
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
        hour = st.get('hour') or {}
        refused = hour.get('refused') or {}
        codes = self.codes((f"entry {st.get('height')}", f"{len(st.get('shadowed') or [])} shadowed", f"{counted(hour.get('turns', 0), 'turn')} this hour",
                            f"{sum(refused.values())} refused" + (f" ({', '.join(f'{k} {v}' for k, v in sorted(refused.items()))})" if refused else ''),
                            f"{counted(hour.get('interpretations', 0), 'reading')}, {counted(hour.get('attempts', 0), 'retry', 'retries')}"))
        editor = ''
        if query.get('object'):
            d = root.dump(self.host, self.owner, query['object'])
            fields = {'state': (d['view'].get('state')), 'law': (d['record'].get('record') or {}).get('law')}
            editor = H['card'].format(text=q(json.dumps(d, indent=1, sort_keys=True)[:6000])) + H['editor'].format(
                base=base, object=q(query['object']), shown=q(json.dumps(fields)),
                fields=''.join(f'<label>{k} <textarea name="{k}" rows="6">{q(json.dumps(v, indent=1))}</textarea></label>' for k, v in fields.items()))
        before = int(query['before']) if query.get('before', '').isdigit() else None
        rows = root.entries(self.st, limit=20, before=before)
        ignored = set(st.get('ignored') or [])
        entries = ''.join(H['entry'].format(
            base=base, tag=q(r['tag']), stamp=q(pages.stamp(r['outcome'])), height=q(r['height']), who=q(r['who']), turn=q(r['turn']), first=q(r['first']),
            links=self.links(r), raw=q(json.dumps(r['raw'], indent=1, sort_keys=True)), verb='unignore' if r['height'] in ignored else 'ignore')
            for r in self.rows(rows)) or '<li class="quiet">— nothing journaled —</li>'
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
        return root.entries(h.st, a.after, a.limit, a.object, a.principal)
    if a.rverb == 'edit':
        found = root.entries(h.st, a.height - 1, 1)
        if not found:
            raise HandError(f'no entry {a.height}')
        return {'saved': a.out, 'run': root.edit_command(found[0], a.height, h.st.journal, a.out)}
    return h.act('root', a.rverb, given(a))


def cli_invite(h, a):
    """`invite [NAME]`, or `invite --count N`: the codes, one per line unless `--json`."""
    if a.count is None:
        return h.invite_guest(a.name, a.note, a.expires)
    if a.name:
        raise HandError('invite: --count mints open codes; give no name')
    got = h.invite_open(a.count, a.note, a.expires)
    return got if a.json else [g['code'] for g in got]


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
    return h.cast(spell, a.topic, a.reply_to, a.intent, a.to)


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
            'outbox': [('--all', dict(action='store_true'))], 'draft': [('draft', {})],
            'edit': [('draft', {}), ('--text-file', {}), ('--stdin', dict(action='store_true'))],
            'post': [('draft', {}), ('--object', {})],
            'posted': [('draft', {}), ('--url', dict(action='append', required=True, metavar='LINK',
                                                     help="the post you made: https://delve.town/profile/<handle>/post/<rkey> or at://; a thread's parts, one --url each, in order"))],
            'match': [], 'skip': [('draft', {}), ('--reason', dict(required=True))], 'hold': [('draft', {})],
            'unpost': [('draft', {}), ('--reason', dict(required=True))], 'status': [], 'search': [('slug', {})], 'retry': [('uri', {})],
            'reply': [('uri', {}), ('--text-file', dict(required=True)), ('--object', dict(required=True))],
            'log': [('--tail', dict(type=int, default=20))], 'spend': [('--month', dict(metavar='YYYY-MM'))], 'serve': [],
            'modlog': [('--object', {}), ('--tail', dict(type=int, default=20))], 'find': [('text', {})],
            'speak': [('spell', dict(nargs='?', help='the spell; - or none reads it from stdin')), ('--spell-file', {}),
                      ('--seed', dict(type=int, metavar='N', help="the plan's seed N")), ('--invitation', dict(type=int, metavar='MINUTE', help="draft the plan's invitation at T+MINUTE")),
                      ('--topic', dict(help='a Zulip world: the topic (default its one topic, else welcome)')),
                      ('--reply-to', dict(metavar='AT_URI', help='a Delve world: the thread to answer')), ('--intent', dict(help='casting twice under one intent is one turn')),
                      ('--to', dict(metavar='CARD', help='words that are no spell go to this card, as direct prose (default commonplace)'))],
            'morning': [('--day', dict(type=int, help='the clock day (default today)')), ('--topic', {}), ('--reply-to', dict(metavar='AT_URI'))],
            'plan': [], 'watch': [('--object', dict(help="one object's history")), ('--limit', dict(type=int, default=30))], 'worlds': [],
            'invite': [('name', dict(nargs='?', help='the guest: [a-z][a-z0-9-]{0,31}, its handle on cards; without it the code is open and the guest registers its own name')),
                       ('--count', dict(type=int, metavar='N', help='mint N open codes at once, one per line')), ('--note', dict(default='', metavar='TEXT')),
                       ('--expires', dict(type=float, default=INVITE_DAYS, metavar='DAYS', help=f'the code may be accepted for DAYS (default {INVITE_DAYS})'))],
            'invites': [], 'revoke-invite': [('name', dict(help='the guest, or for an open code its id from `invites`'))],
            'welcome': [('--spell', dict(help='the move the welcome makes and offers (default WELCOME)')), ('--topic', {}), ('--reply-to', dict(metavar='AT_URI'))]}
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
        data = {'inbox': lambda: h.inbox(a.since, a.kind), 'outbox': lambda: h.outbox(a.all), 'draft': lambda: h.view(a.draft),
                'edit': lambda: h.edit(a.draft, sys.stdin.read() if a.stdin else read(a.text_file)), 'post': lambda: h.post(a.draft, object=a.object),
                'posted': lambda: h.posted(a.draft, a.url), 'match': h.find_posts,
                'skip': lambda: h.skip(a.draft, a.reason), 'hold': lambda: h.hold(a.draft), 'unpost': lambda: h.unpost(a.draft, a.reason),
                'status': h.status, 'search': lambda: h.search(a.slug), 'spend': lambda: h.spend(a.month),
                'retry': lambda: h.retry(a.uri), 'reply': lambda: h.reply(a.uri, read(a.text_file), a.object), 'log': lambda: h.tail(a.tail),
                'modlog': lambda: root.modlog(h.host, h.owner, a.object, a.tail), 'find': lambda: root.find(h.host, h.owner, a.text, h.observed().values()),
                'speak': lambda: cli_speak(h, a), 'morning': lambda: h.morning(a.day, a.topic, a.reply_to), 'plan': h.spoken, 'watch': lambda: h.watch(a.object, a.limit), 'worlds': h.worlds,
                'root': lambda: cli_root(h, a), 'invite': lambda: cli_invite(h, a), 'invites': h.guests,
                'revoke-invite': lambda: h.revoke_guest(a.name), 'welcome': lambda: h.welcome(a.spell, a.topic, a.reply_to), **{v: (lambda: h.act('mod', a.verb, given(a))) for v in [*root.POWERS, 'settings']}}[a.verb]()
    except (HandError, OSError) as err:
        print(f'hand: {err}', file=sys.stderr)
        return 1
    out.write((json.dumps(data, indent=1, sort_keys=True) if a.json else text_of(data)) + '\n')
    return 0
