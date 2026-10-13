"""The town mirrored as records on the PDS (docs/POSTING.md §1): a resident whose window is the PDS reads every card,
page and the index there with no post. Each record is the rendering the web's pages use (`transport.host.place`),
written only when it changed, and the did:web façade answers the same collections from the same functions.

Evidence for docs/POSTING.md §1 (layer: transport).

Refuted by: a card record whose text is not `world-card`'s for the public reader, a page missing from the mirror,
a head in the index, a checkpoint read after the host or written before the index, unchanged bytes written again,
a dry run writing, an unavailable front deleting a checkpoint, a feed post, or another façade rendering.
"""
import json
import tempfile
import unittest
import urllib.parse
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.town import Town
from tests.test_lexicons import record_problems
from tests.wire import label, record
from transport import mirror, post
from transport.atproto.cbor import block, from_json
from transport.delve import Failure, MAX_RESPONSE
from transport.repo import Repo
from transport.config import Config
from transport.state import State

NOWAIT = lambda _: None  # noqa: E731 (no model worker here: a paint is never waited for)


class Writer:
    """What the mirror would have written: {(collection, rkey): value}, deletes as None, in order."""

    def __init__(self):
        self.calls = []

    def __call__(self, collection, rkey, value):
        self.calls.append((collection, rkey, value))


class Front:
    """A signed front's two read responses, or a refusal; no socket is opened."""

    def __init__(self, rev='3aaaaaaaaaaa2', commit='bafyreia', height=7, error=None, events=None):
        self.rev, self.commit, self.height, self.error = rev, commit, height, error
        self.calls, self.events = [], events if events is not None else []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        self.events.append('front')
        assert method == 'GET' and body is None
        if isinstance(self.error, Exception):
            raise self.error
        if self.error:
            return 400, json.dumps({'error': self.error}).encode(), {}
        nsid = urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]
        if nsid == 'com.atproto.sync.getLatestCommit':
            value = {'cid': self.commit, 'rev': self.rev}
        else:
            assert nsid == 'com.atproto.repo.getRecord'
            value = {'value': {'height': self.height}}
        return 200, json.dumps(value).encode(), {}


class ReadHost:
    """An empty public projection at a journal height; records still include its manifest."""

    def __init__(self, events=None):
        self.events, self.closed, self.height = events if events is not None else [], False, 7

    def send(self, request):
        self.events.append('host')
        return {'world-status': {'height': self.height}, 'world-objects': {'status': 'listed', 'ids': []},
                'world-view': {'status': 'denied'}}[request['op']]

    def close(self):
        self.closed = True


