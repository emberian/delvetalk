"""Public GET archive retention and recoverable bounded backfill."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('town_archive_test', ROOT / 'scripts/town_archive.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def post(cid='first'):
    return {'uri': 'at://did:plc:example/town.delve.feed.post/key', 'cid': cid,
            'record': {'text': 'a public record'}, 'author': {'did': 'did:plc:example'}}


class PublicFeed:
    def __init__(self):
        self.pages = [{'feed': [{'post': post()}], 'cursor': 'next'},
                      {'feed': [{'post': post()}]}]
        self.calls = []
        self.failure = False

    def __call__(self, method, base, nsid, *, params):
        self.calls.append((method, base, nsid, dict(params)))
        if self.failure and params.get('cursor') == 'next':
            raise archive.delve.Failure('secret token and headers must not be retained')
        return copy.deepcopy(self.pages[1 if params.get('cursor') == 'next' else 0])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.api = PublicFeed()

    def test_overlap_deduplicates_raw_capture_and_changed_cid_retained(self):
        def read():
            run = archive.Archive(self.state, self.api)
            run('GET', archive.delve.APPVIEW, 'town.delve.feed.getFeed', params={'feed': archive.FEED, 'limit': 50})
            return json.loads(Path(run.finish()).read_text())
        first, again = read(), read()
        self.assertEqual(first['requests'][0]['capture'], again['requests'][0]['capture'])
        self.assertEqual(len(list((self.state / 'captures').glob('*.json'))), 1)
        self.api.pages[0]['feed'][0]['post']['cid'] = 'second'
        changed = read()
        self.assertNotEqual(first['requests'][0]['records'], changed['requests'][0]['records'])
        self.assertEqual(len(list((self.state / 'captures').glob('*.json'))), 2)

    def test_partial_failure_restart_uses_durable_cursor_and_sanitizes_error(self):
        self.api.failure = True
        partial = archive.backfill(self.state, pages=2, request=self.api)
        self.assertTrue(partial['errors'])
        self.assertEqual(partial['coverage']['pages'], 1)
        self.assertEqual(json.loads((self.state / 'backfill.json').read_text())['cursor'], 'next')
        self.api.failure = False
        self.api.calls.clear()
        resumed = archive.backfill(self.state, pages=2, request=self.api)
        self.assertEqual(self.api.calls[0][3]['cursor'], 'next')
        self.assertTrue(resumed['complete'])
        self.assertFalse(resumed['errors'])
        for f in self.state.rglob('*.json'):
            self.assertNotIn('secret token', f.read_text())
        self.api.calls.clear()
        self.assertTrue(archive.backfill(self.state, request=self.api)['complete'])
        self.assertEqual(self.api.calls, [])

    def test_crash_after_capture_before_cursor_save_repeats_without_loss(self):
        run = archive.Archive(self.state, self.api)
        run('GET', archive.delve.APPVIEW, 'town.delve.feed.getFeed', params={'feed': archive.FEED, 'limit': 50})
        # No cursor save/finish models process interruption; repeat is harmless.
        result = archive.backfill(self.state, pages=1, request=self.api)
        self.assertFalse(result['complete'])
        self.assertEqual(len(list((self.state / 'captures').glob('*.json'))), 1)
        pending = json.loads(run.path.read_text())
        self.assertEqual(pending['status'], 'running')
        self.assertEqual(pending['requests'][0]['status'], 'captured')

    def test_interruption_leaves_pending_request_and_retry_starts_at_head(self):
        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt()
        run = archive.Archive(self.state, interrupted)
        with self.assertRaises(KeyboardInterrupt):
            run('GET', archive.delve.APPVIEW, 'town.delve.feed.getFeed', params={'feed': archive.FEED})
        pending = json.loads(run.path.read_text())
        self.assertEqual(pending['requests'][0]['status'], 'pending')
        self.assertFalse((self.state / 'backfill.json').exists())
        result = archive.backfill(self.state, pages=1, request=self.api)
        self.assertFalse(result['complete'])
        self.assertNotIn('cursor', self.api.calls[0][3])

    def test_whitelist_bounds_and_full_thread_capture(self):
        run = archive.Archive(self.state, self.api, max_requests=1)
        for method, base, nsid, params in [
            ('POST', archive.delve.APPVIEW, 'town.delve.feed.getFeed', {}),
            ('GET', archive.delve.PDS, 'com.atproto.repo.getRecord', {}),
            ('GET', archive.delve.APPVIEW, 'town.delve.feed.getFeed', {'token': 'secret'}),
        ]:
            with self.assertRaises(ValueError):
                run(method, base, nsid, params=params)
        self.assertEqual(self.api.calls, [])
        tree = {'thread': {'post': post(), 'replies': [{'post': post('child'), 'replies': []}]}}
        run.request = lambda *args, **kwargs: tree
        run('GET', archive.delve.APPVIEW, 'town.delve.feed.getPostThread', params={'uri': post()['uri'], 'depth': 3, 'parentHeight': 0})
        raw = json.loads(next((self.state / 'captures').glob('*.json')).read_text())
        self.assertEqual(raw['response'], tree)
        with self.assertRaises(archive.delve.Failure):
            run('GET', archive.delve.APPVIEW, 'town.delve.feed.getFeed')
        small = archive.Archive(self.state, self.api, max_bytes=1)
        with self.assertRaises(archive.delve.Failure):
            small('GET', archive.delve.APPVIEW, 'town.delve.feed.getFeed')
        self.assertEqual(small.manifest['requests'][0]['status'], 'unretained')
        self.assertEqual(json.loads(Path(small.finish()).read_text())['status'], 'partial')
        for bounds in [{'max_requests': 0}, {'max_bytes': -1}, {'max_requests': True}]:
            with self.assertRaises(ValueError):
                archive.Archive(self.state, self.api, **bounds)

    def test_invalid_or_looping_page_does_not_advance_cursor(self):
        self.api.pages[1]['cursor'] = 'next'
        result = archive.backfill(self.state, pages=2, request=self.api)
        self.assertTrue(result['errors'])
        self.assertEqual(json.loads((self.state / 'backfill.json').read_text())['pages'], 1)
        self.assertEqual(len(list((self.state / 'captures').glob('*.json'))), 2)


if __name__ == '__main__':
    unittest.main()
