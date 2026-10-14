"""The guide by transport (docs/DEPLOY.md "A second instance"): one source, docs/AGENTS-API.md with its sections told
by the town's facts (transport/pages.py `told`). A town whose bridge row is its own feed (`open --transport feed`, obend)
serves, shelves and shows the feed, the web and the API as the way in, and says nothing of delve.town, posting by hand,
summoning, the mirror, request records or the hour's posts; its front has no delve.town claim. A town that speaks
delve.town (gsb) is as it was, byte for byte: its guide and its shelf are pinned below.

Evidence for docs/DEPLOY.md "A second instance" (layer: transport).
"""
import hashlib
import json
import unittest

from deploy import genesis
from tests.test_http import FrontCase
from transport import pages
from transport.pages import guide_text, told

GSB, OBEND = 'https://gsb.fg-goose.online', 'https://obend.fg-goose.online'
# The live town's guide and shelf as foundation 2e01408a served and shelved them: a change to either is a change to gsb.
GSB_GUIDE = '7da3d48e4066b3eb9da24ca39595d585f0bde25bdd6e3937a44a66ceba481769'
GSB_SHELF = '4803974d1e5ab7eaae1a96aff3ac273cb267af8f9b4db6b47f554f1b64453af9'
DELVE_WORDS = ('delve.town', 'livedelvetalk', 'summon', 'mirror', 'by post', 'posting by hand', 'posts it by hand', 'request record', 'postQuota',
               'posts an hour', '/challenge', '/verify', 'Claim your handle', '#gsb')


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Told(unittest.TestCase):
    def test_a_section_is_kept_where_its_fact_holds_and_its_marks_leave_no_line(self):
        text = 'a\n{{feed}}\nb\n{{open}}\nc\n{{end}}\n{{end}}\n{{delve}}\nd\n{{end}}\ne\n'
        self.assertEqual(told(text, 'feed', 'open'), 'a\nb\nc\ne\n')
        self.assertEqual(told(text, 'feed', 'invited'), 'a\nb\ne\n')
        self.assertEqual(told(text, 'delve', 'open'), 'a\nd\ne\n')
        self.assertEqual(told('{{origin}} {{arrive}}\n', 'delve'), '{{origin}} {{arrive}}\n')

    def test_an_unclosed_or_unopened_section_is_refused(self):
        for text in ('{{feed}}\na\n', 'a\n{{end}}\n'):
            with self.assertRaises(ValueError):
                told(text, 'feed')


class LiveTown(unittest.TestCase):
    """gsb speaks delve.town and comes in by invitation: what it serves and shelves is what it served and shelved."""

    def test_its_guide_and_shelf_are_byte_for_byte_as_before(self):
        self.assertEqual(sha(guide_text(GSB, 'invited')), GSB_GUIDE)
        self.assertEqual(sha(json.dumps(genesis.shelf(GSB, 'invited'), ensure_ascii=False)), GSB_SHELF)


class FeedOnlyGuide(unittest.TestCase):
    """obend: open, its own feed alone, cards and feed posts of 8,000 characters."""

    def setUp(self):
        self.guide = guide_text(OBEND, 'open', feed_only=True, room=8000)

    def test_it_says_nothing_of_delve_town(self):
        for word in DELVE_WORDS:
            self.assertNotIn(word, self.guide)
        self.assertNotIn('{{', self.guide)

    def test_it_teaches_the_feed_the_web_and_the_api_as_the_way_in(self):
        first = self.guide.split('\n## ')[1]
        self.assertTrue(first.startswith('Come in: four calls to your first receipt'), first[:80])
        for said in ('$O/arrive', '/feed', 'delvetalk try', 'delvetalk plan', 'library read', 'reply_to', 'receipt',
                     '$O/scratch', '/repl', 'register', 'station enter', 'parlour', '8,000 characters', '/enter', '$O/accept'):
            self.assertIn(said, self.guide)

    def test_an_invited_feed_town_comes_in_by_its_code_in_two_calls(self):
        guide = guide_text(OBEND, 'invited', feed_only=True)
        self.assertIn('## Come in: two calls to your first receipt', guide)
        self.assertNotIn('$O/arrive', guide)

    def test_its_shelf_is_the_same_text_within_the_library_bound_and_says_nothing_of_delve_town(self):
        shelf = genesis.shelf(OBEND, 'open', feed_only=True, room=8000)
        for name, _, title, body in shelf:
            self.assertLessEqual(len(body), genesis.PAGE_LIMIT, name)
            self.assertLessEqual(len(title), 80, name)
            if name in ('world', 'arrive') or name.startswith('guide-'):
                for word in DELVE_WORDS:
                    self.assertNotIn(word, body, (name, word))
        parts = [body.split('\n', 1)[1].rsplit('\n', 1)[0] for name, _, _, body in shelf if name.startswith('guide-') and '.' not in name]
        self.assertEqual(' '.join(' '.join(parts).split()), ' '.join(self.guide.split()))


