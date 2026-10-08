"""Read-only watch behavior under deterministic AppView mocks."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('watch_test', ROOT / 'scripts/watch.py')
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
AUTHOR = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'


def post(key, text, cid=None):
    return {'uri': f'at://{AUTHOR}/town.delve.feed.post/{key}', 'cid': cid or 'cid-' + key,
            'record': {'$type': 'town.delve.feed.post', 'text': text}, 'author': {'did': AUTHOR}}


class AppView:
    def __init__(self):
        self.feed = [{'feed': []}]
        self.search = [{'posts': []}]
        self.thread = {'thread': {'post': post('anchor', 'discussion context'), 'replies': []}}
        self.calls = []
        self.failure = None

    def __call__(self, method, base, nsid, *, params):
        assert method == 'GET' and base == watch.delve.APPVIEW
        self.calls.append((nsid, params))
        if nsid.endswith('getPostThread'):
            return copy.deepcopy(self.thread)
        source = 'feed' if nsid.endswith('getFeed') else 'search'
        index = int(params.get('cursor', '0'))
        if self.failure == (source, index):
            raise watch.delve.Failure('temporary failure')
        return copy.deepcopy(getattr(self, source)[index])


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.api = AppView()

    def scan(self, **kwargs):
        return watch.scan(self.state, request=self.api, **kwargs)

    def test_empty_search_feed_hit_and_context_repeated_scan(self):
        item = post('match', 'hello @LiveDelveTalk.Delve.Town')
        self.api.feed = [{'feed': [{'post': item}, {'post': post('irrelevant', 'unrelated')}]}]
        first = self.scan()
        self.assertEqual(len(first['new']), 2)
        self.assertEqual(first['coverage']['search']['posts'], 0)
        matched = next(value for value in first['new'] if value['matchedLabel'])
        self.assertEqual(json.loads(Path(matched['observation']).read_text())['record'], item['record'])
        again = self.scan()
        self.assertEqual(again['new'], [])
        self.assertEqual(again['changed'], [])
        self.assertEqual(again['retainedPosts'], 2)
        self.api.feed = [{'feed': []}]
        absent = self.scan()
        self.assertEqual(absent['retainedPosts'], 2)
        self.assertEqual(absent['changed'], [])

    def test_changed_cid_and_same_cid_changed_content_retained(self):
        item = post('match', watch.LABEL)
        self.api.feed = [{'feed': [{'post': item}]}]
        self.scan()
        item['cid'] = 'changed-cid'
        item['record']['text'] += ' updated'
        changed = self.scan()
        self.assertEqual(len(changed['changed']), 1)
        self.assertEqual(changed['changed'][0]['previousCid'], 'cid-match')
        item['record']['text'] += ' changed with same claimed CID'
        changed_again = self.scan()
        self.assertEqual(len(changed_again['changed']), 1)
        self.assertEqual(changed_again['changed'][0]['previousCid'], 'changed-cid')
        self.assertEqual(len(list((self.state / 'observations').glob('*.json'))), 4)
        item['record']['text'] = 'label removed from a previously observed post'
        removed_label = self.scan()
        self.assertEqual(len(removed_label['changed']), 1)
        self.assertFalse(removed_label['changed'][0]['matchedLabel'])

    def test_page_bound_and_partial_failure_preserve_observations(self):
        self.api.feed = [{'feed': [{'post': post('first', watch.LABEL)}], 'cursor': '1'},
                         {'feed': [{'post': post('second', watch.LABEL)}]}]
        first = self.scan(feed_pages=1)
        self.assertTrue(first['coverage']['feed']['truncated'])
        self.assertEqual(first['coverage']['feed']['cursor'], '1')
        self.api.failure = ('feed', 1)
        partial = self.scan(feed_pages=2)
        self.assertEqual(partial['coverage']['feed']['pages'], 1)
        self.assertEqual(len(partial['errors']), 1)
        self.assertEqual(partial['retainedPosts'], 2)
        self.api.failure = None
        complete = self.scan(feed_pages=20, search_pages=2)
        self.assertEqual(len(complete['new']), 1)
        self.assertFalse(complete['coverage']['feed']['truncated'])

    def test_simultaneous_conflicting_observations_do_not_oscillate(self):
        one = post('match', watch.LABEL)
        other = post('match', watch.LABEL + ' divergent', 'cid-other')
        self.api.feed = [{'feed': [{'post': one}]}]
        self.api.search = [{'posts': [other]}]
        first = self.scan()
        self.assertEqual(len(first['conflicts']), 1)
        self.assertEqual(len(first['conflicts'][0]['variants']), 2)
        again = self.scan()
        self.assertEqual(again['new'], [])
        self.assertEqual(again['changed'], [])
        self.assertEqual(len(again['conflicts']), 1)

    def test_thread_depth_coverage_and_cursor_loop_are_explicit(self):
        self.api.thread['thread']['post']['replyCount'] = 3
        self.api.feed = [{'feed': [], 'cursor': '1'}, {'feed': [], 'cursor': '1'}]
        result = self.scan()
        self.assertTrue(result['coverage']['thread']['truncated'])
        self.assertEqual(result['coverage']['thread']['deeperReplies'], 3)
        self.assertIn('repeated', result['coverage']['feed']['error'])
        self.assertEqual(len(result['new']), 1)


if __name__ == '__main__':
    unittest.main()
