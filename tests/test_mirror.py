"""The town mirrored as records on the PDS (docs/POSTING.md §1): a resident whose window is the PDS reads every card,
page and the index there with no post. Each record is the rendering the web's pages use (`transport.host.place`),
written only when it changed, and the did:web façade answers the same collections from the same functions.

Evidence for docs/POSTING.md §1 (layer: transport).

Refuted by: a card record whose text is not `world-card`'s for the public reader, a page missing from the mirror, a
second run writing what did not change, a write that is a feed post, or the façade answering another rendering.
"""
import json
import tempfile
import unittest
from pathlib import Path

from tests.town import Town
from tests.test_lexicons import record_problems
from tests.wire import label, record
from transport import mirror, post
from transport.delve import Failure
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
        dry = mirror.run(st, self.host)
        self.assertTrue(dry['dry_run'])
        self.assertFalse(st.mirror.exists())
        w = Writer()
        first = mirror.run(st, self.host, w)
        self.assertEqual(first['left'], 0)
        self.assertGreater(len(w.calls), 20)
        self.assertFalse(any(c == post.COLLECTION for c, _, _ in w.calls))  # never a feed post
        again = Writer()
        self.assertEqual(mirror.run(st, self.host, again)['written'], [])
        reply = self.host.send({'op': 'world-turn', 'principal': 'did:plc:mirrorer', 'object': 'library', 'method': 'receive',
                                'identity': 'mirror-read', 'argument': record(text=label('delvetalk library read / page: spells'), post=label(''))})
        self.assertEqual(reply['status'], 'admitted', reply)
        self.assertEqual(mirror.run(st, self.host, again)['written'], [])  # a read changes no card

    def test_the_manifest_is_written_last_and_only_when_everything_it_lists_landed(self):
        st = self.state()
        w = Writer()
        cut = mirror.run(st, self.host, w, limit=5)
        self.assertGreater(cut['left'], 0)
        self.assertNotIn(mirror.INDEX, [c for c, _, _ in w.calls])  # a cut run leaves the last complete manifest
        while mirror.run(st, self.host, w, limit=50)['left']:
            pass
        self.assertEqual(w.calls[-1][0], mirror.INDEX)

    def test_a_record_the_world_no_longer_shows_is_deleted(self):
        st = self.state()
        st.write(st.mirror, {f'{mirror.CARD} gone~thing': 'x'})
        w = Writer()
        mirror.run(st, self.host, w)
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