class MirrorCheckpoint(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.st = State(Path(tmp.name) / 'state', world='garden', config=Config(origin='https://gsb.example/'))
        self.host, self.front = ReadHost(), Front()
        self.did = 'did:web:garden.gsb.example'
        self.key = 'online.fg-goose.gsb.checkpoint self'

    def step(self, writer=None, **kw):
        return mirror.run(self.st, self.host, writer, fetch=self.front, **kw)

    def test_two_different_signed_heads_leave_the_index_bytes_identical_and_headless(self):
        indexes = []
        for rev, commit in [('3aaaaaaaaaaa2', 'bafyreia'), ('3aaaaaaaaaaa3', 'bafyreib')]:
            self.front = Front(rev, commit)
            w = Writer()
            self.step(w)
            indexes.extend(v for c, _, v in w.calls if c == mirror.INDEX)
            self.st.mirror.unlink()  # each plan starts with no held records
        self.assertEqual(len(indexes), 2)
        self.assertEqual(mirror.canonical(indexes[0]), mirror.canonical(indexes[1]))
        self.assertEqual(block(from_json(indexes[0])), block(from_json(indexes[1])))
        self.assertFalse({'rev', 'commit', 'head', 'did'} & set(indexes[0]))

    def test_checkpoint_names_the_fronts_head_and_entry_height_after_the_index(self):
        events = []
        self.front, self.host = Front(events=events), ReadHost(events)
        w = Writer()
        result = self.step(w)
        expected = {'$type': 'online.fg-goose.gsb.checkpoint', 'did': self.did,
                    'rev': self.front.rev, 'commit': self.front.commit, 'height': self.front.height}
        self.assertEqual(w.calls, [(mirror.INDEX, 'self', mirror.records(self.host)[mirror.INDEX, 'self']),
                                   (expected['$type'], 'self', expected)])
        self.assertEqual(record_problems(expected), [])
        self.assertEqual(result['written'], [f'{mirror.INDEX} self', self.key])
        self.assertEqual(result['left'], 0)
        self.assertEqual(events[:3], ['front', 'front', 'host'])
        calls = [(m, urllib.parse.urlsplit(u), urllib.parse.parse_qs(urllib.parse.urlsplit(u).query), b)
                 for m, u, _, b in self.front.calls]
        self.assertEqual([(m, p.netloc, p.path, q, b) for m, p, q, b in calls], [
            ('GET', 'garden.gsb.example', '/xrpc/com.atproto.sync.getLatestCommit', {'did': [self.did]}, None),
            ('GET', 'garden.gsb.example', '/xrpc/com.atproto.repo.getRecord',
             {'repo': [self.did], 'collection': [mirror.NS + 'entry'], 'rkey': [self.front.rev]}, None)])

    def test_unsigned_or_unreachable_front_writes_records_without_a_checkpoint_and_says_why(self):
        for error, reason in [('RepoNotServed', 'RepoNotServed'), (Failure('network_error'), 'network_error'),
                              (OSError('front down'), 'front down')]:
            with self.subTest(error=error):
                self.front = Front(error=error)
                w = Writer()
                result = self.step(w)
                self.assertIn(reason, result['checkpoint'])
                self.assertEqual([c for c, _, _ in w.calls], [mirror.INDEX])
                self.assertFalse(any(c.endswith('.checkpoint') for c, _, _ in w.calls))
                self.st.mirror.unlink()

    def test_dry_run_lists_checkpoint_and_command_without_authorization_never_calls_writer(self):
        dry = self.step()
        self.assertTrue(dry['dry_run'])
        self.assertIn(self.key, dry['writes'])
        self.assertFalse(self.st.mirror.exists())
        args = SimpleNamespace(authorized=False, once=False, limit=200)
        out = StringIO()
        with patch.object(self.st, 'host', return_value=self.host), patch.object(post, 'record_writer') as writer:
            self.assertEqual(mirror.command(self.st, args, out, fetch=self.front), 2)
            writer.assert_not_called()
        self.assertIn(self.key, json.loads(out.getvalue())['writes'])
        self.assertTrue(self.host.closed)
        self.assertFalse(self.st.mirror.exists())
        self.assertTrue(all(m == 'GET' and b is None for m, _, _, b in self.front.calls))

    def test_unchanged_head_writes_nothing_and_moved_head_rewrites_only_checkpoint(self):
        self.step(Writer())
        w = Writer()
        self.assertEqual(self.step(w)['written'], [])
        self.assertEqual(w.calls, [])
        self.front = Front('3aaaaaaaaaaa3', 'bafyreib', 8)
        self.host.height = 8
        self.assertEqual(self.step(w)['written'], [self.key])
        self.assertEqual(w.calls, [('online.fg-goose.gsb.checkpoint', 'self', {
            '$type': 'online.fg-goose.gsb.checkpoint', 'did': self.did,
            'rev': '3aaaaaaaaaaa3', 'commit': 'bafyreib', 'height': 8})])

    def test_an_unavailable_front_keeps_the_held_checkpoint_out_of_deletes_and_ledger_unchanged(self):
        self.step(Writer())
        ledger = self.st.mirror.read_bytes()
        self.front = Front(error='RepoNotServed')
        self.assertNotIn(self.key, self.step()['deletes'])
        w = Writer()
        result = self.step(w)
        self.assertIn('RepoNotServed', result['checkpoint'])
        self.assertEqual(w.calls, [])
        self.assertEqual(self.st.mirror.read_bytes(), ledger)

    def test_changed_manifest_rewrites_the_same_checkpoint_after_all_records(self):
        self.step(Writer())
        with patch.object(mirror, 'library_pages', return_value=[{'name': 'new', 'title': 'new', 'body': 'page', 'place': 0}]):
            w = Writer()
            self.step(w)
        self.assertEqual([c for c, _, _ in w.calls], [mirror.PAGE, mirror.INDEX, 'online.fg-goose.gsb.checkpoint'])
        self.assertEqual(w.calls[-1][2], mirror.checkpoint_record(self.did, self.front.rev, self.front.commit, self.front.height))

    def test_bad_head_bad_height_redirect_and_oversized_front_cannot_publish_checkpoint(self):
        head = {'cid': 'bafyreia', 'rev': '3aaaaaaaaaaa2'}
        for responses, reason in [
            ([(200, b'[]', {})], 'response_not_json_object'),
            ([(200, b'not json', {})], 'response_not_json_object'),
            ([(200, b'{"cid":"bafyreia"}', {})], 'checkpoint_invalid'),
            ([(302, b'', {})], 'redirect_refused'),
            ([(200, b' ' * (MAX_RESPONSE + 1), {})], 'response_too_large'),
            ([(200, json.dumps(head).encode(), {}), (200, b'{"value":{"height":true}}', {})], 'checkpoint_invalid'),
            ([(200, json.dumps(head).encode(), {}), (200, b'{"value":{"height":0}}', {})], 'checkpoint_invalid'),
            ([(200, json.dumps(head).encode(), {}), (400, b'{"error":"RecordNotFound"}', {})], 'RecordNotFound'),
        ]:
            with self.subTest(reason=reason, calls=len(responses)):
                replies = iter(responses)
                self.front = lambda *args: next(replies)
                w = Writer()
                result = self.step(w)
                self.assertIn(reason, result['checkpoint'])
                self.assertEqual([c for c, _, _ in w.calls], [mirror.INDEX])
                self.st.mirror.unlink()

    def test_checkpoint_is_absent_from_the_canonical_facades_collections_and_record_reads(self):
        repo = Repo(self.st.config.origin, world=self.st.world)
        code, described, _ = repo.serve(self.host, 'GET', 'com.atproto.repo.describeRepo', {'repo': self.did}, None)
        self.assertEqual(code, 200)
        self.assertNotIn('online.fg-goose.gsb.checkpoint', described['collections'])
        for method in ('com.atproto.repo.getRecord', 'com.atproto.repo.listRecords'):
            code, value, _ = repo.serve(self.host, 'GET', method,
                                       {'repo': self.did, 'collection': 'online.fg-goose.gsb.checkpoint', 'rkey': 'self'}, None)
            self.assertEqual((code, value['error']), (400, 'InvalidRequest'))
        self.assertEqual(self.host.events, [])

    def test_checkpoint_keeps_the_full_repository_height_without_a_wall_clock_timestamp(self):
        self.front.height = self.host.height = (1 << 63) - 1
        w = Writer()
        self.step(w)
        self.assertEqual(w.calls[-1][2]['height'], (1 << 63) - 1)
        self.assertNotIn('createdAt', w.calls[-1][2])

    def test_a_partial_manifest_or_failed_index_never_advances_checkpoint(self):
        answer = {'$type': mirror.ANSWER, 'source': {'$type': mirror.ANSWER + '#request', 'request': {'uri': 'at://did:plc:x/online.fg-goose.gsb.request/3a', 'cid': 'bafy'}},
                  'outcome': {'status': 'admitted', 'line': 'admitted'}, 'height': 7}
        self.st.write(self.st.answers / 'request.json', answer)
        w = Writer()
        result = self.step(w, limit=0)
        self.assertEqual(w.calls, [])
        self.assertEqual(result['left'], 3)
        result = self.step(w, limit=1)
        self.assertEqual([c for c, _, _ in w.calls], [mirror.ANSWER, mirror.INDEX, 'online.fg-goose.gsb.checkpoint'])
        self.assertEqual(result['left'], 0)
        self.st.mirror.unlink()

        def failed_index(collection, rkey, value):
            if collection == mirror.INDEX:
                raise Failure('write_failed')
            w(collection, rkey, value)
        w = Writer()
        with self.assertRaises(Failure):
            self.step(failed_index)
        self.assertNotIn('online.fg-goose.gsb.checkpoint', [c for c, _, _ in w.calls])
        self.assertNotIn(self.key, json.loads(self.st.mirror.read_text()))


class Mirror(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.host = cls.town.client

    def state(self):
        tmp = tempfile.mkdtemp(dir=self.tmp.name)
        return State(Path(tmp) / 'state')

    def test_every_card_the_public_reads_is_a_record_of_its_exact_text_and_every_page_is_one(self):
        held = mirror.records(self.host, NOWAIT)
        for key, value in held.items():
            self.assertEqual(record_problems(value), [], (key, value))
        ids = mirror.ids(self.host)
        self.assertIn('commonplace', ids)
        for oid in ('commonplace', 'library', 'bell/1', 'porch', 'kinds'):
            rec = held[mirror.CARD, mirror.card_key(oid)]
            card = self.host.send({'op': 'world-card', 'principal': 'anonymous', 'object': oid})
            self.assertEqual(rec['card'], card['text'], oid)
            self.assertEqual(rec['version'], self.host.send({'op': 'world-view', 'principal': 'anonymous', 'object': oid})['version'])
        bell = held[mirror.CARD, 'bell~1']
        self.assertTrue(all({'name', 'asks'} <= set(w) for w in bell['wants']), bell['wants'])
        names = [k for c, k in held if c == mirror.PAGE]
        for page in ('spells', 'laws', 'world', 'bell', 'enter', 'tide', 'kind', 'check'):
            self.assertIn(page, names)
            body = held[mirror.PAGE, page]['body']
            self.assertTrue(body.startswith('hob:'), body[:40])
        index = held[mirror.INDEX, 'self']
        self.assertEqual(index['pages'], names)
        self.assertEqual(sorted(index['cards']), sorted(oid for c, oid in ((c, k.replace('~', '/')) for c, k in held) if c == mirror.CARD))
        self.assertTrue(index['coherent'])
        self.assertEqual({oid: held[mirror.CARD, mirror.card_key(oid)]['version'] for oid in index['cards']}, index['cards'])
        self.assertTrue(all(len(json.dumps(v)) < 64 * 1024 for v in held.values()))  # every record far under a PDS record's bound

    def test_a_dry_run_writes_nothing_then_a_run_writes_all_and_a_second_run_only_what_changed(self):
        st = self.state()
        dry = mirror.run(st, self.host, fetch=Front(error='RepoNotServed'))
        self.assertTrue(dry['dry_run'])
        self.assertFalse(st.mirror.exists())
        w = Writer()
        first = mirror.run(st, self.host, w, fetch=Front(error='RepoNotServed'))
        self.assertEqual(first['left'], 0)
        self.assertGreater(len(w.calls), 20)
        self.assertFalse(any(c == post.COLLECTION for c, _, _ in w.calls))  # never a feed post
        again = Writer()
        self.assertEqual(mirror.run(st, self.host, again, fetch=Front(error='RepoNotServed'))['written'], [])
        reply = self.host.send({'op': 'world-turn', 'principal': 'did:plc:mirrorer', 'object': 'library', 'method': 'receive',
                                'identity': 'mirror-read', 'argument': record(text=label('delvetalk library read / page: spells'), post=label(''))})
        self.assertEqual(reply['status'], 'admitted', reply)
        self.assertEqual(mirror.run(st, self.host, again, fetch=Front(error='RepoNotServed'))['written'], [])  # a read changes no card

    def test_the_manifest_is_written_last_and_only_when_everything_it_lists_landed(self):
        st = self.state()
        w = Writer()
        cut = mirror.run(st, self.host, w, limit=5, fetch=Front(error='RepoNotServed'))
        self.assertGreater(cut['left'], 0)
        self.assertNotIn(mirror.INDEX, [c for c, _, _ in w.calls])  # a cut run leaves the last complete manifest
        while mirror.run(st, self.host, w, limit=50, fetch=Front(error='RepoNotServed'))['left']:
            pass
        self.assertEqual(w.calls[-1][0], mirror.INDEX)

    def test_a_record_the_world_no_longer_shows_is_deleted(self):
        st = self.state()
        st.write(st.mirror, {f'{mirror.CARD} gone~thing': 'x'})
        w = Writer()
        mirror.run(st, self.host, w, fetch=Front(error='RepoNotServed'))
        self.assertIn((mirror.CARD, 'gone~thing', None), w.calls)
        self.assertNotIn(f'{mirror.CARD} gone~thing', json.loads(st.mirror.read_text()))

    def test_the_facade_answers_the_mirrors_own_records(self):
        repo = Repo('https://gsb.example')
        code, got, _ = repo.serve(self.host, 'GET', 'com.atproto.repo.getRecord',
                                  {'repo': repo.did, 'collection': mirror.CARD, 'rkey': 'bell~1'}, 'anonymous')
        self.assertEqual(code, 200, got)
        self.assertEqual(got['value'], mirror.card_record(self.host, 'bell/1', sleep=NOWAIT))
        code, listed, _ = repo.serve(self.host, 'GET', 'com.atproto.repo.listRecords',
                                     {'repo': repo.did, 'collection': mirror.PAGE, 'limit': '3'}, 'anonymous')
        self.assertEqual(code, 200, listed)
        self.assertEqual([r['value']['name'] for r in listed['records']], [p['name'] for p in mirror.library_pages(self.host)][:3])
        code, more, _ = repo.serve(self.host, 'GET', 'com.atproto.repo.listRecords',
                                   {'repo': repo.did, 'collection': mirror.PAGE, 'limit': '3', 'cursor': listed['cursor']}, 'anonymous')
        self.assertEqual([r['value']['name'] for r in more['records']], [p['name'] for p in mirror.library_pages(self.host)][3:6])
        self.assertIn(mirror.CARD, repo.serve(self.host, 'GET', 'com.atproto.repo.describeRepo', {'repo': repo.did}, 'anonymous')[1]['collections'])


class RecordWriter(unittest.TestCase):
    """The writer puts a record in the session's own repo and deletes one there; a feed post is never written."""

    def test_put_and_delete_in_the_sessions_own_repo(self):
        sent = []

        class Client:
            def write(self, nsid, body, token=None):
                sent.append((nsid, body, token))
                return {'did': 'did:plc:bot', 'accessJwt': 'jwt'} if nsid.endswith('createSession') else {'uri': 'at://x', 'cid': 'c'}

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cred = Path(tmp.name) / 'cred.json'
        cred.write_text(json.dumps({'identifier': 'bot', 'password': 'pw'}))
        st = State(Path(tmp.name) / 'state', config=Config(credentials=str(cred)))
        write = post.record_writer(st, Client())
        write(mirror.CARD, 'bell~1', {'$type': mirror.CARD, 'card': 'x'})
        write(mirror.CARD, 'bell~1', None)
        self.assertEqual([n for n, _, _ in sent], ['com.atproto.server.createSession', 'com.atproto.repo.putRecord', 'com.atproto.repo.deleteRecord'])
        self.assertEqual(sent[1][1], {'repo': 'did:plc:bot', 'collection': mirror.CARD, 'rkey': 'bell~1', 'record': {'$type': mirror.CARD, 'card': 'x'}, 'validate': False})
        with self.assertRaises(Failure):
            write(post.COLLECTION, 'x', {'text': 'hi'})


if __name__ == '__main__':
    unittest.main()
