"""The town's own feed (transport/feed.py, docs/WEB.md "The town's own feed"): a guest with no delve.town account plays the whole town by
posting at /AGENTS.md/feed, and the bridge's replies land in the feed with no hand between, through the one pipeline a
delve.town post takes (observe, reach, turn, draft), the posting journey of tests/test_posting.py over the feed.

Evidence for docs/WEB.md "The town's own feed" (layer: transport).

Refuted by: a feed post the bridge does not answer as it answers the same text posted on delve.town, a town reply that
waits for the hand, a reply under the town's answer that reaches nothing, or a feed post that is not an observation.
"""
import http.client
import json
import re
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from tests.host import serve
from tests.keys import write_repo_key
from tests.test_scene import plain
from tests.town import Town
from transport import bridge, delve, feed, identity, post
from transport.config import Config
from transport.host import HostClient
from transport.http import Front
from transport.state import State


class Nobody:
    """delve.town, which the feed never asks."""
    def __call__(self, *a):
        raise AssertionError('the feed asked delve.town')


class Feed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.st = State(Path(cls.tmp.name) / 'front', config=Config(origin='http://127.0.0.1:8765',
                       repo_keys=str(Path(cls.tmp.name) / 'front' / 'repo')))
        write_repo_key(cls.st)
        cls.ident = identity.Identity(cls.st, delve.Client(Nobody()))
        cls.front = serve(Front(cls.st, HostClient(cls.town.process.sock), cls.ident, ('127.0.0.1', 0)))
        cls.addClassCleanup(cls.front.server_close)
        cls.addClassCleanup(cls.front.shutdown)

    def request(self, method, path, body=None, token=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.front.server_address[1], timeout=60)
        c.request(method, path, json.dumps(body) if isinstance(body, dict) else body,
                  {**({'Authorization': 'Bearer ' + token} if token else {}), **(headers or {})})
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def guest(self, name):
        code = self.ident.invite(None, 'the feed')['code']
        s, _, body = self.request('POST', '/AGENTS.md/accept', {'code': code, 'name': name})
        self.assertEqual(s, 200, body)
        return json.loads(body)['credential']

    def browser_post(self, path, data, cookie=''):
        status, headers, page = self.request('GET', '/enter', headers={'Accept': 'text/html', 'Cookie': cookie})
        self.assertEqual(status, 200)
        csrf = re.search(rb'name="csrf" value="([^"]+)"', page)[1].decode()
        cookies = dict(part.strip().split('=', 1) for part in cookie.split(';') if '=' in part)
        if headers.get('Set-Cookie'):
            name, value = headers['Set-Cookie'].split(';', 1)[0].split('=', 1)
            cookies[name] = value
        return self.request('POST', path, urllib.parse.urlencode({**data, 'csrf': csrf}),
                            headers={'Cookie': '; '.join(k + '=' + v for k, v in cookies.items()),
                                     'Content-Type': 'application/x-www-form-urlencoded', 'Origin': self.front.origin})

    def say(self, token, text, reply_to=None):
        """Post on the feed, run the bridge's step, -> (the post, the town's replies under it, in order)."""
        s, _, body = self.request('POST', '/AGENTS.md/feed', {'text': text, **({'reply_to': reply_to} if reply_to else {})}, token)
        self.assertEqual(s, 200, body)
        mine = json.loads(body)['post']
        bridge.run(self.st, self.town.client)
        s, _, body = self.request('GET', '/AGENTS.md/feed?thread=' + urllib.parse.quote(mine['root'] or mine['uri'], safe=''), token=token)
        [thread] = json.loads(body)['threads']
        replies = [p for p in thread['replies'] if p['town']]
        chain, under = [], mine['uri']
        while True:  # the town's answer, and its further parts each under the one before
            nxt = next((p for p in replies if p['replyTo'] == under), None)
            if nxt is None:
                return mine, chain
            chain.append(nxt)
            under = nxt['uri']

    def said(self, token, text, reply_to=None):
        mine, chain = self.say(token, text, reply_to)
        self.assertTrue(chain, f'no answer in the feed to {text!r}')
        self.assertTrue(all(len(p['text']) <= post.CLIP for p in chain))
        return '\n'.join(p['text'] for p in chain), chain

    def test_a_guest_who_only_uses_the_feed_learns_makes_grows_rules_and_sees_the_rule_fire(self):
        t = self.guest('wren')
        text = lambda s: self.said(t, s)[0]  # noqa: E731
        from transport.host import PUBLIC, typed
        height = self.town.send(op='world-status')['height']
        guide = self.town.client.send({'op': 'world-try', 'principal': PUBLIC, 'object': 'commonplace', 'method': 'receive',
                                       'identity': 'public-feed-guide', 'argument': typed({'text': 'delvetalk guide', 'post': ''})})
        self.assertTrue(guide.get('tried'), guide)
        self.assertIn(guide['status'], ('usage', 'admitted'), guide)
        self.assertEqual(self.town.send(op='world-status')['height'], height)
        self.assertTrue(text('delvetalk guide').startswith('\n'.join(post.parts(bridge.read_text(self.town.client, PUBLIC, guide)))))
        self.assertIn('KINDS', text('delvetalk commonplace since / entry: 0'))
        make = 'delvetalk kinds make / name: wick / of: record / form: light: text 1..80'
        preview = text('delvetalk try\n  ' + make)
        self.assertTrue(preview.startswith('preview, nothing done'), preview)
        self.assertEqual(self.town.client.send({'op': 'world-view', 'principal': 'anonymous', 'object': 'kind/wick'})['status'], 'unknown')
        guard = next(line for line in preview.splitlines() if line.startswith('if: '))
        self.assertEqual(preview.splitlines()[-1], guard)
        self.assertRegex(guard, r'/b\d+(?:, |$)')
        self.assertIn('admitted', text(guard + '\n' + make))
        thing, chain = self.said(t, 'delvetalk kind/wick make / light: moth glow')
        self.assertIn('admitted', thing)
        made = re.search(r'\b(wick/\d+)\b', thing)[1]
        grown = text(f'delvetalk {made} grow / name: trim / reading: the wick trimmed / takes: nothing\ndelvetalk {made} trim')
        self.assertEqual(grown.count(f'admitted {made}'), 2, grown)
        ruled = text(f'delvetalk {made} rule / name: lit / when: count(new.lines) >= 1 / then: delvetalk me note / text: the wick is lit')
        self.assertIn('admitted', ruled)
        # A reply under the town's answer reaches the card that answer was for, as a reply on delve.town does.
        fired, _ = self.said(t, f'delvetalk {made} trim', reply_to=chain[-1]['uri'])
        self.assertIn('lit', fired)
        self.assertIn('fired', fired)
        slug = re.search(r'receipt ([a-z]+-[a-z]+)', ruled)[1]
        self.assertIn(f'receipt {slug}', text(f'delvetalk receipt / of: {slug}'))
        # Every draft answering the feed was posted by the bridge, none waits for the hand, and each is recorded.
        waiting = [d for _, d in self.st.unposted() if feed.is_feed(d.get('replyTo'), self.st.config.origin)]
        self.assertEqual(waiting, [])
        # The feed's posts are the observer's observations, as delve.town's are.
        observed = {o['uri']: o for o in self.st.observations()}
        mine = [r for r in feed.Feed(self.st).rows() if not r['town']]
        self.assertTrue(mine and all(r['uri'] in observed for r in mine))
        self.assertEqual(observed[mine[0]['uri']]['author']['handle'], 'wren')

    def test_a_jar_made_over_http_and_on_the_feed_reads_its_scene_and_its_owner_rescenes_it(self):
        """Kestrel's jar (2026-10-14): `/ spween: <<END` on the spell line over HTTP receive, a ```spween fence under the
        spell line on the feed, and the owner's rescene, each the scene and never its source as prose."""
        from tests.test_spween import JAR
        t = self.guest('kestrel')
        passages = lambda room: [p['id'] for p in plain(self.town.send(op='world-view', principal='anonymous', object=room)['state'])['passages']]  # noqa: E731
        spell = 'delvetalk kind/room make / name: the jar of honey / spween: <<END\n' + JAR + 'END'
        s, _, body = self.request('POST', '/AGENTS.md/world/kind/room/receive', {'intent': 'jar-http', 'spell': spell}, t)
        self.assertEqual(s, 200, body)
        [room] = [c['name'] for c in json.loads(body)['_links']['created']]
        self.assertEqual(passages(room), ['sill'])
        fed, _ = self.said(t, 'delvetalk kind/room make / name: the jar again\n```spween\n' + JAR + '```')
        again = re.search(r'\b(room/\d+)\b', fed)[1]
        self.assertNotEqual(again, room)
        self.assertEqual(passages(again), ['sill'])
        rescened, _ = self.said(t, f'delvetalk {room} rescene\n```spween\n=== shelf\nThe jar moved to the shelf.\n* [Taste] -> shelf\n```')
        self.assertIn('admitted', rescened)
        self.assertEqual(passages(room), ['shelf'])

    def test_alices_book_of_a_diary_only_she_reads_is_never_published_in_the_feed(self):
        from deploy import genesis
        from deploy.seed import closure, modules_on_disk
        from transport.host import typed
        token = self.guest('alice')
        principal = self.ident.authenticate(token)['did']
        created = self.town.send(op='world-create', principal=principal, identity='feed-alice-diary', object='feed-alice-diary',
                                 modules=closure('Record', modules_on_disk()), entry='initial', law=genesis.RECORD_LAW,
                                 read={'principals': [principal]}, seed=genesis.rec(owner=genesis.lab(principal), maker=genesis.lab(principal), makerHandle=genesis.lab('alice')))
        self.assertEqual(created['status'], 'created', created)
        caller = self.town.send(op='world-turn', principal=principal, object='me', method='receive', identity='feed-read-diary',
                                argument=typed({'text': 'delvetalk me book', 'post': ''}))
        self.assertEqual(caller['status'], 'usage', caller)
        self.assertIn('feed-alice-diary', caller.get('whole') or caller['text'])
        _, chain = self.say(token, 'delvetalk me book')
        self.assertTrue(chain)
        text = '\n'.join(p['text'] for p in chain)
        self.assertNotIn('feed-alice-diary', text)
        self.assertIn("its reader's", text)

    def test_the_feed_page_shows_the_thread_its_receipt_and_takes_a_post_from_a_signed_in_browser(self):
        t = self.guest('robin')
        mine, chain = self.say(t, 'delvetalk library read / page: laws')
        self.assertTrue(chain)
        s, _, page = self.request('GET', '/feed', headers={'Accept': 'text/html'})
        page = page.decode()
        self.assertEqual(s, 200)
        self.assertIn('robin', page)
        self.assertRegex(page, r'class="post reply town"[^>]*>.*?the town.*?receipt [a-z]+-[a-z]+')
        s, _, page = self.request('GET', '/feed', headers={'Accept': 'text/html', 'Cookie': 'dt_credential=' + t})
        self.assertIn('<form class="say" method="post" action="/feed">', page.decode())
        s, headers, _ = self.browser_post('/feed', {'text': 'delvetalk bell/1 ?'}, 'dt_credential=' + t)
        self.assertEqual(s, 303)
        self.assertTrue(headers['Location'].startswith('/feed?posted='))
        s, _, page = self.request('GET', headers['Location'].split('#')[0], headers={'Accept': 'text/html', 'Cookie': 'dt_credential=' + t})
        self.assertNotIn('http-equiv="refresh"', page.decode())
        self.assertIn('<textarea', page.decode())
        import html
        answer = html.unescape(re.search(r'<iframe[^>]*src="([^"]+)"', page.decode())[1])
        self.assertIn(b'http-equiv="refresh"', self.request('GET', answer)[2])
        bridge.run(self.st, self.town.client)
        s, _, page = self.request('GET', answer)
        self.assertEqual(s, 200)
        self.assertIn(b' town', page)
        self.assertNotIn(b'http-equiv="refresh"', page)
        s, headers, _ = self.browser_post('/feed', {'text': 'hello'})
        self.assertEqual((s, headers['Location']), (303, '/enter'))  # nobody signed in: the door

    def test_a_guests_name_is_a_mention_and_a_top_level_post_is_said_to_the_town(self):
        a, b = self.guest('kit'), self.guest('moss')
        mine, chain = self.say(b, 'hello @kit, the porch is quiet')
        [obs] = [o for o in self.st.observations() if o['uri'] == mine['uri']]
        self.assertEqual([m['did'] for m in obs['mentions']], ['guest:127.0.0.1:kit'])
        self.assertEqual(obs['kind'], 'summon')
        s, _, body = self.request('POST', '/AGENTS.md/feed', {'text': 'under nothing', 'reply_to': 'at://did:web:127.0.0.1/town.delve.feed.post/nope'}, a)
        self.assertEqual(s, 400, body)



