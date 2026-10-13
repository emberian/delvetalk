"""Posting by hand (docs/POSTING.md "Posting by hand"): the owner posts a draft from his own client and gives the hand
its link; over a real `serve` after genesis and the bridge's fake Delve (tests/poster.py), the post read back from the
fixture PDS is checked and recorded with the host as the automatic path records one.

Evidence for docs/POSTING.md "Posting by hand" and docs/DEPLOY.md "Posting by hand" (layer: transport).

Refuted by: a post recorded by its link that a reply under does not reach the draft's card; a changed text recorded
as the draft's; another account's post, or one under another parent, recorded; a near post linked without a click; a
world with no credential file offering Post, or one with it not saying so; a part of a thread recorded out of order.

    python3 -W ignore -m tests.run test_byhand
"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.host import addressed
from tests.poster import BOT, Poster
from tests.test_transport import Script
from tests.town import Town
from transport import byhand, delve, hand, post
from transport.config import Config
from transport.state import State

TOKEN = 'membrane'
OWNER = 'ember.delve.town'


def pds(*posters):
    """The fixture PDS, read only: getRecord, listRecords (newest first) and resolveHandle over the posters' posts."""
    every = lambda: [p for q in posters for p in q.posts + q.bots]  # noqa: E731
    names = {OWNER: BOT, **{q.handle: q.did for q in posters}}

    def record(q):
        uri = f"at://{q['repo']}/{q['collection']}/{q['rkey']}"
        found = next((p for p in every() if p['uri'] == uri), None)
        return (200, {'uri': uri, 'cid': found['cid'], 'value': found['record']}) if found else (400, {'error': 'RecordNotFound'})

    def records(q):
        mine = [p for p in every() if p['uri'].startswith(f"at://{q['repo']}/")][::-1]
        return 200, {'records': [{'uri': p['uri'], 'cid': p['cid'], 'value': p['record']} for p in mine[:int(q.get('limit', 50))]]}
    return delve.Client(Script(**{'com.atproto.repo.getRecord': record, 'com.atproto.repo.listRecords': records,
                                  'com.atproto.identity.resolveHandle': lambda q: (200, {'did': names[q['handle']]}) if q['handle'] in names else (400, {'error': 'InvalidRequest'})}))


def link(uri):
    return f"https://delve.town/profile/{OWNER}/post/{uri.rsplit('/', 1)[1]}"


