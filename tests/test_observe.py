"""Observation validates transport bytes at the client boundary (FOUNDATION §7).

Refuted by a malformed timestamp being stored or a URI parsed differently by the observer and record client.
"""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from transport import delve, observe
from transport.config import Config
from transport.state import State


def post(uri='at://did:plc:aaaaaaaaaaaaaaaaaaaaaaaa/town.delve.feed.post/r1', created='2026-10-12T10:00:00Z', text='hello'):
    return {'uri': uri, 'cid': 'c', 'author': {'did': 'did:plc:' + 'a' * 24, 'handle': 'robin.delve.town'},
            'record': {'createdAt': created, 'text': text}}


class Observation(unittest.TestCase):
    def test_not_a_date_is_refused_even_without_a_since_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            st = State(directory, config=Config())
            ob = observe.Observer(st, None)
            self.addCleanup(ob.db.close)
            for stamp in ('not-a-date', '2026-02-30T10:00:00Z', '2026-10-12', '2026-10-12T10:00:00', None, 42):
                with self.subTest(stamp=stamp):
                    self.assertFalse(ob.store(post(created=stamp)))
                    with self.assertRaises(ValueError):
                        ob.before_start(stamp)
            self.assertEqual(st.observations(), [])
            with self.assertRaises(delve.Failure) as caught:
                observe.observation(post(created='not-a-date'))
            self.assertEqual(caught.exception.code, 'malformed_post')

    def test_the_maximum_post_body_and_latest_timestamp_are_observed(self):
        value = post(created='9999-12-31T23:59:59.999999Z', text='x' * observe.MAX_TEXT)
        got = observe.observation(value)
        self.assertEqual((got['createdAt'], got['text']), (value['record']['createdAt'], value['record']['text']))
        with self.assertRaises(delve.Failure) as caught:
            observe.observation(post(text='x' * (observe.MAX_TEXT + 1)))
        self.assertEqual(caught.exception.code, 'post_body_too_large')

    def test_the_observer_uses_the_client_parser_and_keeps_its_did_authority_policy(self):
        with mock.patch.object(delve, 'parse_at_uri', wraps=delve.parse_at_uri) as parser:
            self.assertEqual(observe.observation(post())['uri'], post()['uri'])
            parser.assert_called_once_with(post()['uri'])
        uri = 'at://robin.delve.town/town.delve.feed.post/r1'
        self.assertEqual(delve.parse_at_uri(uri).repo, 'robin.delve.town')
        with self.assertRaises(delve.Failure) as caught:
            observe.observation(post(uri=uri))
        self.assertEqual(caught.exception.code, 'malformed_post')


class ATUris(unittest.TestCase):
    def test_a_did_uri_and_a_handle_uri_supply_structured_record_parameters(self):
        for repo in ('did:plc:' + 'a' * 24, 'robin.delve.town', 'did:web:example.com%3A443'):
            with self.subTest(repo=repo):
                uri = f'at://{repo}/town.delve.feed.post/r~1'
                parsed = delve.parse_at_uri(uri)
                self.assertEqual((parsed.repo, parsed.collection, parsed.rkey), (repo, delve.POST, 'r~1'))
                client = delve.Client(lambda *args: self.fail('unexpected network call'))
                with mock.patch.object(client, 'get', return_value={}) as get:
                    client.record(uri)
                get.assert_called_once_with('com.atproto.repo.getRecord', repo=repo, collection=delve.POST, rkey='r~1')

    def test_maximum_record_parameters_parse_without_truncation(self):
        repo, collection, rkey = 'did:test:' + 'a' * (delve.MAX_PARAM - 9), 'a' * delve.MAX_PARAM, 'r' * 512
        uri = f'at://{repo}/{collection}/{rkey}'
        parsed = delve.parse_at_uri(uri)
        self.assertEqual(tuple(parsed), (repo, collection, rkey))
        self.assertEqual(observe.observation(post(uri=uri))['uri'], uri)

    def test_extra_paths_queries_fragments_spaces_dot_keys_and_oversized_parameters_are_not_records(self):
        base = post()['uri']
        for uri in (None, '', base + '/extra', base + '?q=1', base + '#f', base + '\n', base.replace('r1', '..'),
                    base.replace('r1', '.'), base.replace('r1', 'r' * 513),
                    f'at://did:test:{"a" * delve.MAX_PARAM}/town.delve.feed.post/r1',
                    f'at://did:test:a/{"a" * (delve.MAX_PARAM + 1)}/r1',
                    'at://bad authority/town.delve.feed.post/r1', 'at://did:test:a/town/delve/r1'):
            with self.subTest(uri=uri):
                with self.assertRaises(delve.Failure) as caught:
                    delve.parse_at_uri(uri)
                self.assertEqual(caught.exception.code, 'bad_at_uri')
                client = delve.Client(lambda *args: self.fail('unexpected network call'))
                with self.assertRaises(delve.Failure):
                    client.record(uri)


