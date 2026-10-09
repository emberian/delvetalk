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
        self.tag_search = [{'posts': []}]
        self.thread = {'thread': {'post': post('anchor', 'discussion context'), 'replies': []}}
        self.calls = []
        self.failure = None

    def __call__(self, method, base, nsid, *, params):
        assert method == 'GET' and base == watch.delve.APPVIEW
        self.calls.append((nsid, params))
        if nsid.endswith('getPostThread'):
            return copy.deepcopy(self.thread)
        source = ('feed' if nsid.endswith('getFeed') else
                  'tag_search' if params['q'] == '#gsb' else 'search')
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

    def test_session_markers_discover_candidates_without_requiring_both_for_observation(self):
        paired = post('summon', '@LiveDelveTalk.Delve.Town #GSB Please make a fresh garden.')
        tag_only = post('tag-only', '#gsb Could we try a moon room?')
        label_only = post('label-only', '@livedelvetalk.delve.town a question about making things')
        self.api.feed = [{'feed': [{'post': label_only}, {'post': post('unrelated', '#gsboard news')}]}]
        related = post('related', 'GSB: can we make another room?')
        self.api.tag_search = [{'posts': [paired, tag_only, related]}]
        result = self.scan(search_pages=2)
        items = {item['uri'].rsplit('/', 1)[-1]: item for item in result['new']}
        self.assertTrue(items['summon']['summonCandidate'])
        self.assertFalse(items['tag-only']['summonCandidate'])
        self.assertFalse(items['label-only']['summonCandidate'])
        self.assertTrue(items['tag-only']['matchedTag'])
        self.assertIn('related', items, 'search context is retained without requiring literal markers')
        self.assertFalse(items['related']['matchedTag'])
        self.assertFalse(items['related']['summonCandidate'])
        self.assertEqual(result['newSelectionCounts'], {'marked': 3, 'searchContext': 1, 'replyContext': 1})
        self.assertEqual([item['uri'] for item in result['summonCandidates']], [paired['uri']])
        self.assertNotIn('unrelated', items)
        self.assertEqual(items['summon']['sources'], ['tagSearch'])
        self.assertEqual({params['q'] for nsid, params in self.api.calls if nsid.endswith('searchPosts')},
                         {'livedelvetalk', '#gsb'})
        saved = json.loads(Path(items['summon']['observation']).read_text())
        self.assertEqual(saved['record'], paired['record'])
        self.assertNotIn('request', saved)
        self.assertNotIn('principal', saved)
        self.assertEqual(self.scan()['new'], [])
        paired['record']['text'] = 'Actually, wait for my clarification.'
        changed = self.scan()['changed']
        self.assertEqual(len(changed), 1)
        self.assertFalse(changed[0]['summonCandidate'])

    def test_available_parent_and_untagged_reply_survive_page_order(self):
        invitation = post('invitation', 'Welcome: choose a fresh place to make.')
        summon = post('summon', '@livedelvetalk.delve.town #gsb a room with bells')
        response = post('response', 'Could its ceiling be blue?')
        summon['record']['reply'] = {'root': {'uri': invitation['uri'], 'cid': invitation['cid']},
                                      'parent': {'uri': invitation['uri'], 'cid': invitation['cid']}}
        response['record']['reply'] = {'root': {'uri': invitation['uri'], 'cid': invitation['cid']},
                                        'parent': {'uri': summon['uri'], 'cid': summon['cid']}}
        self.api.feed = [{'feed': [{'post': response}, {'post': invitation}, {'post': summon}]}]
        result = self.scan()
        items = {item['uri']: item for item in result['new']}
        self.assertIn(invitation['uri'], items)
        self.assertIn(response['uri'], items)
        self.assertFalse(items[response['uri']]['summonCandidate'])
        self.assertEqual(json.loads(Path(items[response['uri']]['observation']).read_text())['record'],
                         response['record'])


if __name__ == '__main__':
    unittest.main()