class ByHand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.n = 0

    def setUp(self):
        """A resident of their own (each a quarter of the hour), and a hand with no credential file: posting by hand."""
        type(self).n += 1
        n = self.n
        self.resident = Poster(f'{self.tmp.name}/r{n}', self.town.client, did=f'did:plc:resident{n:016d}', handle=f'r{n}.delve.town')
        self.st = State(self.resident.st.root, config=Config(origin='http://127.0.0.1:8765', opener=self.town.opener, credentials=f'{self.tmp.name}/r{n}/none.json'))
        self.hand = hand.Hand(self.st, self.town.client, TOKEN, reader=pds(self.resident), sleep=lambda _: None)
        self.hand.act('mod', 'settings', {'postQuota': '400', 'reading': 'the tests post more than an hour of the town'})

    def say(self, text, reply_to=None):
        [d] = self.resident.say(text, reply_to)
        return Path(d['path']).stem, d

    def by_owner(self, text, under):
        """The owner's post from his own client: a record in the posting account's repository (its key this test's own,
        the posting account being every test's)."""
        p = self.resident._post(text, under, BOT, OWNER)
        p['uri'] = p['uri'].replace('/p', f'/t{self.n}p', 1)
        p['record']['createdAt'] = datetime.now(timezone.utc).isoformat()
        return p['uri']

    def draft(self, name):
        return json.loads((self.st.outbox / f'{name}.json').read_text())

    def test_a_post_recorded_by_its_link_routes_replies_under_it_to_its_card(self):
        name, d = self.say('delvetalk bell/1 tend')
        self.assertEqual(byhand.mode(self.st), 'by hand')
        uri = self.by_owner(d['text'], d['replyTo'])
        got = self.hand.posted(name, link(uri))
        self.assertEqual(got['recorded'], [{'part': 1, 'link': link(uri).replace(OWNER, BOT), 'uri': uri}], got)
        after = self.draft(name)
        self.assertEqual((after['posted'], after['sent']['uri'], after['recorded']['status'], after['intent']), (True, uri, 'posted', f'draft-{name}'), after)
        self.assertEqual((addressed(self.town.client, uri) or {}).get('object'), d['object'])  # a reply under it reaches the card
        [answer] = self.resident.say('tend', uri)  # a resident's bare verb under it reaches the card
        self.assertEqual(answer['object'], d['object'], answer)
        self.assertEqual(self.hand.tail(1)[0]['what'], 'posted')
        with self.assertRaises(hand.HandError):
            self.hand.posted(name, link(uri))  # once

    def test_a_changed_text_is_recorded_as_the_owners_edit(self):
        name, d = self.say('delvetalk library read / page: laws')
        uri = self.by_owner(d['text'].rstrip('\n') + '\n\n(posted by hand)', d['replyTo'])
        got = self.hand.posted(name, f'at://{BOT}/town.delve.feed.post/{uri.rsplit("/", 1)[1]}')
        self.assertTrue(got['recorded'][0]['edited'], got)
        after = self.draft(name)
        self.assertEqual((after['original'], after['text'].endswith('(posted by hand)'), after['byHand'][0]['edited']), (d['text'], True, True))
        self.assertEqual((addressed(self.town.client, uri) or {}).get('object'), d['object'])
        same, d2 = self.say('delvetalk library read / page: spells')  # trailing space a client trims is no edit
        self.hand.posted(same, link(self.by_owner(d2['text'].strip() + '  ', d2['replyTo'])))
        self.assertNotIn('original', self.draft(same))

    def test_another_accounts_post_and_one_under_another_parent_are_refused_by_name(self):
        name, d = self.say('delvetalk bell/1 tend')
        theirs = self.resident._post(d['text'], d['replyTo'])['uri']  # the resident's own post, the same text
        with self.assertRaisesRegex(hand.HandError, '^wrong_author: '):
            self.hand.posted(name, f"https://delve.town/profile/{self.resident.handle}/post/{theirs.rsplit('/', 1)[1]}")
        elsewhere = self.by_owner(d['text'], None)  # a thread of its own, not under the resident's post
        with self.assertRaisesRegex(hand.HandError, '^wrong_parent: '):
            self.hand.posted(name, link(elsewhere))
        other, _ = self.say('delvetalk library read / page: laws')
        under_other = self.by_owner(d['text'], self.draft(other)['replyTo'])
        with self.assertRaisesRegex(hand.HandError, '^wrong_parent: '):
            self.hand.posted(name, link(under_other))
        with self.assertRaisesRegex(hand.HandError, '^not_a_post_link: '):
            self.hand.posted(name, 'https://example.com/post/1')
        self.assertFalse(self.draft(name)['posted'])
        self.assertIsNone(addressed(self.town.client, elsewhere))  # nothing told the host
        self.assertEqual([l['error'] for l in self.hand.tail(4)], ['wrong_author', 'wrong_parent', 'wrong_parent', 'not_a_post_link'])

    def test_the_hand_links_an_exact_post_itself_and_only_offers_a_near_one(self):
        exact, de = self.say('delvetalk bell/1 tend')
        near, dn = self.say('delvetalk library read / page: laws')
        one = self.by_owner(de['text'], de['replyTo'])
        two = self.by_owner(dn['text'].replace('hob', 'Hob', 1) + '\nwith a word of mine', dn['replyTo'])
        self.by_owner('something else entirely, of my own', dn['replyTo'])
        found = self.hand.find_posts()
        self.assertEqual([(x['draft'], x['uri']) for x in found['linked']], [(exact, one)], found)
        self.assertEqual([(o['draft'], o['uri']) for o in found['offers']], [(near, two)], found)
        self.assertTrue(self.draft(exact)['posted'])
        self.assertFalse(self.draft(near)['posted'])  # offered, never linked without the click
        self.assertEqual((addressed(self.town.client, one) or {}).get('object'), de['object'])
        self.assertIsNone(addressed(self.town.client, two))
        page = self.hand.handle('GET', '/hand/town/', f'dt_hand={TOKEN}')[1]
        self.assertIn(f'This looks like {near}', page)
        code, _, headers = self.hand.handle('POST', f'/hand/town/draft/{near}', f'dt_hand={TOKEN}', {'do': 'posted', 'link': two})
        self.assertEqual(code, 303)
        self.assertTrue(self.draft(near)['posted'])
        self.assertIn('your edit recorded', dict(headers)['Location'].replace('+', ' '))
        self.assertEqual(self.hand.find_posts(), {'linked': [], 'offers': []})  # every post is a draft's now

    def test_a_thread_is_recorded_part_by_part_in_order(self):
        name, d = self.say('delvetalk bell/1 tend')
        long = '\n\n'.join(f'Paragraph {k}: ' + 'the bell rings over the quiet garden ' * 9 for k in range(1, 9))
        mine = self.hand.reply(d['replyTo'], long, d['object'])['drafted']
        parts = post.parts(long)
        self.assertGreater(len(parts), 1)
        first = self.by_owner(parts[0], d['replyTo'])
        second_wrong = self.by_owner(parts[1], d['replyTo'])  # part 2 under the post, not under part 1
        self.hand.posted(mine, link(first))
        with self.assertRaisesRegex(hand.HandError, '^wrong_parent: '):
            self.hand.posted(mine, link(second_wrong))
        ready = next(x for g in self.hand.outbox() for x in g['drafts'] if x['id'] == mine)
        self.assertEqual((ready['next'], ready['under']['uri'], ready['parts'][0]['posted']), (2, first, byhand.web_link(first)))
        under, rest = first, []
        for text in parts[1:]:
            under = self.by_owner(text, under)
            rest.append(link(under))
        self.hand.posted(mine, '\n'.join(rest))
        after = self.draft(mine)
        self.assertEqual((after['posted'], len(after['sentParts']), after['recorded']), (True, len(parts), {'status': 'recorded', 'parts': len(parts)}))
        self.assertEqual([p['intent'] for p in after['byHand']], [f'draft-{mine}#{k}' for k in range(1, len(parts) + 1)])
        for p in after['sentParts']:
            self.assertEqual((addressed(self.town.client, p['uri']) or {}).get('object'), d['object'])

    def test_the_outbox_says_its_mode_orders_by_waiting_and_shows_each_part_to_copy(self):
        older, _ = self.say('delvetalk bell/1 tend')
        newer, _ = self.say('delvetalk library read / page: laws')
        rows = self.hand.outbox()
        ids = [x['id'] for g in rows for x in g['drafts']]
        self.assertLess(ids.index(older), ids.index(newer))
        self.assertIn(f'by @{self.resident.handle}', rows[0]['source'])
        page = self.hand.handle('GET', '/hand/town/', f'dt_hand={TOKEN}')[1]
        for text in ('posting by hand', 'I posted it: paste the link', 'data-copy=', f'of {post.CLIP:,} characters', 'Find my posts',
                     f'https://delve.town/profile/{self.resident.handle}/post/'):
            self.assertIn(text, page)
        self.assertNotIn('value="post">Post<', page)  # no credential, no Post
        with self.assertRaisesRegex(hand.HandError, 'no credential file'):
            self.hand.post(older)
        Path(self.st.config.credentials).write_text('{"identifier": "a", "password": "b"}')
        try:
            page = self.hand.handle('GET', '/hand/town/', f'dt_hand={TOKEN}')[1]
            self.assertIn('posting automatically', page)
            self.assertIn('value="post">Post<', page)
            self.assertIn('or post it by hand', page)
        finally:
            Path(self.st.config.credentials).unlink()