def uri_of(n):
    return f'at://did:plc:{"a" * 24}/town.delve.feed.post/r{n}'


def when(n, base=1_760_000_000):
    return datetime.fromtimestamp(base + n, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Keeping(unittest.TestCase):
    """What the store keeps once the bridge has answered (observe.py's docstring). Refuted by a post turned or asked twice,
    an ancestor `reach` needs lost, an author that stops resolving, or a store that still holds what it should not."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = State(Path(self.tmp.name) / 's', config=Config())
        self.ob = observe.Observer(self.st, None)
        self.addCleanup(self.ob.db.close)

    def put(self, n, text='hello', parent=None, did='a', handle=None):
        p = post(uri=uri_of(n), created=when(n), text=text)
        p['author'] = {'did': 'did:plc:' + did * 24, 'handle': handle or f'{did}.delve.town'}
        if parent is not None:
            p['record']['reply'] = {'parent': {'uri': uri_of(parent)}, 'root': {'uri': uri_of(parent)}}
        self.assertTrue(self.ob.store(p))
        return p

    def count(self, table):
        return self.ob.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def test_a_post_is_stored_once_with_no_copy_of_its_record(self):
        self.put(1, 'x' * 40_000)
        self.assertEqual(self.ob.db.execute('SELECT body FROM posts').fetchall(), [('',)])
        self.assertEqual(len(self.st.observations()[0]['text']), 40_000)
        self.assertLess(self.st.observed.stat().st_size, 120_000)  # one copy of the post, not two

    def test_a_dropped_post_leaves_its_hash_and_is_not_stored_again(self):
        self.put(1)
        (obs,) = self.st.observations()
        self.assertEqual(observe.prune(self.st, [obs], [], at=observe.instant(obs['createdAt']) + 2 * 3600), 1)
        self.assertEqual((self.count('observations'), self.count('posts'), self.count('gone')), (0, 0, 1))
        self.assertTrue(self.ob.seen(uri_of(1)))
        self.assertFalse(self.ob.store(post(uri=uri_of(1), created=when(1))))
        self.assertEqual(self.count('observations'), 0)

    def test_a_skipped_post_is_kept_for_the_grace_and_an_answered_one_for_the_week(self):
        for n in (1, 2):
            self.put(n)
        a, b = self.st.observations()
        t = observe.instant(a['createdAt'])
        self.assertEqual(observe.prune(self.st, [a], [b], at=t + observe.SKIP_MINUTES * 60 - 1), 0)
        self.assertEqual(observe.prune(self.st, [a], [b], at=t + observe.SKIP_MINUTES * 60 + 1), 1)
        self.assertEqual(observe.prune(self.st, [], [b], at=t + observe.RETAIN_DAYS * 86400 - 1), 0)
        self.assertEqual(observe.prune(self.st, [], [b], at=t + observe.RETAIN_DAYS * 86400 + 5), 1)
        self.assertEqual(self.st.observations(), [])

    def test_a_dropped_reply_leaves_a_stub_for_the_chain_and_an_old_stub_goes(self):
        self.put(1)
        self.put(2, parent=1)
        self.put(3)
        rows = self.st.observations()
        late = observe.instant(rows[1]['createdAt']) + 2 * 3600
        observe.prune(self.st, rows, [], at=late)
        self.assertEqual(observe.stubs(self.st), {uri_of(2): {'uri': uri_of(2), 'author': {'did': 'did:plc:' + 'a' * 24}, 'replyTo': uri_of(1)}})
        observe.prune(self.st, [], [], at=late + observe.CHAIN_DAYS * 86400 + 60)
        self.assertEqual(observe.stubs(self.st), {})
        self.assertEqual(self.count('gone'), 3)  # the hashes stay

    def test_every_author_stays_after_the_posts_are_dropped_in_first_seen_order_with_the_latest_handle(self):
        self.put(1, did='b')
        self.put(2, did='c')
        self.put(3, did='b', handle='renamed.delve.town')
        rows = self.st.observations()
        observe.prune(self.st, rows, [], at=observe.instant(rows[-1]['createdAt']) + 2 * 3600)
        self.assertEqual(self.st.observations(), [])
        self.assertEqual(observe.authors(self.st), [('did:plc:' + 'b' * 24, 'renamed.delve.town'), ('did:plc:' + 'c' * 24, 'c.delve.town')])

    def test_a_kept_uri_keeps_its_emptied_posts_row(self):
        self.put(1)
        (obs,) = self.st.observations()
        observe.prune(self.st, [obs], [], at=observe.instant(obs['createdAt']) + 2 * 3600, keep={uri_of(1)})
        self.assertEqual(self.ob.db.execute('SELECT uri, cid, hash, body FROM posts').fetchall(), [(uri_of(1), '', '', '')])

    def test_ages_are_measured_on_the_towns_timeline_and_a_future_post_ages_nothing(self):
        self.put(1)
        (obs,) = self.st.observations()
        future = dict(obs, uri=uri_of(2), createdAt='9999-12-31T23:59:59Z')
        t = observe.instant(obs['createdAt'])
        self.assertEqual(observe.timeline([obs], now=t + 10_000_000), t)
        self.assertEqual(observe.timeline([obs, future], now=t + 100), t + 100)
        self.assertEqual(observe.timeline([], now=5), 0)
        self.assertEqual(observe.timeline([dict(obs, createdAt='not-a-date')], now=5), 0)

    def test_an_answered_request_without_a_time_is_not_aged_out_and_a_skipped_one_is_dropped(self):
        self.put(1)
        (obs,) = self.st.observations()
        timeless = dict(obs, createdAt='')
        self.assertEqual(observe.prune(self.st, [], [timeless], at=10 ** 12), 0)
        self.assertEqual(observe.prune(self.st, [timeless], [], at=0), 1)

    def test_an_old_store_is_migrated_in_place_once_and_keeps_every_observation(self):
        """A copy shaped like the live one: thousands of rows, each post twice, no author table, version 0."""
        path = self.st.observed
        self.ob.db.close()
        path.unlink()
        for side in ('-wal', '-shm'):
            Path(str(path) + side).unlink(missing_ok=True)
        db = sqlite3.connect(path)
        db.executescript('CREATE TABLE posts(uri TEXT PRIMARY KEY, cid TEXT, hash TEXT, body TEXT);'
                         'CREATE TABLE observations(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT UNIQUE, json TEXT);')
        for n in range(3000):
            did = 'did:plc:' + f'{n % 97:024d}'
            obs = {'uri': uri_of(n), 'cid': 'c', 'author': {'did': did, 'handle': f'h{n % 97}-{n // 97 // 20}.delve.town'}, 'createdAt': when(n),
                   'text': 'word ' * 150, 'replyTo': None, 'root': None, 'mentions': [], 'tags': [], 'kind': 'post'}
            db.execute('INSERT INTO posts VALUES(?,?,?,?)', (obs['uri'], 'c', 'h', delve.canonical({'record': obs})))
            db.execute('INSERT INTO observations(uri,json) VALUES(?,?)', (obs['uri'], delve.canonical(obs)))
        db.commit()
        db.close()
        before = path.stat().st_size
        rows = [o['uri'] for o in self.st.observations()]
        ob = observe.Observer(self.st, None)
        self.addCleanup(ob.db.close)
        self.assertEqual([o['uri'] for o in self.st.observations()], rows)
        self.assertEqual(ob.db.execute("SELECT COUNT(*) FROM posts WHERE body!=''").fetchone()[0], 0)
        self.assertEqual(ob.db.execute('PRAGMA user_version').fetchone()[0], observe.VERSION)
        authors = dict(observe.authors(self.st))
        self.assertEqual(len(authors), 97)
        latest = {o['author']['did']: o['author']['handle'] for o in self.st.observations()}
        self.assertEqual(authors, latest)
        self.assertEqual([d for d, _ in observe.authors(self.st)][:2], ['did:plc:' + f'{i:024d}' for i in (0, 1)])
        self.assertLess(path.stat().st_size, before * 0.6)  # the second copy is gone and the file compacted
        once = (path.stat().st_size, ob.db.execute('SELECT COUNT(*) FROM authors').fetchone())
        again = observe.Observer(self.st, None)
        self.addCleanup(again.db.close)
        self.assertEqual((path.stat().st_size, again.db.execute('SELECT COUNT(*) FROM authors').fetchone()), once)  # idempotent
        self.assertTrue(again.store(post(uri=uri_of(5000), created=when(5000))))  # and still writes

    def test_the_store_the_bridge_reads_without_the_new_tables_gives_nothing_not_an_error(self):
        path = self.st.observed
        self.ob.db.close()
        path.unlink()
        for side in ('-wal', '-shm'):
            Path(str(path) + side).unlink(missing_ok=True)
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE observations(seq INTEGER PRIMARY KEY, uri TEXT UNIQUE, json TEXT)')
        db.commit()
        db.close()
        self.assertEqual((observe.authors(self.st), observe.stubs(self.st), observe.owed(self.st)), ([], {}, set()))