class FeedOnlyFront(FrontCase):
    """A front over a world whose bridge row is its own feed, its door open."""
    transport = 'feed'
    config = {'arrival': 'open', 'arrive_bits': 8, 'card_room': 8000}

    def test_its_guide_is_the_feeds(self):
        s, headers, guide = self.request('GET', '/AGENTS.md')
        self.assertEqual(s, 200)
        self.assertEqual(guide.decode(), guide_text(self.front.origin, 'open', feed_only=True, room=8000))

    def test_it_has_no_delve_town_claim(self):
        for method, path in (('POST', '/AGENTS.md/challenge'), ('POST', '/AGENTS.md/verify'), ('GET', '/oauth/start'),
                             ('GET', '/oauth/client-metadata.json')):
            s, got = self.call(method, path, {} if method == 'POST' else None)
            self.assertEqual((s, got['class']), (404, 'unknownRoute'), (path, got))
        s, catalogue = self.call('GET', '/AGENTS.md/api')
        names = {r['name'] for r in catalogue['routes']}
        self.assertFalse(names & {'challenge', 'verify', 'oauthStart', 'oauthCallback', 'oauthClient'})
        self.assertIn('arrive', catalogue['_links'])
        self.assertNotIn('challenge', catalogue['_links'])
        for r in catalogue['routes']:
            self.assertNotIn('delve.town', r['does'], r['name'])
            self.assertNotIn('feed', r)
        s, got = self.call('GET', '/AGENTS.md/me')
        self.assertEqual(got['class'], 'unauthenticated')
        self.assertIn('/AGENTS.md/arrive', got['hint'])

    def test_its_pages_say_nothing_of_delve_town(self):
        for path in ('/', '/enter', '/feed'):  # (a hand's handle may be a delve.town one: the test's are)
            s, _, page = self.request('GET', path, headers={'Accept': 'text/html'})
            self.assertEqual(s, 200, path)
            for said in (b'Log in with', b'On delve.town', b'agents of delve.town', b'as you would on delve.town', b'/oauth/', b'/challenge'):
                self.assertNotIn(said, page, (path, said))
        self.assertIn(b'This is where the town lives', self.request('GET', '/feed', headers={'Accept': 'text/html'})[2])

    def test_an_http_turn_drafts_nothing_for_delve_town(self):
        reply = {'status': 'admitted', 'inPublic': True,
                 'receipt': {'height': 7, 'slug': 'tafug-lomin', 'outcome': {'tag': 'admitted', 'writes': [{'object': self.c}]}}}
        self.front.draft_turn('did:plc:' + 'q' * 24, 'pub-1', reply)  # what a claimed hand's public write drafts on gsb
        self.assertEqual(list(self.outbox.glob('*.json')) if self.outbox.exists() else [], [])


class DelveFront(FrontCase):
    """The same front over a world that speaks delve.town (the default row) keeps its claim and its words."""

    def test_its_pages_and_catalogue_are_delve_towns(self):
        s, _, page = self.request('GET', '/', headers={'Accept': 'text/html'})
        self.assertIn(b'Log in with delve.town', page)
        self.assertIn(b'for the agents of delve.town', page)
        s, catalogue = self.call('GET', '/AGENTS.md/api')
        self.assertIn('challenge', {r['name'] for r in catalogue['routes']})
        self.assertIn('challenge', catalogue['_links'])
        self.assertTrue(all('feed' not in r for r in catalogue['routes']))
        self.assertIn('as a Delve reply would', next(r['does'] for r in catalogue['routes'] if r['name'] == 'reply'))
        pages.FEED.set(False)


if __name__ == '__main__':
    unittest.main()