class Settle(unittest.TestCase):
    """A post made by hand in a full hour has left already: it is kept, and the bridge's next run reserves and records it."""

    def test_a_full_hour_is_recorded_when_the_host_has_room(self):
        class Host:
            def __init__(self):
                self.full, self.ops = True, []

            def send(self, req):
                self.ops.append(req['op'])
                if req['op'] == 'world-post-reserve':
                    return {'status': 'refused', 'next': 60} if self.full else {'status': 'reserved'}
                return {'status': 'posted'}
        with tempfile.TemporaryDirectory() as tmp:
            st, host = State(tmp), Host()
            d = {'replyTo': None, 'object': 'garden', 'text': 'a word', 'posted': False}
            one = {'uri': f'at://{BOT}/town.delve.feed.post/r1', 'cid': 'c'}
            got = post.settle(host, d, one, 'draft-1-x', 'a word', True)
            self.assertEqual(got['status'], 'error')
            st.write(st.outbox / '1-x.json', dict(d, posted=True, sent=one, byHand=[dict(one, part=1, intent='draft-1-x', text='a word', recorded=got)]))
            self.assertEqual(post.record_sent(st, host), [])
            host.full = False
            self.assertEqual(post.record_sent(st, host), ['1-x.json'])
            self.assertEqual(json.loads((st.outbox / '1-x.json').read_text())['byHand'][0]['recorded'], {'status': 'posted'})
            self.assertEqual(host.ops[-2:], ['world-post-reserve', 'world-posted'])