class FeedStore(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.st = State(tmp.name, config=Config(origin='https://town.example'))
        self.feed = feed.Feed(self.st)
        self.addCleanup(self.feed.close)
        self.author = {'did': 'guest:town.example:robin', 'handle': 'robin'}

    def test_25_replies_of_65536_ampersands_fit_the_rendered_page_and_json_budget(self):
        from transport import pages
        from transport.http import MAX_REPLY
        root = self.feed.post(self.author, '&' * 65536)
        for _ in range(25):
            self.feed.post(self.author, '&' * 65536, root['uri'])
        threads, _ = self.feed.threads()
        markup = pages.feed(threads, 'robin')
        self.assertLess(len(markup.encode()), MAX_REPLY)
        self.assertIn('earlier replies', markup)
        self.assertLess(sum(1 + len(rs) for _, rs, _ in threads), 26)
        raw = delve.canonical([{'post': pages.feed_post(h), 'replies': [pages.feed_post(r) for r in rs]}
                              for h, rs, _ in threads])
        self.assertLess(len(raw.encode()), MAX_REPLY)
        self.assertIn('&amp;', markup)

    def test_limit_one_returns_only_the_root_and_a_cursor_to_its_newest_reply(self):
        root = self.feed.post(self.author, 'root')
        newest = self.feed.post(self.author, 'reply', root['uri'])
        [(head, replies, earlier)], more = self.feed.threads(limit=1)
        self.assertEqual((head['uri'], replies, more), (root['uri'], [], None))
        [(head, replies, _)], _ = self.feed.threads(thread=root['uri'], replies_before=earlier, limit=2)
        self.assertEqual([r['uri'] for r in replies], [newest['uri']])

    def test_root_and_reply_keyset_cursors_lose_and_repeat_no_posts_with_equal_timestamps(self):
        roots = [self.feed.post(self.author, str(i), now=1000) for i in range(12)]
        replied = roots[0]
        replies = [self.feed.post(self.author, str(i), replied['uri'], now=1000) for i in range(35)]
        seen, cursor = [], None
        while True:
            threads, cursor = self.feed.threads(before=cursor, limit=1)
            seen.extend(h['uri'] for h, _, _ in threads)
            if cursor is None:
                break
        self.assertEqual(seen, [replied['uri']] + [r['uri'] for r in reversed(roots[1:])])
        seen, cursor = [], None
        while True:
            [(head, rs, cursor)], _ = self.feed.threads(thread=replied['uri'], replies_before=cursor, limit=4)
            seen.extend(r['uri'] for r in reversed(rs))
            if cursor is None:
                break
        self.assertEqual(seen, [r['uri'] for r in reversed(replies)])
        for bad in ('not-a-cursor', '-1', '9' * 65536):
            with self.subTest(cursor=bad), self.assertRaises(delve.Failure):
                self.feed.threads(before=bad)

    def test_65536_apostrophes_expand_to_six_bytes_each_without_exceeding_the_page_budget(self):
        from transport import pages
        from transport.http import MAX_REPLY
        root = self.feed.post(self.author, "'" * 65536)
        for _ in range(25):
            self.feed.post(self.author, "'" * 65536, root['uri'])
        threads, _ = self.feed.threads()
        markup = pages.feed(threads, 'robin')
        self.assertLess(len(markup.encode()), MAX_REPLY)
        self.assertEqual(markup.count('&#x27;'), 65536 * sum(1 + len(rs) for _, rs, _ in threads))
        self.assertIn('earlier replies', markup)

    def test_a_legacy_store_indexes_root_activity_once_and_new_replies_move_only_their_thread(self):
        import sqlite3
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = State(tmp.name, config=Config(origin='https://town.example'))
        st.home.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(st.home / 'feed.sqlite')
        db.executescript("CREATE TABLE feed(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT UNIQUE NOT NULL, cid TEXT NOT NULL, "
                         "did TEXT NOT NULL, handle TEXT NOT NULL, created TEXT NOT NULL, text TEXT NOT NULL, parent TEXT, root TEXT, "
                         "town INTEGER NOT NULL DEFAULT 0, answers TEXT, receipt TEXT, intent TEXT UNIQUE); "
                         "CREATE INDEX feed_root ON feed(root);")
        for seq, uri, root in ((1, 'first', None), (2, 'second', None), (3, 'reply', 'first')):
            db.execute('INSERT INTO feed(seq,uri,cid,did,handle,created,text,parent,root) VALUES(?,?,?,?,?,?,?,?,?)',
                       (seq, uri, 'cid', self.author['did'], 'robin', '1970-01-01T00:00:00.000Z', uri, root, root))
        db.commit()
        db.close()
        local = feed.Feed(st)
        self.addCleanup(local.close)
        self.assertEqual([h['uri'] for h, _, _ in local.threads()[0]], ['first', 'second'])
        local.post(self.author, 'new activity', 'second')
        self.assertEqual([h['uri'] for h, _, _ in local.threads()[0]], ['second', 'first'])
        reopened = feed.Feed(st)
        self.addCleanup(reopened.close)
        self.assertEqual([h['uri'] for h, _, _ in reopened.threads()[0]], ['second', 'first'])
        self.assertNotIn('feed_root', [r['name'] for r in reopened.db.execute('PRAGMA index_list(feed)')])

    def test_eight_concurrent_identical_keys_keep_exactly_one_durable_post(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        stores = [feed.Feed(self.st) for _ in range(8)]
        for store in stores:
            self.addCleanup(store.close)
        barrier = threading.Barrier(len(stores))
        def say(store):
            barrier.wait()
            return store.post(self.author, 'same payload', idempotency_key='same-key', now=1000)['uri']
        with ThreadPoolExecutor(max_workers=8) as pool:
            uris = list(pool.map(say, stores))
        self.assertEqual(len(set(uris)), 1)
        self.assertEqual(len(self.feed.rows()), 1)

    def test_a_maximum_post_retry_survives_reopening_and_a_changed_payload_is_refused_by_name(self):
        row = self.feed.post(self.author, '&' * 65536, idempotency_key='r' * 128, now=1000)
        other = feed.Feed(self.st)
        self.addCleanup(other.close)
        retry = other.post(self.author, '&' * 65536, idempotency_key='r' * 128, now=2000)
        self.assertEqual(retry['uri'], row['uri'])
        for text, parent in (('different', None), ('&' * 65536, row['uri'])):
            with self.assertRaises(delve.Failure) as caught:
                other.post(self.author, text, parent, idempotency_key='r' * 128)
            self.assertEqual(caught.exception.code, 'idempotency_conflict')
        self.assertEqual(len(other.rows()), 1)
        stranger = {**self.author, 'did': 'guest:town.example:wren'}
        self.assertNotEqual(other.post(stranger, '&' * 65536, idempotency_key='r' * 128)['uri'], row['uri'])
        for key in ('x' * 129, [], ''):
            with self.assertRaises(delve.Failure) as caught:
                other.post(self.author, 'hello', idempotency_key=key)
            self.assertEqual(caught.exception.code, 'invalid_idempotency_key')

    def test_concurrent_residents_at_59_posts_admit_only_one_more_and_retries_spend_no_quota(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        for i in range(feed.HOUR_POSTS - 1):
            self.feed.post(self.author, str(i), now=1000)
        stores = [feed.Feed(self.st) for _ in range(8)]
        for store in stores:
            self.addCleanup(store.close)
        barrier = threading.Barrier(len(stores))
        def say(pair):
            i, store = pair
            barrier.wait()
            try:
                return store.post(self.author, 'hello', idempotency_key=str(i), now=1000)
            except delve.Failure as err:
                return err.code
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(say, enumerate(stores)))
        accepted = [r for r in results if not isinstance(r, str)]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(results.count('feed_quota'), 7)
        kept = accepted[0]
        self.assertEqual(self.feed.post(self.author, 'hello', idempotency_key=kept['submission_key'], now=1000)['uri'], kept['uri'])
        self.assertEqual(len(self.feed.rows()), feed.HOUR_POSTS)


class DurablePosting(unittest.TestCase):
    def test_a_feed_crash_after_saving_a_part_is_repaired_without_reposting_it(self):
        from tests.test_transport import Recorder
        from unittest.mock import patch
        from transport import post
        from transport.state import State
        with tempfile.TemporaryDirectory() as tmp:
            st = State(tmp)
            local = feed.Feed(st)
            self.addCleanup(local.close)
            parent = local.post({'did': 'guest:local:test', 'handle': 'test'}, 'hello')
            path = st.outbox / '1-feed.json'
            st.write(path, {'text': 'long ' * 700, 'replyTo': parent['uri'], 'object': 'library', 'posted': False})
            host = Recorder()
            with patch.object(post, 'record_posted', side_effect=RuntimeError('crash')):
                with self.assertRaises(RuntimeError): feed.post_drafts(st, host, local)
            d = json.loads(path.read_text())
            first = d['sentParts'][0]['uri']
            self.assertEqual(post.record_sent(st, host), [path.name])
            feed.post_drafts(st, host, local)
            d = json.loads(path.read_text())
            self.assertEqual(d['sentParts'][0]['uri'], first)
            self.assertEqual(local.db.execute('SELECT COUNT(*) FROM feed WHERE town=1').fetchone()[0], len(post.parts(d['text'])))

    def test_a_completed_feed_thread_keeps_a_part_error_until_registration_is_repaired(self):
        from tests.test_transport import Recorder
        from transport import post
        from transport.state import State
        with tempfile.TemporaryDirectory() as tmp:
            st = State(tmp)
            local = feed.Feed(st)
            self.addCleanup(local.close)
            parent = local.post({'did': 'guest:local:test', 'handle': 'test'}, 'hello')
            path = st.outbox / '1-feed.json'
            st.write(path, {'text': 'long ' * 700, 'replyTo': parent['uri'], 'object': 'library', 'posted': False})
            host = Recorder(fail=1)
            uris = feed.post_drafts(st, host, local)
            d = json.loads(path.read_text())
            self.assertTrue(d['posted'])
            self.assertEqual(d['recorded']['status'], 'error')
            self.assertEqual(d['sentParts'][0]['recorded']['status'], 'error')
            self.assertEqual(post.record_sent(st, host), [path.name])
            self.assertEqual(local.db.execute('SELECT COUNT(*) FROM feed WHERE town=1').fetchone()[0], len(uris))


if __name__ == '__main__':
    unittest.main()