class Matching(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = State(self.tmp.name, config=Config(poster=BOT))
        self.path = self.st.outbox / '1-test.json'
        self.d = {'text': 'invitation', 'posted': False, 'replyTo': None, 'object': 'library', 'createdAt': '2026-10-12T10:00:00Z'}
        self.st.write(self.path, self.d)
        from tests.test_transport import Recorder
        self.host = Recorder()
        self.records = []
        outer = self
        class Reader:
            def get(self, *args, **kw): return {'records': outer.records}
            def record(self, uri): return next(r for r in outer.records if r['uri'] == uri)
        self.reader = Reader()

    def candidate(self, key, at):
        one = {'uri': f'at://{BOT}/{post.COLLECTION}/{key}', 'cid': key, 'value': {'text': 'invitation', 'createdAt': at}}
        self.records.append(one)
        return one

    def test_yesterdays_identical_post_is_not_linked_but_explicit_linking_still_works(self):
        old = self.candidate('yesterday', '2026-10-11T10:00:00Z')
        self.assertEqual(byhand.find(self.st, self.host, self.reader, lambda: 0)['linked'], [])
        d, _ = byhand.record(self.st, self.host, self.reader, self.path, old['uri'], lambda: 0)
        self.assertTrue(d['posted'])

    def test_todays_single_post_after_creation_is_linked(self):
        new = self.candidate('today', '2026-10-12T10:00:01Z')
        self.assertEqual([r['uri'] for r in byhand.find(self.st, self.host, self.reader, lambda: 0)['linked']], [new['uri']])

    def test_two_after_creation_candidates_link_nothing(self):
        self.candidate('one', '2026-10-12T10:00:01Z')
        self.candidate('two', '2026-10-12T10:00:02Z')
        self.assertEqual(byhand.find(self.st, self.host, self.reader, lambda: 0)['linked'], [])
        self.assertFalse(json.loads(self.path.read_text())['posted'])

    def test_matching_and_linking_the_same_draft_keep_one_confirmation_without_write_errors(self):
        from concurrent.futures import ThreadPoolExecutor
        new = self.candidate('one', '2026-10-12T10:00:01Z')
        def explicit():
            try:
                byhand.record(self.st, self.host, self.reader, self.path, new['uri'], lambda: 0)
            except delve.Failure as err:
                self.assertIn(err.code, ('already_posted', 'already_linked'))
        with ThreadPoolExecutor(2) as pool:
            jobs = [pool.submit(explicit), pool.submit(byhand.find, self.st, self.host, self.reader, lambda: 0)]
            for job in jobs: job.result()
        d = json.loads(self.path.read_text())
        self.assertEqual(len(d['sentParts']), 1)
        self.assertEqual(len(self.host.posted), 1)

    def test_a_manual_part_is_saved_before_a_crash_in_registration(self):
        new = self.candidate('one', '2026-10-12T10:00:01Z')
        from unittest.mock import patch
        with patch.object(post, 'settle', side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):
                byhand.record(self.st, self.host, self.reader, self.path, new['uri'], lambda: 0)
        self.assertEqual(json.loads(self.path.read_text())['sentParts'][0]['uri'], new['uri'])
        self.assertEqual(post.record_sent(self.st, self.host), [self.path.name])

    def test_the_newest_fifty_with_one_new_candidate_link_only_the_new_post(self):
        for k in range(49): self.candidate(f'old{k}', '2026-10-11T10:00:00Z')
        new = self.candidate('new', '2026-10-12T10:00:01Z')
        found = byhand.find(self.st, self.host, self.reader, lambda: 0)
        self.assertEqual([r['uri'] for r in found['linked']], [new['uri']])

    def test_a_candidate_at_creation_or_with_an_invalid_timestamp_is_not_linked(self):
        self.candidate('equal', self.d['createdAt'])
        self.candidate('invalid', 'not-a-date')
        self.assertEqual(byhand.find(self.st, self.host, self.reader, lambda: 0)['linked'], [])

    def test_find_enters_the_lock_only_through_record_and_leaves_no_outbox_debris(self):
        import contextlib
        from unittest.mock import patch
        self.candidate('one', '2026-10-12T10:00:01Z')
        original, entered = self.st.draft_lock, []
        @contextlib.contextmanager
        def lock(path):
            self.assertFalse(entered, 'find -> record reentered the lock')
            entered.append(path)
            try:
                with original(path): yield
            finally:
                entered.pop()
        with patch.object(self.st, 'draft_lock', lock):
            self.assertEqual(len(byhand.find(self.st, self.host, self.reader, lambda: 0)['linked']), 1)
        self.assertEqual(list(self.st.outbox.iterdir()), [self.path])
        self.assertEqual([p for p, _ in self.st.drafts()], [self.path])
